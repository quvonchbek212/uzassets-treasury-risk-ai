"""
Payment Calendar Risk Forecast — Gemini AI Client
Gemini REST API bilan ishlaydi: timeout, retry, circuit breaker.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import httpx

from risk_forecast.settings import GeminiConfig, get_config

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# Circuit Breaker
# ──────────────────────────────────────────────

class CircuitState(Enum):
    CLOSED = "CLOSED"       # normal ishlaydi
    OPEN = "OPEN"           # to'xtatilgan
    HALF_OPEN = "HALF_OPEN" # sinov rejimi


@dataclass
class CircuitBreaker:
    failure_threshold: int = 3
    recovery_timeout_seconds: int = 60

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)

    @property
    def state(self) -> CircuitState:
        if (
            self._state == CircuitState.OPEN
            and (time.time() - self._last_failure_time) > self.recovery_timeout_seconds
        ):
            self._state = CircuitState.HALF_OPEN
            logger.info("CircuitBreaker: OPEN → HALF_OPEN")
        return self._state

    def is_open(self) -> bool:
        return self.state == CircuitState.OPEN

    def record_success(self) -> None:
        self._failure_count = 0
        self._state = CircuitState.CLOSED

    def record_failure(self) -> None:
        self._failure_count += 1
        self._last_failure_time = time.time()
        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.warning(
                "CircuitBreaker: OPEN — %d ketma-ket xatolik", self._failure_count
            )


# ──────────────────────────────────────────────
# Gemini API Client
# ──────────────────────────────────────────────

class GeminiAiClientError(Exception):
    """Gemini client xatoligi."""


class GeminiAiClient:
    """
    Gemini REST API bilan ishlaydi.
    - Retry (exponential backoff)
    - Timeout
    - Circuit Breaker
    - Faqat JSON javobini qaytaradi
    """

    SYSTEM_INSTRUCTION = (
        "You are a treasury risk analyst assistant. "
        "You receive a structured JSON risk payload and must return ONLY valid JSON "
        "matching the requested schema. Never invent amounts, dates, statuses, or "
        "payment items not present in the input. Keep recommendations non-binding "
        "and operational."
    )

    def __init__(self, config: Optional[GeminiConfig] = None):
        self._cfg = config or get_config().gemini
        self._circuit = CircuitBreaker()

    # ── Public ────────────────────────────────

    def generate(self, prompt: str) -> str:
        """
        Gemini-ga prompt yuboradi va text javobni qaytaradi.
        Circuit breaker ochiq bo'lsa — GeminiAiClientError raise qiladi.
        """
        if self._circuit.is_open():
            raise GeminiAiClientError("Circuit breaker OPEN — Gemini vaqtincha o'chirilgan")

        last_error: Exception | None = None
        for attempt in range(1, self._cfg.max_retries + 2):  # +1 because range is exclusive
            try:
                result = self._call(prompt)
                self._circuit.record_success()
                return result
            except GeminiAiClientError:
                raise  # circuit breaker xatoliklarini re-raise qil
            except Exception as exc:
                last_error = exc
                self._circuit.record_failure()
                wait = 2 ** (attempt - 1)
                logger.warning(
                    "Gemini urinish %d xato: %s — %ds kutilmoqda", attempt, exc, wait
                )
                if attempt <= self._cfg.max_retries:
                    time.sleep(wait)

        raise GeminiAiClientError(f"Gemini {self._cfg.max_retries + 1} urinishdan keyin ham xato: {last_error}") from last_error

    # ── Private ───────────────────────────────

    def _call(self, prompt: str) -> str:
        url = (
            f"{self._cfg.api_base_url}/models/{self._cfg.model}"
            f":generateContent?key={self._cfg.api_key}"
        )
        body = self._build_body(prompt)

        logger.debug("Gemini → %s (prompt uzunligi: %d)", self._cfg.model, len(prompt))

        with httpx.Client(timeout=self._cfg.timeout_seconds) as client:
            response = client.post(url, json=body)

        if response.status_code != 200:
            logger.error("Gemini HTTP %d: %s", response.status_code, response.text[:300])
            raise GeminiAiClientError(
                f"Gemini HTTP {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        return self._extract_text(data)

    def _build_body(self, prompt: str) -> dict[str, Any]:
        return {
            "system_instruction": {
                "parts": [{"text": self.SYSTEM_INSTRUCTION}]
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [{"text": prompt}]
                }
            ],
            "generationConfig": {
                "temperature": self._cfg.temperature,
                "maxOutputTokens": self._cfg.max_output_tokens,
                "responseMimeType": "application/json",
            },
        }

    @staticmethod
    def _extract_text(data: dict) -> str:
        try:
            candidates = data.get("candidates", [])
            if not candidates:
                raise GeminiAiClientError("Gemini bo'sh candidates qaytardi")
            parts = candidates[0].get("content", {}).get("parts", [])
            if not parts:
                raise GeminiAiClientError("Gemini bo'sh parts qaytardi")
            text = parts[0].get("text", "").strip()
            if not text:
                raise GeminiAiClientError("Gemini bo'sh text qaytardi")
            return text
        except (KeyError, IndexError, TypeError) as exc:
            raise GeminiAiClientError(f"Gemini response parse xatosi: {exc}") from exc
