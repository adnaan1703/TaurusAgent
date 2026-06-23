from __future__ import annotations

import json
import os

from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID, run_analyst_suite
from taurus_core.config import Settings, get_settings
from taurus_core.data.preflight import (
    assert_active_instruments_available,
    assert_daily_candles_available,
)
from taurus_core.db.session import build_session_factory
from taurus_core.llm import build_llm_provider
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.logging import configure_logging


def run_mock_analysts(
    *,
    symbol: str,
    settings: Settings | None = None,
    run_id: str = DEFAULT_ANALYST_RUN_ID,
) -> list[dict[str, object]]:
    settings = settings or get_settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        assert_active_instruments_available(session)
        assert_daily_candles_available(session, symbols=[symbol])
        import_mock_news(session, MockNewsProvider())
    with session_factory() as session:
        reports = run_analyst_suite(
            session,
            symbol=symbol,
            run_id=run_id,
            llm_provider=build_llm_provider(settings),
            enabled_analysts=settings.enabled_analyst_keys,
        )
        return [report.model_dump(mode="json") for report in reports]


if __name__ == "__main__":
    configure_logging()
    symbol = os.environ.get("SYMBOL", "INFY")
    reports = run_mock_analysts(symbol=symbol)
    print(json.dumps({"symbol": symbol.upper(), "reports": reports}, sort_keys=True))
