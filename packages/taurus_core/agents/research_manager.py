from __future__ import annotations

from decimal import Decimal

from taurus_core.agents.schemas import AnalystReport
from taurus_core.research.schemas import (
    BearThesis,
    BullThesis,
    ConsensusLabel,
    DebateRound,
    ResearchManagerSummary,
)

SCORE_QUANT = Decimal("0.0001")


class ResearchManagerAgent:
    agent_name = "ResearchManagerAgent"
    model_version = "research_manager_rules_v1"

    def run(
        self,
        *,
        symbol: str,
        reports: list[AnalystReport],
        bull_thesis: BullThesis,
        bear_thesis: BearThesis,
        rounds: list[DebateRound],
    ) -> ResearchManagerSummary:
        if not reports:
            raise ValueError("Research manager requires at least one analyst report.")
        if not rounds:
            raise ValueError("Research manager requires at least one debate round.")

        consensus_score = self._consensus_score(reports, bull_thesis, bear_thesis)
        label = _label_from_score(consensus_score)
        confidence = self._confidence(reports, bull_thesis, bear_thesis, consensus_score)
        unresolved = self._uncertainties(reports, bear_thesis)
        summary = (
            f"{symbol.upper()} research consensus is {label.replace('_', ' ')} "
            f"with score {consensus_score} after {len(rounds)} debate rounds."
        )
        return ResearchManagerSummary(
            consensus_label=label,
            consensus_score=consensus_score,
            confidence=confidence,
            summary=summary,
            unresolved_uncertainties=unresolved,
        )

    def _consensus_score(
        self,
        reports: list[AnalystReport],
        bull_thesis: BullThesis,
        bear_thesis: BearThesis,
    ) -> Decimal:
        weighted_total = Decimal("0")
        confidence_total = Decimal("0")
        for report in reports:
            weighted_total += report.score * report.confidence
            confidence_total += report.confidence
        analyst_score = weighted_total / confidence_total if confidence_total else Decimal("0")
        score = (analyst_score * Decimal("0.60")) + (bull_thesis.score * Decimal("0.25")) + (
            bear_thesis.score * Decimal("0.15")
        )
        return _clamp(score).quantize(SCORE_QUANT)

    def _confidence(
        self,
        reports: list[AnalystReport],
        bull_thesis: BullThesis,
        bear_thesis: BearThesis,
        consensus_score: Decimal,
    ) -> Decimal:
        average_report_confidence = sum(
            (report.confidence for report in reports),
            Decimal("0"),
        ) / Decimal(len(reports))
        disagreement_penalty = abs(bull_thesis.score - bear_thesis.score) * Decimal("0.08")
        conviction_boost = abs(consensus_score) * Decimal("0.12")
        confidence = (
            (average_report_confidence * Decimal("0.60"))
            + (bull_thesis.confidence * Decimal("0.20"))
            + (bear_thesis.confidence * Decimal("0.20"))
            + conviction_boost
            - disagreement_penalty
        )
        return _clamp_unit(confidence).quantize(SCORE_QUANT)

    def _uncertainties(
        self,
        reports: list[AnalystReport],
        bear_thesis: BearThesis,
    ) -> list[str]:
        uncertainties = list(bear_thesis.risk_flags[:3])
        if any("mock" in " ".join(report.risks).lower() for report in reports):
            uncertainties.append("Some inputs remain mock-mode and require real data before live use.")
        low_confidence = [report.agent_name for report in reports if report.confidence < Decimal("0.50")]
        if low_confidence:
            uncertainties.append(f"Low-confidence reports: {', '.join(sorted(low_confidence))}.")
        return uncertainties[:4] or ["No unresolved uncertainty was identified beyond normal market risk."]


def _label_from_score(score: Decimal) -> ConsensusLabel:
    if score >= Decimal("0.45"):
        return "bullish"
    if score >= Decimal("0.15"):
        return "mild_bullish"
    if score <= Decimal("-0.45"):
        return "bearish"
    if score <= Decimal("-0.15"):
        return "mild_bearish"
    return "neutral"


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal("-1"), min(Decimal("1"), value))


def _clamp_unit(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value))
