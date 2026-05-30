from __future__ import annotations

from decimal import Decimal

from taurus_core.agents.schemas import AnalystReport
from taurus_core.llm.base import LLMBullThesisOutput, LLMProvider, LLMProviderError
from taurus_core.logging import get_logger
from taurus_core.observability.metrics import record_llm_failure
from taurus_core.research.schemas import BullThesis

SCORE_QUANT = Decimal("0.0001")
MAX_LLM_ADJUSTMENT = Decimal("0.1000")
MAX_LLM_ITEMS = 3


class BullResearcherAgent:
    agent_name = "BullResearcherAgent"
    model_version = "research_bull_rules_v1"

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def run(self, *, symbol: str, reports: list[AnalystReport]) -> BullThesis:
        baseline = self._run_rules(symbol=symbol, reports=reports)
        symbol = baseline.symbol
        if self.llm_provider is None:
            record_llm_failure(
                provider="missing",
                agent_name=self.agent_name,
                symbol=symbol,
                error_type="MissingLLMProvider",
            )
            raise LLMProviderError(
                "BullResearcherAgent requires an LLM provider for runtime debate workflow."
            )

        try:
            draft = self.llm_provider.complete_bull_thesis(
                agent_name=self.agent_name,
                symbol=symbol,
                baseline=_baseline_payload(baseline),
                evidence_pack=self._evidence_pack(reports),
            )
            draft = LLMBullThesisOutput.model_validate(draft)
        except Exception as exc:
            record_llm_failure(
                provider=_provider_label(self.llm_provider),
                agent_name=self.agent_name,
                symbol=symbol,
                error_type=exc.__class__.__name__,
            )
            raise LLMProviderError(
                f"{self.agent_name} LLM provider failed for {symbol}: {exc}"
            ) from exc

        key_points = _valid_llm_text(
            candidates=draft.key_points,
            reports=reports,
            fallback=baseline.key_points,
        )
        conditions = _valid_llm_text(
            candidates=draft.conditions,
            reports=reports,
            fallback=baseline.conditions,
        )
        thesis = BullThesis(
            symbol=symbol,
            score=_guarded_decimal(baseline.score, draft.score, unit=False),
            confidence=_guarded_decimal(baseline.confidence, draft.confidence, unit=True),
            key_points=key_points,
            conditions=conditions,
            source_report_ids=baseline.source_report_ids,
        )
        get_logger(__name__).info(
            "research.bull.llm_completed",
            symbol=symbol,
            provider=_provider_label(self.llm_provider),
            model_version=getattr(self.llm_provider, "model_version", "unknown"),
            output_model_version=draft.model_version,
            source_report_ids=thesis.source_report_ids,
        )
        return thesis

    def _run_rules(self, *, symbol: str, reports: list[AnalystReport]) -> BullThesis:
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

    def _evidence_pack(self, reports: list[AnalystReport]) -> list[dict[str, object]]:
        return [
            {
                "report_id": report.report_id,
                "agent_name": report.agent_name,
                "score": str(report.score),
                "confidence": str(report.confidence),
                "stance": report.stance,
                "horizon": report.horizon,
                "key_points": report.key_points[:3],
                "risks": report.risks[:3],
                "source_ids": sorted(report.source_ids),
                "model_version": report.model_version,
            }
            for report in sorted(reports, key=lambda item: item.report_id)
        ]

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


def _baseline_payload(thesis: BullThesis) -> dict[str, object]:
    return {
        "symbol": thesis.symbol,
        "score": str(thesis.score),
        "confidence": str(thesis.confidence),
        "key_points": thesis.key_points,
        "conditions": thesis.conditions,
        "source_report_ids": thesis.source_report_ids,
        "guardrail": "LLM score/confidence may adjust this baseline by at most 0.1000.",
    }


def _guarded_decimal(rule_value: Decimal, llm_value: Decimal, *, unit: bool) -> Decimal:
    delta = llm_value - rule_value
    delta = max(-MAX_LLM_ADJUSTMENT, min(MAX_LLM_ADJUSTMENT, delta))
    adjusted = rule_value + delta
    if unit:
        return _clamp_unit(adjusted).quantize(SCORE_QUANT)
    return _clamp(adjusted).quantize(SCORE_QUANT)


def _valid_llm_text(
    *,
    candidates: list[str],
    reports: list[AnalystReport],
    fallback: list[str],
) -> list[str]:
    evidence_terms = _evidence_terms(reports)
    accepted: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = " ".join(candidate.split())
        normalized = text.casefold()
        if not text or normalized in seen:
            continue
        if not any(term in normalized for term in evidence_terms):
            continue
        seen.add(normalized)
        accepted.append(text)
        if len(accepted) == MAX_LLM_ITEMS:
            break
    return accepted or fallback


def _evidence_terms(reports: list[AnalystReport]) -> set[str]:
    terms: set[str] = set()
    for report in reports:
        for value in [report.report_id, report.agent_name, *report.source_ids]:
            normalized = value.strip().casefold()
            if normalized:
                terms.add(normalized)
        for text in [*report.key_points, *report.risks]:
            for word in text.replace("/", " ").replace("-", " ").split():
                normalized = "".join(char for char in word.casefold() if char.isalnum())
                if len(normalized) >= 5:
                    terms.add(normalized)
    return terms


def _provider_label(provider: LLMProvider) -> str:
    model_version = getattr(provider, "model_version", provider.__class__.__name__)
    return str(model_version).split(":", maxsplit=1)[0]
