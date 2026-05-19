from __future__ import annotations

from decimal import Decimal

from taurus_core.agents.schemas import AnalystReport
from taurus_core.research.schemas import BearThesis

SCORE_QUANT = Decimal("0.0001")


class BearResearcherAgent:
    agent_name = "BearResearcherAgent"
    model_version = "research_bear_rules_v1"

    def run(self, *, symbol: str, reports: list[AnalystReport]) -> BearThesis:
        if not reports:
            raise ValueError("Bear researcher requires at least one analyst report.")

        symbol = symbol.upper()
        source_report_ids = sorted(report.report_id for report in reports)
        score = self._score(reports)
        confidence = self._confidence(reports, score)
        key_points = self._key_points(symbol, reports)
        risk_flags = self._risk_flags(reports)
        return BearThesis(
            symbol=symbol,
            score=score,
            confidence=confidence,
            key_points=key_points,
            risk_flags=risk_flags,
            source_report_ids=source_report_ids,
        )

    def _score(self, reports: list[AnalystReport]) -> Decimal:
        weighted_negative = Decimal("0")
        confidence_total = Decimal("0")
        low_confidence_penalty = Decimal("0")
        for report in reports:
            confidence_total += report.confidence
            weighted_negative += abs(min(report.score, Decimal("0"))) * report.confidence
            if report.confidence < Decimal("0.50"):
                low_confidence_penalty += Decimal("0.05")
        if confidence_total == 0:
            return Decimal("0.0000")
        average_negative = weighted_negative / confidence_total
        risk_density_penalty = min(
            Decimal("0.20"),
            Decimal(sum(len(report.risks) for report in reports)) * Decimal("0.015"),
        )
        score = -(average_negative + low_confidence_penalty + risk_density_penalty)
        return _clamp(score).quantize(SCORE_QUANT)

    def _confidence(self, reports: list[AnalystReport], score: Decimal) -> Decimal:
        average = sum((report.confidence for report in reports), Decimal("0")) / Decimal(len(reports))
        risk_density = sum(len(report.risks) for report in reports) / max(len(reports), 1)
        risk_boost = min(Decimal("0.15"), Decimal(str(risk_density)) * Decimal("0.025"))
        conviction_boost = abs(score) * Decimal("0.20")
        return _clamp_unit(average + risk_boost + conviction_boost).quantize(SCORE_QUANT)

    def _key_points(self, symbol: str, reports: list[AnalystReport]) -> list[str]:
        ranked = sorted(
            reports,
            key=lambda report: (report.score, -report.confidence, report.agent_name),
        )
        points: list[str] = []
        for report in ranked:
            first_risk = report.risks[0]
            points.append(f"{report.agent_name}: {first_risk}")
            if len(points) == 3:
                break
        return points or [f"No bearish evidence was available for {symbol}; no-trade case is minimal."]

    def _risk_flags(self, reports: list[AnalystReport]) -> list[str]:
        flags: list[str] = []
        for report in sorted(reports, key=lambda item: item.agent_name):
            if report.score <= Decimal("-0.10"):
                flags.append(f"{report.agent_name} has bearish score {report.score}.")
            if report.confidence < Decimal("0.50"):
                flags.append(f"{report.agent_name} confidence is only {report.confidence}.")
        for report in sorted(reports, key=lambda item: item.agent_name):
            flags.extend(report.risks[:1])
            if len(flags) >= 4:
                break
        return flags[:4] or ["No explicit bearish risk flags were produced by analyst reports."]


def _clamp(value: Decimal) -> Decimal:
    return max(Decimal("-1"), min(Decimal("1"), value))


def _clamp_unit(value: Decimal) -> Decimal:
    return max(Decimal("0"), min(Decimal("1"), value))
