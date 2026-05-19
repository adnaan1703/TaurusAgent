from __future__ import annotations

from decimal import Decimal

from taurus_core.config import Settings
from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.schemas import RiskPersonaReview

SCORE_QUANT = Decimal("0.0001")


class NeutralRiskAgent:
    agent_name = "NeutralRiskAgent"
    model_version = "risk_persona_neutral_rules_v1"

    def run(self, *, proposal: TraderProposal, settings: Settings) -> RiskPersonaReview:
        max_position = Decimal(str(settings.taurus_max_position_pct))
        if proposal.action != "BUY" or proposal.requested_position_pct_nav == 0:
            recommendation = "reject"
            score = Decimal("-0.2000")
            key_points = [f"No new paper exposure is needed for action {proposal.action}."]
        elif proposal.requested_position_pct_nav > max_position:
            recommendation = "reduce"
            score = Decimal("0.1500")
            key_points = [
                f"Requested {proposal.requested_position_pct_nav}% exceeds cap {max_position}%.",
                "Resize to the configured risk budget before fund manager review.",
            ]
        else:
            recommendation = "allow"
            score = min(Decimal("0.6500"), proposal.confidence).quantize(SCORE_QUANT)
            key_points = [
                f"Requested {proposal.requested_position_pct_nav}% is within position cap.",
                "Paper-only final approval can consider the proposal after hard checks.",
            ]

        return RiskPersonaReview(
            agent_name=self.agent_name,
            recommendation=recommendation,
            score=score.quantize(SCORE_QUANT),
            confidence=Decimal("0.7200"),
            key_points=key_points,
            required_conditions=[
                "Confirm hard-rule results are stored.",
                "Do not route a broker order from risk committee output.",
            ],
            model_version=self.model_version,
        )
