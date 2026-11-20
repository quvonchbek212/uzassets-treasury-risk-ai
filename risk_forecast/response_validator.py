"""
Payment Calendar Risk Forecast — AI Javob Validatori
"""

from __future__ import annotations

import logging
import json
import re
from typing import Any

from risk_forecast.settings import RiskForecastAiConfig, get_config
from risk_forecast.schemas import AiNarrativeResponse, RecommendedAction

logger = logging.getLogger(__name__)

DEFAULT_LIMITATIONS_BY_LANGUAGE = {
    "en": "AI analysis is based only on available payment-calendar data; off-system obligations are not included.",
    "ru": "AI-анализ основан только на доступных данных платежного календаря; внеcистемные обязательства не учтены.",
    "uz": "AI tahlili faqat mavjud to'lov kalendari ma'lumotlariga asoslangan; tizimdan tashqari majburiyatlar hisobga olinmagan.",
}

FORBIDDEN_PHRASES = [
    "i have updated",
    "i have changed",
    "i have approved",
    "i have rejected",
    "i have created",
    "i have scheduled",
    "payment has been moved",
    "i transferred",
    "was rescheduled",
    "limit was increased",
]


class AiResponseValidationError(Exception):
    pass


class AiResponseValidator:

    def __init__(self, config: RiskForecastAiConfig | None = None):
        self._cfg = config or get_config()

    def validate_and_parse(self, raw_text: str, expected_language: str) -> AiNarrativeResponse:
        data = self._parse_json(raw_text)
        data = self._normalize_payload(data, expected_language)
        self._check_schema_and_language(data, expected_language)
        self._check_required_fields(data)
        self._check_bounds(data)
        self._check_forbidden_phrases(data)
        return self._build_response(data, expected_language)

    # ── Private ───────────────────────────────

    @staticmethod
    def _parse_json(raw_text: str) -> dict:
        """
        Truncated, markdown fence, trailing comma va boshqa
        muammolarni tozalab JSON parse qiladi.

        Strategiya (tartibda):
          1. To'g'ridan-to'g'ri parse
          2. Markdown fence tozalab parse
          3. Trailing comma tozalab parse
          4. Kesilgan JSON ni tiklash (truncation recovery)
          5. Birinchi { ... } blokni regex bilan ajratib parse
        """
        if not raw_text or not raw_text.strip():
            raise AiResponseValidationError("AI javobi bo'sh")

        cleaned = raw_text.strip()

        # 1. To'g'ridan-to'g'ri urinish
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 2. Markdown code fence tozalash
        cleaned = re.sub(r"^```(?:json)?\s*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```\s*$", "", cleaned)
        cleaned = cleaned.strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

        # 3. Trailing comma tozalash
        no_trailing = re.sub(r",\s*([}\]])", r"\1", cleaned)
        try:
            return json.loads(no_trailing)
        except json.JSONDecodeError:
            pass

        # 4. Truncation recovery — kesilgan JSON ni tiklash
        #    Gemini max_output_tokens limitiga yetganda javob o'rtada kesiladi.
        #    Ochilgan lekin yopilmagan braces/brackets ni yopamiz.
        recovered = _recover_truncated_json(no_trailing)
        if recovered:
            try:
                return json.loads(recovered)
            except json.JSONDecodeError:
                pass

        # 5. Birinchi { ... } blokni ajratib olish
        match = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if match:
            candidate = re.sub(r",\s*([}\]])", r"\1", match.group())
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

        logger.error("JSON parse xatosi. Raw text (birinchi 500 belgi): %s", raw_text[:500])
        raise AiResponseValidationError(
            f"JSON parse xatosi: barcha urinishlar muvaffaqiyatsiz. "
            f"Raw preview: {raw_text[:200]!r}"
        )

    def _normalize_payload(self, data: dict[str, Any], expected_language: str) -> dict[str, Any]:
        normalized = dict(data)
        self._copy_first_present(normalized, "schemaVersion", ("schema_version", "schema", "version"))
        self._copy_first_present(normalized, "language", ("lang", "til", "locale"))
        self._copy_first_present(
            normalized,
            "summary",
            ("summary_text", "executiveSummary", "executive_summary", "xulosa", "umumiy_xulosa"),
        )
        self._copy_first_present(
            normalized,
            "keyDrivers",
            (
                "key_drivers",
                "drivers",
                "riskDrivers",
                "risk_drivers",
                "topDrivers",
                "top_drivers",
                "asosiyOmillar",
                "asosiy_omillar",
                "riskOmillari",
                "risk_omillari",
                "omillar",
            ),
        )
        self._copy_first_present(
            normalized,
            "recommendedActions",
            (
                "recommended_actions",
                "recommendations",
                "actions",
                "actionItems",
                "action_items",
                "tavsiyalar",
                "tavsiyaEtilganHarakatlar",
                "tavsiya_etilgan_harakatlar",
            ),
        )
        self._copy_first_present(
            normalized,
            "limitations",
            (
                "dataLimitations",
                "data_limitations",
                "limits",
                "dataGaps",
                "data_gaps",
                "cheklovlar",
                "limitlar",
            ),
        )

        if isinstance(normalized.get("keyDrivers"), str):
            normalized["keyDrivers"] = [normalized["keyDrivers"]]
        if isinstance(normalized.get("limitations"), str):
            normalized["limitations"] = [normalized["limitations"]]
        if "recommendedActions" in normalized:
            normalized["recommendedActions"] = self._normalize_actions(normalized["recommendedActions"])

        if isinstance(normalized.get("summary"), str) and normalized["summary"].strip():
            normalized.setdefault("keyDrivers", [])
            normalized.setdefault("recommendedActions", [])
            normalized.setdefault(
                "limitations",
                [DEFAULT_LIMITATIONS_BY_LANGUAGE.get(expected_language, DEFAULT_LIMITATIONS_BY_LANGUAGE["en"])],
            )

        return normalized

    @staticmethod
    def _copy_first_present(target: dict[str, Any], canonical_key: str, aliases: tuple[str, ...]) -> None:
        if canonical_key in target:
            return
        for alias in aliases:
            if alias in target:
                target[canonical_key] = target[alias]
                return

    @staticmethod
    def _normalize_actions(raw_actions: Any) -> list[dict[str, str]]:
        if raw_actions is None:
            return []
        if isinstance(raw_actions, str):
            raw_actions = [raw_actions]
        if not isinstance(raw_actions, list):
            return []

        actions: list[dict[str, str]] = []
        for item in raw_actions:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    actions.append(
                        {
                            "priority": "MEDIUM",
                            "action": text,
                            "rationale": "Recommended based on the AI risk narrative.",
                        }
                    )
                continue
            if not isinstance(item, dict):
                continue
            priority = str(item.get("priority") or item.get("severity") or "MEDIUM").upper()
            if priority not in {"HIGH", "MEDIUM", "LOW"}:
                priority = "MEDIUM"
            action = str(
                item.get("action")
                or item.get("recommendation")
                or item.get("title")
                or item.get("text")
                or item.get("tavsiya")
                or ""
            ).strip()
            rationale = str(
                item.get("rationale")
                or item.get("reason")
                or item.get("explanation")
                or item.get("asos")
                or ""
            ).strip()
            if action:
                actions.append(
                    {
                        "priority": priority,
                        "action": action,
                        "rationale": rationale or "Recommended based on the AI risk narrative.",
                    }
                )
        return actions

    def _check_schema_and_language(self, data: dict, expected_language: str) -> None:
        schema_version = data.get("schemaVersion")
        if schema_version != self._cfg.schema_version_response:
            raise AiResponseValidationError(
                f"schemaVersion '{schema_version}' kutilgan '{self._cfg.schema_version_response}' ga teng emas"
            )

        language = data.get("language")
        if language is not None and language != expected_language:
            raise AiResponseValidationError(
                f"Til '{language}' kutilgan '{expected_language}' ga teng emas"
            )

    @staticmethod
    def _check_required_fields(data: dict) -> None:
        required = ["summary", "keyDrivers", "recommendedActions", "limitations"]
        missing = [f for f in required if f not in data]
        if missing:
            raise AiResponseValidationError(f"Majburiy maydonlar yo'q: {missing}")

        if not isinstance(data["keyDrivers"], list):
            raise AiResponseValidationError("keyDrivers list bo'lishi kerak")
        if not isinstance(data["recommendedActions"], list):
            raise AiResponseValidationError("recommendedActions list bo'lishi kerak")
        if not isinstance(data["limitations"], list):
            raise AiResponseValidationError("limitations list bo'lishi kerak")
        if not isinstance(data["summary"], str) or not data["summary"].strip():
            raise AiResponseValidationError("summary bo'sh bo'lmasligi kerak")

    def _check_bounds(self, data: dict) -> None:
        if len(data["keyDrivers"]) > self._cfg.max_key_drivers:
            raise AiResponseValidationError(
                f"keyDrivers soni {self._cfg.max_key_drivers} dan oshib ketdi"
            )
        if len(data["recommendedActions"]) > self._cfg.max_recommended_actions:
            raise AiResponseValidationError(
                f"recommendedActions soni {self._cfg.max_recommended_actions} dan oshib ketdi"
            )
        if len(data["limitations"]) > self._cfg.max_limitations:
            raise AiResponseValidationError(
                f"limitations soni {self._cfg.max_limitations} dan oshib ketdi"
            )
        if len(data["summary"]) > self._cfg.max_summary_chars:
            raise AiResponseValidationError(
                f"summary {self._cfg.max_summary_chars} belgidan uzun"
            )

        for action in data["recommendedActions"]:
            if not isinstance(action, dict):
                raise AiResponseValidationError(
                    "recommendedActions elementlari dict bo'lishi kerak"
                )
            for key in ("priority", "action", "rationale"):
                if key not in action:
                    raise AiResponseValidationError(
                        f"recommendedAction maydonida '{key}' yo'q"
                    )

    @staticmethod
    def _check_forbidden_phrases(data: dict) -> None:
        full_text = json.dumps(data, ensure_ascii=False).lower()
        for phrase in FORBIDDEN_PHRASES:
            if phrase in full_text:
                raise AiResponseValidationError(
                    f"Taqiqlangan ibora topildi: '{phrase}'"
                )

    @staticmethod
    def _build_response(data: dict, expected_language: str) -> AiNarrativeResponse:
        actions = [
            RecommendedAction(
                priority=a.get("priority", "MEDIUM"),
                action=a.get("action", ""),
                rationale=a.get("rationale", ""),
            )
            for a in data.get("recommendedActions", [])
        ]
        return AiNarrativeResponse(
            schema_version=data.get(
                "schemaVersion", "payment-calendar-risk-ai-response.v1"
            ),
            summary=data["summary"],
            key_drivers=data.get("keyDrivers", []),
            recommended_actions=actions,
            limitations=data.get("limitations", []),
            generated=True,
            language=data.get("language", expected_language),
        )


# ── Yordamchi funksiya ────────────────────────────────────────────────────────

def _recover_truncated_json(text: str) -> str | None:
    """
    Kesilgan (truncated) JSON ni tiklashga harakat qiladi.

    Gemini max_output_tokens ga yetganda javob o'rtada kesiladi:
      {"summary": "...", "language": "uz   ← shu yerda kesilgan

    Bu funksiya:
      - Ochiq string ni yopadi ("  →  "")
      - Yopilmagan { va [ larni qarama-qarshi tartibda yopadi
      - Natijani qaytaradi (muvaffaqiyatsiz bo'lsa None)
    """
    if not text:
        return None

    result = text.rstrip()

    # Kesilgan string ichida qolgan bo'lsa — yopamiz
    # Juft bo'lmagan qo'shtirnoqlarni topish
    in_string = False
    escape_next = False
    for ch in result:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string

    if in_string:
        result += '"'

    # Yopilmagan trailing comma ni olib tashlash
    result = re.sub(r",\s*$", "", result.rstrip())

    # Stack orqali ochiq braces/brackets ni topib yopamiz
    stack = []
    in_string = False
    escape_next = False
    for ch in result:
        if escape_next:
            escape_next = False
            continue
        if ch == "\\":
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if not in_string:
            if ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()

    # Teskari tartibda yopamiz
    closing = {"[": "]", "{": "}"}
    for opener in reversed(stack):
        result += closing[opener]

    return result if result != text.rstrip() else None
