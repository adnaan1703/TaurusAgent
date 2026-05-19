from __future__ import annotations

import json
import os

from scripts.run_risk_review import run_mock_risk_review
from taurus_core.agents.portfolio_manager import PortfolioManagerAgent
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID
from taurus_core.config import Settings, get_settings
from taurus_core.db.repositories import RiskRepository
from taurus_core.db.session import build_session_factory
from taurus_core.risk.schemas import RiskReview


def run_mock_final_approval(
    *,
    symbol: str,
    settings: Settings | None = None,
    run_id: str = DEFAULT_ANALYST_RUN_ID,
) -> dict[str, object]:
    settings = settings or get_settings()
    run_mock_risk_review(symbol=symbol, settings=settings, run_id=run_id)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        review_model = RiskRepository(session).latest_risk_review(symbol=symbol, run_id=run_id)
        if review_model is None:
            raise ValueError(f"No risk review found for {symbol} run_id={run_id}.")
        decision = PortfolioManagerAgent(session, settings).run(
            symbol=symbol,
            run_id=run_id,
            risk_review=RiskReview.model_validate(review_model.payload),
        )
        return decision.model_dump(mode="json")


if __name__ == "__main__":
    symbol = os.environ.get("SYMBOL", "INFY")
    payload = run_mock_final_approval(symbol=symbol)
    print(json.dumps(payload, sort_keys=True))
