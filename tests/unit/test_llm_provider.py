from __future__ import annotations

import json

import pytest

from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.config import Settings
from taurus_core.llm import GeminiProvider, LMStudioProvider, OpenAIProvider, build_llm_provider
from taurus_core.llm.base import (
    LLMBearThesisOutput,
    LLMBullThesisOutput,
    LLMFinalDecisionExplanation,
    LLMProviderError,
    LLMResearchManagerOutput,
    LLMTraderOutput,
    parse_bear_thesis_output,
    parse_bull_thesis_output,
    parse_final_decision_explanation_output,
    parse_llm_output,
    parse_research_manager_output,
    parse_trader_output,
)


def _assert_lmstudio_response_format(
    payload: dict[str, object],
    *,
    schema_name: str,
) -> None:
    response_format = payload["response_format"]
    assert isinstance(response_format, dict)
    assert response_format["type"] == "json_schema"

    json_schema = response_format["json_schema"]
    assert isinstance(json_schema, dict)
    assert json_schema["name"] == schema_name
    assert json_schema["strict"] is True
    assert isinstance(json_schema["schema"], dict)


def test_build_llm_provider_defaults_to_lmstudio() -> None:
    provider = build_llm_provider(Settings())

    assert isinstance(provider, LMStudioProvider)
    assert provider.base_url == "http://localhost:1234/v1"
    assert provider.model == "local-model"


def test_build_llm_provider_uses_provider_specific_openai_defaults() -> None:
    provider = build_llm_provider(Settings(taurus_llm_provider="openai", openai_api_key="sk-test"))

    assert isinstance(provider, OpenAIProvider)
    assert provider.base_url == "https://api.openai.com/v1"
    assert provider.model == "gpt-5-mini"


def test_build_llm_provider_uses_provider_specific_gemini_defaults() -> None:
    provider = build_llm_provider(Settings(taurus_llm_provider="gemini", gemini_api_key="gemini-test"))

    assert isinstance(provider, GeminiProvider)
    assert provider.base_url == "https://generativelanguage.googleapis.com/v1beta"
    assert provider.model == "gemini-2.5-flash"


def test_build_llm_provider_rejects_missing_hosted_provider_credentials() -> None:
    with pytest.raises(LLMProviderError, match="OPENAI_API_KEY"):
        build_llm_provider(Settings(taurus_llm_provider="openai"))

    with pytest.raises(LLMProviderError, match="GEMINI_API_KEY"):
        build_llm_provider(Settings(taurus_llm_provider="gemini"))


def test_build_llm_provider_rejects_runtime_mock_provider() -> None:
    settings = Settings.model_construct(taurus_llm_provider="mock")

    with pytest.raises(LLMProviderError, match="Supported providers: lmstudio, openai, gemini"):
        build_llm_provider(settings)


def test_lmstudio_request_shape_and_response(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["headers"] = dict(request.header_items())
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(_chat_response("lmstudio:local-model"))

    monkeypatch.setattr("taurus_core.llm.lmstudio_provider.urlopen", fake_urlopen)
    provider = LMStudioProvider(timeout_seconds=7)

    output = provider.complete_analyst_report(
        agent_name="TechnicalAnalystAgent",
        symbol="infy",
        context={"score": "0.2", "key_points": ["momentum"], "risks": ["drawdown"]},
    )

    payload = seen["payload"]
    assert seen["url"] == "http://localhost:1234/v1/chat/completions"
    assert seen["timeout"] == 7
    assert seen["headers"]["Authorization"] == "Bearer lmstudio"
    assert payload["model"] == "local-model"
    assert payload["temperature"] == 0
    _assert_lmstudio_response_format(payload, schema_name="taurus_analyst_report")
    assert "Return JSON only" in payload["messages"][0]["content"]
    assert '"symbol": "INFY"' in payload["messages"][1]["content"]
    assert output.model_version == "lmstudio:local-model"


def test_lmstudio_bull_thesis_request_uses_dedicated_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            _chat_response(
                "lmstudio:local-model",
                payload=_bull_payload("lmstudio:local-model"),
            )
        )

    monkeypatch.setattr("taurus_core.llm.lmstudio_provider.urlopen", fake_urlopen)
    provider = LMStudioProvider()

    output = provider.complete_bull_thesis(
        agent_name="BullResearcherAgent",
        symbol="infy",
        baseline={"score": "0.1", "confidence": "0.6"},
        evidence_pack=[{"report_id": "ar-1", "source_ids": ["src-1"]}],
    )

    payload = seen["payload"]
    assert "Taurus BullResearcherAgent" in payload["messages"][0]["content"]
    _assert_lmstudio_response_format(payload, schema_name="taurus_bull_thesis")
    assert '"evidence_pack":' in payload["messages"][1]["content"]
    assert output.model_version == "lmstudio:local-model"


def test_lmstudio_bear_thesis_request_uses_dedicated_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            _chat_response(
                "lmstudio:local-model",
                payload=_bear_payload("lmstudio:local-model"),
            )
        )

    monkeypatch.setattr("taurus_core.llm.lmstudio_provider.urlopen", fake_urlopen)
    provider = LMStudioProvider()

    output = provider.complete_bear_thesis(
        agent_name="BearResearcherAgent",
        symbol="infy",
        baseline={"score": "-0.1", "confidence": "0.6"},
        evidence_pack=[{"report_id": "ar-1", "source_ids": ["src-1"]}],
    )

    payload = seen["payload"]
    assert "Taurus BearResearcherAgent" in payload["messages"][0]["content"]
    _assert_lmstudio_response_format(payload, schema_name="taurus_bear_thesis")
    assert '"risk_flags": "non-empty string array"' in payload["messages"][1]["content"]
    assert output.model_version == "lmstudio:local-model"


def test_lmstudio_research_manager_request_uses_dedicated_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            _chat_response(
                "lmstudio:local-model",
                payload=_manager_payload("lmstudio:local-model"),
            )
        )

    monkeypatch.setattr("taurus_core.llm.lmstudio_provider.urlopen", fake_urlopen)
    provider = LMStudioProvider()

    output = provider.complete_research_manager_summary(
        agent_name="ResearchManagerAgent",
        symbol="infy",
        context={"deterministic_baseline": {"consensus_score": "0.1"}},
    )

    payload = seen["payload"]
    assert "Taurus ResearchManagerAgent" in payload["messages"][0]["content"]
    _assert_lmstudio_response_format(payload, schema_name="taurus_research_manager")
    assert '"deterministic_baseline":' in payload["messages"][1]["content"]
    assert output.model_version == "lmstudio:local-model"


def test_lmstudio_final_decision_explanation_uses_dedicated_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            _chat_response(
                "lmstudio:local-model",
                payload=_final_explanation_payload("lmstudio:local-model"),
            )
        )

    monkeypatch.setattr("taurus_core.llm.lmstudio_provider.urlopen", fake_urlopen)
    provider = LMStudioProvider()

    output = provider.complete_final_decision_explanation(
        agent_name="PortfolioManagerAgent",
        symbol="infy",
        context={"deterministic_decision": {"status": "APPROVED_FOR_PAPER"}},
    )

    payload = seen["payload"]
    assert "Taurus PortfolioManagerAgent" in payload["messages"][0]["content"]
    _assert_lmstudio_response_format(payload, schema_name="taurus_final_decision")
    assert '"deterministic_decision":' in payload["messages"][1]["content"]
    assert output.model_version == "lmstudio:local-model"


def test_openai_request_shape_uses_bearer_auth_and_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["url"] = request.full_url
        seen["headers"] = dict(request.header_items())
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(_chat_response("openai:gpt-5-mini"))

    monkeypatch.setattr("taurus_core.llm.lmstudio_provider.urlopen", fake_urlopen)
    provider = OpenAIProvider(api_key="sk-test")

    output = provider.complete_analyst_report(
        agent_name="NewsAnalystAgent",
        symbol="INFY",
        context={"score": "0.1", "key_points": ["news"], "risks": ["source quality"]},
    )

    payload = seen["payload"]
    assert seen["url"] == "https://api.openai.com/v1/chat/completions"
    assert seen["headers"]["Authorization"] == "Bearer sk-test"
    assert payload["model"] == "gpt-5-mini"
    assert payload["temperature"] == 0
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["name"] == "LLMAnalystOutput"
    assert output.model_version == "openai:gpt-5-mini"


def test_openai_bull_thesis_request_uses_strict_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            _chat_response(
                "openai:gpt-5-mini",
                payload=_bull_payload("openai:gpt-5-mini"),
            )
        )

    monkeypatch.setattr("taurus_core.llm.lmstudio_provider.urlopen", fake_urlopen)
    provider = OpenAIProvider(api_key="sk-test")

    output = provider.complete_bull_thesis(
        agent_name="BullResearcherAgent",
        symbol="INFY",
        baseline={"score": "0.1", "confidence": "0.6"},
        evidence_pack=[{"report_id": "ar-1", "source_ids": ["src-1"]}],
    )

    payload = seen["payload"]
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["name"] == "LLMBullThesisOutput"
    assert output.model_version == "openai:gpt-5-mini"


def test_openai_bear_thesis_request_uses_strict_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            _chat_response(
                "openai:gpt-5-mini",
                payload=_bear_payload("openai:gpt-5-mini"),
            )
        )

    monkeypatch.setattr("taurus_core.llm.lmstudio_provider.urlopen", fake_urlopen)
    provider = OpenAIProvider(api_key="sk-test")

    output = provider.complete_bear_thesis(
        agent_name="BearResearcherAgent",
        symbol="INFY",
        baseline={"score": "-0.1", "confidence": "0.6"},
        evidence_pack=[{"report_id": "ar-1", "source_ids": ["src-1"]}],
    )

    payload = seen["payload"]
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["name"] == "LLMBearThesisOutput"
    assert output.model_version == "openai:gpt-5-mini"


def test_openai_research_manager_request_uses_strict_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            _chat_response(
                "openai:gpt-5-mini",
                payload=_manager_payload("openai:gpt-5-mini"),
            )
        )

    monkeypatch.setattr("taurus_core.llm.lmstudio_provider.urlopen", fake_urlopen)
    provider = OpenAIProvider(api_key="sk-test")

    output = provider.complete_research_manager_summary(
        agent_name="ResearchManagerAgent",
        symbol="INFY",
        context={"deterministic_baseline": {"consensus_score": "0.1"}},
    )

    payload = seen["payload"]
    assert payload["response_format"]["type"] == "json_schema"
    assert payload["response_format"]["json_schema"]["name"] == "LLMResearchManagerOutput"
    assert output.model_version == "openai:gpt-5-mini"


def test_openai_final_decision_explanation_uses_strict_json_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            _chat_response(
                "openai:gpt-5-mini",
                payload=_final_explanation_payload("openai:gpt-5-mini"),
            )
        )

    monkeypatch.setattr("taurus_core.llm.lmstudio_provider.urlopen", fake_urlopen)
    provider = OpenAIProvider(api_key="sk-test")

    output = provider.complete_final_decision_explanation(
        agent_name="PortfolioManagerAgent",
        symbol="INFY",
        context={"deterministic_decision": {"status": "NO_ACTION"}},
    )

    payload = seen["payload"]
    assert payload["response_format"]["type"] == "json_schema"
    assert (
        payload["response_format"]["json_schema"]["name"]
        == "LLMFinalDecisionExplanation"
    )
    assert output.model_version == "openai:gpt-5-mini"


def test_gemini_request_shape_uses_api_key_header_and_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        seen["headers"] = dict(request.header_items())
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [{"text": json.dumps(_analyst_payload("gemini:gemini-2.5-flash"))}]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("taurus_core.llm.gemini_provider.urlopen", fake_urlopen)
    provider = GeminiProvider(api_key="gemini-test", timeout_seconds=9)

    output = provider.complete_analyst_report(
        agent_name="SentimentAnalystAgent",
        symbol="infy",
        context={"score": "0", "key_points": ["flat"], "risks": ["noise"]},
    )

    payload = seen["payload"]
    assert seen["url"] == (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-2.5-flash:generateContent"
    )
    assert seen["timeout"] == 9
    assert seen["headers"]["X-goog-api-key"] == "gemini-test"
    assert payload["generationConfig"]["temperature"] == 0
    assert payload["generationConfig"]["responseMimeType"] == "application/json"
    assert payload["generationConfig"]["responseJsonSchema"]["required"][-1] == "model_version"
    assert '"symbol": "INFY"' in payload["contents"][0]["parts"][0]["text"]
    assert output.model_version == "gemini:gemini-2.5-flash"


def test_gemini_bull_thesis_request_uses_dedicated_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps(_bull_payload("gemini:gemini-2.5-flash"))}
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("taurus_core.llm.gemini_provider.urlopen", fake_urlopen)
    provider = GeminiProvider(api_key="gemini-test")

    output = provider.complete_bull_thesis(
        agent_name="BullResearcherAgent",
        symbol="infy",
        baseline={"score": "0.1", "confidence": "0.6"},
        evidence_pack=[{"report_id": "ar-1", "source_ids": ["src-1"]}],
    )

    payload = seen["payload"]
    assert "Taurus BullResearcherAgent" in payload["systemInstruction"]["parts"][0]["text"]
    assert payload["generationConfig"]["responseJsonSchema"]["required"][-1] == "model_version"
    assert '"symbol": "INFY"' in payload["contents"][0]["parts"][0]["text"]
    assert output.model_version == "gemini:gemini-2.5-flash"


def test_gemini_bear_thesis_request_uses_dedicated_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps(_bear_payload("gemini:gemini-2.5-flash"))}
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("taurus_core.llm.gemini_provider.urlopen", fake_urlopen)
    provider = GeminiProvider(api_key="gemini-test")

    output = provider.complete_bear_thesis(
        agent_name="BearResearcherAgent",
        symbol="infy",
        baseline={"score": "-0.1", "confidence": "0.6"},
        evidence_pack=[{"report_id": "ar-1", "source_ids": ["src-1"]}],
    )

    payload = seen["payload"]
    assert "Taurus BearResearcherAgent" in payload["systemInstruction"]["parts"][0]["text"]
    assert payload["generationConfig"]["responseJsonSchema"]["required"][-1] == "model_version"
    assert '"symbol": "INFY"' in payload["contents"][0]["parts"][0]["text"]
    assert output.model_version == "gemini:gemini-2.5-flash"


def test_gemini_research_manager_request_uses_dedicated_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {"text": json.dumps(_manager_payload("gemini:gemini-2.5-flash"))}
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("taurus_core.llm.gemini_provider.urlopen", fake_urlopen)
    provider = GeminiProvider(api_key="gemini-test")

    output = provider.complete_research_manager_summary(
        agent_name="ResearchManagerAgent",
        symbol="infy",
        context={"deterministic_baseline": {"consensus_score": "0.1"}},
    )

    payload = seen["payload"]
    assert "Taurus ResearchManagerAgent" in payload["systemInstruction"]["parts"][0]["text"]
    assert payload["generationConfig"]["responseJsonSchema"]["required"][-1] == "model_version"
    assert '"symbol": "INFY"' in payload["contents"][0]["parts"][0]["text"]
    assert output.model_version == "gemini:gemini-2.5-flash"


def test_gemini_final_decision_explanation_uses_dedicated_schema(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, object] = {}

    def fake_urlopen(request, timeout: int):
        seen["payload"] = json.loads(request.data.decode("utf-8"))
        return _Response(
            {
                "candidates": [
                    {
                        "content": {
                            "parts": [
                                {
                                    "text": json.dumps(
                                        _final_explanation_payload(
                                            "gemini:gemini-2.5-flash"
                                        )
                                    )
                                }
                            ]
                        }
                    }
                ]
            }
        )

    monkeypatch.setattr("taurus_core.llm.gemini_provider.urlopen", fake_urlopen)
    provider = GeminiProvider(api_key="gemini-test")

    output = provider.complete_final_decision_explanation(
        agent_name="PortfolioManagerAgent",
        symbol="infy",
        context={"deterministic_decision": {"status": "BLOCKED"}},
    )

    payload = seen["payload"]
    assert "Taurus PortfolioManagerAgent" in payload["systemInstruction"]["parts"][0]["text"]
    assert payload["generationConfig"]["responseJsonSchema"]["required"] == [
        "reason",
        "model_version",
    ]
    assert '"symbol": "INFY"' in payload["contents"][0]["parts"][0]["text"]
    assert output.model_version == "gemini:gemini-2.5-flash"


def test_llm_output_parser_rejects_invalid_schema() -> None:
    with pytest.raises(LLMProviderError):
        parse_llm_output(
            '{"score": 2, "confidence": 0.5, "stance": "bullish", '
            '"horizon": "short", "key_points": ["x"], "risks": ["y"]}',
            fallback_model_version="bad",
        )


def test_bull_thesis_parser_rejects_invalid_schema() -> None:
    with pytest.raises(LLMProviderError):
        parse_bull_thesis_output(
            '{"score": 2, "confidence": 0.5, "key_points": ["x"], "conditions": ["y"]}',
            fallback_model_version="bad",
        )


def test_bear_thesis_parser_rejects_invalid_schema() -> None:
    with pytest.raises(LLMProviderError):
        parse_bear_thesis_output(
            '{"score": 2, "confidence": 0.5, "key_points": ["x"], "risk_flags": ["y"]}',
            fallback_model_version="bad",
        )


def test_research_manager_parser_rejects_invalid_schema() -> None:
    with pytest.raises(LLMProviderError):
        parse_research_manager_output(
            '{"consensus_label": "bullish", "consensus_score": 2, '
            '"confidence": 0.5, "summary": "x", "unresolved_uncertainties": ["y"]}',
            fallback_model_version="bad",
        )


def test_final_decision_explanation_parser_rejects_invalid_schema() -> None:
    with pytest.raises(LLMProviderError):
        parse_final_decision_explanation_output(
            '{"reason": "", "model_version": "bad"}',
            fallback_model_version="bad",
        )


def test_trader_parser_replaces_verbose_model_version_with_provider_identifier() -> None:
    payload = _trader_payload(
        "research_consensus_v1: TraderAgent processed GraphAnalyst inputs with debate synthesis."
    )

    output = parse_trader_output(
        json.dumps(payload),
        fallback_model_version="lmstudio:qwen/qwq-32b",
    )

    assert output.model_version == "lmstudio:qwen/qwq-32b"


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _chat_response(
    model_version: str,
    *,
    payload: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(payload or _analyst_payload(model_version)),
                }
            }
        ]
    }


def _analyst_payload(model_version: str) -> dict[str, object]:
    return LLMAnalystOutput(
        score="0.25",
        confidence="0.75",
        stance="bullish",
        horizon="medium",
        key_points=["Schema-valid provider output."],
        risks=["Provider output requires review."],
        model_version=model_version,
    ).model_dump(mode="json")


def _bull_payload(model_version: str) -> dict[str, object]:
    return LLMBullThesisOutput(
        score="0.25",
        confidence="0.75",
        key_points=["TechnicalAnalystAgent: src-1 supports the bull thesis."],
        conditions=["TechnicalAnalystAgent: src-1 must remain supportive."],
        model_version=model_version,
    ).model_dump(mode="json")


def _bear_payload(model_version: str) -> dict[str, object]:
    return LLMBearThesisOutput(
        score="-0.25",
        confidence="0.75",
        key_points=["NewsAnalystAgent: src-1 challenges the bull thesis."],
        risk_flags=["NewsAnalystAgent: src-1 remains a downside risk."],
        model_version=model_version,
    ).model_dump(mode="json")


def _manager_payload(model_version: str) -> dict[str, object]:
    return LLMResearchManagerOutput(
        consensus_label="mild_bullish",
        consensus_score="0.20",
        confidence="0.75",
        summary="TechnicalAnalystAgent: src-1 keeps the manager consensus evidence-bound.",
        unresolved_uncertainties=["NewsAnalystAgent: src-1 remains an unresolved uncertainty."],
        model_version=model_version,
    ).model_dump(mode="json")


def _trader_payload(model_version: str) -> dict[str, object]:
    return LLMTraderOutput(
        action="NO_TRADE",
        confidence="0.75",
        target_position_pct_nav="0",
        stop_loss_pct="6",
        take_profit_pct="12",
        reason_summary="Schema-valid trader output.",
        invalid_if=["Provider output requires review."],
        position_management_summary="Lifecycle summary remains paper-only.",
        model_version=model_version,
    ).model_dump(mode="json")


def _final_explanation_payload(model_version: str) -> dict[str, object]:
    return LLMFinalDecisionExplanation(
        reason="Deterministic final approval remains paper-only and risk-gated.",
        model_version=model_version,
    ).model_dump(mode="json")
