#!/bin/sh
# wait-for-services.sh — Aguarda Kafka e PostgreSQL antes de iniciar o consumer Spark

set -e

KAFKA_HOST="${KAFKA_BROKER:-kafka:9092}"
POSTGRES_HOST="${POSTGRES_HOST:-postgres}"
POSTGRES_PORT="${POSTGRES_PORT:-5432}"
POSTGRES_USER="${POSTGRES_USER:-postgres}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-postgres}"
POSTGRES_DB="${POSTGRES_DB:-iot_data}"

# Aguarda Kafka estar disponível
echo "[consumer/entrypoint] Aguardando Kafka em $KAFKA_HOST..."
until python3 -c "
from kafka import KafkaAdminClient
try:
    client = KafkaAdminClient(bootstrap_servers='$KAFKA_HOST', request_timeout_ms=5000)
    client.close()
    print('[consumer/entrypoint] Kafka OK')
except Exception as e:
    raise SystemExit(1)
" 2>/dev/null; do
  echo "[consumer/entrypoint] Kafka indisponivel - aguardando 3s..."
  sleep 3
done

echo "[consumer/entrypoint] Kafka pronto."

# Aguarda PostgreSQL estar disponível
echo "[consumer/entrypoint] Aguardando PostgreSQL em $POSTGRES_HOST:$POSTGRES_PORT..."
until python3 -c "
import psycopg2
try:
    conn = psycopg2.connect(
        host='$POSTGRES_HOST',
        port=$POSTGRES_PORT,
        user='$POSTGRES_USER',
        password='$POSTGRES_PASSWORD',
        dbname='$POSTGRES_DB',
        connect_timeout=3
    )
    conn.close()
    print('[consumer/entrypoint] PostgreSQL OK')
except Exception as e:
    raise SystemExit(1)
" 2>/dev/null; do
  echo "[consumer/entrypoint] PostgreSQL indisponivel - aguardando 3s..."
  sleep 3
done

echo "[consumer/entrypoint] PostgreSQL pronto."
echo "[consumer/entrypoint] Iniciando spark-submit do consumer IoT..."

exec "$@"
