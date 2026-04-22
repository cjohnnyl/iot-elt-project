"""
main.py — API REST do Pipeline IoT Eucalipto.

FastAPI com endpoints para consulta de leituras agregadas, leituras brutas,
lista de estufas ativas, verificação de alertas e análise com Ollama (LLM local).

Acesse a documentação interativa em: http://localhost:8000/docs

Variáveis de ambiente:
    POSTGRES_USER, POSTGRES_PASSWORD, POSTGRES_DB, POSTGRES_HOST, POSTGRES_PORT
    OLLAMA_HOST, OLLAMA_MODEL
    ALERT_TEMP_MIN, ALERT_TEMP_MAX, ALERT_HUMIDITY_MIN, ALERT_HUMIDITY_MAX
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException, Query

from ai_analyzer import AIAnalyzer
from alert_service import AlertService, AlertSeveridade

# ── Configuração ────────────────────────────────────────────────────────────
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_DB = os.getenv("POSTGRES_DB", "iot_data")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "postgres")
POSTGRES_PORT = int(os.getenv("POSTGRES_PORT", "5432"))

alert_service = AlertService()
ai_analyzer = AIAnalyzer()


# ── Conexão com PostgreSQL ──────────────────────────────────────────────────
def get_connection():
    """Retorna uma conexão com o PostgreSQL. Lança HTTPException se falhar."""
    try:
        return psycopg2.connect(
            host=POSTGRES_HOST,
            port=POSTGRES_PORT,
            user=POSTGRES_USER,
            password=POSTGRES_PASSWORD,
            dbname=POSTGRES_DB,
            connect_timeout=5,
        )
    except psycopg2.OperationalError as e:
        raise HTTPException(status_code=503, detail=f"Banco de dados indisponível: {str(e)}")


# ── Lifespan ────────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[api] Iniciando API IoT Eucalipto...")
    yield
    print("[api] Encerrando API IoT Eucalipto...")


# ── App FastAPI ─────────────────────────────────────────────────────────────
app = FastAPI(
    title="IoT Eucalipto API",
    description=(
        "API REST para monitoramento do viveiro de eucalipto. "
        "Consulta leituras de sensores PT100, alertas de temperatura e umidade, "
        "e análise inteligente com Ollama (LLM local)."
    ),
    version="2.0.0",
    lifespan=lifespan,
)


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/health", tags=["sistema"])
def health_check():
    """Verifica a saúde da API e conectividade com o banco."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        conn.close()
        db_status = "ok"
    except Exception:
        db_status = "indisponivel"

    ollama_status = ai_analyzer.verificar_disponibilidade()

    return {
        "status": "ok",
        "timestamp": datetime.utcnow().isoformat(),
        "servicos": {
            "api": "ok",
            "postgres": db_status,
            "ollama": ollama_status,
        },
        "thresholds": alert_service.thresholds,
    }


@app.get("/estufas", tags=["estufas"])
def listar_estufas():
    """Lista todas as estufas com pelo menos uma leitura registrada."""
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    estufa_id,
                    COUNT(*) AS total_leituras,
                    MAX(processed_at) AS ultima_leitura,
                    ROUND(AVG(avg_soil_temp_c)::numeric, 2) AS temp_media_geral,
                    ROUND(AVG(avg_humidity)::numeric, 2) AS humidity_media_geral
                FROM viveiro_iot
                GROUP BY estufa_id
                ORDER BY estufa_id
            """)
            estufas = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

    return {"estufas": estufas, "total": len(estufas)}


@app.get("/leituras", tags=["leituras"])
def consultar_leituras(
    estufa_id: Optional[str] = Query(None, description="Filtrar por ID da estufa"),
    limit: int = Query(50, ge=1, le=500, description="Quantidade máxima de registros"),
    desde: Optional[datetime] = Query(None, description="Filtrar por data/hora inicial (ISO8601)"),
    ate: Optional[datetime] = Query(None, description="Filtrar por data/hora final (ISO8601)"),
):
    """
    Consulta leituras agregadas pelo Spark Streaming.
    Cada registro representa a média de temperatura e umidade de uma estufa
    em uma janela de 1 minuto.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            filtros = []
            params = []

            if estufa_id:
                filtros.append("estufa_id = %s")
                params.append(estufa_id)
            if desde:
                filtros.append("processed_at >= %s")
                params.append(desde)
            if ate:
                filtros.append("processed_at <= %s")
                params.append(ate)

            where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
            params.append(limit)

            cur.execute(f"""
                SELECT
                    id,
                    estufa_id,
                    avg_soil_temp_c,
                    avg_humidity,
                    window_start,
                    window_end,
                    processed_at
                FROM viveiro_iot
                {where}
                ORDER BY processed_at DESC
                LIMIT %s
            """, params)

            leituras = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

    return {"leituras": leituras, "total": len(leituras)}


@app.get("/leituras/raw", tags=["leituras"])
def consultar_leituras_brutas(
    estufa_id: Optional[str] = Query(None, description="Filtrar por ID da estufa"),
    sensor_id: Optional[str] = Query(None, description="Filtrar por ID do sensor"),
    limit: int = Query(100, ge=1, le=1000, description="Quantidade máxima de registros"),
):
    """
    Consulta leituras brutas individuais de cada sensor.
    Útil para auditoria e análise detalhada sem agregação.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            filtros = []
            params = []

            if estufa_id:
                filtros.append("estufa_id = %s")
                params.append(estufa_id)
            if sensor_id:
                filtros.append("sensor_id = %s")
                params.append(sensor_id)

            where = f"WHERE {' AND '.join(filtros)}" if filtros else ""
            params.append(limit)

            cur.execute(f"""
                SELECT
                    id, sensor_id, estufa_id, bed_id, clone_id,
                    soil_temp_c, humidity, ts, received_at
                FROM sensor_readings_raw
                {where}
                ORDER BY ts DESC
                LIMIT %s
            """, params)

            leituras = [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()

    return {"leituras_brutas": leituras, "total": len(leituras)}


@app.get("/alertas", tags=["alertas"])
def consultar_alertas(
    estufa_id: Optional[str] = Query(None, description="Filtrar por ID da estufa"),
    apenas_ativos: bool = Query(True, description="Se True, retorna apenas alertas de aviso ou crítico"),
):
    """
    Consulta alertas baseados nas leituras mais recentes de cada estufa.
    Avalia temperatura e umidade contra os thresholds configurados.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            filtro_estufa = "AND estufa_id = %s" if estufa_id else ""
            params = [estufa_id] if estufa_id else []

            cur.execute(f"""
                SELECT DISTINCT ON (estufa_id)
                    estufa_id,
                    avg_soil_temp_c,
                    avg_humidity,
                    processed_at
                FROM viveiro_iot
                WHERE processed_at > NOW() - INTERVAL '10 minutes'
                {filtro_estufa}
                ORDER BY estufa_id, processed_at DESC
            """, params)

            leituras_recentes = cur.fetchall()
    finally:
        conn.close()

    if not leituras_recentes:
        return {
            "alertas": [],
            "total": 0,
            "mensagem": "Nenhuma leitura recente encontrada (últimos 10 minutos).",
        }

    todos_alertas = []
    for leitura in leituras_recentes:
        alertas = alert_service.verificar_leitura(
            estufa_id=leitura["estufa_id"],
            avg_soil_temp_c=float(leitura["avg_soil_temp_c"]),
            avg_humidity=float(leitura["avg_humidity"]),
        )
        for alerta in alertas:
            if apenas_ativos and alerta.severidade == AlertSeveridade.OK:
                continue
            todos_alertas.append({
                "estufa_id": alerta.estufa_id,
                "tipo": alerta.tipo,
                "severidade": alerta.severidade.value,
                "valor_atual": alerta.valor_atual,
                "threshold_min": alerta.threshold_min,
                "threshold_max": alerta.threshold_max,
                "mensagem": alerta.mensagem,
                "leitura_timestamp": leitura["processed_at"].isoformat() if leitura["processed_at"] else None,
            })

    return {
        "alertas": todos_alertas,
        "total": len(todos_alertas),
        "thresholds_configurados": alert_service.thresholds,
    }


@app.get("/analise/estufa/{estufa_id}", tags=["ia"])
async def analisar_estufa_com_ollama(estufa_id: str):
    """
    Gera análise inteligente das leituras de uma estufa usando Ollama (LLM local).
    Inclui resumo de condições, detecção de anomalias e recomendações.
    O modelo roda 100% localmente, sem envio de dados para a internet.
    """
    conn = get_connection()
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT
                    estufa_id,
                    avg_soil_temp_c,
                    avg_humidity,
                    processed_at
                FROM viveiro_iot
                WHERE estufa_id = %s
                ORDER BY processed_at DESC
                LIMIT 10
            """, (estufa_id,))
            leituras = cur.fetchall()
    finally:
        conn.close()

    if not leituras:
        raise HTTPException(
            status_code=404,
            detail=f"Nenhuma leitura encontrada para a estufa '{estufa_id}'.",
        )

    leituras_dict = [dict(row) for row in leituras]
    alertas = alert_service.verificar_leitura(
        estufa_id=estufa_id,
        avg_soil_temp_c=float(leituras_dict[0]["avg_soil_temp_c"]),
        avg_humidity=float(leituras_dict[0]["avg_humidity"]),
    )

    analise = await ai_analyzer.analisar_estufa(
        estufa_id=estufa_id,
        leituras=leituras_dict,
        alertas=alertas,
        thresholds=alert_service.thresholds,
    )

    return {
        "estufa_id": estufa_id,
        "total_leituras_analisadas": len(leituras_dict),
        "ultima_leitura": leituras_dict[0]["processed_at"].isoformat() if leituras_dict[0]["processed_at"] else None,
        "alertas_ativos": [
            {"tipo": a.tipo, "severidade": a.severidade.value, "mensagem": a.mensagem}
            for a in alertas if a.severidade.value != "ok"
        ],
        "analise_ia": analise,
    }
