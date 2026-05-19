from __future__ import annotations

import json
import os

from scripts.run_final_approval import run_mock_final_approval
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID
from taurus_core.config import Settings, get_settings
from taurus_core.db.repositories import ExecutionRepository
from taurus_core.db.session import build_session_factory
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.execution.schemas import PaperAccount, PaperPosition
from taurus_core.logging import configure_logging


def run_mock_paper_once(
    *,
    symbol: str,
    settings: Settings | None = None,
    run_id: str = DEFAULT_ANALYST_RUN_ID,
) -> dict[str, object]:
    settings = settings or get_settings()
    final_decision = run_mock_final_approval(symbol=symbol, settings=settings, run_id=run_id)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        order = ExecutionRouter(session, settings).route_latest_for_symbol(
            symbol=symbol,
            run_id=run_id,
        )
        repo = ExecutionRepository(session)
        account_model = repo.latest_account(run_id=run_id)
        positions = repo.list_positions(symbol=symbol)
        return {
            "symbol": symbol.upper(),
            "run_id": run_id,
            "final_decision": final_decision,
            "order": order.model_dump(mode="json") if order is not None else None,
            "account": (
                PaperAccount.model_validate(account_model.payload).model_dump(mode="json")
                if account_model is not None
                else None
            ),
            "positions": [
                PaperPosition.model_validate(position.payload).model_dump(mode="json")
                for position in positions
            ],
        }


if __name__ == "__main__":
    configure_logging()
    symbol = os.environ.get("SYMBOL", "INFY")
    payload = run_mock_paper_once(symbol=symbol)
    print(json.dumps(payload, sort_keys=True))
