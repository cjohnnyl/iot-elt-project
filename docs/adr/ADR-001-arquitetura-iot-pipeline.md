# ADR-001 — Arquitetura do Pipeline IoT Eucalipto v2

**Data:** 2026-04-22  
**Status:** aceito  
**Autores:** Mateus (Arquiteto e Tech Lead) — TimeAtlas  

---

## Contexto

O projeto `iot-elt-project` é um pipeline de dados em tempo real para monitoramento de viveiro de eucalipto. A versão 1 tinha os seguintes problemas estruturais:

- Credenciais hardcoded em `consumer.py` (usuário/senha PostgreSQL)
- Consumer Spark com inicialização manual via `docker exec` — não subia automaticamente
- Tabela `viveiro_iot` sem chave primária nem índices — problema de performance e auditoria
- Producer fixo em uma única estufa (`EUCALIPTO_01`) — sem parametrização
- Sem controle temporal no streaming (sem `window()` nem `watermark()`)
- `startingOffsets: earliest` sem checkpoint estruturado
- Sem camada de API para consulta dos dados
- Sem análise inteligente dos dados com LLM
- Sem visualização de dados além do psql direto

A demanda da v2 é: corrigir todos esses problemas e adicionar API REST, alertas, análise com LLM local (Ollama), visualização com Grafana, e suporte a múltiplas estufas — tudo subindo com um único `docker-compose up`.

---

## Decisão

### Arquitetura geral

Pipeline orientado a streaming com serviços desacoplados por responsabilidade, sem acoplamento direto entre producer e consumer. A comunicação ocorre exclusivamente via Kafka. A persistência é dual: leituras brutas (auditoria) e leituras agregadas (operação). A camada de API é independente do pipeline de streaming.

### Estrutura de pastas

```
iot-elt-project/
├── docker-compose.yml
├── .env
├── .env.example
├── producer/
│   ├── Dockerfile
│   ├── producer.py          (multi-estufa via env var ESTUFAS)
│   └── wait-for-kafka.sh
├── consumer/
│   ├── Dockerfile           (spark-submit automático no entrypoint)
│   └── consumer.py          (window + watermark + env vars)
├── api/
│   ├── Dockerfile
│   ├── main.py              (FastAPI: endpoints REST)
│   ├── ai_analyzer.py       (integração Ollama)
│   └── alert_service.py     (lógica de alertas com thresholds)
├── postgres/
│   └── init_postgres.sql    (tabela agregada + tabela raw + PK + índices)
└── docs/
    └── adr/
        └── ADR-001-arquitetura-iot-pipeline.md
```

### Serviços Docker

| Serviço   | Imagem                          | Porta  | Responsabilidade                      |
|-----------|---------------------------------|--------|---------------------------------------|
| zookeeper | confluentinc/cp-zookeeper:7.2.1 | 2181   | Coordenação do cluster Kafka          |
| kafka     | confluentinc/cp-kafka:7.2.1     | 9092   | Mensageria de eventos IoT             |
| postgres  | postgres:14                     | 5432   | Persistência de leituras e alertas    |
| spark     | build local (consumer/)         | 4040   | Streaming processing automático       |
| producer  | build local (producer/)         | —      | Simulação de sensores PT100           |
| api       | build local (api/)              | 8000   | API REST + análise com Ollama         |
| ollama    | ollama/ollama                   | 11434  | LLM local (sem internet)              |
| grafana   | grafana/grafana                 | 3000   | Dashboard de visualização             |

### Tópico Kafka

**Nome:** `iot_sensors`  
**Schema da mensagem:**
```json
{
  "sensor_id": "string",
  "estufa_id": "string",
  "bed_id": "integer",
  "clone_id": "string",
  "soil_temp_c": "float",
  "humidity": "float",
  "timestamp": "ISO8601 UTC string"
}
```

### Modelo de dados PostgreSQL

**Tabela `viveiro_iot` (agregada):**
```sql
id              SERIAL PRIMARY KEY
estufa_id       VARCHAR(50)  -- INDEX
avg_soil_temp_c NUMERIC(5,2)
avg_humidity    NUMERIC(5,2)
window_start    TIMESTAMP
window_end      TIMESTAMP
processed_at    TIMESTAMP    -- INDEX
```

**Tabela `sensor_readings_raw` (bruta):**
```sql
id          SERIAL PRIMARY KEY
sensor_id   VARCHAR(20)
estufa_id   VARCHAR(50)  -- INDEX
bed_id      INTEGER
clone_id    VARCHAR(20)
soil_temp_c NUMERIC(5,2)
humidity    NUMERIC(5,2)
ts          TIMESTAMP    -- INDEX (timestamp original do sensor)
received_at TIMESTAMP DEFAULT NOW()
```

### Contratos de API REST

```
GET  /health                              → status do sistema e serviços
GET  /estufas                             → lista de estufas com leituras
GET  /leituras?estufa_id=X&limit=N        → leituras agregadas
GET  /leituras/raw?estufa_id=X&limit=N    → leituras brutas
GET  /alertas?estufa_id=X                 → alertas ativos
GET  /analise/estufa/{estufa_id}          → análise com Ollama (LLM)
```

### Variáveis de ambiente

Todas as configurações sensíveis e operacionais via `.env`:

```env
KAFKA_BROKER=kafka:9092
KAFKA_TOPIC=iot_sensors
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=iot_data
POSTGRES_HOST=postgres
POSTGRES_PORT=5432
ESTUFAS=EUCALIPTO_01,EUCALIPTO_02,EUCALIPTO_03
SENSOR_INTERVAL_SECONDS=3
API_PORT=8000
ALERT_TEMP_MIN=22.0
ALERT_TEMP_MAX=30.0
ALERT_HUMIDITY_MIN=50.0
ALERT_HUMIDITY_MAX=80.0
OLLAMA_HOST=http://ollama:11434
OLLAMA_MODEL=llama3.2
GRAFANA_ADMIN_PASSWORD=admin
```

---

## Alternativas consideradas

### KRaft em vez de Zookeeper

**Prós:** Remove dependência do Zookeeper, simplifica topologia, é o padrão moderno do Kafka.  
**Contras:** Exigiria troca da imagem Confluent por imagem KRaft-native, mudança na configuração do Kafka, mais risco de regressão.  
**Decisão:** Manter Zookeeper na v2 para reduzir escopo de mudança. KRaft será avaliado na v3.

### Flask em vez de FastAPI

**Prós:** Mais simples, menor curva.  
**Contras:** Sem async nativo, sem documentação automática OpenAPI, sem validação Pydantic.  
**Decisão:** FastAPI — é a stack correta para API Python moderna com auto-docs.

### Frontend customizado em vez de Grafana

**Prós:** Mais controle visual.  
**Contras:** Exigiria desenvolvimento frontend, CSS, JS, componentes — fora do escopo.  
**Decisão:** Grafana via Docker — datasource PostgreSQL nativo, zero código frontend, configurável via JSON.

### LLM externo (OpenAI, Claude) em vez de Ollama

**Prós:** Modelos mais capazes, menor latência de desenvolvimento.  
**Contras:** Custo por token, dependência de internet, dados do viveiro saem da rede local.  
**Decisão:** Ollama — requisito explícito do usuário. Zero custo, 100% local, dados seguros.

---

## Justificativa

A arquitetura escolhida é proporcional ao problema: um pipeline de dados IoT local para viveiro de eucalipto, com volume controlado e contexto educacional/técnico. Não há necessidade de Kubernetes, microserviços distribuídos ou streaming de alta escala. O objetivo é ter um sistema que:

1. Sobe com um comando (`docker-compose up`)
2. Tem logs estruturados e legíveis
3. Processa dados em streaming real com controle temporal
4. Expõe API REST para consulta
5. Gera análises com LLM local
6. Tem dashboard visual sem código frontend
7. Tem todos os segredos fora do código

---

## Consequências

**Positivas:**
- Execução com um único comando — zero intervenção manual
- Credenciais seguras via `.env` — nada hardcoded
- Múltiplas estufas configuráveis via env var
- Auditoria completa com tabela raw
- API REST documentada automaticamente via FastAPI
- Dashboard visual imediato com Grafana
- Análise inteligente 100% local com Ollama

**Negativas / trade-offs:**
- Ollama exige download do modelo (~2GB) na primeira execução
- Stack completa pode exigir 8–12GB de RAM (Spark + Ollama + Kafka)
- Grafana requer configuração manual do datasource na primeira execução (ou provisionamento via volume)
- Zookeeper ainda presente — será removido na v3

---

## Riscos

| Risco | Severidade | Mitigação |
|-------|-----------|-----------|
| Ollama baixa modelo na primeira execução (~2GB, pode ser lento) | Alta | Documentar no README; script de pull antecipado disponível |
| Spark pode falhar antes do Kafka estar pronto | Média | Health check no Dockerfile do consumer + restart policy |
| Window + Watermark requer timestamp como TimestampType no Spark | Média | Implementado com cast explícito no consumer |
| RAM insuficiente em máquinas com menos de 8GB | Alta | Documentar requisitos mínimos de hardware no README |
| Grafana sem dashboard pré-configurado | Baixa | Provisionar dashboard via arquivo JSON em volume |

---

## Plano de Implementação

### Fase 1 — Frentes paralelas (executadas em paralelo)

**Thiago (DevOps):**
- Refatorar `docker-compose.yml` com todos os serviços
- Criar `.env` e `.env.example`
- Criar `consumer/Dockerfile` com spark-submit automático
- Configurar logging driver para logs estruturados

**Aline (Backend):**
- Melhorar `producer/producer.py` — multi-estufa via env
- Melhorar `consumer/consumer.py` — window + watermark + env vars
- Criar `api/main.py` — FastAPI com todos os endpoints
- Criar `api/alert_service.py` — lógica de alertas com thresholds
- Melhorar `postgres/init_postgres.sql` — PK, índices, tabela raw

**Talita (IA):**
- Criar `api/ai_analyzer.py` — integração Ollama local
- Definir prompts e guardrails
- Implementar fallback para quando Ollama não estiver disponível

**Renan (Documentação):**
- Criar `README.md` completo com arquitetura, comandos, variáveis

### Fase 2 — Validação

**Patrícia (QA):**
- Validar todos os arquivos entregues
- Verificar que nenhum segredo está hardcoded
- Verificar consistência entre docker-compose e .env
- Emitir parecer final

---

*ADR criado por Mateus — Arquiteto e Tech Lead — TimeAtlas*  
*Operação: INFRA-20260422-001*
