from __future__ import annotations

import json

import pytest

from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.config import Settings
from taurus_core.llm import GeminiProvider, LMStudioProvider, OpenAIProvider, build_llm_provider
from taurus_core.llm.base import LLMProviderError, parse_llm_output


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
    assert payload["response_format"] == {"type": "json_object"}
    assert "Return JSON only" in payload["messages"][0]["content"]
    assert '"symbol": "INFY"' in payload["messages"][1]["content"]
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


def test_llm_output_parser_rejects_invalid_schema() -> None:
    with pytest.raises(LLMProviderError):
        parse_llm_output(
            '{"score": 2, "confidence": 0.5, "stance": "bullish", '
            '"horizon": "short", "key_points": ["x"], "risks": ["y"]}',
            fallback_model_version="bad",
        )


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


def _chat_response(model_version: str) -> dict[str, object]:
    return {
        "choices": [
            {
                "message": {
                    "content": json.dumps(_analyst_payload(model_version)),
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
