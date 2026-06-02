from __future__ import annotations

import json
import os
from decimal import Decimal

from scripts.migrate import run_migrations
from taurus_core.backtesting import BacktestConfig, BacktestEngine, BacktestResult
from taurus_core.config import Settings, get_settings
from taurus_core.data.preflight import assert_no_legacy_mock_candles
from taurus_core.db.session import build_session_factory
from taurus_core.logging import configure_logging
from taurus_core.strategies import DEFAULT_STRATEGY_CONFIG_PATH, load_strategy_config


def run_mock_backtest(settings: Settings | None = None) -> BacktestResult:
    settings = settings or get_settings()
    strategy_path = os.environ.get("STRATEGY") or str(DEFAULT_STRATEGY_CONFIG_PATH)
    strategy_config = load_strategy_config(strategy_path)
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        assert_no_legacy_mock_candles(session)

    config = BacktestConfig(
        strategy_name=strategy_config.strategy_name,
        strategy_type=strategy_config.strategy_type,
        strategy_config_path=strategy_config.source_path,
        strategy_parameters=strategy_config.parameters,
        seed=42,
        initial_capital_inr=Decimal(settings.taurus_initial_capital_inr),
        max_open_positions=settings.taurus_max_open_positions,
        target_positions=strategy_config.target_positions
        or settings.taurus_max_open_positions,
        lookback_days=strategy_config.lookback_days,
        rebalance_every_days=strategy_config.rebalance_every_days,
        timeframe=settings.taurus_timeframe,
        graph_enabled=(
            strategy_config.strategy_type == "graph_aware_score"
            or bool(strategy_config.parameters.get("graph_enabled", False))
        ),
    )
    with session_factory() as session:
        return BacktestEngine(session, config).run()


if __name__ == "__main__":
    configure_logging()
    result = run_mock_backtest()
    print(f"run_id={result.run_id}")
    print(json.dumps(result.metrics, sort_keys=True))
