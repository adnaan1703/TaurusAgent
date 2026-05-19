from __future__ import annotations

from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.llm.base import LLMProviderError
from taurus_core.llm.lmstudio_provider import _openai_compatible_completion


class OpenAIProvider:
    """Optional OpenAI-compatible provider; mock remains the default path."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        timeout_seconds: int = 20,
    ) -> None:
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
        if not self.api_key:
            raise LLMProviderError("OPENAI_API_KEY is required for TAURUS_LLM_PROVIDER=openai")
        return _openai_compatible_completion(
            base_url=self.base_url,
            api_key=self.api_key,
            model=self.model,
            model_version=self.model_version,
            agent_name=agent_name,
            symbol=symbol,
            context=context,
            timeout_seconds=self.timeout_seconds,
        )
