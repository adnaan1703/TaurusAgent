from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.db.repositories import CandleRepository, GraphRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle
from taurus_core.graph.stats import compute_graph_edge_stats


def test_graph_stats_compute_and_persist_synthetic_correlations(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        taurus_graph_stats_windows="6",
        taurus_graph_min_edge_sample_size=3,
    )
    run_migrations(settings)
    _seed_correlated_edge_fixture(settings)

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        summary = compute_graph_edge_stats(
            session,
            settings=settings,
            as_of_date=date(2024, 1, 9),
        )

    with session_factory() as session:
        graph_repo = GraphRepository(session)
        edge = graph_repo.get_edge_by_key("peer:AAA:BBB")
        stats = graph_repo.list_edge_stats(edge_key="peer:AAA:BBB")

        assert edge is not None
        assert edge.status == "candidate"
        assert summary.edges_seen == 1
        assert summary.stats_upserted == 1
        assert summary.insufficient_stats == 0
        assert summary.promoted_edges == ()
        assert len(stats) == 1
        assert stats[0].stat_window == "6d"
        assert stats[0].sample_size == 6
        assert stats[0].insufficient_data_reason == ""
        assert stats[0].raw_correlation is not None
        assert stats[0].raw_correlation > Decimal("0.99")
        assert stats[0].residual_correlation is not None
        assert stats[0].stability_score is not None
        assert stats[0].stability_score > Decimal("0.99")
        assert stats[0].stats_metadata["source_symbol"] == "AAA"
        assert stats[0].stats_metadata["target_symbol"] == "BBB"


def test_graph_stats_record_insufficient_data_without_crashing(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        taurus_graph_stats_windows="6",
        taurus_graph_min_edge_sample_size=3,
    )
    run_migrations(settings)
    _seed_correlated_edge_fixture(settings, include_target_candles=False)

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        summary = compute_graph_edge_stats(
            session,
            settings=settings,
            as_of_date=date(2024, 1, 9),
        )

    with session_factory() as session:
        stats = GraphRepository(session).list_edge_stats(edge_key="peer:AAA:BBB")

        assert summary.stats_upserted == 1
        assert summary.insufficient_stats == 1
        assert len(stats) == 1
        assert stats[0].sample_size == 0
        assert stats[0].raw_correlation is None
        assert stats[0].insufficient_data_reason == "missing_candles:BBB"


def test_graph_stats_auto_promote_only_when_explicitly_enabled(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        taurus_graph_auto_promote_edges=True,
        taurus_graph_stats_windows="6",
        taurus_graph_min_edge_sample_size=3,
        taurus_graph_min_edge_confidence=Decimal("0.50"),
        taurus_graph_min_residual_corr=Decimal("0"),
        taurus_graph_min_lead_lag_score=Decimal("0"),
        taurus_graph_min_stability_score=Decimal("0.90"),
    )
    run_migrations(settings)
    _seed_correlated_edge_fixture(settings)

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        summary = compute_graph_edge_stats(
            session,
            settings=settings,
            as_of_date=date(2024, 1, 9),
        )

    with session_factory() as session:
        graph_repo = GraphRepository(session)
        edge = graph_repo.get_edge_by_key("peer:AAA:BBB")

        assert edge is not None
        assert edge.status == "active"
        assert summary.promoted_edges == ("peer:AAA:BBB",)
        assert edge.edge_metadata["latest_review"]["reviewed_by"] == "graph_stats_job"


def _settings_for_temp_db(tmp_path: Path, **overrides: object) -> Settings:
    values = {"database_url": f"sqlite:///{tmp_path / 'taurus.db'}", **overrides}
    return Settings(**values)


def _seed_correlated_edge_fixture(
    settings: Settings,
    *,
    include_target_candles: bool = True,
) -> None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        for symbol in ("AAA", "BBB", "MKT"):
            instrument_repo.upsert(Instrument(symbol=symbol, name=f"{symbol} Limited"))

        graph_repo = GraphRepository(session)
        graph_repo.upsert_node(
            node_key="company:AAA",
            node_type="company",
            display_name="AAA Limited",
            symbol="AAA",
        )
        graph_repo.upsert_node(
            node_key="company:BBB",
            node_type="company",
            display_name="BBB Limited",
            symbol="BBB",
        )
        graph_repo.upsert_edge(
            edge_key="peer:AAA:BBB",
            source_node_key="company:AAA",
            target_node_key="company:BBB",
            edge_type="peer_momentum",
            direction="directed",
            expected_sign="positive",
            strength=Decimal("0.80"),
            confidence=Decimal("0.90"),
            evidence_type="synthetic",
            mechanism="Synthetic same-direction return fixture.",
            tradability_relevance="signal",
            status="candidate",
        )

        candle_repo = CandleRepository(session)
        source_returns = [
            Decimal("0.010"),
            Decimal("-0.020"),
            Decimal("0.030"),
            Decimal("0.010"),
            Decimal("-0.010"),
            Decimal("0.020"),
            Decimal("0.015"),
            Decimal("-0.005"),
        ]
        target_returns = [item * Decimal("1.5") for item in source_returns]
        market_returns = [
            Decimal("0.004"),
            Decimal("0.002"),
            Decimal("-0.003"),
            Decimal("0.005"),
            Decimal("-0.002"),
            Decimal("0.003"),
            Decimal("0.001"),
            Decimal("-0.004"),
        ]
        candle_repo.upsert(_candles_from_returns("AAA", source_returns))
        if include_target_candles:
            candle_repo.upsert(_candles_from_returns("BBB", target_returns))
        candle_repo.upsert(_candles_from_returns("MKT", market_returns))
        session.commit()


def _candles_from_returns(symbol: str, returns: list[Decimal]) -> list[DailyCandle]:
    start_date = date(2024, 1, 1)
    close = Decimal("100.00")
    candles = [
        DailyCandle(
            symbol=symbol,
            trade_date=start_date,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000_000,
            source="synthetic_graph_stats",
        )
    ]
    for index, return_value in enumerate(returns, start=1):
        trade_date = start_date + timedelta(days=index)
        close = close * (Decimal("1") + return_value)
        candles.append(
            DailyCandle(
                symbol=symbol,
                trade_date=trade_date,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1_000_000,
                source="synthetic_graph_stats",
            )
        )
    return candles
