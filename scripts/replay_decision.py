from __future__ import annotations

import json
import os

from sqlalchemy import select

from scripts.migrate import run_migrations
from scripts.run_paper_once import run_mock_paper_once
from taurus_core.config import Settings, get_settings
from taurus_core.db.models import FinalDecisionModel
from taurus_core.db.session import build_session_factory
from taurus_core.logging import configure_logging
from taurus_core.replay.service import DecisionReplayService


def replay_decision(
    *,
    decision_id: str,
    settings: Settings | None = None,
    symbol: str = "INFY",
) -> dict[str, object]:
    settings = settings or get_settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)

    if decision_id == "sample":
        decision_id = _latest_decision_id(session_factory) or _create_sample_decision(
            settings=settings,
            symbol=symbol,
        )

    with session_factory() as session:
        replay = DecisionReplayService(session).replay(decision_id=decision_id)
        return replay.model_dump(mode="json")


def _latest_decision_id(session_factory) -> str | None:
    with session_factory() as session:
        row = session.scalar(
            select(FinalDecisionModel)
            .order_by(FinalDecisionModel.as_of.desc(), FinalDecisionModel.final_decision_id)
            .limit(1)
        )
        return row.decision_id if row is not None else None


def _create_sample_decision(*, settings: Settings, symbol: str) -> str:
    payload = run_mock_paper_once(symbol=symbol, settings=settings)
    final_decision = payload["final_decision"]
    if not isinstance(final_decision, dict):
        raise ValueError("Sample paper run did not produce a final decision.")
    return str(final_decision["decision_id"])


if __name__ == "__main__":
    configure_logging()
    payload = replay_decision(
        decision_id=os.environ.get("DECISION_ID", "sample"),
        symbol=os.environ.get("SYMBOL", "INFY"),
    )
    print(json.dumps(payload, sort_keys=True))
