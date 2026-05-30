from __future__ import annotations

from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.config import DEFAULT_OPENAI_BASE_URL, DEFAULT_OPENAI_MODEL
from taurus_core.llm.base import LLMBullThesisOutput, LLMProviderError
from taurus_core.llm.lmstudio_provider import (
    _openai_compatible_bull_thesis_completion,
    _openai_compatible_completion,
    openai_bull_thesis_json_schema_response_format,
    openai_json_schema_response_format,
)


class OpenAIProvider:
    """OpenAI API provider using API-key billing."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_OPENAI_BASE_URL,
        model: str = DEFAULT_OPENAI_MODEL,
        timeout_seconds: int = 20,
    ) -> None:
        if not api_key:
            raise LLMProviderError("OPENAI_API_KEY is required for TAURUS_LLM_PROVIDER=openai")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def model_version(self) -> str:
        return f"openai:{self.model}"

    def complete_analyst_report(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMAnalystOutput:
        return _openai_compatible_completion(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            model_version=self.model_version,
            agent_name=agent_name,
            symbol=symbol,
            context=context,
            timeout_seconds=self.timeout_seconds,
            response_format=openai_json_schema_response_format(),
            provider_name="OpenAI",
        )

    def complete_bull_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBullThesisOutput:
        return _openai_compatible_bull_thesis_completion(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            model_version=self.model_version,
            agent_name=agent_name,
            symbol=symbol,
            baseline=baseline,
            evidence_pack=evidence_pack,
            timeout_seconds=self.timeout_seconds,
            response_format=openai_bull_thesis_json_schema_response_format(),
            provider_name="OpenAI",
        )
