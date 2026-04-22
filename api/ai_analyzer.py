"""
ai_analyzer.py — Integração com Ollama para análise de dados IoT.

Usa LLM local (via Ollama) para interpretar leituras de estufas e gerar
análises em linguagem natural: resumo de condições, detecção de tendências
e recomendações operacionais.

Execução 100% local — sem internet, sem custo de tokens, dados não saem da rede.

Variáveis de ambiente:
    OLLAMA_HOST: URL do serviço Ollama (padrão: http://ollama:11434)
    OLLAMA_MODEL: modelo a usar (padrão: llama3.2)

Guardrails implementados:
    - Input: dados validados antes de montar prompt
    - Output: estrutura esperada validada; fallback em caso de falha
    - Rate: timeout de 60s por request
    - Fallback: análise determinística quando Ollama indisponível
"""
import os
from datetime import datetime
from typing import Optional

import httpx

from alert_service import Alerta, AlertSeveridade

# ── Configuração ────────────────────────────────────────────────────────────
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://ollama:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")

# Timeout para chamadas ao Ollama
OLLAMA_TIMEOUT_SECONDS = 60

# Versão do prompt — incrementar ao modificar o prompt base
PROMPT_VERSION = "v1.0"


# ── Prompt base (versionado) ────────────────────────────────────────────────
PROMPT_SISTEMA = """Você é um especialista em monitoramento de viveiros de eucalipto.
Analise os dados de sensores IoT de temperatura do solo e umidade fornecidos.
Seja objetivo, técnico e prático. Responda sempre em português do Brasil.
Foque em: condições atuais, tendências observadas e recomendações operacionais.
Não invente dados que não estão presentes. Se os dados forem insuficientes, diga isso."""

PROMPT_ANALISE_TEMPLATE = """
## Dados da Estufa: {estufa_id}

### Thresholds normais configurados:
- Temperatura do solo: {temp_min}°C a {temp_max}°C
- Umidade: {humidity_min}% a {humidity_max}%

### Últimas {n_leituras} leituras agregadas (mais recente primeiro):
{tabela_leituras}

### Alertas ativos:
{alertas_texto}

### Sua análise deve cobrir:
1. **Resumo das condições atuais** (temperatura e umidade estão normais, elevadas ou baixas?)
2. **Tendência observada** (estável, subindo, descendo?)
3. **Risco identificado** (se houver — seja específico)
4. **Recomendação operacional** (o que fazer agora?)

Seja direto e prático. Máximo 200 palavras.
"""


def _formatar_leituras(leituras: list[dict]) -> str:
    """Formata as leituras em tabela texto para o prompt."""
    if not leituras:
        return "Nenhuma leitura disponível."

    linhas = ["Timestamp                | Temp (°C) | Umidade (%)"]
    linhas.append("-" * 48)
    for l in leituras:
        ts = l.get("processed_at")
        ts_str = ts.strftime("%Y-%m-%d %H:%M:%S") if isinstance(ts, datetime) else str(ts)
        temp = l.get("avg_soil_temp_c", "N/A")
        hum = l.get("avg_humidity", "N/A")
        linhas.append(f"{ts_str} | {temp:>9} | {hum:>11}")

    return "\n".join(linhas)


def _formatar_alertas(alertas: list[Alerta]) -> str:
    """Formata os alertas em texto para o prompt."""
    ativos = [a for a in alertas if a.severidade != AlertSeveridade.OK]
    if not ativos:
        return "Nenhum alerta ativo. Todas as métricas dentro do normal."

    return "\n".join([f"- [{a.severidade.value.upper()}] {a.mensagem}" for a in ativos])


def _analise_deterministica(
    estufa_id: str,
    leituras: list[dict],
    alertas: list[Alerta],
    thresholds: dict,
) -> str:
    """
    Fallback determinístico quando Ollama está indisponível.
    Gera análise básica baseada nos dados sem LLM.
    """
    if not leituras:
        return f"[Análise automática — Ollama indisponível] Estufa {estufa_id}: sem leituras recentes."

    ultima = leituras[0]
    temp = float(ultima.get("avg_soil_temp_c", 0))
    hum = float(ultima.get("avg_humidity", 0))

    temp_min = thresholds["temperatura"]["min"]
    temp_max = thresholds["temperatura"]["max"]
    hum_min = thresholds["umidade"]["min"]
    hum_max = thresholds["umidade"]["max"]

    alertas_ativos = [a for a in alertas if a.severidade != AlertSeveridade.OK]

    status_temp = "normal" if temp_min <= temp <= temp_max else ("baixa" if temp < temp_min else "alta")
    status_hum = "normal" if hum_min <= hum <= hum_max else ("baixa" if hum < hum_min else "alta")

    linhas = [
        f"[Análise automática — Ollama indisponível | {PROMPT_VERSION}]",
        f"Estufa: {estufa_id}",
        f"Temperatura atual: {temp}°C ({status_temp})",
        f"Umidade atual: {hum}% ({status_hum})",
    ]

    if alertas_ativos:
        linhas.append(f"Alertas ativos ({len(alertas_ativos)}):")
        for a in alertas_ativos:
            linhas.append(f"  - [{a.severidade.value.upper()}] {a.mensagem}")
    else:
        linhas.append("Nenhum alerta ativo. Condições normais.")

    return "\n".join(linhas)


class AIAnalyzer:
    """
    Integração com Ollama para análise de dados IoT.
    Implementa prompts versionados, guardrails e fallback determinístico.
    """

    def __init__(self):
        self.host = OLLAMA_HOST
        self.model = OLLAMA_MODEL
        self.prompt_version = PROMPT_VERSION

    def verificar_disponibilidade(self) -> str:
        """Verifica se o Ollama está disponível e retorna status."""
        try:
            with httpx.Client(timeout=5) as client:
                response = client.get(f"{self.host}/api/tags")
                if response.status_code == 200:
                    tags = response.json().get("models", [])
                    modelos = [m.get("name", "") for m in tags]
                    if any(self.model in m for m in modelos):
                        return f"ok (modelo {self.model} disponível)"
                    return f"ok (modelo {self.model} não baixado ainda)"
                return f"erro (status {response.status_code})"
        except Exception as e:
            return f"indisponivel ({str(e)[:50]})"

    def _montar_prompt(
        self,
        estufa_id: str,
        leituras: list[dict],
        alertas: list[Alerta],
        thresholds: dict,
    ) -> str:
        """Monta o prompt de análise com os dados da estufa."""
        return PROMPT_ANALISE_TEMPLATE.format(
            estufa_id=estufa_id,
            temp_min=thresholds["temperatura"]["min"],
            temp_max=thresholds["temperatura"]["max"],
            humidity_min=thresholds["umidade"]["min"],
            humidity_max=thresholds["umidade"]["max"],
            n_leituras=len(leituras),
            tabela_leituras=_formatar_leituras(leituras),
            alertas_texto=_formatar_alertas(alertas),
        )

    def _validar_output(self, texto: Optional[str]) -> bool:
        """
        Validação básica do output do LLM.
        Rejeita respostas muito curtas ou que indiquem erro do modelo.
        """
        if not texto or len(texto.strip()) < 50:
            return False
        texto_lower = texto.lower()
        sinais_falha = ["i cannot", "i don't understand", "error:", "i'm sorry, i can't"]
        if any(s in texto_lower for s in sinais_falha):
            return False
        return True

    async def analisar_estufa(
        self,
        estufa_id: str,
        leituras: list[dict],
        alertas: list[Alerta],
        thresholds: dict,
    ) -> dict:
        """
        Gera análise inteligente da estufa usando Ollama.
        Retorna fallback determinístico se Ollama estiver indisponível.
        """
        prompt = self._montar_prompt(estufa_id, leituras, alertas, thresholds)

        try:
            async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    f"{self.host}/api/generate",
                    json={
                        "model": self.model,
                        "prompt": prompt,
                        "system": PROMPT_SISTEMA,
                        "stream": False,
                        "options": {
                            "temperature": 0.3,     # baixo para saídas mais determinísticas
                            "num_predict": 300,     # limite de tokens de saída
                        },
                    },
                )
                response.raise_for_status()
                resultado = response.json()
                texto_gerado = resultado.get("response", "").strip()

                if not self._validar_output(texto_gerado):
                    raise ValueError(f"Output inválido do modelo: '{texto_gerado[:100]}'")

                return {
                    "texto": texto_gerado,
                    "modelo": self.model,
                    "prompt_version": self.prompt_version,
                    "fonte": "ollama",
                    "tokens_usados": resultado.get("eval_count", None),
                }

        except httpx.TimeoutException:
            print(f"[ai_analyzer] Timeout ao chamar Ollama ({OLLAMA_TIMEOUT_SECONDS}s). Usando fallback.")
            fallback = _analise_deterministica(estufa_id, leituras, alertas, thresholds)
            return {
                "texto": fallback,
                "modelo": "fallback_determinístico",
                "prompt_version": self.prompt_version,
                "fonte": "fallback",
                "motivo_fallback": "timeout",
            }

        except httpx.HTTPStatusError as e:
            print(f"[ai_analyzer] Erro HTTP do Ollama: {e.response.status_code}. Usando fallback.")
            fallback = _analise_deterministica(estufa_id, leituras, alertas, thresholds)
            return {
                "texto": fallback,
                "modelo": "fallback_determinístico",
                "prompt_version": self.prompt_version,
                "fonte": "fallback",
                "motivo_fallback": f"http_error_{e.response.status_code}",
            }

        except Exception as e:
            print(f"[ai_analyzer] Erro inesperado: {e}. Usando fallback.")
            fallback = _analise_deterministica(estufa_id, leituras, alertas, thresholds)
            return {
                "texto": fallback,
                "modelo": "fallback_determinístico",
                "prompt_version": self.prompt_version,
                "fonte": "fallback",
                "motivo_fallback": str(e)[:100],
            }
