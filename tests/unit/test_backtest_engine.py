from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import select

from scripts.migrate import run_migrations
from scripts.run_backtest import run_mock_backtest
from taurus_core.backtesting import BacktestConfig, BacktestEngine
from taurus_core.config import Settings
from taurus_core.db.models import (
    BacktestPositionModel,
    BacktestRunModel,
    BacktestSignalModel,
    FeatureValueModel,
)
from taurus_core.db.repositories import (
    BacktestRepository,
    CandleRepository,
    InstrumentRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle
from tests.market_data_fixtures import seed_test_market_data


def test_backtest_engine_stores_deterministic_run_artifacts(tmp_path: Path) -> None:
    settings = Settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_test_market_data(session, candle_count=252)

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
    assert first_counts["feature_values"] > 0
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
        "portfolio_breadth",
        "portfolio_breadth_source",
        "ranked_candidate_count",
        "eligible_candidate_count",
        "ranked_candidates_preview",
        "rebalance_count",
    }


def test_backtest_runner_does_not_require_strategy_yaml_target_positions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    strategy_path = tmp_path / "strategy_with_deprecated_targets.yaml"
    strategy_path.write_text(
        "strategy_name: no_target_positions_test\n"
        "strategy_type: moving_average_crossover\n"
        "target_positions: 1\n"
        "lookback_days: 60\n"
        "rebalance_every_days: 21\n"
        "parameters:\n"
        "  fast_window: 10\n"
        "  slow_window: 30\n"
        "  min_return_20d: -1\n",
        encoding="utf-8",
    )
    settings = Settings(taurus_backtest_target_positions=2)
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_test_market_data(session, candle_count=252)

    monkeypatch.setenv("STRATEGY", str(strategy_path))

    result = run_mock_backtest(settings)

    with session_factory() as session:
        run = session.get(BacktestRunModel, result.run_id)

    assert result.metrics["portfolio_breadth"] == 2
    assert result.metrics["portfolio_breadth_source"] == "backtest_config"
    assert result.metrics["ranked_candidate_count"] > 0
    assert result.metrics["ranked_candidates_preview"]
    assert run is not None
    assert run.parameters["portfolio_breadth"] == 2
    assert run.parameters["deprecated_target_positions_input"] is None
    assert run.parameters["strategy_config_path"] == str(strategy_path)


def test_backtest_engine_aligns_candles_by_common_trade_date(tmp_path: Path) -> None:
    settings = Settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        candle_repo = CandleRepository(session)
        instrument_repo.upsert(Instrument(symbol="AAA", name="AAA Ltd"))
        instrument_repo.upsert(Instrument(symbol="BBB", name="BBB Ltd"))
        candle_repo.insert(
            _increasing_candles("AAA", date(2024, 1, 1), 9, future_spike=True)
        )
        candle_repo.insert(_increasing_candles("BBB", date(2024, 1, 2), 7))
        session.commit()

    config = BacktestConfig(
        strategy_name="moving_average_crossover_test",
        strategy_type="moving_average_crossover",
        strategy_parameters={
            "fast_window": 1,
            "slow_window": 2,
            "min_return_20d": -1,
        },
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


def test_feature_snapshots_are_persisted_without_lookahead(tmp_path: Path) -> None:
    settings = Settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        candle_repo = CandleRepository(session)
        instrument_repo.upsert(Instrument(symbol="AAA", name="AAA Ltd"))
        candle_repo.insert(
            [
                DailyCandle(
                    symbol="AAA",
                    trade_date=date(2024, 1, 1) + timedelta(days=index),
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                    volume=1_000 + index,
                    source="test_fixture",
                )
                for index, price in enumerate(
                    [
                        Decimal("100"),
                        Decimal("101"),
                        Decimal("102"),
                        Decimal("103"),
                        Decimal("104"),
                        Decimal("10000"),
                        Decimal("105"),
                    ]
                )
            ]
        )
        session.commit()

    config = BacktestConfig(
        strategy_name="moving_average_crossover_test",
        strategy_type="moving_average_crossover",
        strategy_parameters={
            "fast_window": 2,
            "slow_window": 3,
            "min_return_20d": -1,
        },
        seed=7,
        initial_capital_inr=Decimal("10000"),
        max_open_positions=1,
        target_positions=1,
        lookback_days=4,
        rebalance_every_days=99,
    )
    with session_factory() as session:
        result = BacktestEngine(session, config).run()

    with session_factory() as session:
        sma_row = session.scalar(
            select(FeatureValueModel).where(
                FeatureValueModel.run_id == result.run_id,
                FeatureValueModel.symbol == "AAA",
                FeatureValueModel.feature_name == "sma_3",
            )
        )
        signal = session.scalar(
            select(BacktestSignalModel).where(
                BacktestSignalModel.run_id == result.run_id,
                BacktestSignalModel.symbol == "AAA",
            )
        )

    assert sma_row is not None
    assert sma_row.feature_time == date(2024, 1, 5)
    assert sma_row.data_available_time.date() == result.start_date
    assert sma_row.feature_value == Decimal("103.00000000")
    assert signal is not None
    assert signal.feature_snapshot_id == sma_row.snapshot_id
    assert signal.explanation is not None
    assert signal.explanation["feature_snapshot_id"] == sma_row.snapshot_id


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
                source="test_fixture",
            )
        )
        current_date += timedelta(days=1)
    return candles
