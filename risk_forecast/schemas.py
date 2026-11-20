"""
Payment Calendar Risk Forecast — AI DTO schemas
Barcha request/response modellari shu yerda.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class RiskDriverType(str, Enum):
    PAYMENT_CONCENTRATION = "PAYMENT_CONCENTRATION"
    OVERDUE_PRESSURE = "OVERDUE_PRESSURE"
    APPROVAL_BOTTLENECK = "APPROVAL_BOTTLENECK"
    BUDGET_LIMIT_STRESS = "BUDGET_LIMIT_STRESS"
    CURRENCY_EXPOSURE = "CURRENCY_EXPOSURE"
    DEBT_SERVICE_STRESS = "DEBT_SERVICE_STRESS"
    COUNTERPARTY_CONCENTRATION = "COUNTERPARTY_CONCENTRATION"
    DATA_QUALITY = "DATA_QUALITY"


class Language(str, Enum):
    EN = "en"
    RU = "ru"
    UZ = "uz"


class ActionPriority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


# ──────────────────────────────────────────────
# AI Request DTOs  (backend → Gemini)
# ──────────────────────────────────────────────

@dataclass
class AiRequestScope:
    from_date: str          # "2026-03-01"
    to_date: str            # "2026-03-31"
    base_currency_code: str  # "UZS"


@dataclass
class AiRequestPeriodRisk:
    risk_score: int
    risk_level: str
    total_amount_base: str
    foreign_currency_share_pct: str
    debt_service_share_pct: str
    overdue_amount_base: Optional[str] = None
    approval_pending_due_soon_amount_base: Optional[str] = None
    payment_count: int = 0


@dataclass
class AiRequestDriver:
    type: str
    severity: str
    amount_base: str
    count: int
    description: str


@dataclass
class AiNarrativeRequest:
    schema_version: str
    language: str
    scope: AiRequestScope
    period_risk: AiRequestPeriodRisk
    top_drivers: list[AiRequestDriver]
    data_limitations: list[str]
    rules: list[str]


# ──────────────────────────────────────────────
# AI Response DTOs  (Gemini → backend)
# ──────────────────────────────────────────────

@dataclass
class RecommendedAction:
    priority: str
    action: str
    rationale: str


@dataclass
class AiNarrativeResponse:
    schema_version: str
    summary: str
    key_drivers: list[str]
    recommended_actions: list[RecommendedAction]
    limitations: list[str]
    generated: bool = True
    model: str = ""
    language: str = "en"


# ──────────────────────────────────────────────
# Day-detail & Explain variants
# ──────────────────────────────────────────────

@dataclass
class DayDetailAiRequest:
    schema_version: str
    language: str
    date: str
    base_currency_code: str
    risk_score: int
    risk_level: str
    total_amount_base: str
    source_breakdown: list[dict]
    top_drivers: list[AiRequestDriver]
    rules: list[str]


@dataclass
class ExplainAiRequest:
    schema_version: str
    language: str
    scope: AiRequestScope
    risk_driver_id: Optional[str]
    driver: Optional[AiRequestDriver]
    context_drivers: list[AiRequestDriver]
    rules: list[str]
