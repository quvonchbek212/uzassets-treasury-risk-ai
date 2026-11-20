from __future__ import annotations

import logging
import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from risk_forecast.router import router as risk_forecast_router

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("risk_forecast")

app = FastAPI(
    title="UzAssets — Payment Calendar Risk Forecast AI Service",
    version="1.0.0",
    description=(
        "«UzAssets» AJ tizimi uchun g'aznachilik to'lovlar taqvimi bo'yicha "
        "kassa uzilishlari va moliyaviy xatarlarni tahlil qiluvchi hamda AI "
        "tahliliy hisobotlarini (Executive Risk Narrative) yaratuvchi xizmat."
    ),
    swagger_ui_parameters={"persistAuthorization": True},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "ok", "service": "payment-calendar-risk-forecast", "version": "1.0.0"}

app.include_router(risk_forecast_router)

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8002"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
