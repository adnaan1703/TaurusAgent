from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.alerts.service import AlertService
from taurus_core.alerts.templates import risk_review_events
from taurus_core.agents.neutral_risk import NeutralRiskAgent
from taurus_core.agents.risky_risk import RiskyRiskAgent
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID
from taurus_core.agents.safe_risk import SafeRiskAgent
from taurus_core.config import Settings, get_settings
from taurus_core.db.repositories import ResearchRepository, RiskRepository
from taurus_core.logging import get_logger
from taurus_core.observability.tracing import bound_trace_context
from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.engine import RiskEngine
from taurus_core.risk.schemas import (
    RiskReview,
    decision_id_for_proposal,
    risk_review_id,
)


class RiskReviewService:
    model_version = "risk_committee_rules_v1"

    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        *,
        kill_switch_enabled: bool | None = None,
        current_open_positions: int = 0,
        daily_loss_pct: Decimal = Decimal("0"),
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.kill_switch_enabled = kill_switch_enabled
        self.current_open_positions = current_open_positions
        self.daily_loss_pct = daily_loss_pct
        self.risky_agent = RiskyRiskAgent()
        self.neutral_agent = NeutralRiskAgent()
        self.safe_agent = SafeRiskAgent()

    def run(
        self,
        *,
        symbol: str,
        run_id: str = DEFAULT_ANALYST_RUN_ID,
        proposal: TraderProposal | None = None,
    ) -> RiskReview:
        symbol = symbol.upper()
        proposal = proposal or self._load_proposal(symbol=symbol, run_id=run_id)
        if proposal.symbol != symbol:
            raise ValueError("Trader proposal symbol does not match risk review symbol.")

        decision_id = decision_id_for_proposal(
            run_id=proposal.run_id,
            symbol=symbol,
            proposal_id=proposal.proposal_id,
        )
        risk_check_id = risk_review_id(
            run_id=proposal.run_id,
            symbol=symbol,
            proposal_id=proposal.proposal_id,
            source_report_ids=proposal.source_report_ids,
        )
        persona_reviews = [
            self.risky_agent.run(proposal=proposal),
            self.neutral_agent.run(proposal=proposal, settings=self.settings),
            self.safe_agent.run(proposal=proposal, settings=self.settings),
        ]
        engine_result = RiskEngine(
            self.session,
            self.settings,
            kill_switch_enabled=self.kill_switch_enabled,
            current_open_positions=self.current_open_positions,
            daily_loss_pct=self.daily_loss_pct,
        ).evaluate(
            proposal=proposal,
            decision_id=decision_id,
            risk_check_id=risk_check_id,
        )
        review = RiskReview(
            risk_check_id=risk_check_id,
            decision_id=decision_id,
            run_id=proposal.run_id,
            symbol=symbol,
            proposal_id=proposal.proposal_id,
            debate_id=proposal.debate_id,
            as_of=proposal.as_of,
            status=engine_result.status,
            requested_position_pct_nav=proposal.requested_position_pct_nav,
            approved_position_pct_nav=engine_result.approved_position_pct_nav,
            hard_rule_results=engine_result.hard_rule_results,
            persona_reviews=persona_reviews,
            risk_committee_summary=self._summary(engine_result.status, persona_reviews),
            source_report_ids=proposal.source_report_ids,
            is_order=False,
            can_send_to_broker=False,
            model_version=self.model_version,
        )
        RiskRepository(self.session).replace_risk_review_for_run_symbol(review)
        self.session.commit()
        self._send_risk_alerts(review)
        with bound_trace_context(
            run_id=proposal.run_id,
            decision_id=decision_id,
            debate_id=proposal.debate_id,
            proposal_id=proposal.proposal_id,
            risk_check_id=risk_check_id,
        ):
            get_logger(__name__).info(
                "risk.review.created",
                symbol=symbol,
                status=review.status,
                approved_position_pct_nav=str(review.approved_position_pct_nav),
                hard_rule_count=len(review.hard_rule_results),
            )
        return review

    def _send_risk_alerts(self, review: RiskReview) -> None:
        events = risk_review_events(review)
        if not events:
            return
        try:
            AlertService(self.session, self.settings).send_many(events)
        except Exception as exc:
            get_logger(__name__).warning(
                "alert.risk_review.failed",
                risk_check_id=review.risk_check_id,
                status=review.status,
                error=str(exc),
            )

    def _load_proposal(self, *, symbol: str, run_id: str) -> TraderProposal:
        proposals = ResearchRepository(self.session).list_trader_proposals(symbol=symbol, limit=100)
        for model in proposals:
            proposal = TraderProposal.model_validate(model.payload)
            if proposal.run_id == run_id:
                return proposal
        raise ValueError(
            f"No trader proposal found for {symbol} run_id={run_id}. "
            "Run make trader-proposal-mock first."
        )

    def _summary(self, status: str, persona_reviews) -> str:
        recommendations = ", ".join(
            f"{review.agent_name}={review.recommendation}" for review in persona_reviews
        )
        return (
            f"Risk committee status {status}; hard rules are authoritative. "
            f"Persona recommendations: {recommendations}."
        )


__all__ = ["RiskReviewService"]
