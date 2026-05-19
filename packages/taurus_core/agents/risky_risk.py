from __future__ import annotations

from decimal import Decimal

from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.schemas import RiskPersonaReview

SCORE_QUANT = Decimal("0.0001")


class RiskyRiskAgent:
    agent_name = "RiskyRiskAgent"
    model_version = "risk_persona_risky_rules_v1"

    def run(self, *, proposal: TraderProposal) -> RiskPersonaReview:
        if proposal.action == "BUY" and proposal.requested_position_pct_nav > 0:
            recommendation = "allow"
            score = min(
                Decimal("1"),
                proposal.confidence + (proposal.requested_position_pct_nav / Decimal("100")),
            )
            key_points = [
                f"Reward-seeking view allows {proposal.action} if hard rules approve.",
                f"Requested position is {proposal.requested_position_pct_nav}% NAV.",
            ]
            conditions = [
                "Hard risk engine must pass before any final paper approval.",
                "Stop-loss and invalidation rules must remain attached to the decision.",
            ]
        else:
            recommendation = "reject"
            score = Decimal("-0.2500")
            key_points = [f"Trader action {proposal.action} does not justify a new risk budget."]
            conditions = ["Wait for a fresh trader proposal before considering exposure."]

        return RiskPersonaReview(
            agent_name=self.agent_name,
            recommendation=recommendation,
            score=score.quantize(SCORE_QUANT),
            confidence=Decimal("0.6500"),
            key_points=key_points,
            required_conditions=conditions,
            model_version=self.model_version,
        )
