from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from taurus_core.agents.research_manager import ResearchManagerAgent
from taurus_core.agents.schemas import AnalystReport
from taurus_core.llm.base import LLMProviderError, LLMResearchManagerOutput
from taurus_core.observability.metrics import current_llm_failure_count
from taurus_core.research.schemas import BearThesis, BullThesis, DebateRound


def test_run_rules_preserves_current_deterministic_baseline() -> None:
    summary = ResearchManagerAgent()._run_rules(
        symbol="infy",
        reports=_reports(),
        bull_thesis=_bull_thesis(),
        bear_thesis=_bear_thesis(),
        rounds=_rounds(),
    )

    assert summary.consensus_label == "neutral"
    assert summary.consensus_score == Decimal("0.0996")
    assert summary.confidence == Decimal("0.6380")
    assert summary.summary == (
        "INFY research consensus is neutral with score 0.0996 after 2 debate rounds."
    )
    assert summary.unresolved_uncertainties == [
        "Guidance risk remains active while src-news evidence persists."
    ]


def test_llm_manager_output_is_guarded_and_label_is_recomputed() -> None:
    summary = ResearchManagerAgent(
        llm_provider=_ManagerProvider(
            consensus_label="bearish",
            consensus_score="0.9000",
            confidence="0.9900",
        )
    ).run(
        symbol="infy",
        reports=_reports(),
        bull_thesis=_bull_thesis(),
        bear_thesis=_bear_thesis(),
        rounds=_rounds(),
    )

    assert summary.consensus_score == Decimal("0.1996")
    assert summary.confidence == Decimal("0.7380")
    assert summary.consensus_label == "mild_bullish"
    assert summary.summary == (
        "TechnicalAnalystAgent: src-tech momentum outweighs NewsAnalystAgent src-news risks."
    )
    assert summary.unresolved_uncertainties == [
        "NewsAnalystAgent: src-news guidance risk is still unresolved."
    ]


def test_llm_text_falls_back_when_not_bound_to_evidence() -> None:
    reports = _reports()
    baseline = ResearchManagerAgent()._run_rules(
        symbol="INFY",
        reports=reports,
        bull_thesis=_bull_thesis(),
        bear_thesis=_bear_thesis(),
        rounds=_rounds(),
    )

    summary = ResearchManagerAgent(
        llm_provider=_ManagerProvider(
            summary="The idea looks interesting.",
            unresolved_uncertainties=["Watch for anything unusual."],
        )
    ).run(
        symbol="INFY",
        reports=reports,
        bull_thesis=_bull_thesis(),
        bear_thesis=_bear_thesis(),
        rounds=_rounds(),
    )

    assert summary.summary == baseline.summary
    assert summary.unresolved_uncertainties == baseline.unresolved_uncertainties


def test_data_quality_uncertainty_is_preserved() -> None:
    reports = _reports(
        risks=[
            "Momentum could reverse on weak volume.",
            "Incomplete real-data coverage remains for this analyst input.",
        ]
    )

    summary = ResearchManagerAgent(llm_provider=_ManagerProvider()).run(
        symbol="INFY",
        reports=reports,
        bull_thesis=_bull_thesis(),
        bear_thesis=_bear_thesis(),
        rounds=_rounds(),
    )

    assert summary.unresolved_uncertainties == [
        "NewsAnalystAgent: src-news guidance risk is still unresolved.",
        "Some inputs have incomplete real-data coverage and require operator review.",
    ]


def test_missing_provider_records_metric_and_raises() -> None:
    before = current_llm_failure_count()

    with pytest.raises(LLMProviderError, match="requires an LLM provider"):
        ResearchManagerAgent().run(
            symbol="INFY",
            reports=_reports(),
            bull_thesis=_bull_thesis(),
            bear_thesis=_bear_thesis(),
            rounds=_rounds(),
        )

    assert current_llm_failure_count() == before + 1


def test_provider_failure_records_metric_and_raises() -> None:
    before = current_llm_failure_count()

    with pytest.raises(LLMProviderError, match="ResearchManagerAgent LLM provider failed"):
        ResearchManagerAgent(llm_provider=_FailingManagerProvider()).run(
            symbol="INFY",
            reports=_reports(),
            bull_thesis=_bull_thesis(),
            bear_thesis=_bear_thesis(),
            rounds=_rounds(),
        )

    assert current_llm_failure_count() == before + 1


def test_invalid_provider_schema_records_metric_and_raises() -> None:
    before = current_llm_failure_count()

    with pytest.raises(LLMProviderError, match="ResearchManagerAgent LLM provider failed"):
        ResearchManagerAgent(llm_provider=_InvalidManagerProvider()).run(
            symbol="INFY",
            reports=_reports(),
            bull_thesis=_bull_thesis(),
            bear_thesis=_bear_thesis(),
            rounds=_rounds(),
        )

    assert current_llm_failure_count() == before + 1


class _ManagerProvider:
    model_version = "test-manager-provider:v1"

    def __init__(
        self,
        *,
        consensus_label: str = "mild_bullish",
        consensus_score: str = "0.1400",
        confidence: str = "0.7000",
        summary: str | None = None,
        unresolved_uncertainties: list[str] | None = None,
    ) -> None:
        self.consensus_label = consensus_label
        self.consensus_score = Decimal(consensus_score)
        self.confidence = Decimal(confidence)
        self.summary = summary or (
            "TechnicalAnalystAgent: src-tech momentum outweighs NewsAnalystAgent src-news risks."
        )
        self.unresolved_uncertainties = unresolved_uncertainties or [
            "NewsAnalystAgent: src-news guidance risk is still unresolved."
        ]

    def complete_research_manager_summary(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMResearchManagerOutput:
        return LLMResearchManagerOutput(
            consensus_label=self.consensus_label,
            consensus_score=self.consensus_score,
            confidence=self.confidence,
            summary=self.summary,
            unresolved_uncertainties=self.unresolved_uncertainties,
            model_version=self.model_version,
        )


class _FailingManagerProvider:
    model_version = "test-manager-provider:failure"

    def complete_research_manager_summary(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMResearchManagerOutput:
        raise LLMProviderError("provider unavailable")


class _InvalidManagerProvider:
    model_version = "test-manager-provider:invalid"

    def complete_research_manager_summary(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> object:
        return {"consensus_label": "bullish", "consensus_score": "2"}


def _bull_thesis() -> BullThesis:
    return BullThesis(
        symbol="INFY",
        score=Decimal("0.2000"),
        confidence=Decimal("0.7000"),
        key_points=["TechnicalAnalystAgent: src-tech momentum supports the bull thesis."],
        conditions=["TechnicalAnalystAgent: bull thesis fails if src-tech momentum deteriorates."],
        source_report_ids=["ar-bear", "ar-tech"],
    )


def _bear_thesis() -> BearThesis:
    return BearThesis(
        symbol="INFY",
        score=Decimal("-0.1000"),
        confidence=Decimal("0.6000"),
        key_points=["NewsAnalystAgent: src-news guidance risk challenges the bull thesis."],
        risk_flags=["Guidance risk remains active while src-news evidence persists."],
        source_report_ids=["ar-bear", "ar-tech"],
    )


def _rounds() -> list[DebateRound]:
    return [
        DebateRound(
            round_number=1,
            bull_argument="INFY bull case round 1: TechnicalAnalystAgent src-tech momentum.",
            bear_argument="INFY bear case round 1: NewsAnalystAgent src-news guidance risk.",
            manager_note="Manager note: weigh upside evidence against risk flags.",
        ),
        DebateRound(
            round_number=2,
            bull_argument="INFY bull case round 2: src-tech remains supportive.",
            bear_argument="INFY bear case round 2: src-news remains unresolved.",
            manager_note="Manager note: research only.",
        ),
    ]


def _reports(*, risks: list[str] | None = None) -> list[AnalystReport]:
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
            risks=[risks[0] if risks else "Momentum could reverse on weak volume."],
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
            risks=[risks[1] if risks else "Guidance risk could pressure the setup."],
            source_ids=["src-news"],
            model_version="news-test",
        ),
    ]
