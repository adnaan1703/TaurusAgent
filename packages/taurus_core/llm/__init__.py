"""LLM provider abstraction for schema-validated Taurus agent output."""

from __future__ import annotations

import os

from taurus_core.config import Settings
from taurus_core.llm.base import LLMProvider, LLMProviderError
from taurus_core.llm.lmstudio_provider import LMStudioProvider
from taurus_core.llm.mock_provider import MockLLMProvider
from taurus_core.llm.openai_provider import OpenAIProvider

__all__ = [
    "LLMProvider",
    "LLMProviderError",
    "MockLLMProvider",
    "LMStudioProvider",
    "OpenAIProvider",
    "build_llm_provider",
]


def build_llm_provider(settings: Settings) -> LLMProvider:
    model = os.environ.get("TAURUS_LLM_MODEL", "")
    if settings.taurus_llm_provider == "mock":
        return MockLLMProvider(model_version=model or "mock-llm-v1")
    if settings.taurus_llm_provider == "lmstudio":
        return LMStudioProvider(
            base_url=settings.taurus_llm_base_url or "http://localhost:1234/v1",
            model=model or "local-model",
        )
    if settings.taurus_llm_provider == "openai":
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            base_url=settings.taurus_llm_base_url or "https://api.openai.com/v1",
            model=model or "gpt-4o-mini",
        )
    raise LLMProviderError(f"Unsupported LLM provider: {settings.taurus_llm_provider}")
