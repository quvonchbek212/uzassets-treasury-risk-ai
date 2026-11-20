"""
Payment Calendar Risk Forecast — Deterministic Fallback Narrative
AI o'chirilgan yoki ishlamagan paytda ishlatiladi.
"""

from __future__ import annotations

from risk_forecast.schemas import (
    AiNarrativeRequest,
    AiNarrativeResponse,
    DayDetailAiRequest,
    ExplainAiRequest,
    RecommendedAction,
)

# ──────────────────────────────────────────────
# Translations
# ──────────────────────────────────────────────

_LABELS: dict[str, dict[str, str]] = {
    "summary_prefix": {
        "en": "Risk forecast summary (automated):",
        "ru": "Сводка по рискам (автоматическая):",
        "uz": "Risk prognoz xulosasi (avtomatik):",
    },
    "no_drivers": {
        "en": "No significant risk drivers identified for the selected period.",
        "ru": "Значимые факторы риска не выявлены.",
        "uz": "Tanlangan davr uchun muhim risk omillari aniqlanmadi.",
    },
    "ai_unavailable": {
        "en": "AI narrative is unavailable. Showing deterministic summary.",
        "ru": "AI нарратив недоступен. Показывается детерминированный итог.",
        "uz": "AI tavsifi mavjud emas. Deterministik xulosa ko'rsatilmoqda.",
    },
    "PAYMENT_CONCENTRATION": {
        "en": "High payment concentration detected — multiple large outflows cluster in a short period.",
        "ru": "Высокая концентрация платежей — крупные выплаты сгруппированы в короткий период.",
        "uz": "Yuqori to'lov kontsentratsiyasi — bir nechta katta chiqimlar qisqa vaqtga to'plangan.",
    },
    "OVERDUE_PRESSURE": {
        "en": "Overdue payment pressure exists — some obligations are past their due date.",
        "ru": "Давление просроченных платежей — часть обязательств просрочена.",
        "uz": "Muddati o'tgan to'lovlar mavjud — bir qism majburiyatlar muddatini o'tkazib yuborgan.",
    },
    "APPROVAL_BOTTLENECK": {
        "en": "Approval bottleneck detected — payments due soon are still pending approval.",
        "ru": "Узкое место согласования — платежи, которые скоро наступят, ещё не утверждены.",
        "uz": "Tasdiqlash to'siqlar aniqlandi — yaqin muddatli to'lovlar hali tasdiqlanmagan.",
    },
    "BUDGET_LIMIT_STRESS": {
        "en": "Budget-limit stress detected — available balances may be insufficient for upcoming payments.",
        "ru": "Стресс лимита бюджета — доступных остатков может не хватить.",
        "uz": "Byudjet limiti stressi — mavjud balanslar yetarli bo'lmasligi mumkin.",
    },
    "CURRENCY_EXPOSURE": {
        "en": "Significant foreign-currency exposure — a large share of outflows is in foreign currency.",
        "ru": "Значительный валютный риск — большая доля выплат в иностранной валюте.",
        "uz": "Muhim valyuta ta'siri — chiqimlarning katta qismi xorijiy valyutada.",
    },
    "DEBT_SERVICE_STRESS": {
        "en": "Debt service stress — debt repayments dominate forecast outflows.",
        "ru": "Долговая нагрузка — погашение долга доминирует в прогнозных выплатах.",
        "uz": "Qarz xizmati stressi — qarzni to'lash prognoz chiqimlarida ustunlik qilmoqda.",
    },
    "COUNTERPARTY_CONCENTRATION": {
        "en": "Counterparty concentration — a single counterparty receives a large share of outflows.",
        "ru": "Концентрация контрагента — один контрагент получает большую долю выплат.",
        "uz": "Kontragent kontsentratsiyasi — bitta kontragent chiqimlarning katta qismini olmoqda.",
    },
    "DATA_QUALITY": {
        "en": "Data quality issues detected — some source rows have missing or invalid fields.",
        "ru": "Проблемы качества данных — в некоторых строках источника отсутствуют или неверные поля.",
        "uz": "Ma'lumotlar sifati muammolari — ba'zi manba qatorlarida yo'q yoki noto'g'ri maydonlar.",
    },
}

_ACTIONS: dict[str, dict[str, dict]] = {
    "APPROVAL_BOTTLENECK": {
        "en": RecommendedAction(
            priority="HIGH",
            action="Review approval queue for payments due within 7 days.",
            rationale="Pending approvals may delay payment execution.",
        ),
        "ru": RecommendedAction(
            priority="HIGH",
            action="Проверьте очередь согласования для платежей, которые наступят в течение 7 дней.",
            rationale="Незавершённые согласования могут задержать исполнение платежей.",
        ),
        "uz": RecommendedAction(
            priority="HIGH",
            action="7 kun ichida muddati keluvchi to'lovlar uchun tasdiqlash navbatini ko'rib chiqing.",
            rationale="Kutilayotgan tasdiqlashlar to'lovni kechiktirishga olib kelishi mumkin.",
        ),
    },
    "CURRENCY_EXPOSURE": {
        "en": RecommendedAction(
            priority="MEDIUM",
            action="Verify FX availability for foreign-currency obligations.",
            rationale="Missing FX rates may prevent timely conversion and payment.",
        ),
        "ru": RecommendedAction(
            priority="MEDIUM",
            action="Проверьте наличие валютной ликвидности для обязательств в иностранной валюте.",
            rationale="Отсутствие курсов валют может помешать своевременной конвертации.",
        ),
        "uz": RecommendedAction(
            priority="MEDIUM",
            action="Xorijiy valyutadagi majburiyatlar uchun valyuta mavjudligini tekshiring.",
            rationale="Valyuta kurslari yo'qligi o'z vaqtida konvertatsiyani to'sishi mumkin.",
        ),
    },
    "DEBT_SERVICE_STRESS": {
        "en": RecommendedAction(
            priority="HIGH",
            action="Review debt service dates before approving discretionary supplier payments.",
            rationale="Debt service is fixed; supplier payments may be sequenced to avoid overlap.",
        ),
        "ru": RecommendedAction(
            priority="HIGH",
            action="Проверьте даты обслуживания долга перед утверждением дискреционных платежей.",
            rationale="Долговые выплаты фиксированы; дискреционные платежи можно упорядочить.",
        ),
        "uz": RecommendedAction(
            priority="HIGH",
            action="Ixtiyoriy etkazib beruvchi to'lovlarini tasdiqlashdan oldin qarz xizmati sanalarini ko'rib chiqing.",
            rationale="Qarz to'lovlari belgilangan; boshqa to'lovlar tartiblantirilishi mumkin.",
        ),
    },
    "BUDGET_LIMIT_STRESS": {
        "en": RecommendedAction(
            priority="HIGH",
            action="Review budget limit balances and initiate limit transfers if needed.",
            rationale="Projected payments may exceed available limit balances.",
        ),
        "ru": RecommendedAction(
            priority="HIGH",
            action="Проверьте балансы лимитов и инициируйте перенос при необходимости.",
            rationale="Прогнозируемые платежи могут превысить доступные остатки лимита.",
        ),
        "uz": RecommendedAction(
            priority="HIGH",
            action="Byudjet limit balanslarini tekshiring va kerak bo'lsa limit o'tkazmalarini boshlang.",
            rationale="Rejalashtirilgan to'lovlar mavjud limit balansdan oshib ketishi mumkin.",
        ),
    },
}


def _t(key: str, lang: str) -> str:
    """Tarjima yordamchi funksiyasi."""
    return _LABELS.get(key, {}).get(lang) or _LABELS.get(key, {}).get("en", key)


# ──────────────────────────────────────────────
# Main Fallback Generator
# ──────────────────────────────────────────────

class FallbackNarrativeGenerator:
    """
    AI o'chirilgan yoki xatolik bergan paytda
    deterministik xulosa yaratadi.
    """

    def generate_forecast_fallback(
        self,
        request: AiNarrativeRequest,
        ai_error: str | None = None,
    ) -> AiNarrativeResponse:
        lang = request.language
        drivers = request.top_drivers

        # Xulosa
        if not drivers:
            summary = _t("no_drivers", lang)
        else:
            prefix = _t("summary_prefix", lang)
            score = request.period_risk.risk_score
            level = request.period_risk.risk_level
            summary = f"{prefix} {level} ({score}/100). "
            summary += "; ".join(
                _t(d.type, lang) for d in drivers[:3]
            )

        # Key drivers
        key_drivers = [_t(d.type, lang) for d in drivers[:5]]

        # Actions — driver type bo'yicha oldindan belgilangan
        actions: list[RecommendedAction] = []
        seen_types: set[str] = set()
        for d in drivers:
            if d.type in _ACTIONS and d.type not in seen_types:
                action = _ACTIONS[d.type].get(lang) or _ACTIONS[d.type].get("en")
                if action:
                    actions.append(action)
                    seen_types.add(d.type)

        # Limitations
        limitations = list(request.data_limitations[:3])
        if ai_error:
            limitations.append(_t("ai_unavailable", lang))

        return AiNarrativeResponse(
            schema_version="payment-calendar-risk-ai-response.v1",
            summary=summary,
            key_drivers=key_drivers,
            recommended_actions=actions,
            limitations=limitations,
            generated=False,
            model="fallback",
            language=lang,
        )

    def generate_day_fallback(
        self,
        request: DayDetailAiRequest,
        ai_error: str | None = None,
    ) -> AiNarrativeResponse:
        lang = request.language
        drivers = request.top_drivers

        summary_prefix = _t("summary_prefix", lang)
        summary = (
            f"{summary_prefix} {request.date} — "
            f"{request.risk_level} ({request.risk_score}/100)."
        )

        key_drivers = [_t(d.type, lang) for d in drivers[:5]]
        actions = self._actions_for_drivers(drivers, lang)
        limitations: list[str] = []
        if ai_error:
            limitations.append(_t("ai_unavailable", lang))

        return AiNarrativeResponse(
            schema_version="payment-calendar-risk-ai-response.v1",
            summary=summary,
            key_drivers=key_drivers,
            recommended_actions=actions,
            limitations=limitations,
            generated=False,
            model="fallback",
            language=lang,
        )

    def generate_explain_fallback(
        self,
        request: ExplainAiRequest,
        ai_error: str | None = None,
    ) -> AiNarrativeResponse:
        lang = request.language
        driver = request.driver

        if driver:
            summary = _t(driver.type, lang)
        else:
            summary = _t("no_drivers", lang)

        actions = self._actions_for_drivers(
            [driver] if driver else [], lang
        )
        limitations: list[str] = []
        if ai_error:
            limitations.append(_t("ai_unavailable", lang))

        return AiNarrativeResponse(
            schema_version="payment-calendar-risk-ai-response.v1",
            summary=summary,
            key_drivers=[summary] if summary else [],
            recommended_actions=actions,
            limitations=limitations,
            generated=False,
            model="fallback",
            language=lang,
        )

    # ── Helpers ───────────────────────────────

    @staticmethod
    def _actions_for_drivers(drivers, lang: str) -> list[RecommendedAction]:
        actions: list[RecommendedAction] = []
        seen: set[str] = set()
        for d in drivers:
            if d.type in _ACTIONS and d.type not in seen:
                action = _ACTIONS[d.type].get(lang) or _ACTIONS[d.type].get("en")
                if action:
                    actions.append(action)
                    seen.add(d.type)
        return actions
