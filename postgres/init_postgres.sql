-- ============================================================
-- init_postgres.sql — Inicialização do banco IoT Eucalipto
-- ============================================================
-- Executado automaticamente pelo PostgreSQL na primeira
-- inicialização do container, via /docker-entrypoint-initdb.d/
-- ============================================================

-- ──────────────────────────────────────────────────────────────
-- Tabela: viveiro_iot
-- Leituras AGREGADAS calculadas pelo Spark Structured Streaming.
-- Cada linha representa a média de temperatura e umidade de uma
-- estufa em uma janela temporal de 1 minuto.
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS viveiro_iot (
    id              SERIAL PRIMARY KEY,
    estufa_id       VARCHAR(50)    NOT NULL,
    avg_soil_temp_c NUMERIC(5, 2)  NOT NULL,
    avg_humidity    NUMERIC(5, 2)  NOT NULL,
    window_start    TIMESTAMP,
    window_end      TIMESTAMP,
    processed_at    TIMESTAMP      NOT NULL DEFAULT NOW()
);

-- Índice para consultas por estufa (filtro mais frequente)
CREATE INDEX IF NOT EXISTS idx_viveiro_estufa_id
    ON viveiro_iot (estufa_id);

-- Índice para consultas por período (ORDER BY / WHERE com datas)
CREATE INDEX IF NOT EXISTS idx_viveiro_processed_at
    ON viveiro_iot (processed_at DESC);

-- Índice composto para consultas por estufa + período
CREATE INDEX IF NOT EXISTS idx_viveiro_estufa_processed
    ON viveiro_iot (estufa_id, processed_at DESC);


-- ──────────────────────────────────────────────────────────────
-- Tabela: sensor_readings_raw
-- Leituras BRUTAS de cada sensor, sem agregação.
-- Usada para auditoria, reprocessamento e análise detalhada.
-- Cada linha representa uma leitura individual de um sensor PT100.
-- ──────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sensor_readings_raw (
    id          SERIAL PRIMARY KEY,
    sensor_id   VARCHAR(20)   NOT NULL,
    estufa_id   VARCHAR(50)   NOT NULL,
    bed_id      INTEGER,
    clone_id    VARCHAR(20),
    soil_temp_c NUMERIC(5, 2) NOT NULL,
    humidity    NUMERIC(5, 2) NOT NULL,
    ts          TIMESTAMP     NOT NULL,    -- timestamp original do sensor
    received_at TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- Índice para consultas por estufa
CREATE INDEX IF NOT EXISTS idx_raw_estufa_id
    ON sensor_readings_raw (estufa_id);

-- Índice para consultas por tempo do sensor
CREATE INDEX IF NOT EXISTS idx_raw_ts
    ON sensor_readings_raw (ts DESC);

-- Índice para consultas por sensor individual
CREATE INDEX IF NOT EXISTS idx_raw_sensor_id
    ON sensor_readings_raw (sensor_id);

-- Índice composto para consultas por estufa + período
CREATE INDEX IF NOT EXISTS idx_raw_estufa_ts
    ON sensor_readings_raw (estufa_id, ts DESC);
