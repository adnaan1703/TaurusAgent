from __future__ import annotations

import json
from decimal import Decimal

from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.backtesting import BacktestConfig, BacktestEngine, BacktestResult
from taurus_core.config import Settings, get_settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.session import build_session_factory


def run_mock_backtest(settings: Settings | None = None) -> BacktestResult:
    settings = settings or get_settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    provider = MockMarketDataProvider(
        seed=settings.taurus_mock_seed,
        candle_count=settings.taurus_mock_candle_count,
    )
    with session_factory() as session:
        seed_mock_data(session, provider)

    config = BacktestConfig(
        seed=settings.taurus_mock_seed,
        initial_capital_inr=Decimal(settings.taurus_initial_capital_inr),
        max_open_positions=settings.taurus_max_open_positions,
        timeframe=settings.taurus_timeframe,
    )
    with session_factory() as session:
        return BacktestEngine(session, config).run()


if __name__ == "__main__":
    result = run_mock_backtest()
    print(f"run_id={result.run_id}")
    print(json.dumps(result.metrics, sort_keys=True))
