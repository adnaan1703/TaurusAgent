from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from scripts.migrate import run_migrations
from taurus_core.backtesting import BacktestConfig, BacktestEngine, GraphBacktestSignalLoader
from taurus_core.backtesting.graph import GraphBacktestSignal
from taurus_core.config import Settings
from taurus_core.db.repositories import CandleRepository, GraphRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.store import FeatureSnapshot
from taurus_core.strategies.graph_aware import GraphAwareScoreStrategy


def test_graph_signal_loader_uses_only_stats_available_by_as_of_date(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    _seed_graph_fixture(settings)

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        loader = GraphBacktestSignalLoader(session)
        as_of_signal = loader.load_symbol(as_of_date=date(2024, 1, 5), symbol="AAA")
        future_signal = loader.load_symbol(as_of_date=date(2024, 1, 10), symbol="AAA")

    assert as_of_signal is not None
    assert future_signal is not None
    assert as_of_signal.score < Decimal("0")
    assert future_signal.score > Decimal("0")
    assert as_of_signal.contributions[0].stat_as_of_date == date(2024, 1, 4)
    assert future_signal.contributions[0].stat_as_of_date == date(2024, 1, 9)


def test_graph_signal_loader_excludes_future_edges_and_evidence(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    _seed_graph_fixture(
        settings,
        valid_from=date(2024, 1, 8),
        evidence_date=date(2024, 1, 8),
        include_future_stat=False,
    )

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        loader = GraphBacktestSignalLoader(session)
        before_available = loader.load_symbol(as_of_date=date(2024, 1, 5), symbol="AAA")
        after_available = loader.load_symbol(as_of_date=date(2024, 1, 8), symbol="AAA")

    assert before_available is None
    assert after_available is not None
    assert after_available.contributions[0].evidence_count == 1


def test_graph_aware_strategy_combines_technical_and_graph_scores() -> None:
    strategy = GraphAwareScoreStrategy(
        name="graph_aware_test",
        target_positions=1,
        parameters={
            "fast_window": 1,
            "slow_window": 2,
            "technical_weight": "0",
            "graph_weight": "1",
            "min_combined_score": "0.10",
            "require_graph_signal": True,
        },
    )
    graph_signal = GraphBacktestSignal(
        symbol="AAA",
        as_of_date=date(2024, 1, 5),
        score=Decimal("0.50000000"),
        confidence=Decimal("0.90000000"),
        contributions=(),
    )

    targets, signals = strategy.select_targets_with_graph(
        trade_date=date(2024, 1, 5),
        features_by_symbol={
            "AAA": _feature_snapshot("AAA", sma_1=Decimal("101"), sma_2=Decimal("100")),
            "BBB": _feature_snapshot("BBB", sma_1=Decimal("120"), sma_2=Decimal("100")),
        },
        current_positions=set(),
        graph_signals_by_symbol={"AAA": graph_signal},
    )

    assert targets == {"AAA"}
    assert len(signals) == 1
    assert signals[0].score == Decimal("0.50000000")
    assert signals[0].explanation.metadata["graph_signal"]["score"] == "0.50000000"


def test_graph_aware_backtest_summarizes_performance_by_edge_type(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    _seed_backtest_fixture(settings)

    config = BacktestConfig(
        strategy_name="graph_aware_score_test",
        strategy_type="graph_aware_score",
        strategy_parameters={
            "fast_window": 1,
            "slow_window": 2,
            "technical_weight": "0",
            "graph_weight": "1",
            "min_combined_score": "0",
            "require_graph_signal": True,
        },
        seed=7,
        initial_capital_inr=Decimal("10000"),
        max_open_positions=1,
        target_positions=1,
        lookback_days=2,
        rebalance_every_days=2,
        graph_enabled=True,
    )

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        result = BacktestEngine(session, config).run()

    assert result.metrics["graph_trade_count"] == 1
    assert result.metrics["graph_hit_rate"] == 1.0
    assert result.metrics["graph_average_return"] > 0
    grouped = result.metrics["graph_performance_by_edge_type"]
    assert isinstance(grouped, dict)
    assert grouped["peer_momentum"]["trade_count"] == 1
    assert grouped["peer_momentum"]["hit_rate"] == 1.0


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")


def _seed_graph_fixture(
    settings: Settings,
    *,
    valid_from: date | None = date(2024, 1, 1),
    evidence_date: date | None = date(2024, 1, 3),
    include_future_stat: bool = True,
) -> None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        _seed_instruments(session, ("AAA", "BBB"))
        graph_repo = GraphRepository(session)
        _seed_company_nodes(graph_repo, ("AAA", "BBB"))
        graph_repo.upsert_edge(
            edge_key="peer:AAA:BBB",
            source_node_key="company:AAA",
            target_node_key="company:BBB",
            edge_type="peer_momentum",
            direction="bidirectional",
            expected_sign="positive",
            strength=Decimal("0.8000"),
            confidence=Decimal("0.9000"),
            status="active",
            valid_from=valid_from,
        )
        if evidence_date is not None:
            graph_repo.upsert_edge_evidence(
                edge_key="peer:AAA:BBB",
                evidence_id=f"evidence:{evidence_date.isoformat()}",
                claim_type="peer_mapping",
                claim_summary="Synthetic graph backtest evidence.",
                source_date=evidence_date,
                confidence=Decimal("0.9000"),
            )
        graph_repo.upsert_edge_stats(
            edge_key="peer:AAA:BBB",
            window="20d",
            as_of_date=date(2024, 1, 4),
            sample_size=20,
            raw_correlation=Decimal("-0.8000"),
            residual_correlation=Decimal("-0.7500"),
            lead_lag_score=Decimal("-0.5000"),
            stability_score=Decimal("0.9000"),
        )
        if include_future_stat:
            graph_repo.upsert_edge_stats(
                edge_key="peer:AAA:BBB",
                window="20d",
                as_of_date=date(2024, 1, 9),
                sample_size=20,
                raw_correlation=Decimal("0.8000"),
                residual_correlation=Decimal("0.7500"),
                lead_lag_score=Decimal("0.5000"),
                stability_score=Decimal("0.9000"),
            )
        session.commit()


def _seed_backtest_fixture(settings: Settings) -> None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        _seed_instruments(session, ("AAA", "BBB"))
        CandleRepository(session).upsert(_candles("AAA", [100, 101, 102, 100, 106, 110, 109, 108]))
        CandleRepository(session).upsert(_candles("BBB", [100, 101, 102, 103, 104, 105, 106, 107]))

        graph_repo = GraphRepository(session)
        _seed_company_nodes(graph_repo, ("AAA", "BBB"))
        graph_repo.upsert_edge(
            edge_key="peer:AAA:BBB",
            source_node_key="company:AAA",
            target_node_key="company:BBB",
            edge_type="peer_momentum",
            direction="bidirectional",
            expected_sign="positive",
            strength=Decimal("0.8000"),
            confidence=Decimal("0.9000"),
            status="active",
            valid_from=date(2024, 1, 1),
            valid_to=date(2024, 1, 4),
        )
        graph_repo.upsert_edge_evidence(
            edge_key="peer:AAA:BBB",
            evidence_id="evidence:peer:AAA:BBB",
            claim_type="peer_mapping",
            claim_summary="Synthetic graph backtest evidence.",
            source_date=date(2024, 1, 3),
            confidence=Decimal("0.9000"),
        )
        graph_repo.upsert_edge_stats(
            edge_key="peer:AAA:BBB",
            window="20d",
            as_of_date=date(2024, 1, 4),
            sample_size=20,
            raw_correlation=Decimal("0.8000"),
            residual_correlation=Decimal("0.7500"),
            lead_lag_score=Decimal("0.5000"),
            stability_score=Decimal("0.9000"),
        )
        session.commit()


def _seed_instruments(session, symbols: tuple[str, ...]) -> None:
    instrument_repo = InstrumentRepository(session)
    for symbol in symbols:
        instrument_repo.upsert(Instrument(symbol=symbol, name=f"{symbol} Limited"))


def _seed_company_nodes(graph_repo: GraphRepository, symbols: tuple[str, ...]) -> None:
    for symbol in symbols:
        graph_repo.upsert_node(
            node_key=f"company:{symbol}",
            node_type="company",
            display_name=f"{symbol} Limited",
            symbol=symbol,
        )


def _candles(symbol: str, prices: list[int]) -> list[DailyCandle]:
    start = date(2024, 1, 1)
    return [
        DailyCandle(
            symbol=symbol,
            trade_date=start + timedelta(days=index),
            open=Decimal(price),
            high=Decimal(price),
            low=Decimal(price),
            close=Decimal(price),
            volume=1_000 + index,
        )
        for index, price in enumerate(prices)
    ]


def _feature_snapshot(symbol: str, *, sma_1: Decimal, sma_2: Decimal) -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=f"fs-{symbol}",
        symbol=symbol,
        as_of_date=date(2024, 1, 5),
        feature_time=date(2024, 1, 4),
        values={
            "sma_1": sma_1,
            "sma_2": sma_2,
            "return_20d": Decimal("0"),
        },
        rows=(),
    )
