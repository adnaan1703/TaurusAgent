from __future__ import annotations

import json
from typing import Protocol

from pydantic import ValidationError

from taurus_core.agents.schemas import LLMAnalystOutput


class LLMProviderError(RuntimeError):
    pass


class LLMProvider(Protocol):
    @property
    def model_version(self) -> str:
        ...

    def complete_analyst_report(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMAnalystOutput:
        ...


def parse_llm_output(raw_content: str, *, fallback_model_version: str) -> LLMAnalystOutput:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM response was not valid JSON") from exc
    if isinstance(payload, dict) and "model_version" not in payload:
        payload["model_version"] = fallback_model_version
    try:
        return LLMAnalystOutput.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError("LLM response failed AnalystOutput schema validation") from exc
