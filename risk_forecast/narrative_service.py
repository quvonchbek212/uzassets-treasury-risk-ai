"""
Payment Calendar Risk Forecast — AI Narrative Service
3 ta endpoint uchun asosiy orkestratsiya:
  1. /risk-forecast              → generate_forecast_narrative()
  2. /risk-forecast/days/{date}  → generate_day_narrative()
  3. /risk-forecast/explain      → generate_explain_narrative()

Har bir metod:
  - AI yoqilgan bo'lsa tanlangan providerga so'rov yuboradi
  - Javobni validatsiyadan o'tkazadi
  - Xatolikda fallback qaytaradi
  - AI o'chirilgan bo'lsa to'g'ridan-to'g'ri fallback qaytaradi
"""

from __future__ import annotations

import logging

from risk_forecast.gemini_client import GeminiAiClient, GeminiAiClientError
from risk_forecast.vllm_client import VllmAiClient, VllmAiClientError
from risk_forecast.settings import RiskForecastAiConfig, get_config, normalize_ai_model
from risk_forecast.schemas import (
    AiNarrativeRequest,
    AiNarrativeResponse,
    DayDetailAiRequest,
    ExplainAiRequest,
)
from risk_forecast.narrative_fallback import FallbackNarrativeGenerator
from risk_forecast.prompt_builder import PromptBuilder
from risk_forecast.response_validator import (
    AiResponseValidationError,
    AiResponseValidator,
)

logger = logging.getLogger(__name__)


class PaymentCalendarRiskNarrativeService:
    """
    AI narrative service — barcha 3 ta endpoint uchun.
    Dependency injection orqali sozlanadi (yoki default singleton).
    """

    def __init__(
        self,
        config: RiskForecastAiConfig | None = None,
        client: GeminiAiClient | VllmAiClient | None = None,
        prompt_builder: PromptBuilder | None = None,
        validator: AiResponseValidator | None = None,
        fallback: FallbackNarrativeGenerator | None = None,
    ):
        self._cfg = config or get_config()
        self._client = client
        self._prompt = prompt_builder or PromptBuilder()
        self._validator = validator or AiResponseValidator(self._cfg)
        self._fallback = fallback or FallbackNarrativeGenerator()

    def _build_default_client(self, ai_model: str | None = None) -> GeminiAiClient | VllmAiClient:
        if normalize_ai_model(ai_model) == "GEMMA":
            return VllmAiClient(self._cfg.vllm)
        return GeminiAiClient(self._cfg.gemini)

    def _active_model_name(self, ai_model: str | None = None) -> str:
        return self._cfg.vllm.model if normalize_ai_model(ai_model) == "GEMMA" else self._cfg.gemini.model

    # ──────────────────────────────────────────────
    # 1. /risk-forecast
    # ──────────────────────────────────────────────

    def generate_forecast_narrative(
        self,
        request: AiNarrativeRequest,
        ai_model: str | None = None,
    ) -> AiNarrativeResponse:
        """Umumiy forecast uchun AI narrative."""
        if not self._cfg.ai_enabled:
            logger.debug("AI o'chirilgan — forecast fallback qaytarilmoqda")
            return self._fallback.generate_forecast_fallback(request)

        try:
            prompt = self._prompt.build_forecast_prompt(request)
            client = self._client or self._build_default_client(ai_model)
            raw = client.generate(prompt)

            # ✅ Gemini javob uzunligini log qilamiz — truncation diagnostikasi uchun
            logger.debug(
                "AI forecast javobi: %d belgi [lang=%s, score=%d]",
                len(raw),
                request.language,
                request.period_risk.risk_score,
            )

            result = self._validator.validate_and_parse(raw, request.language)
            result.model = self._active_model_name(ai_model)
            logger.info(
                "Forecast AI narrative muvaffaqiyatli yaratildi [lang=%s, score=%d]",
                request.language,
                request.period_risk.risk_score,
            )
            return result

        except (GeminiAiClientError, VllmAiClientError, AiResponseValidationError) as exc:
            logger.warning("Forecast AI xatolik — fallback: %s", exc)
            return self._fallback.generate_forecast_fallback(request, ai_error=str(exc))

        except Exception:
            logger.exception("Forecast AI kutilmagan xatolik")
            return self._fallback.generate_forecast_fallback(
                request, ai_error="Kutilmagan xatolik"
            )

    # ──────────────────────────────────────────────
    # 2. /risk-forecast/days/{date}
    # ──────────────────────────────────────────────

    def generate_day_narrative(
        self,
        request: DayDetailAiRequest,
        ai_model: str | None = None,
    ) -> AiNarrativeResponse:
        """Bitta kun uchun AI narrative."""
        if not self._cfg.ai_enabled:
            logger.debug("AI o'chirilgan — day fallback qaytarilmoqda")
            return self._fallback.generate_day_fallback(request)

        try:
            prompt = self._prompt.build_day_detail_prompt(request)
            client = self._client or self._build_default_client(ai_model)
            raw = client.generate(prompt)

            logger.debug(
                "AI day javobi: %d belgi [date=%s, lang=%s]",
                len(raw),
                request.date,
                request.language,
            )

            result = self._validator.validate_and_parse(raw, request.language)
            result.model = self._active_model_name(ai_model)
            logger.info(
                "Day AI narrative muvaffaqiyatli yaratildi [date=%s, lang=%s]",
                request.date,
                request.language,
            )
            return result

        except (GeminiAiClientError, VllmAiClientError, AiResponseValidationError) as exc:
            logger.warning("Day AI xatolik — fallback: %s", exc)
            return self._fallback.generate_day_fallback(request, ai_error=str(exc))

        except Exception:
            logger.exception("Day AI kutilmagan xatolik")
            return self._fallback.generate_day_fallback(
                request, ai_error="Kutilmagan xatolik"
            )

    # ──────────────────────────────────────────────
    # 3. /risk-forecast/explain
    # ──────────────────────────────────────────────

    def generate_explain_narrative(
        self,
        request: ExplainAiRequest,
        ai_model: str | None = None,
    ) -> AiNarrativeResponse:
        """Risk driver tushuntirishi uchun AI narrative."""
        if not self._cfg.ai_enabled:
            logger.debug("AI o'chirilgan — explain fallback qaytarilmoqda")
            return self._fallback.generate_explain_fallback(request)

        try:
            prompt = self._prompt.build_explain_prompt(request)
            client = self._client or self._build_default_client(ai_model)
            raw = client.generate(prompt)

            logger.debug(
                "AI explain javobi: %d belgi [driver=%s, lang=%s]",
                len(raw),
                request.risk_driver_id,
                request.language,
            )

            result = self._validator.validate_and_parse(raw, request.language)
            result.model = self._active_model_name(ai_model)
            logger.info(
                "Explain AI narrative yaratildi [driver=%s, lang=%s]",
                request.risk_driver_id,
                request.language,
            )
            return result

        except (GeminiAiClientError, VllmAiClientError, AiResponseValidationError) as exc:
            logger.warning("Explain AI xatolik — fallback: %s", exc)
            return self._fallback.generate_explain_fallback(request, ai_error=str(exc))

        except Exception:
            logger.exception("Explain AI kutilmagan xatolik")
            return self._fallback.generate_explain_fallback(
                request, ai_error="Kutilmagan xatolik"
            )