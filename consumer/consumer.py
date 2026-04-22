"""
consumer.py — Consumer Spark Structured Streaming para pipeline IoT.

Consome mensagens do Kafka, aplica janela temporal de 1 minuto com
watermark de 10 segundos, agrega por estufa e persiste no PostgreSQL.
Também grava leituras brutas na tabela sensor_readings_raw para auditoria.

Variáveis de ambiente:
    KAFKA_BROKER: endereço do broker (padrão: kafka:9092)
    KAFKA_TOPIC: tópico a consumir (padrão: iot_sensors)
    POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT
"""
import os

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    avg,
    col,
    current_timestamp,
    from_json,
    to_timestamp,
    window,
)
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

# ── Configuração via variáveis de ambiente ──────────────────────────────────
KAFKA_BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
KAFKA_TOPIC = os.getenv("KAFKA_TOPIC", "iot_sensors")
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "iot_data")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")

DB_URL = f"jdbc:postgresql://{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
DB_PROPS = {
    "user": POSTGRES_USER,
    "password": POSTGRES_PASSWORD,
    "driver": "org.postgresql.Driver",
}

# ── Schema das mensagens JSON do Kafka ──────────────────────────────────────
SENSOR_SCHEMA = StructType([
    StructField("sensor_id", StringType(), True),
    StructField("estufa_id", StringType(), True),
    StructField("bed_id", IntegerType(), True),
    StructField("clone_id", StringType(), True),
    StructField("soil_temp_c", DoubleType(), True),
    StructField("humidity", DoubleType(), True),
    StructField("timestamp", StringType(), True),
])

# ── Parâmetros de streaming ─────────────────────────────────────────────────
WINDOW_DURATION = "1 minute"
WATERMARK_DELAY = "10 seconds"
TRIGGER_INTERVAL = "10 seconds"
CHECKPOINT_LOCATION = "/tmp/spark-checkpoint"


def criar_spark_session() -> SparkSession:
    """Cria e configura a SparkSession com pacotes Kafka e PostgreSQL."""
    return (
        SparkSession.builder
        .appName("IoTConsumer-Eucalipto")
        .config(
            "spark.jars.packages",
            "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,"
            "org.postgresql:postgresql:42.6.0",
        )
        .config("spark.sql.streaming.checkpointLocation", CHECKPOINT_LOCATION)
        .getOrCreate()
    )


def ler_kafka(spark: SparkSession) -> DataFrame:
    """Lê o stream do Kafka e retorna DataFrame com campo 'value' como string."""
    return (
        spark.readStream
        .format("kafka")
        .option("kafka.bootstrap.servers", KAFKA_BROKER)
        .option("subscribe", KAFKA_TOPIC)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )


def parsear_json(kafka_df: DataFrame) -> DataFrame:
    """Parseia o campo value do Kafka como JSON e retorna campos tipados."""
    return (
        kafka_df
        .selectExpr("CAST(value AS STRING) AS json_data")
        .select(from_json(col("json_data"), SENSOR_SCHEMA).alias("data"))
        .select("data.*")
        .withColumn("event_time", to_timestamp(col("timestamp")))
        .filter(col("event_time").isNotNull())
        .filter(col("estufa_id").isNotNull())
        .filter(col("soil_temp_c").isNotNull())
        .filter(col("humidity").isNotNull())
    )


def agregar_por_janela(sensor_df: DataFrame) -> DataFrame:
    """
    Aplica watermark e agrupa por janela temporal de 1 minuto por estufa.
    Calcula médias de temperatura e umidade.
    """
    return (
        sensor_df
        .withWatermark("event_time", WATERMARK_DELAY)
        .groupBy(
            window(col("event_time"), WINDOW_DURATION),
            col("estufa_id"),
        )
        .agg(
            avg("soil_temp_c").cast("decimal(5,2)").alias("avg_soil_temp_c"),
            avg("humidity").cast("decimal(5,2)").alias("avg_humidity"),
        )
        .withColumn("window_start", col("window.start"))
        .withColumn("window_end", col("window.end"))
        .withColumn("processed_at", current_timestamp())
        .drop("window")
    )


def gravar_agregado(batch_df: DataFrame, batch_id: int) -> None:
    """Persiste leituras agregadas por janela no PostgreSQL."""
    if batch_df.count() == 0:
        return
    batch_df.write.jdbc(
        url=DB_URL,
        table="viveiro_iot",
        mode="append",
        properties=DB_PROPS,
    )
    registros = batch_df.count()
    print(f"[consumer] Batch {batch_id} | aggregado | {registros} registro(s) gravado(s) em viveiro_iot")


def gravar_raw(batch_df: DataFrame, batch_id: int) -> None:
    """Persiste leituras brutas no PostgreSQL para auditoria."""
    if batch_df.count() == 0:
        return
    raw_df = batch_df.select(
        col("sensor_id"),
        col("estufa_id"),
        col("bed_id"),
        col("clone_id"),
        col("soil_temp_c"),
        col("humidity"),
        col("event_time").alias("ts"),
        current_timestamp().alias("received_at"),
    )
    raw_df.write.jdbc(
        url=DB_URL,
        table="sensor_readings_raw",
        mode="append",
        properties=DB_PROPS,
    )
    registros = raw_df.count()
    print(f"[consumer] Batch {batch_id} | raw | {registros} leitura(s) bruta(s) gravada(s) em sensor_readings_raw")


def main() -> None:
    print(f"[consumer] Iniciando | broker={KAFKA_BROKER} | topic={KAFKA_TOPIC}")

    spark = criar_spark_session()
    spark.sparkContext.setLogLevel("WARN")

    kafka_df = ler_kafka(spark)
    sensor_df = parsear_json(kafka_df)
    agg_df = agregar_por_janela(sensor_df)

    # Stream 1: leituras agregadas com window
    query_agregado = (
        agg_df.writeStream
        .foreachBatch(gravar_agregado)
        .outputMode("append")
        .option("checkpointLocation", f"{CHECKPOINT_LOCATION}/agregado")
        .trigger(processingTime=TRIGGER_INTERVAL)
        .start()
    )

    # Stream 2: leituras brutas para auditoria
    query_raw = (
        sensor_df.writeStream
        .foreachBatch(gravar_raw)
        .outputMode("append")
        .option("checkpointLocation", f"{CHECKPOINT_LOCATION}/raw")
        .trigger(processingTime=TRIGGER_INTERVAL)
        .start()
    )

    print(f"[consumer] Streaming iniciado. Aguardando dados do tópico '{KAFKA_TOPIC}'...")
    spark.streams.awaitAnyTermination()


if __name__ == "__main__":
    main()
