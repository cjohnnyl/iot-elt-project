FROM apache/spark:3.5.0

USER root

# Diretório de trabalho da aplicação
WORKDIR /opt/spark-app

# Copia o consumer para o container
COPY consumer.py .

# Script de espera para Kafka e PostgreSQL
COPY wait-for-services.sh .
RUN chmod +x wait-for-services.sh

# Instala dependências Python necessárias para o consumer
RUN pip install --no-cache-dir \
    kafka-python==2.0.2 \
    psycopg2-binary==2.9.9

# Entrypoint: aguarda dependências e inicia spark-submit automaticamente
ENTRYPOINT ["/opt/spark-app/wait-for-services.sh"]
CMD ["/opt/spark/bin/spark-submit", \
     "--packages", "org.apache.spark:spark-sql-kafka-0-10_2.12:3.5.0,org.postgresql:postgresql:42.6.0", \
     "/opt/spark-app/consumer.py"]
