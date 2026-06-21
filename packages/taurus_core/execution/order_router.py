from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID
from taurus_core.brokers.paper_broker import PaperBroker
from taurus_core.config import Settings, get_settings
from taurus_core.db.repositories import PaperRunRepository, ResearchRepository, RiskRepository
from taurus_core.execution.schemas import ExecutionPolicy, PaperOrder
from taurus_core.risk.schemas import FinalDecision


class ExecutionRouter:
    """Routes only approved final paper decisions to the PaperBroker."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.paper_broker = PaperBroker(session, self.settings)

    def route_decision(
        self,
        decision: FinalDecision,
        *,
        execution_policy: ExecutionPolicy | None = None,
        submitted_at: datetime | None = None,
        pending_affordability_cash_inr: Decimal | None = None,
    ) -> PaperOrder | None:
        if not self._is_paper_routable(decision):
            return None
        policy = execution_policy or self._execution_policy_for_decision(decision)
        return self.paper_broker.place_order(
            decision,
            execution_policy=policy,
            submitted_at=submitted_at,
            pending_affordability_cash_inr=pending_affordability_cash_inr,
        )

    def route_latest_for_symbol(
        self,
        *,
        symbol: str,
        run_id: str = DEFAULT_ANALYST_RUN_ID,
        execution_policy: ExecutionPolicy | None = None,
    ) -> PaperOrder | None:
        model = RiskRepository(self.session).latest_final_decision(
            symbol=symbol,
            run_id=run_id,
        )
        if model is None:
            raise ValueError(
                f"No final decision found for {symbol.upper()} run_id={run_id}. "
                "Run make final-approval-mock first."
            )
        return self.route_decision(
            FinalDecision.model_validate(model.payload),
            execution_policy=execution_policy,
        )

    def _is_paper_routable(self, decision: FinalDecision) -> bool:
        return (
            self.settings.live_trading_enabled is False
            and self.settings.broker_provider == "paper"
            and decision.status == "APPROVED_FOR_PAPER"
            and decision.can_send_to_broker is True
            and decision.approved_quantity > 0
            and decision.final_action in {"BUY", "REDUCE", "EXIT"}
        )

    def _execution_policy_for_decision(self, decision: FinalDecision) -> ExecutionPolicy:
        proposal = ResearchRepository(self.session).get_trader_proposal(decision.proposal_id)
        if proposal is not None:
            if proposal.evaluation_mode == "market_hours":
                return "immediate"
            if proposal.evaluation_mode == "after_close":
                return "next_open"

        run = PaperRunRepository(self.session).get(decision.run_id)
        if run is not None:
            return "next_open" if run.run_after_market_close else "immediate"

        return "immediate"
