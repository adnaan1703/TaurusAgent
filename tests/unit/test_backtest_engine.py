from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.backtesting import BacktestConfig, BacktestEngine
from taurus_core.config import Settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.models import BacktestPositionModel
from taurus_core.db.repositories import BacktestRepository, CandleRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle


def test_backtest_engine_stores_deterministic_run_artifacts(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_mock_data(session, MockMarketDataProvider(seed=42, candle_count=252))

    config = BacktestConfig(
        seed=42,
        initial_capital_inr=Decimal("1000000"),
        max_open_positions=8,
    )
    with session_factory() as session:
        first = BacktestEngine(session, config).run()

    with session_factory() as session:
        repo = BacktestRepository(session)
        persisted = repo.get_run(first.run_id)
        first_counts = repo.count_artifacts(first.run_id)

    with session_factory() as session:
        second = BacktestEngine(session, config).run()

    with session_factory() as session:
        second_counts = BacktestRepository(session).count_artifacts(second.run_id)

    assert persisted is not None
    assert first.run_id == second.run_id
    assert first.metrics == second.metrics
    assert first_counts == second_counts
    assert first_counts["signals"] > 0
    assert first_counts["orders"] > 0
    assert first_counts["fills"] == first_counts["orders"]
    assert first_counts["positions"] > 0
    assert first_counts["equity_points"] > 0
    assert first_counts["audit_rows"] == 2
    assert set(first.metrics) == {
        "total_return",
        "cagr",
        "sharpe",
        "sortino",
        "max_drawdown",
        "win_rate",
        "profit_factor",
    }


def test_backtest_engine_aligns_candles_by_common_trade_date(tmp_path: Path) -> None:
    settings = Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        candle_repo = CandleRepository(session)
        instrument_repo.upsert(Instrument(symbol="AAA", name="AAA Ltd"))
        instrument_repo.upsert(Instrument(symbol="BBB", name="BBB Ltd"))
        candle_repo.insert(_increasing_candles("AAA", date(2024, 1, 1), 9, future_spike=True))
        candle_repo.insert(_increasing_candles("BBB", date(2024, 1, 2), 7))
        session.commit()

    config = BacktestConfig(
        seed=7,
        initial_capital_inr=Decimal("10000"),
        max_open_positions=2,
        target_positions=2,
        lookback_days=2,
        rebalance_every_days=99,
    )
    with session_factory() as session:
        result = BacktestEngine(session, config).run()

    with session_factory() as session:
        aaa_position = session.scalar(
            select(BacktestPositionModel).where(
                BacktestPositionModel.run_id == result.run_id,
                BacktestPositionModel.symbol == "AAA",
            )
        )

    assert result.end_date == date(2024, 1, 8)
    assert aaa_position is not None
    assert aaa_position.market_value_inr < Decimal("20000")


def _increasing_candles(
    symbol: str,
    start_date: date,
    count: int,
    *,
    future_spike: bool = False,
) -> list[DailyCandle]:
    candles: list[DailyCandle] = []
    current_date = start_date
    for index in range(count):
        price = Decimal("100") + Decimal(index)
        if future_spike and index == count - 1:
            price = Decimal("10000")
        candles.append(
            DailyCandle(
                symbol=symbol,
                trade_date=current_date,
                open=price,
                high=price,
                low=price,
                close=price,
                volume=1_000,
            )
        )
        current_date += timedelta(days=1)
    return candles
