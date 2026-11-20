"""
Payment Calendar Risk Forecast — vLLM AI Client

Replaces the Ollama client (risk_forecast/ollama_client.py) for the local model.
Same behaviour around the call — retry with exponential backoff, timeout, shared
circuit breaker, JSON-only output — only the wire format changed:

  POST /api/generate  ->  POST /v1/chat/completions
  "prompt" + "system" ->  "messages": [system, user]
  "format": "json"    ->  "response_format": {"type": "json_object"}
  "num_predict"       ->  "max_tokens"
  data["response"]    ->  data["choices"][0]["message"]["content"]
  (no auth)           ->  Authorization: Bearer VLLM_API_KEY

The circuit breaker is imported from gemini_client as before, so both providers
degrade the same way and the narrative service's fallback path is untouched.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Optional

import httpx

from risk_forecast.gemini_client import CircuitBreaker
from risk_forecast.settings import VllmConfig, get_config

logger = logging.getLogger(__name__)


class VllmAiClientError(Exception):
    """vLLM client xatoligi."""


class VllmAiClient:
    """
    vLLM OpenAI-mos API bilan ishlaydi.
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
        "and operational. Always return one top-level JSON object with these exact "
        "camelCase keys: schemaVersion, language, summary, keyDrivers, "
        "recommendedActions, limitations. Never rename keys, never omit arrays, "
        "and never return markdown."
    )

    def __init__(self, config: Optional[VllmConfig] = None):
        self._cfg = config or get_config().vllm
        self._circuit = CircuitBreaker()

    def generate(self, prompt: str) -> str:
        if self._circuit.is_open():
            raise VllmAiClientError("Circuit breaker OPEN - vLLM vaqtincha o'chirilgan")

        last_error: Exception | None = None
        for attempt in range(1, self._cfg.max_retries + 2):
            try:
                result = self._call(prompt)
                self._circuit.record_success()
                return result
            except VllmAiClientError:
                raise
            except Exception as exc:
                last_error = exc
                self._circuit.record_failure()
                wait = 2 ** (attempt - 1)
                logger.warning(
                    "vLLM urinish %d xato: %s - %ds kutilmoqda",
                    attempt,
                    exc,
                    wait,
                )
                if attempt <= self._cfg.max_retries:
                    time.sleep(wait)

        raise VllmAiClientError(
            f"vLLM {self._cfg.max_retries + 1} urinishdan keyin ham xato: {last_error}"
        ) from last_error

    def _call(self, prompt: str) -> str:
        url = f"{self._cfg.base_url.rstrip('/')}/chat/completions"
        body = self._build_body(prompt)
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "ngrok-skip-browser-warning": "true",
        }
        if self._cfg.api_key:
            headers["Authorization"] = f"Bearer {self._cfg.api_key}"

        logger.debug("vLLM -> %s (prompt uzunligi: %d)", self._cfg.model, len(prompt))

        timeout = httpx.Timeout(
            connect=min(20.0, float(self._cfg.timeout_seconds)),
            read=float(self._cfg.timeout_seconds),
            write=float(self._cfg.timeout_seconds),
            pool=20.0,
        )
        with httpx.Client(timeout=timeout, headers=headers) as client:
            response = client.post(url, json=body)

        if response.status_code != 200:
            logger.error("vLLM HTTP %d: %s", response.status_code, response.text[:300])
            raise VllmAiClientError(
                f"vLLM HTTP {response.status_code}: {response.text[:200]}"
            )

        data = response.json()
        return self._extract_text(data)

    def _build_body(self, prompt: str) -> dict[str, Any]:
        return {
            "model": self._cfg.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_INSTRUCTION},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
            "temperature": self._cfg.temperature,
            "max_tokens": self._cfg.max_output_tokens,
        }

    @staticmethod
    def _extract_text(data: dict[str, Any]) -> str:
        choices = data.get("choices")
        if not isinstance(choices, list) or not choices:
            raise VllmAiClientError("vLLM javobida choices yo'q")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        text = message.get("content") if isinstance(message, dict) else None
        if not isinstance(text, str) or not text.strip():
            raise VllmAiClientError("vLLM bo'sh text qaytardi")
        return text.strip()
