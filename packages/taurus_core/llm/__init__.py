"""LLM provider abstraction for schema-validated Taurus agent output."""

from __future__ import annotations

from taurus_core.config import (
    DEFAULT_GEMINI_BASE_URL,
    DEFAULT_LMSTUDIO_BASE_URL,
    DEFAULT_OPENAI_BASE_URL,
    SUPPORTED_LLM_PROVIDERS,
    Settings,
)
from taurus_core.llm.base import LLMProvider, LLMProviderError, LLMTraderOutput
from taurus_core.llm.gemini_provider import GeminiProvider
from taurus_core.llm.lmstudio_provider import LMStudioProvider
from taurus_core.llm.openai_provider import OpenAIProvider

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "LLMTraderOutput",
    "LMStudioProvider",
    "OpenAIProvider",
    "GeminiProvider",
    "build_llm_provider",
]


def build_llm_provider(settings: Settings) -> LLMProvider:
    if settings.taurus_llm_provider == "mock":
        raise _unsupported_provider_error(settings.taurus_llm_provider)
    if settings.taurus_llm_provider == "lmstudio":
        return LMStudioProvider(
            base_url=settings.taurus_llm_base_url or DEFAULT_LMSTUDIO_BASE_URL,
            model=settings.configured_llm_model,
            timeout_seconds=settings.taurus_llm_timeout_seconds,
        )
    if settings.taurus_llm_provider == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            base_url=settings.taurus_llm_base_url or DEFAULT_OPENAI_BASE_URL,
            model=settings.configured_llm_model,
            timeout_seconds=settings.taurus_llm_timeout_seconds,
        )
    if settings.taurus_llm_provider == "gemini":
        return GeminiProvider(
            api_key=settings.gemini_api_key,
            base_url=settings.taurus_llm_base_url or DEFAULT_GEMINI_BASE_URL,
            model=settings.configured_llm_model,
            timeout_seconds=settings.taurus_llm_timeout_seconds,
        )
    raise _unsupported_provider_error(settings.taurus_llm_provider)


def _unsupported_provider_error(provider: str) -> LLMProviderError:
    supported = ", ".join(SUPPORTED_LLM_PROVIDERS)
    return LLMProviderError(
        f"Unsupported LLM provider {provider!r}. Supported providers: {supported}. "
        "Example values: TAURUS_LLM_PROVIDER=lmstudio, TAURUS_LLM_PROVIDER=openai, "
        "TAURUS_LLM_PROVIDER=gemini."
    )
