from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select

from scripts.migrate import run_migrations
from taurus_core.backtesting import BacktestConfig, BacktestEngine
from taurus_core.data.importers import import_market_data
from taurus_core.data.providers.csv_market_data import (
    CSVMarketDataProvider,
    DisabledExternalMarketDataProvider,
)
from taurus_core.config import Settings
from taurus_core.db.models import DailyCandleModel
from taurus_core.db.repositories import BacktestRepository, CandleRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.market_data import MarketDataProviderError

PRICE_FIXTURE = Path("mock/market_data/prices_sample.csv")


def test_csv_market_data_provider_reads_synthetic_fixture() -> None:
    provider = CSVMarketDataProvider(csv_path=PRICE_FIXTURE)

    assert provider.provider_name == "csv"
    assert [instrument.symbol for instrument in provider.list_instruments()] == [
        "INFY",
        "RELIANCE",
        "TCS",
    ]
    infy_candles = provider.get_daily_candles("infy")
    assert len(infy_candles) == 12
    assert infy_candles[0].open == Decimal("1400.00")
    assert infy_candles[0].source == "csv_market_data:prices_sample.csv"
    assert infy_candles[0].data_available_time == datetime(
        2024,
        1,
        1,
        18,
        tzinfo=timezone.utc,
    )
    assert provider.get_latest_candle("INFY") == infy_candles[-1]

    snapshots = provider.get_latest_snapshots(["infy"])
    assert len(snapshots) == 1
    assert snapshots[0].symbol == "INFY"
    assert snapshots[0].provider == "csv"
    assert snapshots[0].last_price == infy_candles[-1].close
    assert snapshots[0].source == "csv_market_data:prices_sample.csv:latest_candle"


def test_csv_market_data_import_records_source_and_available_time(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    provider = CSVMarketDataProvider(csv_path=PRICE_FIXTURE)

    with session_factory() as session:
        first_summary = import_market_data(session, provider)

    with session_factory() as session:
        second_summary = import_market_data(session, provider)
        candle_repo = CandleRepository(session)
        persisted = session.scalar(
            select(DailyCandleModel).where(
                DailyCandleModel.symbol == "INFY",
                DailyCandleModel.trade_date == date(2024, 1, 1),
            )
        )
        infy_count = candle_repo.count_by_symbol(symbol="INFY")

    assert first_summary == second_summary
    assert first_summary.candle_count == 36
    assert infy_count == 12
    assert persisted is not None
    assert persisted.source == "csv_market_data:prices_sample.csv"
    assert _as_utc(persisted.data_available_time) == datetime(
        2024,
        1,
        1,
        18,
        tzinfo=timezone.utc,
    )


def test_backtest_can_run_after_csv_import(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        import_market_data(session, CSVMarketDataProvider(csv_path=PRICE_FIXTURE))

    config = BacktestConfig(
        strategy_name="csv_market_data_smoke_v1",
        strategy_type="moving_average_crossover",
        strategy_parameters={
            "fast_window": 2,
            "slow_window": 4,
            "min_spread": 0,
            "min_return_20d": -1,
        },
        seed=42,
        initial_capital_inr=Decimal("1000000"),
        max_open_positions=2,
        target_positions=2,
        lookback_days=5,
        rebalance_every_days=2,
    )
    with session_factory() as session:
        result = BacktestEngine(session, config).run()

    with session_factory() as session:
        counts = BacktestRepository(session).count_artifacts(result.run_id)

    assert result.start_date.isoformat() == "2024-01-09"
    assert counts["feature_values"] > 0
    assert counts["signals"] > 0
    assert counts["orders"] > 0


def test_external_market_data_provider_is_disabled_without_credentials() -> None:
    provider = DisabledExternalMarketDataProvider()

    with pytest.raises(MarketDataProviderError, match="disabled"):
        provider.list_instruments()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
