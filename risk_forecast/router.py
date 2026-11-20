"""
Payment Calendar Risk Forecast — FastAPI Router (AI qismi)
"""

from __future__ import annotations

import logging
import os
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Security
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from risk_forecast.settings import RiskForecastAiConfig, get_config
from risk_forecast.schemas import (
    AiNarrativeRequest,
    AiNarrativeResponse,
    AiRequestDriver,
    AiRequestPeriodRisk,
    AiRequestScope,
    DayDetailAiRequest,
    ExplainAiRequest,
)
from risk_forecast.narrative_service import PaymentCalendarRiskNarrativeService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/treasury/payment-calendar/risk-forecast", tags=["AI Risk Narrative"])

BACKEND_BASE_URL = os.getenv("BACKEND_API_BASE_URL", "https://api.uz-assets.uz/api/v1")

security = HTTPBearer()


# ──────────────────────────────────────────────
# Dependency
# ──────────────────────────────────────────────

def get_narrative_service() -> PaymentCalendarRiskNarrativeService:
    return PaymentCalendarRiskNarrativeService()


def get_ai_config() -> RiskForecastAiConfig:
    return get_config()


# ──────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────

@router.get("/narrative", summary="Forecast AI Narrative", response_model=dict)
async def forecast_narrative(
    request_http: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(security)],
    from_date: Annotated[str, Query(alias="from", description="Boshlanish sanasi (YYYY-MM-DD)")],
    to_date: Annotated[str, Query(alias="to", description="Tugash sanasi (YYYY-MM-DD)")],
    year: Annotated[int | None, Query(description="Yil")] = None,
    month: Annotated[int | None, Query(description="Oy")] = None,
    organization_id: Annotated[int | None, Query(alias="organizationId")] = None,
    organization_ids: Annotated[list[int] | None, Query(alias="organizationIds")] = None,
    base_currency_code: Annotated[str, Query(alias="baseCurrencyCode")] = "UZS",
    horizon_days: Annotated[int | None, Query(alias="horizonDays")] = None,
    granularity: Annotated[str, Query(description="DAY | WEEK | MONTH | AUTO")] = "AUTO",
    include_source_items: Annotated[bool, Query(alias="includeSourceItems")] = False,
    language: Annotated[str, Query()] = "en",
    ai_model: Annotated[str | None, Query(alias="aiModel", description="GEMINI or GEMMA. Defaults to GEMINI.")] = None,
    service: Annotated[PaymentCalendarRiskNarrativeService, Depends(get_narrative_service)] = None,
    cfg: Annotated[RiskForecastAiConfig, Depends(get_ai_config)] = None,
):
    _validate_language(language)
    headers = {"Authorization": f"Bearer {credentials.credentials}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{BACKEND_BASE_URL}/treasury/payment-calendar/risk-forecast",
                params={
                    "from": from_date,
                    "to": to_date,
                    "year": year,
                    "month": month,
                    "organizationId": organization_id,
                    "organizationIds": organization_ids,
                    "baseCurrencyCode": base_currency_code,
                    "horizonDays": horizon_days,
                    "granularity": granularity,
                    "includeSourceItems": include_source_items,
                    "includeAiNarrative": False,
                    "language": language,
                },
                headers=headers,
            )
            if response.status_code == 401:
                raise HTTPException(status_code=401, detail="Token yaroqsiz.")
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Backend ma'lumot bera olmadi.")
            backend_data = response.json()
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Backend xizmati mavjud emas.")

    try:
        scope_data = backend_data.get("scope", {})
        risk_data = backend_data.get("periodRisk", {})        # ✅ camelCase
        drivers_list = backend_data.get("riskDrivers", [])    # ✅ camelCase

        logger.info(f"riskScore: {risk_data.get('riskScore')}, riskDrivers soni: {len(drivers_list)}")

        request = AiNarrativeRequest(
            schema_version=cfg.schema_version_request,
            language=language,
            scope=AiRequestScope(
                from_date=scope_data.get("from", from_date),
                to_date=scope_data.get("to", to_date),
                base_currency_code=scope_data.get("baseCurrencyCode", cfg.base_currency_code),  # ✅
            ),
            period_risk=AiRequestPeriodRisk(
                risk_score=risk_data.get("riskScore", 0),                                        # ✅
                risk_level=risk_data.get("riskLevel", "LOW"),                                    # ✅
                total_amount_base=str(risk_data.get("totalAmountBase", "0")),                    # ✅
                foreign_currency_share_pct=str(risk_data.get("foreignCurrencySharePct", "0")),  # ✅
                debt_service_share_pct=str(risk_data.get("debtServiceSharePct", "0")),          # ✅
                overdue_amount_base=risk_data.get("overdueAmountBase"),                          # ✅
                approval_pending_due_soon_amount_base=risk_data.get("approvalPendingDueSoonAmountBase"),  # ✅
                payment_count=risk_data.get("paymentCount", 0),                                  # ✅
            ),
            top_drivers=[
                AiRequestDriver(
                    type=d.get("type"),
                    severity=d.get("severity"),
                    amount_base=str(d.get("amountBase", "0")),  # ✅
                    count=d.get("count", 0),
                    description=d.get("description", ""),
                ) for d in drivers_list
            ],
            data_limitations=backend_data.get("dataLimitations", []),  # ✅
            rules=[],
        )
    except Exception as exc:
        logger.error(f"Backend JSON formati mos kelmadi: {str(exc)}")
        raise HTTPException(status_code=422, detail="Backend taqdim etgan ma'lumotlar strukturasi mos emas.")

    result = service.generate_forecast_narrative(request, ai_model=ai_model)
    return _narrative_to_dict(result)


@router.get("/days/narrative", summary="Day Detail AI Narrative", response_model=dict)
async def day_narrative(
    request_http: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(security)],
    date: Annotated[str, Query(description="Kun (YYYY-MM-DD)")],
    organization_id: Annotated[int | None, Query(alias="organizationId")] = None,
    organization_ids: Annotated[list[int] | None, Query(alias="organizationIds")] = None,
    base_currency_code: Annotated[str, Query(alias="baseCurrencyCode")] = "UZS",
    language: Annotated[str, Query()] = "en",
    ai_model: Annotated[str | None, Query(alias="aiModel", description="GEMINI or GEMMA. Defaults to GEMINI.")] = None,
    service: Annotated[PaymentCalendarRiskNarrativeService, Depends(get_narrative_service)] = None,
    cfg: Annotated[RiskForecastAiConfig, Depends(get_ai_config)] = None,
):
    _validate_language(language)
    headers = {"Authorization": f"Bearer {credentials.credentials}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{BACKEND_BASE_URL}/treasury/payment-calendar/risk-forecast/days/{date}",
                params={
                    "organizationId": organization_id,
                    "organizationIds": organization_ids,
                    "baseCurrencyCode": base_currency_code,
                    "includeAiNarrative": False,
                    "language": language,
                },
                headers=headers,
            )
            if response.status_code == 401:
                raise HTTPException(status_code=401, detail="Token yaroqsiz.")
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Backend ma'lumot bera olmadi.")
            backend_data = response.json()
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Backend xizmati mavjud emas.")

    try:
        drivers_list = backend_data.get("riskDrivers", [])    # ✅ camelCase

        request_data = DayDetailAiRequest(
            schema_version=cfg.schema_version_request,
            language=language,
            date=backend_data.get("date", date),
            base_currency_code=backend_data.get("baseCurrencyCode", cfg.base_currency_code),  # ✅
            risk_score=backend_data.get("riskScore", 0),          # ✅
            risk_level=backend_data.get("riskLevel", "LOW"),      # ✅
            total_amount_base=str(backend_data.get("totalAmountBase", "0")),  # ✅
            source_breakdown=backend_data.get("sourceBreakdown", []),         # ✅
            top_drivers=[
                AiRequestDriver(
                    type=d.get("type"),
                    severity=d.get("severity"),
                    amount_base=str(d.get("amountBase", "0")),  # ✅
                    count=d.get("count", 0),
                    description=d.get("description", ""),
                ) for d in drivers_list
            ],
            rules=[],
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Ma'lumot xatosi: {str(exc)}")

    result = service.generate_day_narrative(request_data, ai_model=ai_model)
    return _narrative_to_dict(result)


@router.get("/explain/narrative", summary="Explain AI Narrative", response_model=dict)
async def explain_narrative(
    request_http: Request,
    credentials: Annotated[HTTPAuthorizationCredentials, Security(security)],
    from_date: Annotated[str, Query(alias="from")],
    to_date: Annotated[str, Query(alias="to")],
    risk_driver_id: Annotated[str | None, Query(alias="riskDriverId")] = None,
    organization_id: Annotated[int | None, Query(alias="organizationId")] = None,
    language: Annotated[str, Query()] = "en",
    ai_model: Annotated[str | None, Query(alias="aiModel", description="GEMINI or GEMMA. Defaults to GEMINI.")] = None,
    service: Annotated[PaymentCalendarRiskNarrativeService, Depends(get_narrative_service)] = None,
    cfg: Annotated[RiskForecastAiConfig, Depends(get_ai_config)] = None,
):
    _validate_language(language)
    headers = {"Authorization": f"Bearer {credentials.credentials}"}

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(
                f"{BACKEND_BASE_URL}/treasury/payment-calendar/risk-forecast/explain",
                params={
                    "from": from_date,
                    "to": to_date,
                    "riskDriverId": risk_driver_id,
                    "organizationId": organization_id,
                    "language": language,
                },
                headers=headers,
            )
            if response.status_code == 401:
                raise HTTPException(status_code=401, detail="Token yaroqsiz.")
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail="Backend ma'lumot bera olmadi.")
            backend_data = response.json()
        except httpx.RequestError:
            raise HTTPException(status_code=503, detail="Backend xizmati mavjud emas.")

    try:
        scope_data = backend_data.get("scope", {})
        main_driver = backend_data.get("driver")
        context_list = backend_data.get("contextDrivers", [])  # ✅ camelCase

        request_data = ExplainAiRequest(
            schema_version=cfg.schema_version_request,
            language=language,
            scope=AiRequestScope(
                from_date=scope_data.get("from", from_date),
                to_date=scope_data.get("to", to_date),
                base_currency_code=scope_data.get("baseCurrencyCode", cfg.base_currency_code),  # ✅
            ),
            risk_driver_id=risk_driver_id,
            driver=AiRequestDriver(
                type=main_driver.get("type"),
                severity=main_driver.get("severity"),
                amount_base=str(main_driver.get("amountBase", "0")),  # ✅
                count=main_driver.get("count", 0),
                description=main_driver.get("description", ""),
            ) if main_driver else None,
            context_drivers=[
                AiRequestDriver(
                    type=cd.get("type"),
                    severity=cd.get("severity"),
                    amount_base=str(cd.get("amountBase", "0")),  # ✅
                    count=cd.get("count", 0),
                    description=cd.get("description", ""),
                ) for cd in context_list
            ],
            rules=[],
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Ma'lumot xatosi: {str(exc)}")

    result = service.generate_explain_narrative(request_data, ai_model=ai_model)
    return _narrative_to_dict(result)


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _validate_language(lang: str) -> None:
    if lang not in ("en", "ru", "uz"):
        raise HTTPException(status_code=400, detail=f"Qo'llab-quvvatlanmagan til: {lang}")


def _narrative_to_dict(r: AiNarrativeResponse) -> dict:
    return {
        "generated": r.generated,
        "model": r.model,
        "language": r.language,
        "summary": r.summary,
        "keyDrivers": r.key_drivers,
        "recommendedActions": [
            {
                "priority": a.priority,
                "action": a.action,
                "rationale": a.rationale,
            }
            for a in r.recommended_actions
        ],
        "limitations": r.limitations,
    }
