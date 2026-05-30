from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.config import DEFAULT_GEMINI_BASE_URL, DEFAULT_GEMINI_MODEL
from taurus_core.llm.base import (
    ANALYST_OUTPUT_JSON_SCHEMA,
    BULL_THESIS_OUTPUT_JSON_SCHEMA,
    LLMBullThesisOutput,
    LLMProviderError,
    analyst_output_system_prompt,
    bull_thesis_system_prompt,
    parse_bull_thesis_output,
    parse_llm_output,
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
            raise LLMProviderError("GEMINI_API_KEY is required for TAURUS_LLM_PROVIDER=gemini")
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    @property
    def model_version(self) -> str:
        return f"gemini:{self.model}"

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
        request = Request(
            f"{self.base_url}/models/{quote(self.model, safe='')}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMProviderError("Gemini request failed") from exc

        try:
            content = response_payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("Gemini response did not include generated JSON text") from exc
        return parse_llm_output(str(content), fallback_model_version=self.model_version)

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
        request = Request(
            f"{self.base_url}/models/{quote(self.model, safe='')}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": self.api_key,
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise LLMProviderError("Gemini request failed") from exc

        try:
            content = response_payload["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMProviderError("Gemini response did not include generated JSON text") from exc
        return parse_bull_thesis_output(str(content), fallback_model_version=self.model_version)
