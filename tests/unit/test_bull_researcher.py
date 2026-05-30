from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from taurus_core.agents.bull_researcher import BullResearcherAgent
from taurus_core.agents.schemas import AnalystReport
from taurus_core.llm.base import LLMBullThesisOutput, LLMProviderError
from taurus_core.observability.metrics import current_llm_failure_count


def test_run_rules_preserves_current_deterministic_baseline() -> None:
    thesis = BullResearcherAgent()._run_rules(symbol="infy", reports=_reports())

    assert thesis.symbol == "INFY"
    assert thesis.score == Decimal("0.1577")
    assert thesis.confidence == Decimal("0.7415")
    assert thesis.source_report_ids == ["ar-bear", "ar-tech"]
    assert thesis.key_points[0] == "TechnicalAnalystAgent: Momentum improved above the 20 day average."


def test_llm_bull_output_is_guarded_and_preserves_taurus_owned_fields() -> None:
    thesis = BullResearcherAgent(llm_provider=_BullProvider(score="0.9000", confidence="0.9900")).run(
        symbol="infy",
        reports=_reports(),
    )

    assert thesis.symbol == "INFY"
    assert thesis.score == Decimal("0.2577")
    assert thesis.confidence == Decimal("0.8415")
    assert thesis.source_report_ids == ["ar-bear", "ar-tech"]
    assert thesis.key_points == [
        "TechnicalAnalystAgent: src-tech momentum supports the bull thesis."
    ]
    assert thesis.conditions == [
        "TechnicalAnalystAgent: bull thesis fails if src-tech momentum deteriorates."
    ]


def test_llm_text_falls_back_when_not_bound_to_evidence() -> None:
    reports = _reports()
    baseline = BullResearcherAgent()._run_rules(symbol="INFY", reports=reports)

    thesis = BullResearcherAgent(
        llm_provider=_BullProvider(
            key_points=["This is a great opportunity."],
            conditions=["Wait for confirmation."],
        )
    ).run(symbol="INFY", reports=reports)

    assert thesis.key_points == baseline.key_points
    assert thesis.conditions == baseline.conditions


def test_missing_provider_records_metric_and_raises() -> None:
    before = current_llm_failure_count()

    with pytest.raises(LLMProviderError, match="requires an LLM provider"):
        BullResearcherAgent().run(symbol="INFY", reports=_reports())

    assert current_llm_failure_count() == before + 1


def test_provider_failure_records_metric_and_raises() -> None:
    before = current_llm_failure_count()

    with pytest.raises(LLMProviderError, match="BullResearcherAgent LLM provider failed"):
        BullResearcherAgent(llm_provider=_FailingBullProvider()).run(
            symbol="INFY",
            reports=_reports(),
        )

    assert current_llm_failure_count() == before + 1


def test_invalid_provider_schema_records_metric_and_raises() -> None:
    before = current_llm_failure_count()

    with pytest.raises(LLMProviderError, match="BullResearcherAgent LLM provider failed"):
        BullResearcherAgent(llm_provider=_InvalidBullProvider()).run(
            symbol="INFY",
            reports=_reports(),
        )

    assert current_llm_failure_count() == before + 1


class _BullProvider:
    model_version = "test-bull-provider:v1"

    def __init__(
        self,
        *,
        score: str = "0.2000",
        confidence: str = "0.8000",
        key_points: list[str] | None = None,
        conditions: list[str] | None = None,
    ) -> None:
        self.score = Decimal(score)
        self.confidence = Decimal(confidence)
        self.key_points = key_points or [
            "TechnicalAnalystAgent: src-tech momentum supports the bull thesis."
        ]
        self.conditions = conditions or [
            "TechnicalAnalystAgent: bull thesis fails if src-tech momentum deteriorates."
        ]

    def complete_bull_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBullThesisOutput:
        return LLMBullThesisOutput(
            score=self.score,
            confidence=self.confidence,
            key_points=self.key_points,
            conditions=self.conditions,
            model_version=self.model_version,
        )


class _FailingBullProvider:
    model_version = "test-bull-provider:failure"

    def complete_bull_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBullThesisOutput:
        raise LLMProviderError("provider unavailable")


class _InvalidBullProvider:
    model_version = "test-bull-provider:invalid"

    def complete_bull_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> object:
        return {"score": "2", "confidence": "0.5"}


def _reports() -> list[AnalystReport]:
    as_of = datetime(2026, 5, 30, tzinfo=timezone.utc)
    return [
        AnalystReport(
            report_id="ar-tech",
            run_id="run-test",
            symbol="INFY",
            agent_name="TechnicalAnalystAgent",
            as_of=as_of,
            score=Decimal("0.30"),
            confidence=Decimal("0.80"),
            stance="bullish",
            horizon="short",
            key_points=["Momentum improved above the 20 day average."],
            risks=["Momentum could reverse on weak volume."],
            source_ids=["src-tech"],
            model_version="technical-test",
        ),
        AnalystReport(
            report_id="ar-bear",
            run_id="run-test",
            symbol="INFY",
            agent_name="NewsAnalystAgent",
            as_of=as_of,
            score=Decimal("-0.20"),
            confidence=Decimal("0.50"),
            stance="bearish",
            horizon="short",
            key_points=["Weak guidance remains a near term concern."],
            risks=["Guidance risk could pressure the setup."],
            source_ids=["src-news"],
            model_version="news-test",
        ),
    ]
