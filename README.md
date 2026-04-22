# IoT ELT Project — Viveiro de Eucalipto v2

Pipeline de dados em tempo real para monitoramento de viveiro de eucalipto.  
**Sobe com um único comando. Analisa com IA local. Visualiza com Grafana.**

---

## Visão Geral

Este projeto simula sensores PT100 de temperatura do solo e umidade em um viveiro de eucalipto. Os dados fluem por Kafka, são processados em streaming pelo Spark, persistidos no PostgreSQL, expostos via API REST e analisados por um LLM local (Ollama) — tudo orquestrado por Docker Compose.

**Versão 2 — o que mudou:**
- Execução com um único comando (`docker-compose up`)
- Consumer Spark automático — sem `docker exec` manual
- Multi-estufa configurável via variável de ambiente
- Janela temporal no streaming (window + watermark)
- Credenciais via `.env` — nada hardcoded
- API REST FastAPI com documentação automática
- Sistema de alertas com thresholds configuráveis
- Análise com LLM local via Ollama
- Dashboard Grafana pré-configurado
- Tabela de leituras brutas para auditoria

---

## Arquitetura

```
┌─────────────────────────────────────────────────────────────────┐
│                    docker-compose up                             │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────┐    ┌──────────────┐    ┌──────────────────────────┐
│  Zookeeper   │◄───│    Kafka     │◄───│  Producer (Python)        │
│  :2181       │    │  :9092       │    │  Simula sensores PT100    │
└──────────────┘    └──────┬───────┘    │  Multi-estufa via env    │
                           │            └──────────────────────────┘
                           │ tópico: iot_sensors
                           ▼
                  ┌──────────────────┐
                  │  Spark Consumer  │
                  │  :4040 (UI)      │
                  │  window(1min)    │
                  │  watermark(10s)  │
                  └────────┬─────────┘
                           │ 2 streams paralelos
                    ┌──────┴───────┐
                    ▼              ▼
           ┌──────────────┐  ┌──────────────────────┐
           │  viveiro_iot │  │  sensor_readings_raw  │
           │  (agregado)  │  │  (bruto/auditoria)    │
           └──────┬───────┘  └──────────────────────┘
                  │                   │
                  └────────┬──────────┘
                           │ PostgreSQL :5432
                           ▼
              ┌────────────────────────┐
              │  FastAPI  :8000        │
              │  /leituras             │
              │  /alertas              │
              │  /estufas              │
              │  /analise/{estufa_id}  │◄──── Ollama :11434
              │  /docs (Swagger)       │      LLM local
              └────────────────────────┘
                           │
                           ▼
              ┌────────────────────────┐
              │  Grafana  :3000        │
              │  Dashboard IoT         │
              │  Datasource: Postgres  │
              └────────────────────────┘
```

### Serviços

| Serviço   | Porta   | Função                                      |
|-----------|---------|---------------------------------------------|
| zookeeper | 2181    | Coordenação do cluster Kafka                |
| kafka     | 9092    | Mensageria de eventos IoT                   |
| postgres  | 5432    | Persistência de leituras e alertas          |
| spark     | 4040    | Streaming processing (automático)            |
| producer  | —       | Simulação de sensores PT100                 |
| api       | 8000    | API REST + análise com Ollama               |
| ollama    | 11434   | LLM local (sem internet, zero custo)        |
| grafana   | 3000    | Dashboard de visualização                   |

---

## Pré-requisitos

| Requisito      | Versão mínima | Link |
|----------------|--------------|------|
| Docker         | 24.0         | [docs.docker.com/get-docker](https://docs.docker.com/get-docker/) |
| Docker Compose | 2.0          | [docs.docker.com/compose/install](https://docs.docker.com/compose/install/) |
| RAM livre      | 8 GB         | Spark + Ollama + Kafka juntos exigem bastante |
| Disco livre    | 10 GB        | Imagens Docker + modelo Ollama (~2GB) |

---

## Início Rápido

### 1. Clone o repositório

```bash
git clone https://github.com/cjohnnyl/iot-elt-project.git
cd iot-elt-project
```

### 2. Configure as variáveis de ambiente

```bash
cp .env.example .env
# Ajuste as variáveis se necessário (as padrões já funcionam para desenvolvimento)
```

### 3. Baixe o modelo Ollama (primeira vez — ~2GB)

```bash
docker-compose run --rm ollama ollama pull llama3.2
```

> Este passo é necessário apenas na primeira execução. O modelo fica armazenado no volume `iot_ollama_data`.

### 4. Suba todos os serviços

```bash
docker-compose up --build
```

Aguarde todos os serviços iniciarem (pode levar 2–3 minutos na primeira vez).

### 5. Acesse os serviços

| Serviço     | URL                          | Credenciais     |
|-------------|------------------------------|-----------------|
| API REST    | http://localhost:8000        | —               |
| Swagger UI  | http://localhost:8000/docs   | —               |
| Grafana     | http://localhost:3000        | admin / admin   |
| Spark UI    | http://localhost:4040        | —               |

---

## Variáveis de Ambiente

Todas as configurações estão no arquivo `.env`. Copie `.env.example` como base.

| Variável                  | Padrão                        | Descrição                                      |
|---------------------------|-------------------------------|------------------------------------------------|
| `KAFKA_BROKER`            | `kafka:9092`                  | Endereço do broker Kafka (interno)             |
| `KAFKA_TOPIC`             | `iot_sensors`                 | Tópico de eventos IoT                          |
| `POSTGRES_USER`           | `postgres`                    | Usuário do banco                               |
| `POSTGRES_PASSWORD`       | `postgres`                    | Senha do banco                                 |
| `POSTGRES_DB`             | `iot_data`                    | Nome do banco                                  |
| `POSTGRES_HOST`           | `postgres`                    | Host do banco (interno)                        |
| `POSTGRES_PORT`           | `5432`                        | Porta do banco                                 |
| `ESTUFAS`                 | `EUCALIPTO_01,EUCALIPTO_02,EUCALIPTO_03` | Estufas simuladas (separadas por vírgula) |
| `SENSOR_INTERVAL_SECONDS` | `3`                           | Intervalo entre leituras do producer (segundos) |
| `API_PORT`                | `8000`                        | Porta da API REST                              |
| `ALERT_TEMP_MIN`          | `22.0`                        | Temperatura mínima aceitável (°C)              |
| `ALERT_TEMP_MAX`          | `30.0`                        | Temperatura máxima aceitável (°C)              |
| `ALERT_HUMIDITY_MIN`      | `50.0`                        | Umidade mínima aceitável (%)                   |
| `ALERT_HUMIDITY_MAX`      | `80.0`                        | Umidade máxima aceitável (%)                   |
| `OLLAMA_HOST`             | `http://ollama:11434`         | URL do serviço Ollama (interno)                |
| `OLLAMA_MODEL`            | `llama3.2`                    | Modelo LLM a usar                              |
| `GRAFANA_ADMIN_USER`      | `admin`                       | Usuário admin do Grafana                       |
| `GRAFANA_ADMIN_PASSWORD`  | `admin`                       | Senha admin do Grafana                         |

---

## API REST — Endpoints

Documentação interativa completa em: **http://localhost:8000/docs**

### `GET /health`
Status da API e conectividade com banco e Ollama.

```bash
curl http://localhost:8000/health
```

### `GET /estufas`
Lista todas as estufas com estatísticas gerais.

```bash
curl http://localhost:8000/estufas
```

### `GET /leituras`
Leituras agregadas pelo Spark. Suporta filtros por estufa e período.

```bash
# Últimas 50 leituras
curl http://localhost:8000/leituras

# Filtrar por estufa e limitar quantidade
curl "http://localhost:8000/leituras?estufa_id=EUCALIPTO_01&limit=10"

# Filtrar por período
curl "http://localhost:8000/leituras?desde=2026-04-22T00:00:00&ate=2026-04-22T23:59:59"
```

### `GET /leituras/raw`
Leituras brutas individuais de cada sensor (sem agregação).

```bash
curl "http://localhost:8000/leituras/raw?estufa_id=EUCALIPTO_01&limit=20"
```

### `GET /alertas`
Alertas baseados nas leituras mais recentes de cada estufa.

```bash
# Apenas alertas ativos (aviso e crítico)
curl http://localhost:8000/alertas

# Todos os status (incluindo OK)
curl "http://localhost:8000/alertas?apenas_ativos=false"

# Filtrar por estufa
curl "http://localhost:8000/alertas?estufa_id=EUCALIPTO_01"
```

### `GET /analise/estufa/{estufa_id}`
Análise com LLM local (Ollama). Gera texto interpretativo com condições, tendências e recomendações.

```bash
curl http://localhost:8000/analise/estufa/EUCALIPTO_01
```

---

## Visualização com Grafana

1. Acesse **http://localhost:3000** (admin / admin)
2. O datasource PostgreSQL já está pré-configurado automaticamente
3. O dashboard **"IoT Viveiro de Eucalipto"** está disponível em Dashboards

**Painéis disponíveis:**
- Temperatura média atual por estufa (gauge com thresholds)
- Umidade média atual por estufa (gauge com thresholds)
- Temperatura ao longo do tempo (série temporal)
- Umidade ao longo do tempo (série temporal)
- Últimas leituras brutas dos sensores (tabela)

O dashboard atualiza automaticamente a cada 10 segundos.

---

## Verificando o Funcionamento

### Logs de cada serviço

```bash
# Producer — veja as mensagens sendo enviadas
docker logs -f producer

# Consumer Spark — veja os batches sendo processados
docker logs -f spark

# API — veja as requisições
docker logs -f api

# Ollama — veja as inferências
docker logs -f ollama
```

**Saída esperada do producer:**
```
[producer] Iniciando | broker=kafka:9092 | topic=iot_sensors | estufas=['EUCALIPTO_01', 'EUCALIPTO_02', 'EUCALIPTO_03']
[producer] estufa=EUCALIPTO_01 sensor=s3 temp=27.45°C humidity=65.30%
[producer] estufa=EUCALIPTO_02 sensor=s1 temp=24.12°C humidity=71.80%
[producer] estufa=EUCALIPTO_03 sensor=s5 temp=29.88°C humidity=58.40%
```

**Saída esperada do consumer:**
```
[consumer] Iniciando | broker=kafka:9092 | topic=iot_sensors
[consumer] Streaming iniciado. Aguardando dados do tópico 'iot_sensors'...
[consumer] Batch 0 | agregado | 3 registro(s) gravado(s) em viveiro_iot
[consumer] Batch 0 | raw | 12 leitura(s) bruta(s) gravada(s) em sensor_readings_raw
```

### Consultando o banco diretamente

```bash
# Leituras agregadas
docker exec -it postgres psql -U postgres -d iot_data -c \
  "SELECT estufa_id, avg_soil_temp_c, avg_humidity, processed_at FROM viveiro_iot ORDER BY processed_at DESC LIMIT 10;"

# Leituras brutas
docker exec -it postgres psql -U postgres -d iot_data -c \
  "SELECT sensor_id, estufa_id, soil_temp_c, humidity, ts FROM sensor_readings_raw ORDER BY ts DESC LIMIT 10;"

# Total de registros
docker exec -it postgres psql -U postgres -d iot_data -c \
  "SELECT 'agregado' AS tabela, COUNT(*) FROM viveiro_iot UNION SELECT 'raw', COUNT(*) FROM sensor_readings_raw;"
```

---

## Estrutura do Projeto

```
iot-elt-project/
├── docker-compose.yml              # Orquestra todos os 8 serviços
├── .env                            # Variáveis de ambiente (não commitar)
├── .env.example                    # Template de variáveis
│
├── producer/
│   ├── Dockerfile                  # Imagem Python do producer
│   ├── producer.py                 # Simula sensores PT100 (multi-estufa)
│   └── wait-for-kafka.sh           # Aguarda Kafka antes de iniciar
│
├── consumer/
│   ├── Dockerfile                  # Imagem Spark com spark-submit automático
│   ├── consumer.py                 # Streaming: window + watermark + 2 tabelas
│   └── wait-for-services.sh        # Aguarda Kafka e PostgreSQL
│
├── api/
│   ├── Dockerfile                  # Imagem FastAPI
│   ├── requirements.txt            # Dependências Python da API
│   ├── main.py                     # Endpoints REST (leituras, alertas, análise)
│   ├── alert_service.py            # Lógica de alertas com thresholds
│   └── ai_analyzer.py              # Integração Ollama com guardrails e fallback
│
├── postgres/
│   └── init_postgres.sql           # Tabelas, PK e índices (executado automaticamente)
│
├── grafana/
│   └── provisioning/
│       ├── datasources/
│       │   └── postgres.yml        # Datasource PostgreSQL automático
│       └── dashboards/
│           ├── dashboard.yml       # Configuração do provider
│           └── iot-viveiro.json    # Dashboard pré-configurado
│
└── docs/
    └── adr/
        └── ADR-001-arquitetura-iot-pipeline.md  # Decisões arquiteturais
```

---

## Comandos Úteis

```bash
# Subir tudo (modo attached — vê todos os logs)
docker-compose up --build

# Subir em background
docker-compose up -d --build

# Parar e remover containers (mantém volumes)
docker-compose down

# Parar, remover containers e volumes (reset completo)
docker-compose down -v

# Ver status dos containers
docker-compose ps

# Escalar o producer (rodar 2 instâncias)
docker-compose up --scale producer=2

# Baixar modelo Ollama diferente (ex: phi3)
docker-compose run --rm ollama ollama pull phi3
```

---

## Modelo de Dados

### `viveiro_iot` — Leituras Agregadas

| Coluna           | Tipo         | Descrição                          |
|------------------|--------------|------------------------------------|
| `id`             | SERIAL PK    | Identificador único                |
| `estufa_id`      | VARCHAR(50)  | ID da estufa (ex: EUCALIPTO_01)    |
| `avg_soil_temp_c`| NUMERIC(5,2) | Média de temperatura do solo (°C)  |
| `avg_humidity`   | NUMERIC(5,2) | Média de umidade (%)               |
| `window_start`   | TIMESTAMP    | Início da janela temporal          |
| `window_end`     | TIMESTAMP    | Fim da janela temporal             |
| `processed_at`   | TIMESTAMP    | Quando foi processado pelo Spark   |

### `sensor_readings_raw` — Leituras Brutas

| Coluna       | Tipo         | Descrição                          |
|--------------|--------------|------------------------------------|
| `id`         | SERIAL PK    | Identificador único                |
| `sensor_id`  | VARCHAR(20)  | ID do sensor (ex: s1)              |
| `estufa_id`  | VARCHAR(50)  | ID da estufa                       |
| `bed_id`     | INTEGER      | ID do canteiro                     |
| `clone_id`   | VARCHAR(20)  | ID do clone de eucalipto           |
| `soil_temp_c`| NUMERIC(5,2) | Temperatura do solo (°C)           |
| `humidity`   | NUMERIC(5,2) | Umidade (%)                        |
| `ts`         | TIMESTAMP    | Timestamp original do sensor       |
| `received_at`| TIMESTAMP    | Quando foi recebido pelo sistema   |

---

## Fluxo de Dados

O pipeline segue um fluxo linear de ingestão → processamento → persistência → exposição → visualização:

1. **Geração (Producer):** O producer Python simula sensores PT100 em múltiplas estufas. A cada `SENSOR_INTERVAL_SECONDS` segundos, cada sensor gera uma leitura de temperatura do solo (°C) e umidade (%), serializada como JSON e publicada no tópico Kafka `iot_sensors`.

2. **Transporte (Kafka + Zookeeper):** O Kafka recebe e armazena as mensagens no tópico `iot_sensors`. O Zookeeper coordena o cluster. As mensagens ficam disponíveis para consumo com offset rastreável.

3. **Processamento em Streaming (Spark):** O consumer Spark Structured Streaming lê o tópico Kafka, parseia o JSON com schema tipado, aplica watermark de 10 segundos para tolerância a atraso e agrupa por janela temporal de 1 minuto e por estufa. Dois streams paralelos escrevem no banco:
   - **Stream 1:** leituras agregadas (médias por janela) → tabela `viveiro_iot`
   - **Stream 2:** leituras brutas individuais → tabela `sensor_readings_raw`

4. **Persistência (PostgreSQL):** Os dados são gravados via JDBC em duas tabelas. `viveiro_iot` armazena médias por janela temporal (ideal para análise e dashboards). `sensor_readings_raw` armazena cada leitura individual (ideal para auditoria e debug).

5. **Exposição (FastAPI):** A API REST consulta o PostgreSQL e disponibiliza os dados via endpoints REST documentados com Swagger. O endpoint `/analise/{estufa_id}` envia o histórico recente para o Ollama e retorna análise textual gerada pelo LLM local.

6. **Análise com IA (Ollama):** O Ollama roda o LLM (`llama3.2` por padrão) 100% localmente, sem envio de dados para a internet. A análise inclui resumo das condições atuais, detecção de tendências e recomendações agronômicas.

7. **Visualização (Grafana):** O Grafana consulta o PostgreSQL diretamente via datasource pré-configurado e exibe o dashboard com gauges de temperatura e umidade, séries temporais e tabela de leituras brutas — atualizado a cada 10 segundos.

---

## Stack Tecnológica

| Tecnologia | Versão | Função no Pipeline |
|-----------|--------|-------------------|
| Apache Kafka | 7.5.0 (Confluent) | Mensageria de eventos IoT — transporte das leituras dos sensores |
| Apache Zookeeper | 7.5.0 (Confluent) | Coordenação do cluster Kafka |
| Apache Spark | 3.5.0 | Structured Streaming — janela temporal, watermark, agregação |
| PostgreSQL | 15 | Persistência relacional — leituras agregadas e brutas |
| FastAPI | 0.111.0 | API REST — endpoints de consulta, alertas e análise |
| Uvicorn | 0.29.0 | Servidor ASGI para FastAPI |
| psycopg2-binary | 2.9.9 | Driver Python para PostgreSQL |
| httpx | 0.27.0 | Cliente HTTP async para chamadas ao Ollama |
| Ollama | latest | Runtime de LLM local — executa o modelo sem internet |
| llama3.2 | ~2GB | Modelo LLM padrão para análise das estufas |
| Grafana | 10.x | Dashboards de visualização com datasource PostgreSQL |
| Python | 3.11+ | Linguagem do producer, consumer e API |
| Docker Compose | 2.0+ | Orquestração de todos os 8 serviços |

---

## Troubleshooting

### Ollama ainda baixando o modelo
Se o endpoint `/analise` retornar erro 503 ou timeout logo após o primeiro `docker-compose up`, o modelo `llama3.2` pode ainda estar sendo baixado em background. Verifique o progresso com:

```bash
docker logs -f ollama
```

Aguarde até ver a mensagem de conclusão do pull antes de chamar `/analise`. Alternativamente, faça o pull antes de subir o stack completo:

```bash
docker-compose run --rm ollama ollama pull llama3.2
docker-compose up --build
```

### Ollama demorando para responder
O modelo pode levar 10–60 segundos na primeira inferência. O endpoint `/analise` tem timeout de 60s e fallback automático.

### Consumer Spark não iniciando
Verifique se Kafka e PostgreSQL estão healthy:
```bash
docker-compose ps
docker logs spark
```

### Grafana sem dados
Aguarde 2–3 minutos para o pipeline inicializar completamente. Verifique se o consumer está ativo:
```bash
docker logs -f spark
```

### Requisitos de memória
Se os containers estiverem sendo mortos (OOMKilled), aumente a memória disponível para o Docker nas configurações do Docker Desktop.

---

## Autor

**Carlos Johnny Leite**  
Engenheiro de Dados  
[github.com/cjohnnyl](https://github.com/cjohnnyl)

---

*Documentação produzida pelo TimeAtlas — Renan (Especialista em Documentação)*  
*Arquitetura: Mateus | Infra: Thiago | Backend: Aline | IA: Talita*
