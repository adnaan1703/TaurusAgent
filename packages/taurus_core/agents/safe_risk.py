from __future__ import annotations

from decimal import Decimal

from taurus_core.config import Settings
from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.schemas import RiskPersonaReview

SCORE_QUANT = Decimal("0.0001")


class SafeRiskAgent:
    agent_name = "SafeRiskAgent"
    model_version = "risk_persona_safe_rules_v1"

    def run(self, *, proposal: TraderProposal, settings: Settings) -> RiskPersonaReview:
        half_cap = (Decimal(str(settings.taurus_max_position_pct)) / Decimal("2")).quantize(
            SCORE_QUANT
        )
        if proposal.action != "BUY" or proposal.requested_position_pct_nav == 0:
            recommendation = "reject"
            score = Decimal("-0.3000")
            key_points = [f"Conservative view avoids exposure for action {proposal.action}."]
        elif proposal.confidence < Decimal("0.5500"):
            recommendation = "reduce"
            score = Decimal("0.0500")
            key_points = [
                f"Proposal confidence {proposal.confidence} is modest.",
                f"Conservative size should not exceed {half_cap}% NAV.",
            ]
        else:
            recommendation = "reduce" if proposal.requested_position_pct_nav > half_cap else "allow"
            score = Decimal("0.2500")
            key_points = [
                f"Safe view prefers sizing at or below {half_cap}% NAV.",
                "Fresh severe negative events should block long exposure.",
            ]

        return RiskPersonaReview(
            agent_name=self.agent_name,
            recommendation=recommendation,
            score=score.quantize(SCORE_QUANT),
            confidence=Decimal("0.8000"),
            key_points=key_points,
            required_conditions=[
                "Use deterministic hard rules over persona recommendations.",
                "Require portfolio manager final approval before paper execution.",
            ],
            model_version=self.model_version,
        )
