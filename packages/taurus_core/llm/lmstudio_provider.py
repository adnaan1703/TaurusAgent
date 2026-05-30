from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.config import DEFAULT_LMSTUDIO_BASE_URL, DEFAULT_LMSTUDIO_MODEL
from taurus_core.llm.base import (
    ANALYST_OUTPUT_JSON_SCHEMA,
    LLMProviderError,
    analyst_output_system_prompt,
    parse_llm_output,
)


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
            response_format={"type": "json_object"},
            provider_name="LM Studio",
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
) -> LLMAnalystOutput:
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": analyst_output_system_prompt(),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "agent_name": agent_name,
                        "symbol": symbol.upper(),
                        "context": context,
                    },
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
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise LLMProviderError(f"{provider_name} request failed") from exc

    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise LLMProviderError(f"{provider_name} response did not include chat content") from exc
    return parse_llm_output(str(content), fallback_model_version=model_version)


def openai_json_schema_response_format() -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": "LLMAnalystOutput",
            "strict": True,
            "schema": ANALYST_OUTPUT_JSON_SCHEMA,
        },
    }
