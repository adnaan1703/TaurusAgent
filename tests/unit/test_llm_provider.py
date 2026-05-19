from __future__ import annotations

import pytest

from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.llm.base import LLMProviderError, parse_llm_output
from taurus_core.llm.mock_provider import MockLLMProvider


def test_mock_llm_provider_returns_schema_valid_output() -> None:
    output = MockLLMProvider().complete_analyst_report(
        agent_name="NewsAnalystAgent",
        symbol="INFY",
        context={
            "score": "0.25",
            "confidence": "0.75",
            "horizon": "medium",
            "key_points": ["Infosys has a positive mock event."],
            "risks": ["Mock event feed only."],
        },
    )

    validated = LLMAnalystOutput.model_validate(output.model_dump())

    assert validated.score > 0
    assert validated.stance == "bullish"
    assert validated.model_version == "mock-llm-v1"


def test_llm_output_parser_rejects_invalid_schema() -> None:
    with pytest.raises(LLMProviderError):
        parse_llm_output(
            '{"score": 2, "confidence": 0.5, "stance": "bullish", '
            '"horizon": "short", "key_points": ["x"], "risks": ["y"]}',
            fallback_model_version="bad",
        )
