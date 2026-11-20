"""
Payment Calendar Risk Forecast — AI konfiguratsiya
GEMINI_MODEL=gemini-3-flash-preview
"""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv

# This module reads the environment directly and does NOT go through config.py,
# so it must load the .env itself. Without this it only saw the real values by
# accident of import order (main.py imports config first, whose module-level
# load_dotenv() runs before get_config()); imported on its own — a script, a
# test, a different import order — every VLLM_* read fell back to its default
# and the client dialled 127.0.0.1:8000. load_dotenv never overrides variables
# already set in the environment, so calling it twice is harmless.
load_dotenv()


def _default_ai_provider() -> str:
    raw_model = (os.getenv("RISK_DEFAULT_AI_MODEL") or os.getenv("DEFAULT_AI_MODEL") or "GEMINI").strip().upper()
    if raw_model not in {"GEMINI", "GEMMA"}:
        raise ValueError("RISK_DEFAULT_AI_MODEL/DEFAULT_AI_MODEL must be either GEMINI or GEMMA")
    return "vllm" if raw_model == "GEMMA" else "gemini"


def normalize_ai_model(ai_model: str | None = None) -> str:
    value = (ai_model or "").strip().upper()
    if not value:
        raw_default = (os.getenv("RISK_DEFAULT_AI_MODEL") or os.getenv("DEFAULT_AI_MODEL") or "GEMINI").strip().upper()
        return "GEMMA" if raw_default == "GEMMA" else "GEMINI"
    aliases = {
        "GEMINI": "GEMINI",
        "GOOGLE": "GEMINI",
        "GOOGLE_GEMINI": "GEMINI",
        "GEMMA": "GEMMA",
        "GEMMA4": "GEMMA",
        "OLLAMA": "GEMMA",
        "VLLM": "GEMMA",
    }
    normalized = aliases.get(value)
    if normalized not in {"GEMINI", "GEMMA"}:
        raise ValueError("aiModel must be either GEMINI or GEMMA")
    return normalized


def _vllm_base_url() -> str:
    """VLLM_BASE_URL, with the OpenAI route prefix ensured (…/v1)."""
    raw = (os.getenv("VLLM_BASE_URL") or "http://127.0.0.1:8000/v1").strip().rstrip("/")
    return raw if raw.endswith("/v1") else f"{raw}/v1"


def _get_int_env(*names: str, default: int) -> int:
    for name in names:
        raw = os.getenv(name)
        if raw is not None and raw.strip():
            return int(raw)
    return default


@dataclass
class GeminiConfig:
    model: str = field(
        default_factory=lambda: os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")
    )
    api_key: str = field(
        default_factory=lambda: os.getenv("GEMINI_API_KEY", "")
    )
    api_base_url: str = field(
        default_factory=lambda: os.getenv(
            "GEMINI_API_BASE",
            "https://generativelanguage.googleapis.com/v1beta"
        )
    )
    timeout_seconds: int = field(
        default_factory=lambda: int(os.getenv("GEMINI_TIMEOUT_SECONDS", "15"))
    )
    max_retries: int = field(
        default_factory=lambda: int(os.getenv("GEMINI_MAX_RETRIES", "2"))
    )
    max_output_tokens: int = field(
        default_factory=lambda: _get_int_env("RISK_GEMINI_MAX_OUTPUT_TOKENS", "GEMINI_MAX_OUTPUT_TOKENS", default=2048)
    )
    temperature: float = 0.2          # deterministik javob uchun past temperatura


@dataclass
class VllmConfig:
    """The local model, served by vLLM. Reads the same VLLM_* env as config.py."""

    # The id vLLM was launched with (e.g. "gemma4-31b"), NOT the Ollama tag —
    # an unknown id comes back as HTTP 404 from /v1/chat/completions.
    model: str = field(
        default_factory=lambda: os.getenv("VLLM_MODEL", "gemma4-31b").strip() or "gemma4-31b"
    )
    base_url: str = field(default_factory=lambda: _vllm_base_url())
    api_key: str = field(default_factory=lambda: os.getenv("VLLM_API_KEY", "").strip())
    timeout_seconds: int = field(
        default_factory=lambda: _get_int_env(
            "VLLM_TIMEOUT_SECONDS", "VLLM_TIMEOUT_SEC", "OLLAMA_TIMEOUT_SEC", default=180
        )
    )
    max_retries: int = field(
        default_factory=lambda: _get_int_env("VLLM_MAX_RETRIES", "GEMINI_MAX_RETRIES", default=2)
    )
    max_output_tokens: int = field(
        default_factory=lambda: _get_int_env(
            "RISK_VLLM_MAX_TOKENS", "VLLM_MAX_TOKENS", "OLLAMA_NUM_PREDICT", default=2048
        )
    )
    temperature: float = 0.2


@dataclass
class RiskForecastAiConfig:
    ai_provider: str = field(default_factory=_default_ai_provider)
    ai_enabled: bool = field(
        default_factory=lambda: os.getenv("RISK_AI_ENABLED", "true").lower() == "true"
    )
    max_range_days: int = 366
    default_horizon_days: int = 90
    due_soon_days: int = 7
    base_currency_code: str = "UZS"
    schema_version_request: str = "payment-calendar-risk-ai-request.v1"
    schema_version_response: str = "payment-calendar-risk-ai-response.v1"

    # Response limitleri
    max_key_drivers: int = 5
    max_recommended_actions: int = 4
    max_limitations: int = 3
    max_summary_chars: int = 600

    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    vllm: VllmConfig = field(default_factory=VllmConfig)

    @property
    def active_model(self) -> str:
        return self.vllm.model if self.ai_provider == "vllm" else self.gemini.model


# Global singleton
_config: RiskForecastAiConfig | None = None


def get_config() -> RiskForecastAiConfig:
    global _config
    if _config is None:
        _config = RiskForecastAiConfig()
    return _config
