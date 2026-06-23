from __future__ import annotations

from dataclasses import dataclass
import json
from collections.abc import Iterable, Mapping
from typing import Protocol

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from taurus_core.agents.schemas import LLMAnalystOutput


class LLMProviderError(RuntimeError):
    pass


MODEL_VERSION_MAX_CHARS = 160


@dataclass(frozen=True, slots=True)
class LLMUsageRecord:
    provider: str
    model_version: str
    agent_name: str
    symbol: str
    elapsed_seconds: float
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    cached_input_tokens: int | None = None
    reasoning_tokens: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "model_version": self.model_version,
            "agent_name": self.agent_name,
            "symbol": self.symbol.upper(),
            "elapsed_seconds": round(self.elapsed_seconds, 6),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cached_input_tokens": self.cached_input_tokens,
            "reasoning_tokens": self.reasoning_tokens,
        }


_USAGE_TOKEN_KEYS = (
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cached_input_tokens",
    "reasoning_tokens",
)


def append_llm_usage_record(provider: object | None, record: LLMUsageRecord) -> None:
    if provider is None:
        return
    records = getattr(provider, "_llm_usage_records", None)
    if records is None:
        records = []
        setattr(provider, "_llm_usage_records", records)
    records.append(record)


def get_llm_usage_records(provider: object | None) -> list[LLMUsageRecord]:
    if provider is None:
        return []
    records = getattr(provider, "_llm_usage_records", None)
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, LLMUsageRecord)]


def summarize_llm_usage(records: Iterable[LLMUsageRecord]) -> dict[str, object]:
    usage_records = list(records)
    elapsed_seconds = round(sum(record.elapsed_seconds for record in usage_records), 6)
    summary: dict[str, object] = {
        "provider": _single_or_mixed(record.provider for record in usage_records),
        "providers": sorted({record.provider for record in usage_records}),
        "model_versions": sorted({record.model_version for record in usage_records}),
        "request_count": len(usage_records),
        "elapsed_seconds": elapsed_seconds,
    }
    for key in _USAGE_TOKEN_KEYS:
        summary[key] = _sum_optional_record_field(usage_records, key)
    summary["output_tokens_per_second"] = _tokens_per_second(
        summary["output_tokens"],
        elapsed_seconds,
    )
    summary["total_tokens_per_second"] = _tokens_per_second(
        summary["total_tokens"],
        elapsed_seconds,
    )
    summary["by_agent"] = _summarize_llm_usage_by_agent(usage_records)
    return summary


def aggregate_llm_usage_summaries(
    summaries: Iterable[Mapping[str, object]],
) -> dict[str, object]:
    usage_summaries = [summary for summary in summaries if summary]
    request_count = sum(
        _int_value(summary.get("request_count")) or 0 for summary in usage_summaries
    )
    elapsed_seconds = round(
        sum(
            _float_value(summary.get("elapsed_seconds")) or 0.0
            for summary in usage_summaries
        ),
        6,
    )
    providers = sorted(
        {
            str(provider)
            for summary in usage_summaries
            for provider in _list_value(summary.get("providers"))
        }
    )
    model_versions = sorted(
        {
            str(model_version)
            for summary in usage_summaries
            for model_version in _list_value(summary.get("model_versions"))
        }
    )
    aggregate: dict[str, object] = {
        "provider": _single_or_mixed(providers),
        "providers": providers,
        "model_versions": model_versions,
        "request_count": request_count,
        "elapsed_seconds": elapsed_seconds,
    }
    for key in _USAGE_TOKEN_KEYS:
        aggregate[key] = _sum_optional_summary_key(usage_summaries, key)
    aggregate["output_tokens_per_second"] = _tokens_per_second(
        aggregate["output_tokens"],
        elapsed_seconds,
    )
    aggregate["total_tokens_per_second"] = _tokens_per_second(
        aggregate["total_tokens"],
        elapsed_seconds,
    )
    aggregate["by_agent"] = _aggregate_llm_usage_by_agent(usage_summaries)
    return aggregate


def llm_usage_record_from_openai_response(
    response_payload: Mapping[str, object],
    *,
    model_version: str,
    agent_name: str,
    symbol: str,
    elapsed_seconds: float,
) -> LLMUsageRecord:
    usage = _mapping_value(response_payload.get("usage"))
    prompt_details = _mapping_value(usage.get("prompt_tokens_details")) if usage else {}
    completion_details = (
        _mapping_value(usage.get("completion_tokens_details")) if usage else {}
    )
    return LLMUsageRecord(
        provider=_provider_from_model_version(model_version),
        model_version=model_version,
        agent_name=agent_name,
        symbol=symbol,
        elapsed_seconds=elapsed_seconds,
        input_tokens=_int_value(usage.get("prompt_tokens")) if usage else None,
        output_tokens=_int_value(usage.get("completion_tokens")) if usage else None,
        total_tokens=_int_value(usage.get("total_tokens")) if usage else None,
        cached_input_tokens=_int_value(prompt_details.get("cached_tokens")),
        reasoning_tokens=_int_value(completion_details.get("reasoning_tokens")),
    )


def llm_usage_record_from_gemini_response(
    response_payload: Mapping[str, object],
    *,
    model_version: str,
    agent_name: str,
    symbol: str,
    elapsed_seconds: float,
) -> LLMUsageRecord:
    usage = _mapping_value(response_payload.get("usageMetadata"))
    return LLMUsageRecord(
        provider=_provider_from_model_version(model_version),
        model_version=model_version,
        agent_name=agent_name,
        symbol=symbol,
        elapsed_seconds=elapsed_seconds,
        input_tokens=_int_value(usage.get("promptTokenCount")) if usage else None,
        output_tokens=_int_value(usage.get("candidatesTokenCount")) if usage else None,
        total_tokens=_int_value(usage.get("totalTokenCount")) if usage else None,
        cached_input_tokens=_int_value(usage.get("cachedContentTokenCount"))
        if usage
        else None,
        reasoning_tokens=_int_value(usage.get("thoughtsTokenCount")) if usage else None,
    )


MODEL_VERSION_JSON_SCHEMA: dict[str, object] = {
    "type": "string",
    "minLength": 1,
    "maxLength": MODEL_VERSION_MAX_CHARS,
}


ANALYST_OUTPUT_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "score": {"type": "number", "minimum": -1, "maximum": 1},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "stance": {"type": "string", "enum": ["bullish", "bearish", "neutral"]},
        "horizon": {"type": "string", "enum": ["intraday", "short", "medium", "long"]},
        "key_points": {"type": "array", "items": {"type": "string"}},
        "risks": {"type": "array", "items": {"type": "string"}},
        "model_version": MODEL_VERSION_JSON_SCHEMA,
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
        "model_version": MODEL_VERSION_JSON_SCHEMA,
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
        "model_version": MODEL_VERSION_JSON_SCHEMA,
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
        "model_version": MODEL_VERSION_JSON_SCHEMA,
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

TRADER_OUTPUT_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["BUY", "HOLD", "NO_TRADE", "REDUCE", "EXIT"],
        },
        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
        "target_position_pct_nav": {"type": "number", "minimum": 0, "maximum": 100},
        "stop_loss_pct": {"type": "number", "minimum": 0, "maximum": 100},
        "take_profit_pct": {"type": "number", "minimum": 0, "maximum": 100},
        "reason_summary": {"type": "string", "minLength": 1},
        "invalid_if": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "position_management_summary": {"type": "string", "minLength": 1},
        "model_version": MODEL_VERSION_JSON_SCHEMA,
    },
    "required": [
        "action",
        "confidence",
        "target_position_pct_nav",
        "stop_loss_pct",
        "take_profit_pct",
        "reason_summary",
        "invalid_if",
        "position_management_summary",
        "model_version",
    ],
    "additionalProperties": False,
}

FINAL_DECISION_EXPLANATION_JSON_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "minLength": 1, "maxLength": 900},
        "model_version": MODEL_VERSION_JSON_SCHEMA,
    },
    "required": ["reason", "model_version"],
    "additionalProperties": False,
}


class LLMBullThesisOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    key_points: list[str] = Field(min_length=1)
    conditions: list[str] = Field(min_length=1)
    model_version: str = Field(min_length=1, max_length=MODEL_VERSION_MAX_CHARS)

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
    model_version: str = Field(min_length=1, max_length=MODEL_VERSION_MAX_CHARS)

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
    model_version: str = Field(min_length=1, max_length=MODEL_VERSION_MAX_CHARS)

    @field_validator("summary")
    @classmethod
    def clean_summary(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("summary must not be empty")
        return cleaned

    @field_validator("unresolved_uncertainties")
    @classmethod
    def remove_empty_uncertainty_items(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty item is required")
        return cleaned


class LLMTraderOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: str = Field(pattern="^(BUY|HOLD|NO_TRADE|REDUCE|EXIT)$")
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    target_position_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    stop_loss_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    take_profit_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    reason_summary: str = Field(min_length=1)
    invalid_if: list[str] = Field(min_length=1)
    position_management_summary: str = Field(min_length=1)
    model_version: str = Field(min_length=1, max_length=MODEL_VERSION_MAX_CHARS)

    @field_validator("reason_summary", "position_management_summary")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("text field must not be empty")
        return cleaned

    @field_validator("invalid_if")
    @classmethod
    def remove_empty_items(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty item is required")
        return cleaned


class LLMFinalDecisionExplanation(BaseModel):
    model_config = ConfigDict(frozen=True)

    reason: str = Field(min_length=1, max_length=900)
    model_version: str = Field(min_length=1, max_length=MODEL_VERSION_MAX_CHARS)

    @field_validator("reason", "model_version")
    @classmethod
    def clean_text(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("text field must not be empty")
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


def trader_system_prompt() -> str:
    return (
        "You are Taurus TraderAgent, a paper-trading lifecycle proposal agent for a\n"
        "long-only portfolio. You convert validated research consensus and current paper\n"
        "portfolio context into one structured proposal for BUY, HOLD, REDUCE, EXIT, or\n"
        "NO_TRADE.\n\n"
        "Hard rules:\n"
        "- You are advisory. Taurus deterministic guardrails decide the allowed action\n"
        "  envelope, final sizing, risk approval, and broker routing.\n"
        "- Never recommend live trading, real broker order placement, leverage, shorts,\n"
        "  options, futures, or intraday speculation.\n"
        "- Use only the evidence in the provided context. Do not invent prices, fills,\n"
        "  positions, source IDs, research claims, or news.\n"
        "- Respect the supplied lifecycle trigger, evaluation mode, current position,\n"
        "  target exposure bounds, stop-loss, take-profit, and allowed actions.\n"
        "- If stop-loss is breached, explain EXIT only.\n"
        "- If take-profit is breached, recommend REDUCE or stricter EXIT only.\n"
        "- Return valid JSON matching the requested schema and no prose outside JSON."
    )


def portfolio_manager_system_prompt() -> str:
    return (
        "You are Taurus PortfolioManagerAgent, the final paper-trading approval explainer.\n"
        "The deterministic Taurus approval logic has already fixed the final status,\n"
        "action, quantity, exposure, order flag, and broker-routing flag. Your only job\n"
        "is to explain that fixed decision clearly.\n\n"
        "Hard rules:\n"
        "- Do not change or suggest changing final action, status, quantity, exposure,\n"
        "  order flags, broker routing, portfolio IDs, run IDs, or trace IDs.\n"
        "- Do not recommend live trading, real broker order placement, leverage, shorts,\n"
        "  options, or futures.\n"
        "- Explain the deterministic decision using only supplied proposal, risk review,\n"
        "  hard-rule, persona, and safety-config context.\n"
        "- If the final decision is HOLD, NO_TRADE, or NO_ACTION, make clear that no paper\n"
        "  order is expected.\n"
        "- Do not invent facts, prices, positions, source IDs, or external news.\n"
        "- Return valid JSON matching the requested schema and no prose outside JSON."
    )


class LLMProvider(Protocol):
    @property
    def model_version(self) -> str: ...

    def complete_analyst_report(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMAnalystOutput: ...

    def complete_bull_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBullThesisOutput: ...

    def complete_bear_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBearThesisOutput: ...

    def complete_research_manager_summary(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMResearchManagerOutput: ...

    def complete_trader_proposal(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMTraderOutput: ...

    def complete_final_decision_explanation(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMFinalDecisionExplanation: ...


def _summarize_llm_usage_by_agent(
    records: list[LLMUsageRecord],
) -> list[dict[str, object]]:
    grouped: dict[str, list[LLMUsageRecord]] = {}
    for record in records:
        grouped.setdefault(record.agent_name, []).append(record)

    rows: list[dict[str, object]] = []
    for agent_name, agent_records in sorted(grouped.items()):
        elapsed_seconds = round(
            sum(record.elapsed_seconds for record in agent_records), 6
        )
        row: dict[str, object] = {
            "agent_name": agent_name,
            "request_count": len(agent_records),
            "symbols": sorted({record.symbol.upper() for record in agent_records}),
            "elapsed_seconds": elapsed_seconds,
        }
        for key in _USAGE_TOKEN_KEYS:
            row[key] = _sum_optional_record_field(agent_records, key)
        row["output_tokens_per_second"] = _tokens_per_second(
            row["output_tokens"],
            elapsed_seconds,
        )
        row["total_tokens_per_second"] = _tokens_per_second(
            row["total_tokens"],
            elapsed_seconds,
        )
        rows.append(row)
    return rows


def _aggregate_llm_usage_by_agent(
    summaries: list[Mapping[str, object]],
) -> list[dict[str, object]]:
    grouped: dict[str, list[Mapping[str, object]]] = {}
    symbols_by_agent: dict[str, set[str]] = {}
    for summary in summaries:
        for row in _list_value(summary.get("by_agent")):
            if not isinstance(row, Mapping):
                continue
            agent_name = str(row.get("agent_name") or "")
            if not agent_name:
                continue
            grouped.setdefault(agent_name, []).append(row)
            symbols_by_agent.setdefault(agent_name, set()).update(
                str(symbol).upper() for symbol in _list_value(row.get("symbols"))
            )

    rows: list[dict[str, object]] = []
    for agent_name, agent_rows in sorted(grouped.items()):
        elapsed_seconds = round(
            sum(_float_value(row.get("elapsed_seconds")) or 0.0 for row in agent_rows),
            6,
        )
        row: dict[str, object] = {
            "agent_name": agent_name,
            "request_count": sum(
                _int_value(agent_row.get("request_count")) or 0
                for agent_row in agent_rows
            ),
            "symbols": sorted(symbols_by_agent.get(agent_name, set())),
            "elapsed_seconds": elapsed_seconds,
        }
        for key in _USAGE_TOKEN_KEYS:
            row[key] = _sum_optional_summary_key(agent_rows, key)
        row["output_tokens_per_second"] = _tokens_per_second(
            row["output_tokens"],
            elapsed_seconds,
        )
        row["total_tokens_per_second"] = _tokens_per_second(
            row["total_tokens"],
            elapsed_seconds,
        )
        rows.append(row)
    return rows


def _sum_optional_record_field(records: list[LLMUsageRecord], key: str) -> int | None:
    values = [_int_value(getattr(record, key)) for record in records]
    known_values = [value for value in values if value is not None]
    if not known_values:
        return None
    return sum(known_values)


def _sum_optional_summary_key(
    summaries: Iterable[Mapping[str, object]], key: str
) -> int | None:
    values = [_int_value(summary.get(key)) for summary in summaries]
    known_values = [value for value in values if value is not None]
    if not known_values:
        return None
    return sum(known_values)


def _tokens_per_second(tokens: object, elapsed_seconds: float) -> float | None:
    token_count = _int_value(tokens)
    if token_count is None or elapsed_seconds <= 0:
        return None
    return round(token_count / elapsed_seconds, 4)


def _provider_from_model_version(model_version: str) -> str:
    if ":" not in model_version:
        return "unknown"
    return model_version.split(":", maxsplit=1)[0] or "unknown"


def _single_or_mixed(values: Iterable[str]) -> str | None:
    unique_values = sorted({value for value in values if value})
    if not unique_values:
        return None
    if len(unique_values) == 1:
        return unique_values[0]
    return "mixed"


def _int_value(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _float_value(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _mapping_value(value: object) -> Mapping[str, object]:
    if isinstance(value, Mapping):
        return value
    return {}


def _list_value(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def parse_llm_output(
    raw_content: str, *, fallback_model_version: str
) -> LLMAnalystOutput:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM response was not valid JSON") from exc
    payload = _payload_with_model_version(payload, fallback_model_version)
    try:
        return LLMAnalystOutput.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError(
            "LLM response failed AnalystOutput schema validation"
        ) from exc


def parse_bull_thesis_output(
    raw_content: str,
    *,
    fallback_model_version: str,
) -> LLMBullThesisOutput:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM bull thesis response was not valid JSON") from exc
    payload = _payload_with_model_version(payload, fallback_model_version)
    try:
        return LLMBullThesisOutput.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError(
            "LLM bull thesis response failed schema validation"
        ) from exc


def parse_bear_thesis_output(
    raw_content: str,
    *,
    fallback_model_version: str,
) -> LLMBearThesisOutput:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM bear thesis response was not valid JSON") from exc
    payload = _payload_with_model_version(payload, fallback_model_version)
    try:
        return LLMBearThesisOutput.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError(
            "LLM bear thesis response failed schema validation"
        ) from exc


def parse_research_manager_output(
    raw_content: str,
    *,
    fallback_model_version: str,
) -> LLMResearchManagerOutput:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError(
            "LLM research manager response was not valid JSON"
        ) from exc
    payload = _payload_with_model_version(payload, fallback_model_version)
    try:
        return LLMResearchManagerOutput.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError(
            "LLM research manager response failed schema validation"
        ) from exc


def parse_trader_output(
    raw_content: str,
    *,
    fallback_model_version: str,
) -> LLMTraderOutput:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError("LLM trader response was not valid JSON") from exc
    payload = _payload_with_model_version(payload, fallback_model_version)
    try:
        return LLMTraderOutput.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError("LLM trader response failed schema validation") from exc


def parse_final_decision_explanation_output(
    raw_content: str,
    *,
    fallback_model_version: str,
) -> LLMFinalDecisionExplanation:
    try:
        payload = json.loads(raw_content)
    except json.JSONDecodeError as exc:
        raise LLMProviderError(
            "LLM final-decision explanation response was not valid JSON"
        ) from exc
    payload = _payload_with_model_version(payload, fallback_model_version)
    try:
        return LLMFinalDecisionExplanation.model_validate(payload)
    except ValidationError as exc:
        raise LLMProviderError(
            "LLM final-decision explanation response failed schema validation"
        ) from exc


def normalize_llm_model_version(value: object, *, fallback_model_version: str) -> str:
    candidate = str(value or "").strip()
    if _is_machine_model_version(candidate):
        return candidate
    return _compact_model_version(fallback_model_version)


def _payload_with_model_version(payload: object, fallback_model_version: str) -> object:
    if not isinstance(payload, dict):
        return payload
    updated = dict(payload)
    updated["model_version"] = normalize_llm_model_version(
        updated.get("model_version"),
        fallback_model_version=fallback_model_version,
    )
    return updated


def _is_machine_model_version(value: str) -> bool:
    if not value or len(value) > MODEL_VERSION_MAX_CHARS:
        return False
    return not any(character.isspace() for character in value)


def _compact_model_version(value: object) -> str:
    cleaned = "_".join(str(value or "").strip().split())
    if not cleaned:
        return "unknown"
    return cleaned[:MODEL_VERSION_MAX_CHARS]
