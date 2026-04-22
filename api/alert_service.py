"""
alert_service.py — Serviço de alertas IoT com thresholds configuráveis.

Avalia leituras de temperatura e umidade contra os thresholds definidos
via variáveis de ambiente e retorna alertas estruturados.

Thresholds padrão (configuráveis via .env):
    ALERT_TEMP_MIN: 22.0°C
    ALERT_TEMP_MAX: 30.0°C
    ALERT_HUMIDITY_MIN: 50.0%
    ALERT_HUMIDITY_MAX: 80.0%
"""
from dataclasses import dataclass
from enum import Enum
from typing import Optional
import os


class AlertSeveridade(str, Enum):
    CRITICO = "critico"
    AVISO = "aviso"
    OK = "ok"


@dataclass
class Alerta:
    estufa_id: str
    tipo: str
    severidade: AlertSeveridade
    valor_atual: float
    threshold_min: Optional[float]
    threshold_max: Optional[float]
    mensagem: str


class AlertService:
    """Avalia leituras contra thresholds e gera alertas estruturados."""

    def __init__(self):
        self.temp_min = float(os.getenv("ALERT_TEMP_MIN", "22.0"))
        self.temp_max = float(os.getenv("ALERT_TEMP_MAX", "30.0"))
        self.humidity_min = float(os.getenv("ALERT_HUMIDITY_MIN", "50.0"))
        self.humidity_max = float(os.getenv("ALERT_HUMIDITY_MAX", "80.0"))

    def _avaliar_metrica(
        self,
        estufa_id: str,
        tipo: str,
        valor: float,
        min_threshold: float,
        max_threshold: float,
        unidade: str,
    ) -> Alerta:
        """Avalia uma métrica contra thresholds e retorna um Alerta."""
        desvio_pct_min = (min_threshold - valor) / min_threshold * 100 if valor < min_threshold else 0
        desvio_pct_max = (valor - max_threshold) / max_threshold * 100 if valor > max_threshold else 0

        if valor < min_threshold:
            severidade = AlertSeveridade.CRITICO if desvio_pct_min > 10 else AlertSeveridade.AVISO
            mensagem = (
                f"{tipo} abaixo do mínimo: {valor}{unidade} "
                f"(mínimo: {min_threshold}{unidade}, desvio: -{desvio_pct_min:.1f}%)"
            )
        elif valor > max_threshold:
            severidade = AlertSeveridade.CRITICO if desvio_pct_max > 10 else AlertSeveridade.AVISO
            mensagem = (
                f"{tipo} acima do máximo: {valor}{unidade} "
                f"(máximo: {max_threshold}{unidade}, desvio: +{desvio_pct_max:.1f}%)"
            )
        else:
            severidade = AlertSeveridade.OK
            mensagem = f"{tipo} dentro do range normal: {valor}{unidade}"

        return Alerta(
            estufa_id=estufa_id,
            tipo=tipo,
            severidade=severidade,
            valor_atual=valor,
            threshold_min=min_threshold,
            threshold_max=max_threshold,
            mensagem=mensagem,
        )

    def verificar_leitura(
        self,
        estufa_id: str,
        avg_soil_temp_c: float,
        avg_humidity: float,
    ) -> list[Alerta]:
        """
        Verifica uma leitura agregada e retorna lista de alertas.
        Alertas com severidade OK são incluídos para rastreabilidade.
        """
        alertas = [
            self._avaliar_metrica(
                estufa_id=estufa_id,
                tipo="Temperatura do Solo",
                valor=avg_soil_temp_c,
                min_threshold=self.temp_min,
                max_threshold=self.temp_max,
                unidade="°C",
            ),
            self._avaliar_metrica(
                estufa_id=estufa_id,
                tipo="Umidade",
                valor=avg_humidity,
                min_threshold=self.humidity_min,
                max_threshold=self.humidity_max,
                unidade="%",
            ),
        ]
        return alertas

    def tem_alerta_ativo(self, alertas: list[Alerta]) -> bool:
        """Retorna True se houver pelo menos um alerta não-OK."""
        return any(a.severidade != AlertSeveridade.OK for a in alertas)

    @property
    def thresholds(self) -> dict:
        """Retorna os thresholds configurados atualmente."""
        return {
            "temperatura": {"min": self.temp_min, "max": self.temp_max, "unidade": "°C"},
            "umidade": {"min": self.humidity_min, "max": self.humidity_max, "unidade": "%"},
        }
