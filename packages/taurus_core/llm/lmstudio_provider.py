from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.config import DEFAULT_LMSTUDIO_BASE_URL, DEFAULT_LMSTUDIO_MODEL
from taurus_core.llm.base import (
    ANALYST_OUTPUT_JSON_SCHEMA,
    BEAR_THESIS_OUTPUT_JSON_SCHEMA,
    BULL_THESIS_OUTPUT_JSON_SCHEMA,
    FINAL_DECISION_EXPLANATION_JSON_SCHEMA,
    RESEARCH_MANAGER_OUTPUT_JSON_SCHEMA,
    TRADER_OUTPUT_JSON_SCHEMA,
    LLMBearThesisOutput,
    LLMBullThesisOutput,
    LLMFinalDecisionExplanation,
    LLMResearchManagerOutput,
    LLMTraderOutput,
    LLMProviderError,
    LLMUsageRecord,
    append_llm_usage_record,
    analyst_output_system_prompt,
    bear_thesis_system_prompt,
    bull_thesis_system_prompt,
    llm_usage_record_from_openai_response,
    portfolio_manager_system_prompt,
    research_manager_system_prompt,
    trader_system_prompt,
    parse_bear_thesis_output,
    parse_bull_thesis_output,
    parse_final_decision_explanation_output,
    parse_llm_output,
    parse_research_manager_output,
    parse_trader_output,
)


def _lmstudio_schema_response_format(
    name: str, schema: dict[str, object]
) -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": True,
            "schema": schema,
        },
    }


class LMStudioProvider:
    """OpenAI-compatible local provider for local real-model inference."""

    def __init__(
        self,
        *,
        base_url: str = DEFAULT_LMSTUDIO_BASE_URL,
        model: str = DEFAULT_LMSTUDIO_MODEL,
        timeout_seconds: int = 20,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def model_version(self) -> str:
        return f"lmstudio:{self.model}"

    def complete_analyst_report(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMAnalystOutput:
        return _openai_compatible_completion(
            base_url=self.base_url,
            api_key="lmstudio",
            model=self.model,
            model_version=self.model_version,
            agent_name=agent_name,
            symbol=symbol,
            context=context,
            timeout_seconds=self.timeout_seconds,
            response_format=_lmstudio_schema_response_format(
                "taurus_analyst_report",
                ANALYST_OUTPUT_JSON_SCHEMA,
            ),
            provider_name="LM Studio",
            usage_sink=self,
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
            api_key="lmstudio",
            model=self.model,
            model_version=self.model_version,
            agent_name=agent_name,
            symbol=symbol,
            baseline=baseline,
            evidence_pack=evidence_pack,
            timeout_seconds=self.timeout_seconds,
            response_format=_lmstudio_schema_response_format(
                "taurus_bull_thesis",
                BULL_THESIS_OUTPUT_JSON_SCHEMA,
            ),
            provider_name="LM Studio",
            usage_sink=self,
        )

    def complete_bear_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBearThesisOutput:
        return _openai_compatible_bear_thesis_completion(
            base_url=self.base_url,
            api_key="lmstudio",
            model=self.model,
            model_version=self.model_version,
            agent_name=agent_name,
            symbol=symbol,
            baseline=baseline,
            evidence_pack=evidence_pack,
            timeout_seconds=self.timeout_seconds,
            response_format=_lmstudio_schema_response_format(
                "taurus_bear_thesis",
                BEAR_THESIS_OUTPUT_JSON_SCHEMA,
            ),
            provider_name="LM Studio",
            usage_sink=self,
        )

    def complete_research_manager_summary(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMResearchManagerOutput:
        return _openai_compatible_research_manager_completion(
            base_url=self.base_url,
            api_key="lmstudio",
            model=self.model,
            model_version=self.model_version,
            agent_name=agent_name,
            symbol=symbol,
            context=context,
            timeout_seconds=self.timeout_seconds,
            response_format=_lmstudio_schema_response_format(
                "taurus_research_manager",
                RESEARCH_MANAGER_OUTPUT_JSON_SCHEMA,
            ),
            provider_name="LM Studio",
            usage_sink=self,
        )

    def complete_trader_proposal(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMTraderOutput:
        return _openai_compatible_trader_completion(
            base_url=self.base_url,
            api_key="lmstudio",
            model=self.model,
            model_version=self.model_version,
            agent_name=agent_name,
            symbol=symbol,
            context=context,
            timeout_seconds=self.timeout_seconds,
            response_format=_lmstudio_schema_response_format(
                "taurus_trader",
                TRADER_OUTPUT_JSON_SCHEMA,
            ),
            provider_name="LM Studio",
            usage_sink=self,
        )

    def complete_final_decision_explanation(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMFinalDecisionExplanation:
        return _openai_compatible_final_decision_explanation_completion(
            base_url=self.base_url,
            api_key="lmstudio",
            model=self.model,
            model_version=self.model_version,
            agent_name=agent_name,
            symbol=symbol,
            context=context,
            timeout_seconds=self.timeout_seconds,
            response_format=_lmstudio_schema_response_format(
                "taurus_final_decision",
                FINAL_DECISION_EXPLANATION_JSON_SCHEMA,
            ),
            provider_name="LM Studio",
            usage_sink=self,
        )


def _openai_compatible_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    model_version: str,
    agent_name: str,
    symbol: str,
    context: dict[str, object],
    timeout_seconds: int,
    response_format: dict[str, object] | None = None,
    provider_name: str = "LLM provider",
    usage_sink: object | None = None,
) -> LLMAnalystOutput:
    content, usage_record = _openai_compatible_chat_content(
        base_url=base_url,
        api_key=api_key,
        model=model,
        model_version=model_version,
        agent_name=agent_name,
        symbol=symbol,
        system_prompt=analyst_output_system_prompt(),
        user_payload={
            "agent_name": agent_name,
            "symbol": symbol.upper(),
            "context": context,
        },
        timeout_seconds=timeout_seconds,
        response_format=response_format,
        provider_name=provider_name,
    )
    output = parse_llm_output(str(content), fallback_model_version=model_version)
    append_llm_usage_record(usage_sink, usage_record)
    return output


def _openai_compatible_bull_thesis_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    model_version: str,
    agent_name: str,
    symbol: str,
    baseline: dict[str, object],
    evidence_pack: list[dict[str, object]],
    timeout_seconds: int,
    response_format: dict[str, object] | None = None,
    provider_name: str = "LLM provider",
    usage_sink: object | None = None,
) -> LLMBullThesisOutput:
    content, usage_record = _openai_compatible_chat_content(
        base_url=base_url,
        api_key=api_key,
        model=model,
        model_version=model_version,
        agent_name=agent_name,
        symbol=symbol,
        system_prompt=bull_thesis_system_prompt(),
        user_payload={
            "agent_name": agent_name,
            "symbol": symbol.upper(),
            "baseline": baseline,
            "evidence_pack": evidence_pack,
            "output_schema": {
                "score": "number -1..1",
                "confidence": "number 0..1",
                "key_points": "non-empty string array",
                "conditions": "non-empty string array",
                "model_version": "provider/model identifier string",
            },
        },
        timeout_seconds=timeout_seconds,
        response_format=response_format,
        provider_name=provider_name,
    )
    output = parse_bull_thesis_output(
        str(content), fallback_model_version=model_version
    )
    append_llm_usage_record(usage_sink, usage_record)
    return output


def _openai_compatible_bear_thesis_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    model_version: str,
    agent_name: str,
    symbol: str,
    baseline: dict[str, object],
    evidence_pack: list[dict[str, object]],
    timeout_seconds: int,
    response_format: dict[str, object] | None = None,
    provider_name: str = "LLM provider",
    usage_sink: object | None = None,
) -> LLMBearThesisOutput:
    content, usage_record = _openai_compatible_chat_content(
        base_url=base_url,
        api_key=api_key,
        model=model,
        model_version=model_version,
        agent_name=agent_name,
        symbol=symbol,
        system_prompt=bear_thesis_system_prompt(),
        user_payload={
            "agent_name": agent_name,
            "symbol": symbol.upper(),
            "baseline": baseline,
            "evidence_pack": evidence_pack,
            "output_schema": {
                "score": "number -1..1; Taurus guardrails force final bear thesis <= 0",
                "confidence": "number 0..1",
                "key_points": "non-empty string array",
                "risk_flags": "non-empty string array",
                "model_version": "provider/model identifier string",
            },
        },
        timeout_seconds=timeout_seconds,
        response_format=response_format,
        provider_name=provider_name,
    )
    output = parse_bear_thesis_output(
        str(content), fallback_model_version=model_version
    )
    append_llm_usage_record(usage_sink, usage_record)
    return output


def _openai_compatible_research_manager_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    model_version: str,
    agent_name: str,
    symbol: str,
    context: dict[str, object],
    timeout_seconds: int,
    response_format: dict[str, object] | None = None,
    provider_name: str = "LLM provider",
    usage_sink: object | None = None,
) -> LLMResearchManagerOutput:
    content, usage_record = _openai_compatible_chat_content(
        base_url=base_url,
        api_key=api_key,
        model=model,
        model_version=model_version,
        agent_name=agent_name,
        symbol=symbol,
        system_prompt=research_manager_system_prompt(),
        user_payload={
            "agent_name": agent_name,
            "symbol": symbol.upper(),
            "context": context,
            "output_schema": {
                "consensus_label": "bullish|mild_bullish|neutral|mild_bearish|bearish",
                "consensus_score": "number -1..1; Taurus clamps final adjustment to +/-0.1000",
                "confidence": "number 0..1; Taurus clamps final adjustment to +/-0.1000",
                "summary": "evidence-bound string",
                "unresolved_uncertainties": "non-empty evidence-bound string array",
                "model_version": "provider/model identifier string",
            },
        },
        timeout_seconds=timeout_seconds,
        response_format=response_format,
        provider_name=provider_name,
    )
    output = parse_research_manager_output(
        str(content), fallback_model_version=model_version
    )
    append_llm_usage_record(usage_sink, usage_record)
    return output


def _openai_compatible_trader_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    model_version: str,
    agent_name: str,
    symbol: str,
    context: dict[str, object],
    timeout_seconds: int,
    response_format: dict[str, object] | None = None,
    provider_name: str = "LLM provider",
    usage_sink: object | None = None,
) -> LLMTraderOutput:
    content, usage_record = _openai_compatible_chat_content(
        base_url=base_url,
        api_key=api_key,
        model=model,
        model_version=model_version,
        agent_name=agent_name,
        symbol=symbol,
        system_prompt=trader_system_prompt(),
        user_payload={
            "agent_name": agent_name,
            "symbol": symbol.upper(),
            "context": context,
            "output_schema": {
                "action": "BUY|HOLD|NO_TRADE|REDUCE|EXIT",
                "confidence": "number 0..1",
                "target_position_pct_nav": "number 0..100",
                "stop_loss_pct": "number 0..100",
                "take_profit_pct": "number 0..100",
                "reason_summary": "evidence-bound string",
                "invalid_if": "non-empty string array",
                "position_management_summary": "position lifecycle rationale string",
                "model_version": "provider/model identifier string",
            },
        },
        timeout_seconds=timeout_seconds,
        response_format=response_format,
        provider_name=provider_name,
    )
    output = parse_trader_output(str(content), fallback_model_version=model_version)
    append_llm_usage_record(usage_sink, usage_record)
    return output


def _openai_compatible_final_decision_explanation_completion(
    *,
    base_url: str,
    api_key: str,
    model: str,
    model_version: str,
    agent_name: str,
    symbol: str,
    context: dict[str, object],
    timeout_seconds: int,
    response_format: dict[str, object] | None = None,
    provider_name: str = "LLM provider",
    usage_sink: object | None = None,
) -> LLMFinalDecisionExplanation:
    content, usage_record = _openai_compatible_chat_content(
        base_url=base_url,
        api_key=api_key,
        model=model,
        model_version=model_version,
        agent_name=agent_name,
        symbol=symbol,
        system_prompt=portfolio_manager_system_prompt(),
        user_payload={
            "agent_name": agent_name,
            "symbol": symbol.upper(),
            "context": context,
            "output_schema": {
                "reason": "concise explanation string, anchored to deterministic_reason",
                "model_version": "provider/model identifier string",
            },
        },
        timeout_seconds=timeout_seconds,
        response_format=response_format,
        provider_name=provider_name,
    )
    output = parse_final_decision_explanation_output(
        str(content),
        fallback_model_version=model_version,
    )
    append_llm_usage_record(usage_sink, usage_record)
    return output


def _openai_compatible_chat_content(
    *,
    base_url: str,
    api_key: str,
    model: str,
    model_version: str,
    agent_name: str,
    symbol: str,
    system_prompt: str,
    user_payload: dict[str, object],
    timeout_seconds: int,
    response_format: dict[str, object] | None,
    provider_name: str,
) -> tuple[str, LLMUsageRecord]:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {
                "role": "user",
                "content": json.dumps(
                    user_payload,
                    sort_keys=True,
                    default=str,
                ),
            },
        ],
        "temperature": 0,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    request = Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started_at = time.perf_counter()
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMProviderError(f"{provider_name} request failed") from exc
    elapsed_seconds = time.perf_counter() - started_at

    try:
        message = response_payload["choices"][0]["message"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMProviderError(
            f"{provider_name} response did not include chat content"
        ) from exc
    content = _non_empty_string(
        message.get("content") if isinstance(message, dict) else None
    )
    if content is None and provider_name == "LM Studio" and isinstance(message, dict):
        content = _non_empty_string(message.get("reasoning_content"))
    if content is None:
        if provider_name == "LM Studio":
            raise LLMProviderError(
                "LM Studio response did not include usable message.content or fallback "
                "message.reasoning_content"
            )
        raise LLMProviderError(
            f"{provider_name} response did not include usable message.content"
        )
    usage_record = llm_usage_record_from_openai_response(
        response_payload,
        model_version=model_version,
        agent_name=agent_name,
        symbol=symbol,
        elapsed_seconds=elapsed_seconds,
    )
    return content, usage_record


def _non_empty_string(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    content = value.strip()
    if not content:
        return None
    return content


def openai_json_schema_response_format() -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "LLMAnalystOutput",
            "strict": True,
            "schema": ANALYST_OUTPUT_JSON_SCHEMA,
        },
    }


def openai_bull_thesis_json_schema_response_format() -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "LLMBullThesisOutput",
            "strict": True,
            "schema": BULL_THESIS_OUTPUT_JSON_SCHEMA,
        },
    }


def openai_bear_thesis_json_schema_response_format() -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "LLMBearThesisOutput",
            "strict": True,
            "schema": BEAR_THESIS_OUTPUT_JSON_SCHEMA,
        },
    }


def openai_research_manager_json_schema_response_format() -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "LLMResearchManagerOutput",
            "strict": True,
            "schema": RESEARCH_MANAGER_OUTPUT_JSON_SCHEMA,
        },
    }


def openai_trader_json_schema_response_format() -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "LLMTraderOutput",
            "strict": True,
            "schema": TRADER_OUTPUT_JSON_SCHEMA,
        },
    }


def openai_final_decision_explanation_json_schema_response_format() -> dict[
    str, object
]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "LLMFinalDecisionExplanation",
            "strict": True,
            "schema": FINAL_DECISION_EXPLANATION_JSON_SCHEMA,
        },
    }
