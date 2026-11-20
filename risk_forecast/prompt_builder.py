"""
Payment Calendar Risk Forecast — Prompt Builder
Har 3 ta endpoint uchun xavfsiz, sanitize qilingan prompt yaratadi.
AI ga hech qachon maxfiy ma'lumotlar (tokenlar, hash, PKCS7) yuborilmaydi.
"""

from __future__ import annotations

import json

from risk_forecast.schemas import (
    AiNarrativeRequest,
    AiRequestDriver,
    DayDetailAiRequest,
    ExplainAiRequest,
)

# Har 3 ta endpoint uchun umumiy qoidalar
_COMMON_RULES = [
    "Return ONLY valid JSON matching the schema. No markdown, no explanation.",
    "Use exactly these top-level camelCase keys: schemaVersion, language, summary, keyDrivers, recommendedActions, limitations.",
    "Do not translate, rename, omit, or snake_case JSON keys. Translate only text values.",
    "Do not invent source items, amounts, dates, or statuses not present in the input.",
    "Recommendations must be non-binding and operational.",
    "Do not say a payment can be delayed unless source type is not DEBT_SCHEDULE.",
    # ✅ FIX: limitations HAR DOIM qaytarilishi kerakligi aniq ko'rsatildi
    "The 'limitations' field is REQUIRED. Always include at least one limitation string "
    "describing data gaps, coverage constraints, or AI analysis boundaries. "
    "If dataLimitations in input is empty, still include a general AI limitation note.",
    "Do not include internal IDs, token values, or file hashes in the response.",
    "Set schemaVersion to exactly 'payment-calendar-risk-ai-response.v1'.",
]

# Javob schema shabloni — AI uchun
# ✅ FIX: limitations required ekanligi va misol qo'shildi
_RESPONSE_SCHEMA = {
    "schemaVersion": "payment-calendar-risk-ai-response.v1",
    "language": "<requested language code>",
    "summary": "<1-3 sentence executive summary in the requested language>",
    "keyDrivers": ["<driver explanation 1>", "..."],
    "recommendedActions": [
        {
            "priority": "HIGH|MEDIUM|LOW",
            "action": "<operational recommendation>",
            "rationale": "<brief rationale>"
        }
    ],
    # ✅ FIX: empty array RUXSAT ETILMAYDI, kamida 1 ta element bo'lishi kerak
    "limitations": [
        "<REQUIRED: at least one data gap, coverage limitation, or AI analysis boundary. "
        "Example: 'Analysis based on available payment data only; off-system obligations not included.'>"
    ],
}

# ✅ FIX: limitations uchun fallback — input bo'sh bo'lsa ishlatiladi
_DEFAULT_LIMITATION = (
    "AI tahlili faqat tizimga kiritilgan to'lov ma'lumotlari asosida amalga oshirildi; "
    "tizimdan tashqari majburiyatlar hisobga olinmagan."
)


class PromptBuilder:
    """
    Gemini uchun prompt yaratadi.
    3 ta metod: forecast, day_detail, explain.
    """

    # ── 1. /risk-forecast ─────────────────────

    def build_forecast_prompt(self, request: AiNarrativeRequest) -> str:
        # ✅ FIX: dataLimitations bo'sh bo'lsa default qo'shamiz
        data_limitations = list(request.data_limitations or [])
        if not data_limitations:
            data_limitations = [_DEFAULT_LIMITATION]

        payload = {
            "schemaVersion": request.schema_version,
            "language": request.language,
            "scope": {
                "from": request.scope.from_date,
                "to": request.scope.to_date,
                "baseCurrencyCode": request.scope.base_currency_code,
            },
            "periodRisk": {
                "riskScore": request.period_risk.risk_score,
                "riskLevel": request.period_risk.risk_level,
                "totalAmountBase": request.period_risk.total_amount_base,
                "foreignCurrencySharePct": request.period_risk.foreign_currency_share_pct,
                "debtServiceSharePct": request.period_risk.debt_service_share_pct,
                "overdueAmountBase": request.period_risk.overdue_amount_base,
                "approvalPendingDueSoonAmountBase": request.period_risk.approval_pending_due_soon_amount_base,
                "paymentCount": request.period_risk.payment_count,
            },
            "topDrivers": [self._driver_to_dict(d) for d in request.top_drivers],
            "dataLimitations": data_limitations,
            "rules": _COMMON_RULES,
            "responseSchema": _RESPONSE_SCHEMA,
        }
        return self._wrap(payload, request.language)

    # ── 2. /risk-forecast/days/{date} ─────────

    def build_day_detail_prompt(self, request: DayDetailAiRequest) -> str:
        payload = {
            "schemaVersion": request.schema_version,
            "language": request.language,
            "date": request.date,
            "baseCurrencyCode": request.base_currency_code,
            "dayRisk": {
                "riskScore": request.risk_score,
                "riskLevel": request.risk_level,
                "totalAmountBase": request.total_amount_base,
            },
            "sourceBreakdown": request.source_breakdown,
            "topDrivers": [self._driver_to_dict(d) for d in request.top_drivers],
            "rules": _COMMON_RULES,
            "responseSchema": _RESPONSE_SCHEMA,
        }
        return self._wrap(payload, request.language)

    # ── 3. /risk-forecast/explain ─────────────

    def build_explain_prompt(self, request: ExplainAiRequest) -> str:
        payload = {
            "schemaVersion": request.schema_version,
            "language": request.language,
            "scope": {
                "from": request.scope.from_date,
                "to": request.scope.to_date,
                "baseCurrencyCode": request.scope.base_currency_code,
            },
            "riskDriverId": request.risk_driver_id,
            "driver": self._driver_to_dict(request.driver) if request.driver else None,
            "contextDrivers": [self._driver_to_dict(d) for d in request.context_drivers],
            "rules": _COMMON_RULES
            + [
                "Focus the explanation on the single driver if riskDriverId is provided.",
                "If no driver is specified, give a high-level period explanation.",
            ],
            "responseSchema": _RESPONSE_SCHEMA,
        }
        return self._wrap(payload, request.language)

    # ── Helpers ───────────────────────────────

    @staticmethod
    def _driver_to_dict(driver: AiRequestDriver) -> dict:
        return {
            "type": driver.type,
            "severity": driver.severity,
            "amountBase": driver.amount_base,
            "count": driver.count,
            "description": driver.description,
        }

    @staticmethod
    def _wrap(payload: dict, language: str) -> str:
        lang_instruction = {
            "en": "Respond in English.",
            "ru": "Отвечайте на русском языке.",
            "uz": "O'zbek tilida javob bering.",
        }.get(language, "Respond in English.")

        return (
            f"{lang_instruction}\n\n"
            "Input JSON:\n"
            f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
        )
