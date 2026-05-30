from __future__ import annotations

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
from taurus_core.logging import get_logger
from taurus_core.observability.tracing import bound_trace_context
from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.schemas import (
    FinalDecision,
    RiskReview,
    final_decision_id,
)

SCORE_QUANT = Decimal("0.0001")


class PortfolioManagerAgent:
    agent_name = "PortfolioManagerAgent"
    model_version = "portfolio_manager_lifecycle_rules_v1"

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

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
        final_action = "NO_TRADE"
        status = "REJECTED"
        can_send_to_broker = False
        approved_position = Decimal("0.0000")
        approved_quantity = 0
        reason = f"Rejected because risk status is {risk_review.status}."

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
                reason = f"Approved {final_action}; no paper order expected."
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

        decision = FinalDecision(
            final_decision_id=final_decision_id(
                run_id=risk_review.run_id,
                symbol=symbol,
                proposal_id=risk_review.proposal_id,
                risk_check_id=risk_review.risk_check_id,
            ),
            decision_id=risk_review.decision_id,
            run_id=risk_review.run_id,
            symbol=symbol,
            proposal_id=risk_review.proposal_id,
            risk_check_id=risk_review.risk_check_id,
            as_of=risk_review.as_of,
            final_action=final_action,
            status=status,
            approved_quantity=approved_quantity,
            approved_position_pct_nav=approved_position,
            reason=reason,
            is_order=False,
            can_send_to_broker=can_send_to_broker,
            model_version=self.model_version,
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
            else Decimal(str(self.settings.taurus_initial_capital_inr))
        )
        notional = equity * approved_position_pct_nav / Decimal("100")
        return int(notional // latest_close)

    def _paper_safe(self) -> bool:
        return (
            self.settings.live_trading_enabled is False
            and self.settings.broker_provider == "paper"
            and self.settings.taurus_mode in {"paper", "backtest"}
        )
