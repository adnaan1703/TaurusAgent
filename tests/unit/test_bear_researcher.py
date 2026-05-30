from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from taurus_core.agents.bear_researcher import BearResearcherAgent
from taurus_core.agents.schemas import AnalystReport
from taurus_core.llm.base import LLMBearThesisOutput, LLMProviderError
from taurus_core.observability.metrics import current_llm_failure_count


def test_run_rules_preserves_current_deterministic_baseline() -> None:
    thesis = BearResearcherAgent()._run_rules(symbol="infy", reports=_reports())

    assert thesis.symbol == "INFY"
    assert thesis.score == Decimal("-0.1069")
    assert thesis.confidence == Decimal("0.6964")
    assert thesis.source_report_ids == ["ar-bear", "ar-tech"]
    assert thesis.key_points[0] == "NewsAnalystAgent: Guidance risk could pressure the setup."
    assert thesis.risk_flags[0] == "NewsAnalystAgent has bearish score -0.20."


def test_llm_bear_output_is_guarded_and_preserves_taurus_owned_fields() -> None:
    thesis = BearResearcherAgent(llm_provider=_BearProvider(score="-0.9000", confidence="0.9900")).run(
        symbol="infy",
        reports=_reports(),
    )

    assert thesis.symbol == "INFY"
    assert thesis.score == Decimal("-0.2069")
    assert thesis.confidence == Decimal("0.7964")
    assert thesis.source_report_ids == ["ar-bear", "ar-tech"]
    assert thesis.key_points == [
        "NewsAnalystAgent: src-news guidance risk challenges the bull thesis."
    ]
    assert thesis.risk_flags == [
        "NewsAnalystAgent: src-news guidance risk remains an explicit downside flag."
    ]


def test_llm_score_cannot_make_bear_thesis_bullish() -> None:
    thesis = BearResearcherAgent(llm_provider=_BearProvider(score="0.9000")).run(
        symbol="INFY",
        reports=_reports(),
    )

    assert thesis.score == Decimal("-0.0069")
    assert thesis.score <= Decimal("0.0000")


def test_llm_text_falls_back_when_not_bound_to_evidence() -> None:
    reports = _reports()
    baseline = BearResearcherAgent()._run_rules(symbol="INFY", reports=reports)

    thesis = BearResearcherAgent(
        llm_provider=_BearProvider(
            key_points=["Valuation stretched."],
            risk_flags=["Opaque premise."],
        )
    ).run(symbol="INFY", reports=reports)

    assert thesis.key_points == baseline.key_points
    assert thesis.risk_flags == baseline.risk_flags


def test_missing_provider_records_metric_and_raises() -> None:
    before = current_llm_failure_count()

    with pytest.raises(LLMProviderError, match="requires an LLM provider"):
        BearResearcherAgent().run(symbol="INFY", reports=_reports())

    assert current_llm_failure_count() == before + 1


def test_provider_failure_records_metric_and_raises() -> None:
    before = current_llm_failure_count()

    with pytest.raises(LLMProviderError, match="BearResearcherAgent LLM provider failed"):
        BearResearcherAgent(llm_provider=_FailingBearProvider()).run(
            symbol="INFY",
            reports=_reports(),
        )

    assert current_llm_failure_count() == before + 1


def test_invalid_provider_schema_records_metric_and_raises() -> None:
    before = current_llm_failure_count()

    with pytest.raises(LLMProviderError, match="BearResearcherAgent LLM provider failed"):
        BearResearcherAgent(llm_provider=_InvalidBearProvider()).run(
            symbol="INFY",
            reports=_reports(),
        )

    assert current_llm_failure_count() == before + 1


class _BearProvider:
    model_version = "test-bear-provider:v1"

    def __init__(
        self,
        *,
        score: str = "-0.2000",
        confidence: str = "0.8000",
        key_points: list[str] | None = None,
        risk_flags: list[str] | None = None,
    ) -> None:
        self.score = Decimal(score)
        self.confidence = Decimal(confidence)
        self.key_points = key_points or [
            "NewsAnalystAgent: src-news guidance risk challenges the bull thesis."
        ]
        self.risk_flags = risk_flags or [
            "NewsAnalystAgent: src-news guidance risk remains an explicit downside flag."
        ]

    def complete_bear_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBearThesisOutput:
        return LLMBearThesisOutput(
            score=self.score,
            confidence=self.confidence,
            key_points=self.key_points,
            risk_flags=self.risk_flags,
            model_version=self.model_version,
        )


class _FailingBearProvider:
    model_version = "test-bear-provider:failure"

    def complete_bear_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBearThesisOutput:
        raise LLMProviderError("provider unavailable")


class _InvalidBearProvider:
    model_version = "test-bear-provider:invalid"

    def complete_bear_thesis(
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
