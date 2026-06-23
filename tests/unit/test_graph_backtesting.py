from __future__ import annotations

import json
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from scripts.migrate import run_migrations
from scripts.validate_technical_v2 import (
    ValidationRequest,
    build_data_readiness,
    run_validation,
)
from taurus_core.backtesting import (
    BacktestConfig,
    BacktestEngine,
    GraphBacktestSignalLoader,
)
from taurus_core.backtesting.graph import GraphBacktestSignal
from taurus_core.config import Settings
from taurus_core.db.repositories import (
    CandleRepository,
    GraphRepository,
    InstrumentRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.store import FeatureSnapshot
from taurus_core.strategies.graph_aware import GraphAwareScoreStrategy


def test_graph_signal_loader_uses_only_stats_available_by_as_of_date(
    tmp_path: Path,
) -> None:
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


def test_graph_signal_loader_ignores_raw_edge_confidence_for_contributions(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    _seed_graph_fixture(settings, confidence=Decimal("0.1000"))

    low_confidence_signal = _load_graph_signal(settings, as_of_date=date(2024, 1, 10))
    _seed_graph_fixture(settings, confidence=Decimal("0.9500"))
    high_confidence_signal = _load_graph_signal(settings, as_of_date=date(2024, 1, 10))

    assert low_confidence_signal is not None
    assert high_confidence_signal is not None
    low_contribution = low_confidence_signal.contributions[0]
    high_contribution = high_confidence_signal.contributions[0]
    assert low_confidence_signal.score == high_confidence_signal.score
    assert low_confidence_signal.confidence == high_confidence_signal.confidence
    assert low_contribution.score == high_contribution.score
    assert low_contribution.confidence == high_contribution.confidence
    assert low_contribution.metadata["raw_edge_confidence_metadata"] == "0.10000000"
    assert high_contribution.metadata["raw_edge_confidence_metadata"] == "0.95000000"


def test_graph_signal_loader_excludes_inferred_candidates_until_promoted(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    _seed_graph_fixture(
        settings,
        provenance_type="inferred",
        status="candidate",
    )

    candidate_signal = _load_graph_signal(settings, as_of_date=date(2024, 1, 10))
    _seed_graph_fixture(
        settings,
        provenance_type="inferred",
        status="active",
    )
    promoted_signal = _load_graph_signal(settings, as_of_date=date(2024, 1, 10))

    assert candidate_signal is None
    assert promoted_signal is not None
    assert promoted_signal.contributions[0].edge_status == "active"
    assert promoted_signal.contributions[0].metadata["provenance_type"] == "inferred"


def test_graph_aware_strategy_combines_technical_and_graph_scores() -> None:
    strategy = GraphAwareScoreStrategy(
        name="graph_aware_test",
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
    second_graph_signal = GraphBacktestSignal(
        symbol="BBB",
        as_of_date=date(2024, 1, 5),
        score=Decimal("0.40000000"),
        confidence=Decimal("0.90000000"),
        contributions=(),
    )

    rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 5),
        features_by_symbol={
            "AAA": _feature_snapshot("AAA", sma_1=Decimal("101"), sma_2=Decimal("100")),
            "BBB": _feature_snapshot("BBB", sma_1=Decimal("120"), sma_2=Decimal("100")),
        },
        current_positions=set(),
        graph_signals_by_symbol={"AAA": graph_signal, "BBB": second_graph_signal},
    )

    targets, signals = strategy.select_targets_with_graph(
        trade_date=date(2024, 1, 5),
        features_by_symbol={
            "AAA": _feature_snapshot("AAA", sma_1=Decimal("101"), sma_2=Decimal("100")),
            "BBB": _feature_snapshot("BBB", sma_1=Decimal("120"), sma_2=Decimal("100")),
        },
        current_positions=set(),
        graph_signals_by_symbol={"AAA": graph_signal, "BBB": second_graph_signal},
        target_limit=1,
    )

    assert [ranking.symbol for ranking in rankings if ranking.is_eligible] == [
        "AAA",
        "BBB",
    ]
    assert targets == {"AAA"}
    assert len(signals) == 1
    assert signals[0].score == Decimal("0.50000000")
    assert signals[0].explanation.metadata["graph_signal"]["score"] == "0.50000000"


def test_graph_aware_strategy_preserves_weighted_sma_and_graph_combined_score() -> None:
    strategy = GraphAwareScoreStrategy(
        name="graph_aware_weighted_score_test",
        parameters={
            "fast_window": 1,
            "slow_window": 2,
            "technical_weight": "0.60",
            "graph_weight": "0.40",
            "min_combined_score": "-1",
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

    rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 5),
        features_by_symbol={
            "AAA": _feature_snapshot("AAA", sma_1=Decimal("110"), sma_2=Decimal("100")),
        },
        current_positions=set(),
        graph_signals_by_symbol={"AAA": graph_signal},
    )
    targets, signals = strategy.select_targets_with_graph(
        trade_date=date(2024, 1, 5),
        features_by_symbol={
            "AAA": _feature_snapshot("AAA", sma_1=Decimal("110"), sma_2=Decimal("100")),
        },
        current_positions=set(),
        graph_signals_by_symbol={"AAA": graph_signal},
    )

    assert [ranking.symbol for ranking in rankings if ranking.is_eligible] == ["AAA"]
    assert rankings[0].raw_strategy_score == Decimal("0.26000000")
    assert rankings[0].metadata["technical_score"] == "0.10000000"
    assert "technical_score=0.10000000" in rankings[0].reasons
    payload = rankings[0].to_dict()
    assert payload["raw_strategy_score"] == "0.26000000"
    assert payload["rank"] == 1
    assert payload["eligibility_status"] == "eligible"
    assert payload["feature_snapshot_id"] == "fs-AAA"
    assert payload["metadata"] == {
        "strategy_type": "graph_aware_score",
        "technical_weight": "0.60",
        "graph_weight": "0.40",
        "technical_score": "0.10000000",
        "graph_signal": {
            "symbol": "AAA",
            "as_of_date": "2024-01-05",
            "score": "0.50000000",
            "confidence": "0.90000000",
            "edge_types": [],
            "edge_keys": [],
            "contributions": [],
        },
    }
    assert targets == {"AAA"}
    assert [signal.score for signal in signals] == [Decimal("0.26000000")]
    assert signals[0].explanation.metadata["technical_score"] == "0.10000000"


def test_graph_aware_backtest_summarizes_performance_by_edge_type(
    tmp_path: Path,
) -> None:
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


def test_technical_validation_readiness_reports_insufficient_history(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    symbols = ("VALA", "VALB")
    with session_factory() as session:
        _seed_instruments(session, symbols)
        CandleRepository(session).upsert(_candles("VALA", [100, 101, 102, 103]))
        CandleRepository(session).upsert(_candles("VALB", [100, 101, 102, 103]))
        session.commit()

    request = _validation_request(
        tmp_path,
        symbols=symbols,
        warmup_days=4,
        evaluation_days=3,
    )
    with session_factory() as session:
        readiness = build_data_readiness(session, request)

    assert readiness.status == "insufficient_data"
    assert readiness.artifact["window"]["required_common_candle_count"] == 8
    assert readiness.artifact["window"]["missing_common_candle_count"] == 4
    assert readiness.artifact["next_actions"]


def test_technical_validation_runs_comparable_profiles_with_shared_window(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    symbols = ("VTA", "VTB")
    with session_factory() as session:
        _seed_instruments(session, symbols)
        CandleRepository(session).upsert(_candles("VTA", list(range(100, 142))))
        CandleRepository(session).upsert(_candles("VTB", list(range(120, 162))))
        session.commit()

    request = _validation_request(
        tmp_path,
        symbols=symbols,
        warmup_days=30,
        evaluation_days=3,
    )
    outcome = run_validation(settings=settings, request=request)

    assert outcome.status == "complete"
    manifest = json.loads(
        (outcome.artifact_dir / "validation_manifest.json").read_text(
            encoding="utf-8"
        )
    )
    assert manifest["profile_run_count"] == 4
    assert manifest["window"]["selected_scoring_start_date"] == "2024-02-09"
    assert manifest["window"]["selected_evaluation_end_date"] == "2024-02-11"
    profile_runs = json.loads(
        (outcome.artifact_dir / "profile_runs.json").read_text(encoding="utf-8")
    )
    assert {run["profile_name"] for run in profile_runs} == {
        "graph_aware_score_v1",
        "graph_aware_score_v1_technical_only",
        "graph_aware_score_v2",
        "graph_aware_score_v2_technical_only",
    }
    assert {run["start_date"] for run in profile_runs} == {"2024-02-09"}
    assert {run["end_date"] for run in profile_runs} == {"2024-02-11"}
    assert (outcome.artifact_dir / "profile_comparison_matrix.csv").exists()


def test_technical_validation_writes_reports_and_conservative_gate(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    symbols = ("VGA", "VGB")
    with session_factory() as session:
        _seed_instruments(session, symbols)
        CandleRepository(session).upsert(_candles("VGA", list(range(100, 230))))
        CandleRepository(session).upsert(_candles("VGB", list(range(230, 100, -1))))
        session.commit()

    request = _validation_request(
        tmp_path,
        symbols=symbols,
        warmup_days=30,
        evaluation_days=80,
    )
    outcome = run_validation(settings=settings, request=request)

    assert outcome.status == "complete"
    assert outcome.report_path is not None
    assert outcome.report_path.exists()
    assert outcome.promotion_decision in {"promote", "keep_opt_in", "defer"}

    expected_artifacts = {
        "technical_agent_predictive_report.json",
        "technical_agent_prediction_checks.csv",
        "technical_agent_predictive_report.md",
        "system_backtest_report.json",
        "system_backtest_profile_summary.csv",
        "system_backtest_report.md",
        "profile_comparison_matrix.csv",
        "promotion_gate.json",
        "validation_manifest.json",
    }
    assert expected_artifacts.issubset(
        {path.name for path in outcome.artifact_dir.iterdir()}
    )

    technical_report = json.loads(
        (outcome.artifact_dir / "technical_agent_predictive_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert technical_report["status"] == "complete"
    assert {
        (row["profile_name"], row["horizon_days"])
        for row in technical_report["checks"]
    } == {
        ("technical_rule_v1", 5),
        ("technical_rule_v1", 21),
        ("technical_rule_v1", 63),
        ("technical_ohlcv_v2", 5),
        ("technical_ohlcv_v2", 21),
        ("technical_ohlcv_v2", 63),
    }
    assert any(
        row["profile_name"] == "technical_ohlcv_v2" and row["observation_count"] > 0
        for row in technical_report["checks"]
    )

    system_report = json.loads(
        (outcome.artifact_dir / "system_backtest_report.json").read_text(
            encoding="utf-8"
        )
    )
    assert system_report["status"] == "complete"
    assert {
        "turnover",
        "win_rate",
        "profit_factor",
        "total_return",
        "cagr",
        "sharpe",
        "sortino",
        "max_drawdown",
    }.issubset(system_report["profiles"][0]["metrics"])
    assert "allocation_candidate_score_behavior" in system_report["profiles"][0]

    gate = json.loads(
        (outcome.artifact_dir / "promotion_gate.json").read_text(encoding="utf-8")
    )
    assert gate["decision"] in {"promote", "keep_opt_in", "defer"}
    assert {check["name"] for check in gate["checks"]} >= {
        "after_costs_return",
        "max_drawdown",
        "turnover_control",
        "rank_monotonicity",
        "allocation_utilization",
    }


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings()


def _load_graph_signal(
    settings: Settings, *, as_of_date: date
) -> GraphBacktestSignal | None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        loader = GraphBacktestSignalLoader(session)
        return loader.load_symbol(as_of_date=as_of_date, symbol="AAA")


def _seed_graph_fixture(
    settings: Settings,
    *,
    valid_from: date | None = date(2024, 1, 1),
    evidence_date: date | None = date(2024, 1, 3),
    include_future_stat: bool = True,
    provenance_type: str = "derived",
    status: str = "active",
    confidence: Decimal = Decimal("0.9000"),
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
            provenance_type=provenance_type,
            direction="bidirectional",
            expected_sign="positive",
            strength=Decimal("0.8000"),
            confidence=confidence,
            status=status,
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
        CandleRepository(session).upsert(
            _candles("AAA", [100, 101, 102, 100, 106, 110, 109, 108])
        )
        CandleRepository(session).upsert(
            _candles("BBB", [100, 101, 102, 103, 104, 105, 106, 107])
        )

        graph_repo = GraphRepository(session)
        _seed_company_nodes(graph_repo, ("AAA", "BBB"))
        graph_repo.upsert_edge(
            edge_key="peer:AAA:BBB",
            source_node_key="company:AAA",
            target_node_key="company:BBB",
            edge_type="peer_momentum",
            provenance_type="derived",
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
            source="test_fixture",
        )
        for index, price in enumerate(prices)
    ]


def _feature_snapshot(
    symbol: str, *, sma_1: Decimal, sma_2: Decimal
) -> FeatureSnapshot:
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


def _validation_request(
    tmp_path: Path,
    *,
    symbols: tuple[str, ...],
    warmup_days: int,
    evaluation_days: int,
) -> ValidationRequest:
    return ValidationRequest(
        symbols=tuple(sorted(symbols)),
        universe_source="manual_symbols",
        universe_path=None,
        mode="standard",
        validation_years=1,
        evaluation_days=evaluation_days,
        warmup_days=warmup_days,
        timeframe="1d",
        artifact_root=tmp_path / "technical_validation",
        initial_capital_inr=Decimal("10000"),
        max_open_positions=2,
        portfolio_breadth=2,
        rebalance_every_days=2,
        cost_bps=Decimal("0"),
        slippage_bps=Decimal("0"),
        report_root=tmp_path / "reports",
    )
