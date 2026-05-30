from __future__ import annotations

from decimal import Decimal

from taurus_core.agents.schemas import AnalystReport
from taurus_core.llm.base import LLMProvider, LLMProviderError, LLMResearchManagerOutput
from taurus_core.logging import get_logger
from taurus_core.observability.metrics import record_llm_failure
from taurus_core.research.schemas import (
    BearThesis,
    BullThesis,
    ConsensusLabel,
    DebateRound,
    ResearchManagerSummary,
)

SCORE_QUANT = Decimal("0.0001")
MAX_LLM_ADJUSTMENT = Decimal("0.1000")
MAX_LLM_ITEMS = 4
GENERIC_EVIDENCE_WORDS = {
    "active",
    "analyst",
    "bearish",
    "bullish",
    "consensus",
    "evidence",
    "manager",
    "research",
    "support",
    "supports",
    "thesis",
}


class ResearchManagerAgent:
    agent_name = "ResearchManagerAgent"
    model_version = "research_manager_rules_v1"

    def __init__(self, llm_provider: LLMProvider | None = None) -> None:
        self.llm_provider = llm_provider

    def run(
        self,
        *,
        symbol: str,
        reports: list[AnalystReport],
        bull_thesis: BullThesis,
        bear_thesis: BearThesis,
        rounds: list[DebateRound],
    ) -> ResearchManagerSummary:
        baseline = self._run_rules(
            symbol=symbol,
            reports=reports,
            bull_thesis=bull_thesis,
            bear_thesis=bear_thesis,
            rounds=rounds,
        )
        symbol = symbol.upper()
        if self.llm_provider is None:
            record_llm_failure(
                provider="missing",
                agent_name=self.agent_name,
                symbol=symbol,
                error_type="MissingLLMProvider",
            )
            raise LLMProviderError(
                "ResearchManagerAgent requires an LLM provider for runtime debate workflow."
            )

        try:
            draft = self.llm_provider.complete_research_manager_summary(
                agent_name=self.agent_name,
                symbol=symbol,
                context=self._manager_context(
                    reports=reports,
                    bull_thesis=bull_thesis,
                    bear_thesis=bear_thesis,
                    rounds=rounds,
                    baseline=baseline,
                ),
            )
            draft = LLMResearchManagerOutput.model_validate(draft)
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

        consensus_score = _guarded_decimal(
            baseline.consensus_score,
            draft.consensus_score,
            unit=False,
        )
        confidence = _guarded_decimal(baseline.confidence, draft.confidence, unit=True)
        summary = _valid_llm_summary(
            candidate=draft.summary,
            reports=reports,
            bull_thesis=bull_thesis,
            bear_thesis=bear_thesis,
            fallback=baseline.summary,
        )
        unresolved = _valid_llm_uncertainties(
            candidates=draft.unresolved_uncertainties,
            reports=reports,
            bull_thesis=bull_thesis,
            bear_thesis=bear_thesis,
            baseline=baseline.unresolved_uncertainties,
        )
        result = ResearchManagerSummary(
            consensus_label=_label_from_score(consensus_score),
            consensus_score=consensus_score,
            confidence=confidence,
            summary=summary,
            unresolved_uncertainties=unresolved,
        )
        get_logger(__name__).info(
            "research.manager.llm_completed",
            symbol=symbol,
            provider=_provider_label(self.llm_provider),
            model_version=getattr(self.llm_provider, "model_version", "unknown"),
            output_model_version=draft.model_version,
            consensus_label=result.consensus_label,
        )
        return result

    def _run_rules(
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

        symbol = symbol.upper()
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

    def _manager_context(
        self,
        *,
        reports: list[AnalystReport],
        bull_thesis: BullThesis,
        bear_thesis: BearThesis,
        rounds: list[DebateRound],
        baseline: ResearchManagerSummary,
    ) -> dict[str, object]:
        return {
            "analyst_reports": self._evidence_pack(reports),
            "bull_thesis": _bull_payload(bull_thesis),
            "bear_thesis": _bear_payload(bear_thesis),
            "debate_rounds": [
                {
                    "round_number": item.round_number,
                    "bull_argument": item.bull_argument,
                    "bear_argument": item.bear_argument,
                    "manager_note": item.manager_note,
                }
                for item in sorted(rounds, key=lambda item: item.round_number)
            ],
            "deterministic_baseline": _baseline_payload(baseline),
            "guardrails": {
                "research_only": (
                    "Do not decide broker actions, order sizes, position sizes, "
                    "or order routing."
                ),
                "score_adjustment_limit": "0.1000",
                "confidence_adjustment_limit": "0.1000",
                "final_label": "Taurus recomputes from final adjusted score.",
            },
        }

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
        if any(_mentions_incomplete_real_data(report.risks) for report in reports):
            uncertainties.append("Some inputs have incomplete real-data coverage and require operator review.")
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


def _baseline_payload(summary: ResearchManagerSummary) -> dict[str, object]:
    return {
        "consensus_label": summary.consensus_label,
        "consensus_score": str(summary.consensus_score),
        "confidence": str(summary.confidence),
        "summary": summary.summary,
        "unresolved_uncertainties": summary.unresolved_uncertainties,
        "guardrail": "LLM score/confidence may adjust this baseline by at most 0.1000.",
    }


def _bull_payload(thesis: BullThesis) -> dict[str, object]:
    return {
        "symbol": thesis.symbol,
        "score": str(thesis.score),
        "confidence": str(thesis.confidence),
        "key_points": thesis.key_points,
        "conditions": thesis.conditions,
        "source_report_ids": thesis.source_report_ids,
    }


def _bear_payload(thesis: BearThesis) -> dict[str, object]:
    return {
        "symbol": thesis.symbol,
        "score": str(thesis.score),
        "confidence": str(thesis.confidence),
        "key_points": thesis.key_points,
        "risk_flags": thesis.risk_flags,
        "source_report_ids": thesis.source_report_ids,
    }


def _guarded_decimal(rule_value: Decimal, llm_value: Decimal, *, unit: bool) -> Decimal:
    delta = llm_value - rule_value
    delta = max(-MAX_LLM_ADJUSTMENT, min(MAX_LLM_ADJUSTMENT, delta))
    adjusted = rule_value + delta
    if unit:
        return _clamp_unit(adjusted).quantize(SCORE_QUANT)
    return _clamp(adjusted).quantize(SCORE_QUANT)


def _valid_llm_summary(
    *,
    candidate: str,
    reports: list[AnalystReport],
    bull_thesis: BullThesis,
    bear_thesis: BearThesis,
    fallback: str,
) -> str:
    text = " ".join(candidate.split())
    if not text or _is_repetitive(text):
        return fallback
    if not _is_evidence_bound(text, reports, bull_thesis, bear_thesis):
        return fallback
    return text


def _valid_llm_uncertainties(
    *,
    candidates: list[str],
    reports: list[AnalystReport],
    bull_thesis: BullThesis,
    bear_thesis: BearThesis,
    baseline: list[str],
) -> list[str]:
    accepted: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = " ".join(candidate.split())
        normalized = text.casefold()
        if not text or normalized in seen or _is_repetitive(text):
            continue
        if not _is_evidence_bound(text, reports, bull_thesis, bear_thesis):
            continue
        seen.add(normalized)
        accepted.append(text)
        if len(accepted) == MAX_LLM_ITEMS:
            break

    if not accepted:
        accepted = list(baseline)
        seen = {item.casefold() for item in accepted}

    for uncertainty in baseline:
        if not _is_data_quality_warning(uncertainty):
            continue
        normalized = uncertainty.casefold()
        if normalized not in seen:
            accepted.append(uncertainty)
            seen.add(normalized)
    return accepted


def _is_evidence_bound(
    text: str,
    reports: list[AnalystReport],
    bull_thesis: BullThesis,
    bear_thesis: BearThesis,
) -> bool:
    normalized = text.casefold()
    return any(term in normalized for term in _evidence_terms(reports, bull_thesis, bear_thesis))


def _evidence_terms(
    reports: list[AnalystReport],
    bull_thesis: BullThesis,
    bear_thesis: BearThesis,
) -> set[str]:
    terms: set[str] = set()
    for report in reports:
        for value in [report.report_id, report.agent_name, *report.source_ids]:
            normalized = value.strip().casefold()
            if normalized:
                terms.add(normalized)
        for text in [*report.key_points, *report.risks]:
            terms.update(_significant_words(text))
    for text in [
        *bull_thesis.key_points,
        *bull_thesis.conditions,
        *bear_thesis.key_points,
        *bear_thesis.risk_flags,
    ]:
        terms.update(_significant_words(text))
    return terms


def _significant_words(text: str) -> set[str]:
    terms: set[str] = set()
    for word in text.replace("/", " ").replace("-", " ").split():
        normalized = "".join(char for char in word.casefold() if char.isalnum())
        if len(normalized) >= 5 and normalized not in GENERIC_EVIDENCE_WORDS:
            terms.add(normalized)
    return terms


def _is_repetitive(text: str) -> bool:
    words = [
        "".join(char for char in word.casefold() if char.isalnum())
        for word in text.split()
    ]
    words = [word for word in words if word]
    return len(words) >= 8 and len(set(words)) <= 3


def _mentions_incomplete_real_data(risks: list[str]) -> bool:
    text = " ".join(risks).casefold()
    return "incomplete" in text and ("real data" in text or "real-data" in text or "coverage" in text)


def _is_data_quality_warning(text: str) -> bool:
    normalized = text.casefold()
    return "mock" in normalized or (
        "incomplete" in normalized and ("real data" in normalized or "real-data" in normalized)
    )


def _provider_label(provider: LLMProvider) -> str:
    model_version = getattr(provider, "model_version", provider.__class__.__name__)
    return str(model_version).split(":", maxsplit=1)[0]
