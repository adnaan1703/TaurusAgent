from __future__ import annotations

from decimal import Decimal

from taurus_core.agents.schemas import LLMAnalystOutput, stance_from_score
from taurus_core.llm.base import (
    LLMBearThesisOutput,
    LLMBullThesisOutput,
    LLMFinalDecisionExplanation,
    LLMResearchManagerOutput,
    LLMTraderOutput,
)


class FakeLLMProvider:
    """Test-only fake LLM provider; not part of runtime Taurus wiring."""

    def __init__(self, *, model_version: str = "test-fake-llm-v1") -> None:
        self._model_version = model_version

    @property
    def model_version(self) -> str:
        return self._model_version

    def complete_analyst_report(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMAnalystOutput:
        score = _decimal_context(context, "score", Decimal("0"))
        confidence = _decimal_context(context, "confidence", Decimal("0.55"))
        horizon = str(context.get("horizon") or "short")
        key_points = _list_context(
            context,
            "key_points",
            [f"{agent_name} test fake analysis completed for {symbol.upper()}."],
        )
        risks = _list_context(
            context,
            "risks",
            ["Test-only fake LLM output."],
        )
        bounded_score = max(Decimal("-1"), min(Decimal("1"), score))
        return LLMAnalystOutput(
            score=bounded_score,
            confidence=max(Decimal("0"), min(Decimal("1"), confidence)),
            stance=stance_from_score(bounded_score),
            horizon=horizon,  # type: ignore[arg-type]
            key_points=key_points,
            risks=risks,
            model_version=self.model_version,
        )

    def complete_bull_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBullThesisOutput:
        baseline_score = _decimal_context(baseline, "score", Decimal("0"))
        baseline_confidence = _decimal_context(baseline, "confidence", Decimal("0.55"))
        first_report = evidence_pack[0] if evidence_pack else {}
        agent = str(first_report.get("agent_name") or agent_name)
        source_ids = first_report.get("source_ids")
        source_id = source_ids[0] if isinstance(source_ids, list) and source_ids else "test-source"
        return LLMBullThesisOutput(
            score=max(Decimal("-1"), min(Decimal("1"), baseline_score + Decimal("0.0500"))),
            confidence=max(
                Decimal("0"),
                min(Decimal("1"), baseline_confidence + Decimal("0.0500")),
            ),
            key_points=[
                f"{agent}: bullish evidence remains tied to {source_id} for {symbol.upper()}."
            ],
            conditions=[
                f"{agent}: bullish setup remains invalid if {source_id} evidence deteriorates."
            ],
            model_version=self.model_version,
        )

    def complete_bear_thesis(
        self,
        *,
        agent_name: str,
        symbol: str,
        baseline: dict[str, object],
        evidence_pack: list[dict[str, object]],
    ) -> LLMBearThesisOutput:
        baseline_score = _decimal_context(baseline, "score", Decimal("0"))
        baseline_confidence = _decimal_context(baseline, "confidence", Decimal("0.55"))
        first_report = evidence_pack[0] if evidence_pack else {}
        agent = str(first_report.get("agent_name") or agent_name)
        source_ids = first_report.get("source_ids")
        source_id = source_ids[0] if isinstance(source_ids, list) and source_ids else "test-source"
        return LLMBearThesisOutput(
            score=min(Decimal("0"), max(Decimal("-1"), baseline_score - Decimal("0.0500"))),
            confidence=max(
                Decimal("0"),
                min(Decimal("1"), baseline_confidence + Decimal("0.0500")),
            ),
            key_points=[
                f"{agent}: bearish evidence remains tied to {source_id} for {symbol.upper()}."
            ],
            risk_flags=[
                f"{agent}: downside risk remains active while {source_id} evidence persists."
            ],
            model_version=self.model_version,
        )

    def complete_research_manager_summary(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMResearchManagerOutput:
        baseline = context.get("deterministic_baseline")
        if not isinstance(baseline, dict):
            baseline = {}
        baseline_score = _decimal_context(baseline, "consensus_score", Decimal("0"))
        baseline_confidence = _decimal_context(baseline, "confidence", Decimal("0.55"))
        reports = context.get("analyst_reports")
        first_report = reports[0] if isinstance(reports, list) and reports else {}
        if not isinstance(first_report, dict):
            first_report = {}
        agent = str(first_report.get("agent_name") or agent_name)
        source_ids = first_report.get("source_ids")
        source_id = source_ids[0] if isinstance(source_ids, list) and source_ids else "test-source"
        return LLMResearchManagerOutput(
            consensus_label=str(baseline.get("consensus_label") or "neutral"),
            consensus_score=max(Decimal("-1"), min(Decimal("1"), baseline_score + Decimal("0.0500"))),
            confidence=max(
                Decimal("0"),
                min(Decimal("1"), baseline_confidence + Decimal("0.0500")),
            ),
            summary=f"{agent}: manager consensus remains tied to {source_id} for {symbol.upper()}.",
            unresolved_uncertainties=[
                f"{agent}: manager uncertainty remains tied to {source_id} for {symbol.upper()}."
            ],
            model_version=self.model_version,
        )

    def complete_trader_proposal(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMTraderOutput:
        fallback = context.get("deterministic_fallback")
        if not isinstance(fallback, dict):
            fallback = {}
        return LLMTraderOutput(
            action=str(fallback.get("action") or "NO_TRADE"),
            confidence=_decimal_context(fallback, "confidence", Decimal("0.5500")),
            target_position_pct_nav=_decimal_context(
                fallback,
                "target_position_pct_nav",
                Decimal("0.0000"),
            ),
            stop_loss_pct=_decimal_context(fallback, "stop_loss_pct", Decimal("6.0000")),
            take_profit_pct=_decimal_context(fallback, "take_profit_pct", Decimal("12.0000")),
            reason_summary=str(
                fallback.get("reason_summary")
                or f"{agent_name}: fake trader proposal for {symbol.upper()}."
            ),
            invalid_if=[
                str(item)
                for item in fallback.get(
                    "invalid_if",
                    ["Test-only fake trader invalidation."],
                )
            ],
            position_management_summary=str(
                fallback.get("position_management_summary")
                or f"{agent_name}: fake lifecycle summary for {symbol.upper()}."
            ),
            model_version=self.model_version,
        )

    def complete_final_decision_explanation(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMFinalDecisionExplanation:
        decision = context.get("deterministic_decision")
        if not isinstance(decision, dict):
            decision = {}
        final_action = str(decision.get("final_action") or "NO_TRADE")
        status = str(decision.get("status") or "NO_ACTION")
        deterministic_reason = str(
            decision.get("deterministic_reason")
            or f"{agent_name}: deterministic final decision for {symbol.upper()}."
        )
        return LLMFinalDecisionExplanation(
            reason=(
                f"{deterministic_reason} Test-only explanation confirms {status} "
                f"for {final_action} on {symbol.upper()}."
            ),
            model_version=self.model_version,
        )


def _decimal_context(context: dict[str, object], key: str, default: Decimal) -> Decimal:
    value = context.get(key)
    if value is None:
        return default
    return Decimal(str(value))


def _list_context(
    context: dict[str, object],
    key: str,
    default: list[str],
) -> list[str]:
    value = context.get(key)
    if not isinstance(value, list):
        return default
    cleaned = [str(item) for item in value if str(item).strip()]
    return cleaned or default
