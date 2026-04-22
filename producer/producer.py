"""
producer.py — Simulação de sensores PT100 para múltiplas estufas.

Publica mensagens JSON no Kafka com leituras de temperatura do solo
e umidade para cada estufa configurada via variável de ambiente ESTUFAS.

Variáveis de ambiente:
    KAFKA_BROKER: endereço do broker Kafka (padrão: kafka:9092)
    TOPIC: nome do tópico Kafka (padrão: iot_sensors)
    ESTUFAS: estufas separadas por vírgula (padrão: EUCALIPTO_01)
    SENSOR_INTERVAL_SECONDS: intervalo entre mensagens (padrão: 3)
"""
import json
import os
import random
import time
from datetime import datetime, timezone

from kafka import KafkaProducer
from kafka.errors import KafkaError

# ── Configuração via variáveis de ambiente ──────────────────────────────────
BROKER = os.getenv("KAFKA_BROKER", "kafka:9092")
TOPIC = os.getenv("TOPIC", "iot_sensors")
ESTUFAS = [e.strip() for e in os.getenv("ESTUFAS", "EUCALIPTO_01").split(",") if e.strip()]
INTERVAL = int(os.getenv("SENSOR_INTERVAL_SECONDS", "3"))

# ── Ranges de leitura dos sensores PT100 ───────────────────────────────────
TEMP_MIN = 20.0
TEMP_MAX = 35.0
HUMIDITY_MIN = 40.0
HUMIDITY_MAX = 90.0

print(f"[producer] Iniciando | broker={BROKER} | topic={TOPIC} | estufas={ESTUFAS} | intervalo={INTERVAL}s")


def criar_producer() -> KafkaProducer:
    """Cria e retorna um KafkaProducer configurado."""
    return KafkaProducer(
        bootstrap_servers=BROKER,
        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
        acks="all",
        retries=3,
    )


def gerar_leitura(estufa_id: str) -> dict:
    """Gera uma leitura simulada de sensor PT100 para a estufa informada."""
    return {
        "sensor_id": f"s{random.randint(1, 5)}",
        "estufa_id": estufa_id,
        "bed_id": random.randint(1, 10),
        "clone_id": f"CL{random.randint(100, 999)}",
        "soil_temp_c": round(random.uniform(TEMP_MIN, TEMP_MAX), 2),
        "humidity": round(random.uniform(HUMIDITY_MIN, HUMIDITY_MAX), 2),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def on_send_success(record_metadata):
    """Callback chamado quando a mensagem é confirmada pelo broker."""
    pass  # sucesso silencioso — evitar flood de logs


def on_send_error(excp):
    """Callback chamado em caso de falha no envio."""
    print(f"[producer] ERRO ao enviar mensagem: {excp}")


def main():
    producer = criar_producer()
    print(f"[producer] Conectado ao Kafka. Publicando a cada {INTERVAL}s...")

    try:
        while True:
            for estufa_id in ESTUFAS:
                leitura = gerar_leitura(estufa_id)
                (
                    producer.send(TOPIC, leitura)
                    .add_callback(on_send_success)
                    .add_errback(on_send_error)
                )
                print(
                    f"[producer] estufa={leitura['estufa_id']} "
                    f"sensor={leitura['sensor_id']} "
                    f"temp={leitura['soil_temp_c']}°C "
                    f"humidity={leitura['humidity']}%"
                )
            producer.flush()
            time.sleep(INTERVAL)
    except KeyboardInterrupt:
        print("[producer] Encerrando...")
    finally:
        producer.close()
        print("[producer] Conexão encerrada.")


if __name__ == "__main__":
    main()
