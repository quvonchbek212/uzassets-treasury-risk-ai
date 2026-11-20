"""
Payment Calendar Risk Forecast — AI qism testlari
Barcha komponentlar uchun unit testlar.
"""

from __future__ import annotations

import json
import unittest
from unittest.mock import MagicMock, patch

from risk_forecast.gemini_client import CircuitBreaker, CircuitState, GeminiAiClientError
from risk_forecast.settings import GeminiConfig, RiskForecastAiConfig
from risk_forecast.schemas import (
    AiNarrativeRequest,
    AiRequestDriver,
    AiRequestPeriodRisk,
    AiRequestScope,
    DayDetailAiRequest,
    ExplainAiRequest,
)
from risk_forecast.narrative_fallback import FallbackNarrativeGenerator
from risk_forecast.narrative_service import PaymentCalendarRiskNarrativeService
from risk_forecast.prompt_builder import PromptBuilder
from risk_forecast.response_validator import AiResponseValidationError, AiResponseValidator


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

def _make_cfg(ai_enabled: bool = True) -> RiskForecastAiConfig:
    cfg = RiskForecastAiConfig()
    cfg.ai_enabled = ai_enabled
    cfg.gemini = GeminiConfig(
        model="gemini-3-flash-preview",
        api_key="test-key",
        timeout_seconds=5,
        max_retries=1,
    )
    return cfg


def _make_forecast_request(lang: str = "en") -> AiNarrativeRequest:
    return AiNarrativeRequest(
        schema_version="payment-calendar-risk-ai-request.v1",
        language=lang,
        scope=AiRequestScope(from_date="2026-03-01", to_date="2026-03-31", base_currency_code="UZS"),
        period_risk=AiRequestPeriodRisk(
            risk_score=82,
            risk_level="HIGH",
            total_amount_base="42800000000.00",
            foreign_currency_share_pct="40.89",
            debt_service_share_pct="42.99",
            payment_count=64,
        ),
        top_drivers=[
            AiRequestDriver(
                type="DEBT_SERVICE_STRESS",
                severity="HIGH",
                amount_base="18400000000.00",
                count=5,
                description="Debt service 43% of outflow.",
            ),
            AiRequestDriver(
                type="APPROVAL_BOTTLENECK",
                severity="MEDIUM",
                amount_base="6100000000.00",
                count=6,
                description="6 payments pending approval.",
            ),
        ],
        data_limitations=["Budget limit coverage partial."],
        rules=[],
    )


def _make_valid_ai_response(lang: str = "en") -> str:
    return json.dumps({
        "schemaVersion": "payment-calendar-risk-ai-response.v1",
        "language": lang,
        "summary": "March has high payment pressure driven by debt service.",
        "keyDrivers": [
            "Debt service accounts for 43% of forecast outflow.",
            "6 payments are pending approval.",
        ],
        "recommendedActions": [
            {
                "priority": "HIGH",
                "action": "Review approval queue for payments due within 7 days.",
                "rationale": "Pending approvals may delay payment execution.",
            }
        ],
        "limitations": ["Budget-limit coverage is partial."],
    })


# ──────────────────────────────────────────────
# 1. Circuit Breaker testlari
# ──────────────────────────────────────────────

class TestCircuitBreaker(unittest.TestCase):

    def test_initial_state_is_closed(self):
        cb = CircuitBreaker(failure_threshold=3, recovery_timeout_seconds=60)
        self.assertEqual(cb.state, CircuitState.CLOSED)
        self.assertFalse(cb.is_open())

    def test_opens_after_threshold_failures(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        self.assertFalse(cb.is_open())
        cb.record_failure()
        self.assertTrue(cb.is_open())

    def test_resets_on_success(self):
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()
        self.assertTrue(cb.is_open())
        cb.record_success()
        self.assertFalse(cb.is_open())
        self.assertEqual(cb.state, CircuitState.CLOSED)

    def test_transitions_to_half_open_after_timeout(self):
        import time
        cb = CircuitBreaker(failure_threshold=1, recovery_timeout_seconds=1)
        cb.record_failure()
        # Hali OPEN bo'lishi kerak
        self.assertTrue(cb._state == CircuitState.OPEN)
        # Timeout o'tgandan keyin HALF_OPEN ga o'tishi kerak
        cb._last_failure_time = time.time() - 2  # 2 soniya oldin bo'lgandek qilamiz
        self.assertEqual(cb.state, CircuitState.HALF_OPEN)


# ──────────────────────────────────────────────
# 2. Validator testlari
# ──────────────────────────────────────────────

class TestAiResponseValidator(unittest.TestCase):

    def setUp(self):
        self.validator = AiResponseValidator(config=_make_cfg())

    def test_valid_response_parsed_correctly(self):
        raw = _make_valid_ai_response("en")
        result = self.validator.validate_and_parse(raw, "en")
        self.assertTrue(result.generated)
        self.assertEqual(result.language, "en")
        self.assertIn("March", result.summary)
        self.assertEqual(len(result.key_drivers), 2)
        self.assertEqual(len(result.recommended_actions), 1)
        self.assertEqual(result.recommended_actions[0].priority, "HIGH")

    def test_wrong_schema_version_raises(self):
        data = json.loads(_make_valid_ai_response())
        data["schemaVersion"] = "wrong-version"
        with self.assertRaises(AiResponseValidationError) as ctx:
            self.validator.validate_and_parse(json.dumps(data), "en")
        self.assertIn("schemaVersion", str(ctx.exception))

    def test_missing_required_field_raises(self):
        data = json.loads(_make_valid_ai_response())
        del data["summary"]
        with self.assertRaises(AiResponseValidationError):
            self.validator.validate_and_parse(json.dumps(data), "en")

    def test_too_many_key_drivers_raises(self):
        data = json.loads(_make_valid_ai_response())
        data["keyDrivers"] = ["d"] * 10
        with self.assertRaises(AiResponseValidationError) as ctx:
            self.validator.validate_and_parse(json.dumps(data), "en")
        self.assertIn("keyDrivers", str(ctx.exception))

    def test_forbidden_phrase_raises(self):
        data = json.loads(_make_valid_ai_response())
        data["summary"] = "I have approved the payments."
        with self.assertRaises(AiResponseValidationError) as ctx:
            self.validator.validate_and_parse(json.dumps(data), "en")
        self.assertIn("Taqiqlangan ibora", str(ctx.exception))

    def test_language_mismatch_raises(self):
        data = json.loads(_make_valid_ai_response())
        data["language"] = "ru"
        with self.assertRaises(AiResponseValidationError) as ctx:
            self.validator.validate_and_parse(json.dumps(data), "en")
        self.assertIn("Til", str(ctx.exception))

    def test_markdown_fenced_json_accepted(self):
        raw = "```json\n" + _make_valid_ai_response() + "\n```"
        result = self.validator.validate_and_parse(raw, "en")
        self.assertIsNotNone(result)

    def test_local_model_snake_case_aliases_are_normalized(self):
        raw = json.dumps({
            "schema_version": "payment-calendar-risk-ai-response.v1",
            "language": "uz",
            "summary": "To'lov kalendarida o'rtacha risk kuzatilmoqda.",
            "key_drivers": ["Qarz xizmati bosimi mavjud."],
            "recommended_actions": ["Yaqin muddatdagi to'lovlarni qayta ko'rib chiqing."],
            "data_limitations": ["Faqat mavjud to'lov ma'lumotlari tahlil qilindi."],
        })
        result = self.validator.validate_and_parse(raw, "uz")
        self.assertEqual(result.language, "uz")
        self.assertEqual(result.key_drivers, ["Qarz xizmati bosimi mavjud."])
        self.assertEqual(result.recommended_actions[0].priority, "MEDIUM")

    def test_local_model_summary_only_gets_safe_empty_lists(self):
        raw = json.dumps({
            "schemaVersion": "payment-calendar-risk-ai-response.v1",
            "language": "uz",
            "summary": "To'lov kalendarida risk mavjud.",
        })
        result = self.validator.validate_and_parse(raw, "uz")
        self.assertEqual(result.key_drivers, [])
        self.assertEqual(result.recommended_actions, [])
        self.assertTrue(result.limitations)

    def test_empty_summary_raises(self):
        data = json.loads(_make_valid_ai_response())
        data["summary"] = "   "
        with self.assertRaises(AiResponseValidationError):
            self.validator.validate_and_parse(json.dumps(data), "en")


# ──────────────────────────────────────────────
# 3. Prompt Builder testlari
# ──────────────────────────────────────────────

class TestPromptBuilder(unittest.TestCase):

    def setUp(self):
        self.builder = PromptBuilder()

    def test_forecast_prompt_contains_risk_score(self):
        req = _make_forecast_request()
        prompt = self.builder.build_forecast_prompt(req)
        self.assertIn("82", prompt)
        self.assertIn("DEBT_SERVICE_STRESS", prompt)
        self.assertIn("Respond in English", prompt)

    def test_forecast_prompt_uz_language(self):
        req = _make_forecast_request(lang="uz")
        prompt = self.builder.build_forecast_prompt(req)
        self.assertIn("O'zbek tilida", prompt)

    def test_day_prompt_contains_date(self):
        req = DayDetailAiRequest(
            schema_version="payment-calendar-risk-ai-request.v1",
            language="ru",
            date="2026-03-12",
            base_currency_code="UZS",
            risk_score=91,
            risk_level="CRITICAL",
            total_amount_base="12400000000.00",
            source_breakdown=[{"sourceType": "DEBT_SCHEDULE", "count": 2}],
            top_drivers=[],
            rules=[],
        )
        prompt = self.builder.build_day_detail_prompt(req)
        self.assertIn("2026-03-12", prompt)
        self.assertIn("91", prompt)
        self.assertIn("русском", prompt)

    def test_explain_prompt_contains_driver(self):
        req = ExplainAiRequest(
            schema_version="payment-calendar-risk-ai-request.v1",
            language="en",
            scope=AiRequestScope("2026-03-01", "2026-03-31", "UZS"),
            risk_driver_id="driver_approval_1",
            driver=AiRequestDriver("APPROVAL_BOTTLENECK", "HIGH", "6100000000", 6, "6 pending."),
            context_drivers=[],
            rules=[],
        )
        prompt = self.builder.build_explain_prompt(req)
        self.assertIn("APPROVAL_BOTTLENECK", prompt)
        self.assertIn("driver_approval_1", prompt)

    def test_prompt_does_not_contain_secrets(self):
        req = _make_forecast_request()
        prompt = self.builder.build_forecast_prompt(req)
        # Token, hash, PKCS7 yo'q
        self.assertNotIn("Bearer", prompt)
        self.assertNotIn("PKCS7", prompt)


# ──────────────────────────────────────────────
# 4. Fallback Generator testlari
# ──────────────────────────────────────────────

class TestFallbackNarrativeGenerator(unittest.TestCase):

    def setUp(self):
        self.gen = FallbackNarrativeGenerator()

    def test_forecast_fallback_generated_false(self):
        req = _make_forecast_request()
        result = self.gen.generate_forecast_fallback(req)
        self.assertFalse(result.generated)
        self.assertEqual(result.model, "fallback")

    def test_forecast_fallback_has_summary(self):
        req = _make_forecast_request()
        result = self.gen.generate_forecast_fallback(req)
        self.assertTrue(len(result.summary) > 0)

    def test_forecast_fallback_uz_language(self):
        req = _make_forecast_request(lang="uz")
        result = self.gen.generate_forecast_fallback(req)
        self.assertIn("uz", result.language)

    def test_fallback_no_drivers_returns_no_risk_message(self):
        req = _make_forecast_request()
        req.top_drivers = []
        result = self.gen.generate_forecast_fallback(req)
        self.assertTrue(len(result.summary) > 0)
        self.assertEqual(result.key_drivers, [])

    def test_fallback_includes_ai_error_in_limitations(self):
        req = _make_forecast_request()
        result = self.gen.generate_forecast_fallback(req, ai_error="Connection timeout")
        any_ai_limit = any("AI" in lim or "mavjud" in lim or "unavailable" in lim.lower() for lim in result.limitations)
        self.assertTrue(any_ai_limit)

    def test_day_fallback(self):
        req = DayDetailAiRequest(
            schema_version="v1",
            language="en",
            date="2026-03-12",
            base_currency_code="UZS",
            risk_score=91,
            risk_level="CRITICAL",
            total_amount_base="12400000000",
            source_breakdown=[],
            top_drivers=[AiRequestDriver("DEBT_SERVICE_STRESS", "HIGH", "5000000", 2, "desc")],
            rules=[],
        )
        result = self.gen.generate_day_fallback(req)
        self.assertFalse(result.generated)
        self.assertIn("2026-03-12", result.summary)


# ──────────────────────────────────────────────
# 5. Narrative Service testlari
# ──────────────────────────────────────────────

class TestNarrativeService(unittest.TestCase):

    def _make_service(self, ai_enabled=True, client_response=None, client_raises=None):
        cfg = _make_cfg(ai_enabled=ai_enabled)

        mock_client = MagicMock()
        if client_raises:
            mock_client.generate.side_effect = client_raises
        elif client_response:
            mock_client.generate.return_value = client_response

        return PaymentCalendarRiskNarrativeService(
            config=cfg,
            client=mock_client,
        )

    def test_ai_disabled_returns_fallback(self):
        service = self._make_service(ai_enabled=False)
        req = _make_forecast_request()
        result = service.generate_forecast_narrative(req)
        self.assertFalse(result.generated)
        self.assertEqual(result.model, "fallback")

    def test_ai_enabled_valid_response_returned(self):
        service = self._make_service(client_response=_make_valid_ai_response("en"))
        req = _make_forecast_request()
        result = service.generate_forecast_narrative(req)
        self.assertTrue(result.generated)
        self.assertIn("March", result.summary)
        self.assertEqual(result.model, "gemini-3-flash-preview")

    def test_gemini_error_returns_fallback(self):
        service = self._make_service(client_raises=GeminiAiClientError("timeout"))
        req = _make_forecast_request()
        result = service.generate_forecast_narrative(req)
        self.assertFalse(result.generated)
        self.assertEqual(result.model, "fallback")

    def test_invalid_ai_response_returns_fallback(self):
        service = self._make_service(client_response='{"invalid": true}')
        req = _make_forecast_request()
        result = service.generate_forecast_narrative(req)
        self.assertFalse(result.generated)

    def test_day_narrative_ai_disabled(self):
        service = self._make_service(ai_enabled=False)
        req = DayDetailAiRequest(
            schema_version="v1", language="en", date="2026-03-12",
            base_currency_code="UZS", risk_score=91, risk_level="CRITICAL",
            total_amount_base="12400000000", source_breakdown=[],
            top_drivers=[], rules=[],
        )
        result = service.generate_day_narrative(req)
        self.assertFalse(result.generated)

    def test_explain_narrative_ai_enabled(self):
        service = self._make_service(client_response=_make_valid_ai_response("en"))
        req = ExplainAiRequest(
            schema_version="v1", language="en",
            scope=AiRequestScope("2026-03-01", "2026-03-31", "UZS"),
            risk_driver_id="d1",
            driver=AiRequestDriver("APPROVAL_BOTTLENECK", "HIGH", "6100000000", 6, "desc"),
            context_drivers=[], rules=[],
        )
        result = service.generate_explain_narrative(req)
        self.assertTrue(result.generated)

    def test_circuit_breaker_open_returns_fallback(self):
        service = self._make_service(
            client_raises=GeminiAiClientError("Circuit breaker OPEN")
        )
        req = _make_forecast_request()
        result = service.generate_forecast_narrative(req)
        self.assertFalse(result.generated)


# ──────────────────────────────────────────────
# Run
# ──────────────────────────────────────────────

if __name__ == "__main__":
    unittest.main(verbosity=2)
