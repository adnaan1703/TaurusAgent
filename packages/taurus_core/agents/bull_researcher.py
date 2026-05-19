from __future__ import annotations

from decimal import Decimal

from taurus_core.agents.schemas import AnalystReport
from taurus_core.research.schemas import BullThesis

SCORE_QUANT = Decimal("0.0001")


class BullResearcherAgent:
    agent_name = "BullResearcherAgent"
    model_version = "research_bull_rules_v1"

    def run(self, *, symbol: str, reports: list[AnalystReport]) -> BullThesis:
        if not reports:
            raise ValueError("Bull researcher requires at least one analyst report.")

        symbol = symbol.upper()
        source_report_ids = sorted(report.report_id for report in reports)
        score = self._score(reports)
        confidence = self._confidence(reports, score)
        key_points = self._key_points(symbol, reports)
        conditions = [
            "Positive thesis requires risk approval before any order can be considered.",
            "Position size must remain within configured portfolio limits.",
            "No new severe negative event should appear before execution review.",
        ]
        return BullThesis(
            symbol=symbol,
            score=score,
            confidence=confidence,
            key_points=key_points,
            conditions=conditions,
            source_report_ids=source_report_ids,
        )

    def _score(self, reports: list[AnalystReport]) -> Decimal:
        weighted_positive = Decimal("0")
        confidence_total = Decimal("0")
        bearish_drag = Decimal("0")
        for report in reports:
            confidence_total += report.confidence
            weighted_positive += max(report.score, Decimal("0")) * report.confidence
            bearish_drag += abs(min(report.score, Decimal("0"))) * report.confidence
        if confidence_total == 0:
            return Decimal("0.0000")
        score = (weighted_positive - (bearish_drag * Decimal("0.35"))) / confidence_total
        return _clamp(score).quantize(SCORE_QUANT)

    def _confidence(self, reports: list[AnalystReport], score: Decimal) -> Decimal:
        average = sum((report.confidence for report in reports), Decimal("0")) / Decimal(len(reports))
        directional_support = sum(1 for report in reports if report.score >= Decimal("0.05"))
        support_boost = Decimal(directional_support) / Decimal(len(reports)) * Decimal("0.12")
        conviction_boost = abs(score) * Decimal("0.20")
        return _clamp_unit(average + support_boost + conviction_boost).quantize(SCORE_QUANT)

    def _key_points(self, symbol: str, reports: list[AnalystReport]) -> list[str]:
        ranked = sorted(
            reports,
            key=lambda report: (report.score, report.confidence, report.agent_name),
            reverse=True,
        )
        points: list[str] = []
        for report in ranked:
            if report.score < Decimal("-0.05") and points:
                continue
            first_point = report.key_points[0]
            points.append(f"{report.agent_name}: {first_point}")
            if len(points) == 3:
                break
        return points or [f"No positive analyst evidence was available for {symbol}; bull case is minimal."]


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal("-1"), min(Decimal("1"), value))


def _clamp_unit(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value))
