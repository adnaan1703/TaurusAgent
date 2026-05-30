from __future__ import annotations

import json
from typing import Protocol

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

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

BULL_THESIS_OUTPUT_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": -1, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "key_points": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "conditions": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "model_version": {"type": "string"},
    },
    "required": [
        "score",
        "confidence",
        "key_points",
        "conditions",
        "model_version",
    ],
    "additionalProperties": False,
}

BEAR_THESIS_OUTPUT_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": -1, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "key_points": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "risk_flags": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "model_version": {"type": "string"},
    },
    "required": [
        "score",
        "confidence",
        "key_points",
        "risk_flags",
        "model_version",
    ],
    "additionalProperties": False,
}

RESEARCH_MANAGER_OUTPUT_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "consensus_label": {
            "type": "string",
            "enum": ["bullish", "mild_bullish", "neutral", "mild_bearish", "bearish"],
        },
        "consensus_score": {"type": "number", "minimum": -1, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "summary": {"type": "string", "minLength": 1},
        "unresolved_uncertainties": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "model_version": {"type": "string"},
    },
    "required": [
        "consensus_label",
        "consensus_score",
        "confidence",
        "summary",
        "unresolved_uncertainties",
        "model_version",
    ],
    "additionalProperties": False,
}


class LLMBullThesisOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    key_points: list[str] = Field(min_length=1)
    conditions: list[str] = Field(min_length=1)
    model_version: str

    @field_validator("key_points", "conditions")
    @classmethod
    def remove_empty_items(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty item is required")
        return cleaned


class LLMBearThesisOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    key_points: list[str] = Field(min_length=1)
    risk_flags: list[str] = Field(min_length=1)
    model_version: str

    @field_validator("key_points", "risk_flags")
    @classmethod
    def remove_empty_items(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty item is required")
        return cleaned


class LLMResearchManagerOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    consensus_label: str = Field(
        pattern="^(bullish|mild_bullish|neutral|mild_bearish|bearish)$"
    )
    consensus_score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    summary: str = Field(min_length=1)
    unresolved_uncertainties: list[str] = Field(min_length=1)
    model_version: str

    @field_validator("summary")
    @classmethod
    def clean_summary(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("summary must not be empty")
        return cleaned

    @field_validator("unresolved_uncertainties")
    @classmethod
    def remove_empty_items(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty item is required")
        return cleaned


def analyst_output_system_prompt() -> str:
    return (
        "Return JSON only. The JSON must conform to LLMAnalystOutput: score number -1..1, "
        "confidence number 0..1, stance bullish|bearish|neutral, horizon intraday|short|medium|long, "
        "key_points string array, risks string array, and model_version string. Do not include prose "
        "outside the JSON object."
    )


def bull_thesis_system_prompt() -> str:
    return (
        "You are Taurus BullResearcherAgent, the bullish research voice in a local\n"
        "paper-trading decision workflow. Your job is to build the strongest evidence-led\n"
        "bull case for the symbol from the supplied analyst reports.\n\n"
        "Hard rules:\n"
        "- Use only provided analyst evidence, scores, risks, source IDs, and report IDs.\n"
        "- Address material negative evidence directly; do not ignore risks to make the\n"
        "  bull case stronger.\n"
        "- Do not invent facts, prices, filings, news, source IDs, broker actions, or\n"
        "  order instructions.\n"
        "- Do not decide trades or position sizes. TraderAgent and deterministic risk\n"
        "  gates handle that later.\n"
        "- Keep score and confidence within the requested schema ranges and grounded in\n"
        "  the evidence.\n"
        "- Return valid JSON matching the requested schema and no prose outside JSON."
    )


def bear_thesis_system_prompt() -> str:
    return (
        "You are Taurus BearResearcherAgent, the skeptical research voice in a local\n"
        "paper-trading decision workflow. Your job is to build the strongest\n"
        "evidence-led bear case for the symbol from the supplied analyst reports.\n\n"
        "Hard rules:\n"
        "- Use only provided analyst evidence, scores, risks, source IDs, and report IDs.\n"
        "- Challenge bullish assumptions and identify downside, invalidation, liquidity,\n"
        "  data-quality, and concentration risks where the supplied evidence supports\n"
        "  them.\n"
        "- Do not invent facts, prices, filings, news, source IDs, broker actions, or\n"
        "  order instructions.\n"
        "- Do not decide trades or position sizes. TraderAgent and deterministic risk\n"
        "  gates handle that later.\n"
        "- Keep bearish score non-positive after Taurus guardrails and keep confidence\n"
        "  grounded in evidence quality.\n"
        "- Return valid JSON matching the requested schema and no prose outside JSON."
    )


def research_manager_system_prompt() -> str:
    return (
        "You are Taurus ResearchManagerAgent, the debate facilitator and synthesis agent\n"
        "for a local paper-trading research workflow. Your job is to synthesize analyst\n"
        "reports plus bull and bear theses into one evidence-bound consensus summary.\n\n"
        "Hard rules:\n"
        "- Synthesize research only. Do not place trades, size positions, route orders,\n"
        "  or override deterministic risk controls.\n"
        "- Use only supplied analyst reports, bull thesis, bear thesis, source IDs,\n"
        "  scores, confidence, risks, and the deterministic baseline.\n"
        "- Preserve material disagreement and unresolved uncertainty instead of forcing\n"
        "  false consensus.\n"
        "- Do not invent facts, source IDs, prices, filings, news, broker actions, or\n"
        "  order instructions.\n"
        "- Taurus recomputes the final consensus label from the final score; your label\n"
        "  must be consistent with the evidence.\n"
        "- Return valid JSON matching the requested schema and no prose outside JSON."
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

    def complete_bull_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBullThesisOutput:
        ...

    def complete_bear_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBearThesisOutput:
        ...

    def complete_research_manager_summary(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMResearchManagerOutput:
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


def parse_bull_thesis_output(
    raw_content: str,
    *,
    fallback_model_version: str,
) -> LLMBullThesisOutput:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM bull thesis response was not valid JSON") from exc
    if isinstance(payload, dict) and "model_version" not in payload:
        payload["model_version"] = fallback_model_version
    try:
        return LLMBullThesisOutput.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError("LLM bull thesis response failed schema validation") from exc


def parse_bear_thesis_output(
    raw_content: str,
    *,
    fallback_model_version: str,
) -> LLMBearThesisOutput:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM bear thesis response was not valid JSON") from exc
    if isinstance(payload, dict) and "model_version" not in payload:
        payload["model_version"] = fallback_model_version
    try:
        return LLMBearThesisOutput.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError("LLM bear thesis response failed schema validation") from exc


def parse_research_manager_output(
    raw_content: str,
    *,
    fallback_model_version: str,
) -> LLMResearchManagerOutput:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM research manager response was not valid JSON") from exc
    if isinstance(payload, dict) and "model_version" not in payload:
        payload["model_version"] = fallback_model_version
    try:
        return LLMResearchManagerOutput.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError("LLM research manager response failed schema validation") from exc
