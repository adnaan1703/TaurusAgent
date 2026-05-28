from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

from scripts.migrate import run_migrations
from taurus_core.agents.graph_analyst import GRAPH_ANALYST_MODEL_VERSION
from taurus_core.agents.runner import run_analyst_suite
from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.config import Settings
from taurus_core.db.models import GraphSignalContributionModel, GraphSignalModel
from taurus_core.db.repositories import CandleRepository, GraphRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle
from taurus_core.llm.mock_provider import MockLLMProvider


def test_graph_analyst_returns_neutral_when_no_graph_evidence_exists(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    _seed_instruments(settings, ["AAA"])

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        reports = run_analyst_suite(
            session,
            symbol="AAA",
            run_id="graph-neutral",
            llm_provider=MockLLMProvider(),
            enabled_analysts=("graph",),
        )

    with session_factory() as session:
        signal_count = session.scalar(select(func.count()).select_from(GraphSignalModel))
        contribution_count = session.scalar(
            select(func.count()).select_from(GraphSignalContributionModel)
        )

    assert len(reports) == 1
    report = reports[0]
    assert report.agent_name == "GraphAnalystAgent"
    assert report.stance == "neutral"
    assert report.score == Decimal("0.0000")
    assert report.confidence == Decimal("0.2500")
    assert report.model_version == GRAPH_ANALYST_MODEL_VERSION
    assert "graph:none" in report.source_ids
    assert signal_count == 1
    assert contribution_count == 0


def test_graph_analyst_explains_bullish_positive_peer_momentum(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    _seed_graph_fixture(settings, edge_key="peer:AAA:BBB", expected_sign="positive")

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        report = run_analyst_suite(
            session,
            symbol="AAA",
            run_id="graph-bullish",
            llm_provider=MockLLMProvider(),
            enabled_analysts=("graph",),
        )[0]

    with session_factory() as session:
        graph_repo = GraphRepository(session)
        signal = graph_repo.list_signals(symbol="AAA", source_agent="GraphAnalystAgent")[0]
        contributions = graph_repo.list_signal_contributions(signal_id=signal.signal_id)

    assert report.stance == "bullish"
    assert report.score > Decimal("0.10")
    assert report.model_version == GRAPH_ANALYST_MODEL_VERSION
    assert any("BBB" in point for point in report.key_points)
    assert signal.score == report.score
    assert len(contributions) == 1
    assert contributions[0].direction == "bullish"
    assert contributions[0].score_contribution == report.score
    assert contributions[0].contribution_metadata["related_symbol"] == "BBB"


def test_graph_analyst_explains_bearish_negative_dependency_signal(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    _seed_graph_fixture(
        settings,
        edge_key="supplier:BBB:AAA",
        edge_type="raw_material_dependency",
        expected_sign="negative",
        direction="directed",
        source_symbol="BBB",
        target_symbol="AAA",
    )

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        report = run_analyst_suite(
            session,
            symbol="AAA",
            run_id="graph-bearish",
            llm_provider=MockLLMProvider(),
            enabled_analysts=("graph",),
        )[0]

    with session_factory() as session:
        graph_repo = GraphRepository(session)
        signal = graph_repo.list_signals(symbol="AAA", source_agent="GraphAnalystAgent")[0]
        contributions = graph_repo.list_signal_contributions(signal_id=signal.signal_id)

    assert report.stance == "bearish"
    assert report.score < Decimal("-0.10")
    assert any("expected sign is negative" in point.lower() for point in report.key_points)
    assert signal.score == report.score
    assert len(contributions) == 1
    assert contributions[0].direction == "bearish"
    assert contributions[0].contribution_metadata["expected_sign"] == "negative"


def test_graph_analyst_does_not_let_llm_failure_override_deterministic_output(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    _seed_graph_fixture(settings, edge_key="peer:AAA:BBB", expected_sign="positive")

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        report = run_analyst_suite(
            session,
            symbol="AAA",
            run_id="graph-llm-fails",
            llm_provider=FailingLLMProvider(),
            enabled_analysts=("graph",),
        )[0]

    assert report.stance == "bullish"
    assert report.model_version == GRAPH_ANALYST_MODEL_VERSION
    assert not report.model_version.endswith("+llm_fallback")


class FailingLLMProvider:
    @property
    def model_version(self) -> str:
        return "failing"

    def complete_analyst_report(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMAnalystOutput:
        raise RuntimeError("simulated provider failure")


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")


def _seed_instruments(settings: Settings, symbols: list[str]) -> None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        for symbol in symbols:
            instrument_repo.upsert(Instrument(symbol=symbol, name=f"{symbol} Limited"))
        session.commit()


def _seed_graph_fixture(
    settings: Settings,
    *,
    edge_key: str,
    expected_sign: str,
    edge_type: str = "peer_momentum",
    direction: str = "bidirectional",
    source_symbol: str = "AAA",
    target_symbol: str = "BBB",
) -> None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        for symbol in ("AAA", "BBB"):
            instrument_repo.upsert(Instrument(symbol=symbol, name=f"{symbol} Limited"))

        graph_repo = GraphRepository(session)
        for symbol in ("AAA", "BBB"):
            graph_repo.upsert_node(
                node_key=f"company:{symbol}",
                node_type="company",
                display_name=f"{symbol} Limited",
                symbol=symbol,
            )
        graph_repo.upsert_edge(
            edge_key=edge_key,
            source_node_key=f"company:{source_symbol}",
            target_node_key=f"company:{target_symbol}",
            edge_type=edge_type,
            direction=direction,
            expected_sign=expected_sign,
            strength=Decimal("0.80"),
            confidence=Decimal("0.90"),
            evidence_type="synthetic",
            mechanism="Synthetic graph analyst fixture.",
            tradability_relevance="signal",
            status="active",
        )
        graph_repo.upsert_edge_stats(
            edge_key=edge_key,
            window="20d",
            as_of_date=date(2024, 2, 1),
            sample_size=20,
            raw_correlation=Decimal("0.86"),
            residual_correlation=Decimal("0.82"),
            lead_lag_score=Decimal("0.30"),
            stability_score=Decimal("0.90"),
        )

        candle_repo = CandleRepository(session)
        candle_repo.upsert(_candles_with_constant_return("BBB", Decimal("0.012")))
        session.commit()


def _candles_with_constant_return(symbol: str, daily_return: Decimal) -> list[DailyCandle]:
    trade_date = date(2024, 1, 1)
    close = Decimal("100.00")
    candles = [
        DailyCandle(
            symbol=symbol,
            trade_date=trade_date,
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000_000,
            source="synthetic_graph_analyst",
        )
    ]
    for offset in range(1, 22):
        trade_date = trade_date + timedelta(days=1)
        close = close * (Decimal("1") + daily_return)
        candles.append(
            DailyCandle(
                symbol=symbol,
                trade_date=trade_date,
                open=close,
                high=close,
                low=close,
                close=close,
                volume=1_000_000,
                source="synthetic_graph_analyst",
            )
        )
    return candles
