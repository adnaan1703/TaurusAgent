from __future__ import annotations

import json
import time
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.config import DEFAULT_GEMINI_BASE_URL, DEFAULT_GEMINI_MODEL
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
    llm_usage_record_from_gemini_response,
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


class GeminiProvider:
    """Gemini native REST provider using API-key billing."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str = DEFAULT_GEMINI_BASE_URL,
        model: str = DEFAULT_GEMINI_MODEL,
        timeout_seconds: int = 20,
    ) -> None:
        if not api_key:
            raise LLMProviderError(
                "GEMINI_API_KEY is required for TAURUS_LLM_PROVIDER=gemini"
            )
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def model_version(self) -> str:
        return f"gemini:{self.model}"

    def _generate_content(
        self,
        payload: dict[str, object],
        *,
        agent_name: str,
        symbol: str,
    ) -> tuple[str, LLMUsageRecord]:
        request = Request(
            f"{self.base_url}/models/{quote(self.model, safe='')}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        started_at = time.perf_counter()
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMProviderError("Gemini request failed") from exc
        elapsed_seconds = time.perf_counter() - started_at

        try:
            content = response_payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError(
                "Gemini response did not include generated JSON text"
            ) from exc
        usage_record = llm_usage_record_from_gemini_response(
            response_payload,
            model_version=self.model_version,
            agent_name=agent_name,
            symbol=symbol,
            elapsed_seconds=elapsed_seconds,
        )
        return str(content), usage_record

    def complete_analyst_report(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMAnalystOutput:
        payload = {
            "systemInstruction": {
                "parts": [{"text": analyst_output_system_prompt()}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "agent_name": agent_name,
                                    "symbol": symbol.upper(),
                                    "context": context,
                                },
                                sort_keys=True,
                                default=str,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": ANALYST_OUTPUT_JSON_SCHEMA,
            },
        }
        content, usage_record = self._generate_content(
            payload,
            agent_name=agent_name,
            symbol=symbol,
        )
        output = parse_llm_output(
            str(content), fallback_model_version=self.model_version
        )
        append_llm_usage_record(self, usage_record)
        return output

    def complete_bull_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBullThesisOutput:
        payload = {
            "systemInstruction": {
                "parts": [{"text": bull_thesis_system_prompt()}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
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
                                sort_keys=True,
                                default=str,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": BULL_THESIS_OUTPUT_JSON_SCHEMA,
            },
        }
        content, usage_record = self._generate_content(
            payload,
            agent_name=agent_name,
            symbol=symbol,
        )
        output = parse_bull_thesis_output(
            str(content), fallback_model_version=self.model_version
        )
        append_llm_usage_record(self, usage_record)
        return output

    def complete_bear_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBearThesisOutput:
        payload = {
            "systemInstruction": {
                "parts": [{"text": bear_thesis_system_prompt()}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "agent_name": agent_name,
                                    "symbol": symbol.upper(),
                                    "baseline": baseline,
                                    "evidence_pack": evidence_pack,
                                    "output_schema": {
                                        "score": (
                                            "number -1..1; Taurus guardrails force final "
                                            "bear thesis <= 0"
                                        ),
                                        "confidence": "number 0..1",
                                        "key_points": "non-empty string array",
                                        "risk_flags": "non-empty string array",
                                        "model_version": "provider/model identifier string",
                                    },
                                },
                                sort_keys=True,
                                default=str,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": BEAR_THESIS_OUTPUT_JSON_SCHEMA,
            },
        }
        content, usage_record = self._generate_content(
            payload,
            agent_name=agent_name,
            symbol=symbol,
        )
        output = parse_bear_thesis_output(
            str(content), fallback_model_version=self.model_version
        )
        append_llm_usage_record(self, usage_record)
        return output

    def complete_research_manager_summary(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMResearchManagerOutput:
        payload = {
            "systemInstruction": {
                "parts": [{"text": research_manager_system_prompt()}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "agent_name": agent_name,
                                    "symbol": symbol.upper(),
                                    "context": context,
                                    "output_schema": {
                                        "consensus_label": (
                                            "bullish|mild_bullish|neutral|"
                                            "mild_bearish|bearish"
                                        ),
                                        "consensus_score": (
                                            "number -1..1; Taurus clamps final "
                                            "adjustment to +/-0.1000"
                                        ),
                                        "confidence": (
                                            "number 0..1; Taurus clamps final "
                                            "adjustment to +/-0.1000"
                                        ),
                                        "summary": "evidence-bound string",
                                        "unresolved_uncertainties": (
                                            "non-empty evidence-bound string array"
                                        ),
                                        "model_version": "provider/model identifier string",
                                    },
                                },
                                sort_keys=True,
                                default=str,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": RESEARCH_MANAGER_OUTPUT_JSON_SCHEMA,
            },
        }
        content, usage_record = self._generate_content(
            payload,
            agent_name=agent_name,
            symbol=symbol,
        )
        output = parse_research_manager_output(
            str(content), fallback_model_version=self.model_version
        )
        append_llm_usage_record(self, usage_record)
        return output

    def complete_trader_proposal(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMTraderOutput:
        payload = {
            "systemInstruction": {
                "parts": [{"text": trader_system_prompt()}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
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
                                        "position_management_summary": (
                                            "position lifecycle rationale string"
                                        ),
                                        "model_version": "provider/model identifier string",
                                    },
                                },
                                sort_keys=True,
                                default=str,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": TRADER_OUTPUT_JSON_SCHEMA,
            },
        }
        content, usage_record = self._generate_content(
            payload,
            agent_name=agent_name,
            symbol=symbol,
        )
        output = parse_trader_output(
            str(content), fallback_model_version=self.model_version
        )
        append_llm_usage_record(self, usage_record)
        return output

    def complete_final_decision_explanation(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMFinalDecisionExplanation:
        payload = {
            "systemInstruction": {
                "parts": [{"text": portfolio_manager_system_prompt()}],
            },
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {
                            "text": json.dumps(
                                {
                                    "agent_name": agent_name,
                                    "symbol": symbol.upper(),
                                    "context": context,
                                    "output_schema": {
                                        "reason": (
                                            "concise explanation string, anchored to "
                                            "deterministic_reason"
                                        ),
                                        "model_version": "provider/model identifier string",
                                    },
                                },
                                sort_keys=True,
                                default=str,
                            )
                        }
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": FINAL_DECISION_EXPLANATION_JSON_SCHEMA,
            },
        }
        content, usage_record = self._generate_content(
            payload,
            agent_name=agent_name,
            symbol=symbol,
        )
        output = parse_final_decision_explanation_output(
            str(content),
            fallback_model_version=self.model_version,
        )
        append_llm_usage_record(self, usage_record)
        return output
