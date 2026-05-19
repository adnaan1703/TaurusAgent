from __future__ import annotations

import json
import os

from scripts.run_trader_proposal import run_mock_trader_proposal
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID
from taurus_core.config import Settings, get_settings
from taurus_core.db.session import build_session_factory
from taurus_core.risk.review_service import RiskReviewService


def run_mock_risk_review(
    *,
    symbol: str,
    settings: Settings | None = None,
    run_id: str = DEFAULT_ANALYST_RUN_ID,
) -> dict[str, object]:
    settings = settings or get_settings()
    run_mock_trader_proposal(symbol=symbol, settings=settings, run_id=run_id)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        review = RiskReviewService(session, settings).run(symbol=symbol, run_id=run_id)
        return review.model_dump(mode="json")


if __name__ == "__main__":
    symbol = os.environ.get("SYMBOL", "INFY")
    payload = run_mock_risk_review(symbol=symbol)
    print(json.dumps(payload, sort_keys=True))
