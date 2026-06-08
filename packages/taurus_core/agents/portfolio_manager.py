from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID
from taurus_core.config import Settings, get_settings
from taurus_core.db.repositories import (
    CandleRepository,
    ExecutionRepository,
    ResearchRepository,
    RiskRepository,
)
from taurus_core.llm import LLMProvider, LLMProviderError
from taurus_core.llm.base import LLMFinalDecisionExplanation
from taurus_core.logging import get_logger
from taurus_core.observability.metrics import record_llm_failure
from taurus_core.observability.tracing import bound_trace_context
from taurus_core.profiles.runtime import resolve_runtime_profile
from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.schemas import (
    FinalDecision,
    RiskReview,
    final_decision_id,
)

SCORE_QUANT = Decimal("0.0001")
REASON_MAX_CHARS = 1200


@dataclass(slots=True, frozen=True)
class _RuleDecisionFields:
    final_action: str
    status: str
    approved_quantity: int
    approved_position_pct_nav: Decimal
    reason: str
    can_send_to_broker: bool


class PortfolioManagerAgent:
    agent_name = "PortfolioManagerAgent"
    model_version = "portfolio_manager_lifecycle_rules_v1"

    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        *,
        llm_provider: LLMProvider | None = None,
        enable_llm_explanation: bool = True,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.llm_provider = llm_provider
        self.enable_llm_explanation = enable_llm_explanation

    def run(
        self,
        *,
        symbol: str,
        run_id: str = DEFAULT_ANALYST_RUN_ID,
        risk_review: RiskReview | None = None,
    ) -> FinalDecision:
        symbol = symbol.upper()
        risk_review = risk_review or self._load_risk_review(symbol=symbol, run_id=run_id)
        if risk_review.symbol != symbol:
            raise ValueError("Risk review symbol does not match final approval symbol.")

        proposal = self._load_proposal(risk_review.proposal_id)
        decision = self._rule_final_decision(
            symbol=symbol,
            proposal=proposal,
            risk_review=risk_review,
        )
        decision = self._with_llm_explanation(
            decision=decision,
            proposal=proposal,
            risk_review=risk_review,
        )
        RiskRepository(self.session).replace_final_decision_for_run_symbol(decision)
        self.session.commit()
        with bound_trace_context(
            run_id=risk_review.run_id,
            decision_id=risk_review.decision_id,
            proposal_id=risk_review.proposal_id,
            risk_check_id=risk_review.risk_check_id,
            final_decision_id=decision.final_decision_id,
        ):
            get_logger(__name__).info(
                "portfolio.final_decision.created",
                symbol=symbol,
                status=decision.status,
                final_action=decision.final_action,
                approved_quantity=decision.approved_quantity,
                can_send_to_broker=decision.can_send_to_broker,
            )
        return decision

    def _rule_final_decision(
        self,
        *,
        symbol: str,
        proposal: TraderProposal,
        risk_review: RiskReview,
    ) -> FinalDecision:
        fields = self._rule_decision_fields(proposal=proposal, risk_review=risk_review)
        return FinalDecision(
            final_decision_id=final_decision_id(
                run_id=risk_review.run_id,
                symbol=symbol,
                proposal_id=risk_review.proposal_id,
                risk_check_id=risk_review.risk_check_id,
            ),
            decision_id=risk_review.decision_id,
            run_id=risk_review.run_id,
            portfolio_id=risk_review.portfolio_id,
            symbol=symbol,
            proposal_id=risk_review.proposal_id,
            risk_check_id=risk_review.risk_check_id,
            as_of=risk_review.as_of,
            final_action=fields.final_action,
            status=fields.status,
            approved_quantity=fields.approved_quantity,
            approved_position_pct_nav=fields.approved_position_pct_nav,
            reason=fields.reason,
            is_order=False,
            can_send_to_broker=fields.can_send_to_broker,
            allocation_decision=risk_review.allocation_decision or proposal.allocation_decision,
            model_version=self.model_version,
        )

    def _rule_decision_fields(
        self,
        *,
        proposal: TraderProposal,
        risk_review: RiskReview,
    ) -> _RuleDecisionFields:
        final_action = "NO_TRADE"
        status = "REJECTED"
        can_send_to_broker = False
        approved_position = Decimal("0.0000")
        approved_quantity = 0
        reason = f"Rejected because risk status is {risk_review.status}."
        allocation_no_trade_reason = _allocation_no_trade_reason(
            proposal.allocation_decision or risk_review.allocation_decision
        )

        if risk_review.status == "BLOCKED":
            status = "BLOCKED"
            reason = "Blocked by hard risk rules; no paper decision may proceed."
        elif risk_review.status in {"APPROVED", "APPROVED_WITH_REDUCTION"}:
            final_action = proposal.action
            approved_position = risk_review.approved_position_pct_nav.quantize(SCORE_QUANT)
            approved_quantity = self._approved_quantity(
                proposal=proposal,
                approved_position_pct_nav=approved_position,
            )
            if final_action in {"HOLD", "NO_TRADE"}:
                status = "NO_ACTION"
                can_send_to_broker = False
                approved_quantity = 0
                reason = allocation_no_trade_reason or (
                    f"Approved {final_action}; no paper order expected."
                )
            elif approved_quantity > 0 and self._paper_safe():
                status = "APPROVED_FOR_PAPER"
                can_send_to_broker = True
                reason = (
                    f"Approved {final_action} for PaperBroker execution after stored "
                    "risk review and paper-safe configuration checks."
                )
            elif final_action in {"REDUCE", "EXIT"}:
                status = "NO_ACTION"
                can_send_to_broker = False
                reason = (
                    f"Approved {final_action}, but current and target quantities do not "
                    "produce a positive paper sell order."
                )
            else:
                reason = "Approved risk percentage could not produce a positive paper quantity."

        return _RuleDecisionFields(
            final_action=final_action,
            status=status,
            approved_quantity=approved_quantity,
            approved_position_pct_nav=approved_position,
            reason=reason,
            can_send_to_broker=can_send_to_broker,
        )

    def _with_llm_explanation(
        self,
        *,
        decision: FinalDecision,
        proposal: TraderProposal,
        risk_review: RiskReview,
    ) -> FinalDecision:
        if not self.enable_llm_explanation:
            return decision
        if self.llm_provider is None:
            self._record_llm_failure(symbol=decision.symbol, error_type="MissingLLMProvider")
            return decision
        try:
            output = self.llm_provider.complete_final_decision_explanation(
                agent_name=self.agent_name,
                symbol=decision.symbol,
                context=self._llm_explanation_context(
                    decision=decision,
                    proposal=proposal,
                    risk_review=risk_review,
                ),
            )
            reason = self._enriched_reason(
                deterministic_reason=decision.reason,
                output=output,
            )
        except (LLMProviderError, ValueError) as exc:
            self._record_llm_failure(
                symbol=decision.symbol,
                error_type=exc.__class__.__name__,
            )
            return decision
        return decision.model_copy(
            update={
                "reason": reason,
                "model_version": f"{self.model_version}+llm_explainer",
            }
        )

    def _llm_explanation_context(
        self,
        *,
        decision: FinalDecision,
        proposal: TraderProposal,
        risk_review: RiskReview,
    ) -> dict[str, object]:
        return {
            "symbol": decision.symbol,
            "run_id": decision.run_id,
            "proposal_id": decision.proposal_id,
            "risk_check_id": decision.risk_check_id,
            "deterministic_decision": {
                "final_action": decision.final_action,
                "status": decision.status,
                "approved_quantity": decision.approved_quantity,
                "approved_position_pct_nav": str(decision.approved_position_pct_nav),
                "is_order": decision.is_order,
                "can_send_to_broker": decision.can_send_to_broker,
                "deterministic_reason": decision.reason,
            },
            "proposal": {
                "action": proposal.action,
                "confidence": str(proposal.confidence),
                "requested_position_pct_nav": str(proposal.requested_position_pct_nav),
                "current_position_quantity": proposal.current_position_quantity,
                "current_position_pct_nav": str(proposal.current_position_pct_nav),
                "target_position_pct_nav": str(proposal.target_position_pct_nav),
                "lifecycle_trigger": proposal.lifecycle_trigger,
                "evaluation_mode": proposal.evaluation_mode,
                "reason_summary": proposal.reason_summary,
                "invalid_if": list(proposal.invalid_if),
                "position_management_summary": proposal.position_management_summary,
                "allocation_decision": proposal.allocation_decision.model_dump(mode="json")
                if proposal.allocation_decision is not None
                else None,
            },
            "risk_review": {
                "status": risk_review.status,
                "approved_position_pct_nav": str(risk_review.approved_position_pct_nav),
                "risk_committee_summary": risk_review.risk_committee_summary,
                "allocation_decision": risk_review.allocation_decision.model_dump(mode="json")
                if risk_review.allocation_decision is not None
                else None,
            },
            "hard_rules": [
                {
                    "rule": result.rule,
                    "status": result.status,
                    "details": result.details,
                }
                for result in risk_review.hard_rule_results
            ],
            "persona_reviews": [
                {
                    "agent_name": review.agent_name,
                    "recommendation": review.recommendation,
                    "required_conditions": list(review.required_conditions),
                }
                for review in risk_review.persona_reviews
            ],
            "safety_config": {
                "live_trading_enabled": self.settings.live_trading_enabled,
                "broker_provider": self.settings.broker_provider,
                "taurus_mode": self.settings.taurus_mode,
                "paper_portfolio_id": self.settings.taurus_paper_portfolio_id,
                "can_send_to_broker": decision.can_send_to_broker,
            },
            "provider_model_version": _provider_label(self.llm_provider),
        }

    def _enriched_reason(
        self,
        *,
        deterministic_reason: str,
        output: LLMFinalDecisionExplanation,
    ) -> str:
        explanation = " ".join(output.reason.split())
        if not explanation:
            raise ValueError("LLM final-decision explanation reason was empty")
        if deterministic_reason in explanation:
            return _bounded_text(explanation, deterministic_reason)
        return _bounded_text(
            f"{deterministic_reason} LLM explainer: {explanation}",
            deterministic_reason,
        )

    def _record_llm_failure(self, *, symbol: str, error_type: str) -> None:
        record_llm_failure(
            provider=_provider_label(self.llm_provider),
            agent_name=self.agent_name,
            symbol=symbol,
            error_type=error_type,
        )

    def _load_risk_review(self, *, symbol: str, run_id: str) -> RiskReview:
        model = RiskRepository(self.session).latest_risk_review(symbol=symbol, run_id=run_id)
        if model is None:
            raise ValueError(
                f"No risk review found for {symbol} run_id={run_id}. "
                "Run risk review before final approval."
            )
        return RiskReview.model_validate(model.payload)

    def _load_proposal(self, proposal_id: str) -> TraderProposal:
        model = ResearchRepository(self.session).get_trader_proposal(proposal_id)
        if model is None:
            raise ValueError(f"Trader proposal {proposal_id} not found for final approval.")
        return TraderProposal.model_validate(model.payload)

    def _approved_quantity(
        self,
        *,
        proposal: TraderProposal,
        approved_position_pct_nav: Decimal,
    ) -> int:
        if proposal.action in {"HOLD", "NO_TRADE"}:
            return 0
        current_quantity = proposal.current_position_quantity
        if proposal.action == "EXIT":
            return current_quantity

        target_quantity = self._target_quantity(
            symbol=proposal.symbol,
            approved_position_pct_nav=approved_position_pct_nav,
        )
        if proposal.action == "BUY":
            return max(0, target_quantity - current_quantity)
        if proposal.action == "REDUCE":
            return max(0, current_quantity - target_quantity)
        return 0

    def _target_quantity(self, *, symbol: str, approved_position_pct_nav: Decimal) -> int:
        if approved_position_pct_nav <= 0:
            return 0
        candles = CandleRepository(self.session).get_by_symbol_and_date_range(symbol=symbol)
        if not candles:
            return 0
        latest_close = candles[-1].close
        if latest_close <= 0:
            return 0
        account = ExecutionRepository(self.session).latest_account_by_portfolio(
            portfolio_id=self.settings.taurus_paper_portfolio_id,
        )
        equity = (
            account.equity_inr
            if account is not None
            else resolve_runtime_profile(self.session, self.settings).starting_corpus_inr
        )
        notional = equity * approved_position_pct_nav / Decimal("100")
        return int(notional // latest_close)

    def _paper_safe(self) -> bool:
        return (
            self.settings.live_trading_enabled is False
            and self.settings.broker_provider == "paper"
            and self.settings.taurus_mode in {"paper", "backtest"}
        )


def _bounded_text(value: str, anchor: str) -> str:
    cleaned = " ".join(value.split())
    if len(cleaned) <= REASON_MAX_CHARS:
        return cleaned
    budget = REASON_MAX_CHARS - len(anchor) - len(" LLM explainer: ...")
    if budget <= 0:
        return anchor
    suffix = cleaned[-budget:].lstrip()
    return f"{anchor} LLM explainer: ...{suffix}"


def _provider_label(provider: LLMProvider | None) -> str:
    if provider is None:
        return "none"
    return getattr(provider, "model_version", provider.__class__.__name__)


def _allocation_no_trade_reason(allocation_decision) -> str | None:
    if allocation_decision is None or allocation_decision.action != "BUY":
        return None
    if allocation_decision.status == "not_selected":
        binding = allocation_decision.binding_constraint or "none"
        return (
            "No paper trade: not_selected_by_run_allocation; "
            f"binding_constraint={binding}."
        )
    if allocation_decision.status == "allocation_rejected":
        binding = allocation_decision.binding_constraint or "none"
        return (
            "No paper trade: allocation_rejected_by_run_allocation; "
            f"binding_constraint={binding}."
        )
    return None
