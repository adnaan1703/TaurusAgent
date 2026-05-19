from __future__ import annotations

from sqlalchemy.orm import Session

from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID
from taurus_core.brokers.paper_broker import PaperBroker
from taurus_core.config import Settings, get_settings
from taurus_core.db.repositories import RiskRepository
from taurus_core.execution.schemas import PaperOrder
from taurus_core.risk.schemas import FinalDecision


class ExecutionRouter:
    """Routes only approved final paper decisions to the PaperBroker."""

    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.paper_broker = PaperBroker(session, self.settings)

    def route_decision(self, decision: FinalDecision) -> PaperOrder | None:
        if not self._is_paper_routable(decision):
            return None
        return self.paper_broker.place_order(decision)

    def route_latest_for_symbol(
        self,
        *,
        symbol: str,
        run_id: str = DEFAULT_ANALYST_RUN_ID,
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
        return self.route_decision(FinalDecision.model_validate(model.payload))

    def _is_paper_routable(self, decision: FinalDecision) -> bool:
        return (
            self.settings.live_trading_enabled is False
            and self.settings.broker_provider == "paper"
            and decision.status == "APPROVED_FOR_PAPER"
            and decision.can_send_to_broker is True
            and decision.approved_quantity > 0
            and decision.final_action in {"BUY", "SELL", "REDUCE", "EXIT"}
        )
