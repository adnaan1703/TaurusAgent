from __future__ import annotations

import json
from typing import Protocol

from pydantic import ValidationError

from taurus_core.agents.schemas import LLMAnalystOutput


class LLMProviderError(RuntimeError):
    pass


ANALYST_OUTPUT_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": -1, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "stance": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "horizon": {"type": "string", "enum": ["intraday", "short", "medium", "long"]},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "model_version": {"type": "string"},
    },
    "required": [
        "score",
        "confidence",
        "stance",
        "horizon",
        "key_points",
        "risks",
        "model_version",
    ],
    "additionalProperties": False,
}


def analyst_output_system_prompt() -> str:
    return (
        "Return JSON only. The JSON must conform to LLMAnalystOutput: score number -1..1, "
        "confidence number 0..1, stance bullish|bearish|neutral, horizon intraday|short|medium|long, "
        "key_points string array, risks string array, and model_version string. Do not include prose "
        "outside the JSON object."
    )


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
