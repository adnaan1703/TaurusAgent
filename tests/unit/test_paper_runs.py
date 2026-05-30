from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from apps.dashboard.data import list_paper_runs
from scripts.run_paper_loop import _resolve_symbols_from_env, run_paper_loop
from taurus_core.config import Settings
from taurus_core.db.models import (
    AnalystReportModel,
    AuditLogModel,
    PaperOrderModel,
    PaperRunModel,
    RiskReviewModel,
)
from taurus_core.db.repositories import GraphRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.paper_trading.service import PaperRunService
from tests.llm_fakes import FakeLLMProvider
from tests.market_data_fixtures import FakeKiteMarketDataProvider, TEST_INSTRUMENTS


@pytest.fixture(autouse=True)
def fake_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_llm_provider",
        lambda settings: FakeLLMProvider(),
    )
    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_market_data_provider",
        lambda settings: FakeKiteMarketDataProvider(),
    )


def test_paper_run_service_executes_full_chain_and_api_returns_runs(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["INFY"])

    assert run.run_id.startswith("pr-")
    assert run.status == "COMPLETED"
    assert run.succeeded_symbols == ["INFY"]
    assert run.failed_symbols == []
    assert run.completed_at is not None
    assert run.market_data_summary["provider_name"] == "kite"
    assert run.market_data_summary["candle_count"] >= 252
    assert run.artifacts["strategy"]["strategy_name"]
    assert run.artifacts["symbols"]["INFY"]["final_status"] == "APPROVED_FOR_PAPER"
    assert run.artifacts["symbols"]["INFY"]["order_status"] == "FILLED"
    assert run.artifacts["symbols"]["INFY"]["analyst_roster"] == {
        "enabled": ["technical"],
        "skipped": ["news", "sentiment", "fundamentals", "graph"],
        "report_count": 1,
        "min_required": 1,
        "status": "enough_reports",
    }

    client = TestClient(create_app(settings))
    runs_response = client.get("/runs")
    run_response = client.get(f"/runs/{run.run_id}")

    assert runs_response.status_code == 200
    assert run_response.status_code == 200
    assert runs_response.json()[0]["run_id"] == run.run_id
    assert run_response.json()["status"] == "COMPLETED"

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        dashboard_runs = list_paper_runs(session)
        order_count = session.scalar(select(func.count()).select_from(PaperOrderModel))

    assert dashboard_runs[0]["run_id"] == run.run_id
    assert dashboard_runs[0]["status"] == "COMPLETED"
    assert order_count == 1


def test_paper_run_records_symbol_failure_without_losing_success(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["INFY", "MISSING"])

    assert run.status == "PARTIAL_FAILED"
    assert run.succeeded_symbols == ["INFY"]
    assert run.failed_symbols == ["MISSING"]
    assert run.errors[0].symbol == "MISSING"
    assert run.errors[0].stage == "symbol_pipeline"

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        stored_run = session.get(PaperRunModel, run.run_id)
        order_count = session.scalar(select(func.count()).select_from(PaperOrderModel))
        failure_audits = session.scalar(
            select(func.count())
            .select_from(AuditLogModel)
            .where(AuditLogModel.event_type == "paper_run.symbol_failed")
        )

    assert stored_run is not None
    assert stored_run.status == "PARTIAL_FAILED"
    assert order_count == 1
    assert failure_audits == 1


def test_paper_run_succeeds_without_fundamentals(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical,news,sentiment",
    )
    run = PaperRunService(settings).run_once(symbols=["INFY"])

    roster = run.artifacts["symbols"]["INFY"]["analyst_roster"]

    assert run.status == "COMPLETED"
    assert roster == {
        "enabled": ["technical", "news", "sentiment"],
        "skipped": ["fundamentals", "graph"],
        "report_count": 3,
        "min_required": 1,
        "status": "enough_reports",
    }

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        agent_names = {
            row.agent_name
            for row in session.scalars(select(AnalystReportModel))
        }

    assert agent_names == {
        "TechnicalAnalystAgent",
        "NewsAnalystAgent",
        "SentimentAnalystAgent",
    }


def test_paper_run_succeeds_with_technical_only_roster(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path, enabled_analysts="technical")
    run = PaperRunService(settings).run_once(symbols=["INFY"])

    roster = run.artifacts["symbols"]["INFY"]["analyst_roster"]

    assert run.status == "COMPLETED"
    assert run.succeeded_symbols == ["INFY"]
    assert roster == {
        "enabled": ["technical"],
        "skipped": ["news", "sentiment", "fundamentals", "graph"],
        "report_count": 1,
        "min_required": 1,
        "status": "enough_reports",
    }


def test_graph_enabled_kite_paper_run_uses_graph_roster_strategy_and_risk(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical,graph",
        graph_enabled=True,
        graph_risk_enabled=True,
    )
    _seed_paper_graph_fixture(settings)

    run = PaperRunService(settings).run_once(
        symbols=["INFY"],
        strategy_config_path="configs/strategies/graph_aware_score_v1.yaml",
    )
    strategy = run.artifacts["strategy"]
    roster = run.artifacts["symbols"]["INFY"]["analyst_roster"]

    assert run.status == "COMPLETED"
    assert strategy["graph_enabled_profile"] is True
    assert strategy["graph_risk_enabled"] is True
    assert strategy["graph_signal_count"] >= 1
    assert "INFY" in strategy["symbols_with_graph_signals"]
    assert strategy["graph_strategy_config_path"] == "configs/strategies/graph_aware_score_v1.yaml"
    assert strategy["select_targets_with_graph_called"] is True
    assert strategy["symbol_selection"]["INFY"]["selection_source"] == "explicit_symbol"
    assert strategy["symbol_selection"]["INFY"]["has_graph_signal"] is True
    assert roster["enabled"] == ["technical", "graph"]

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        agent_names = {
            row.agent_name
            for row in session.scalars(select(AnalystReportModel))
        }
        risk_review = session.scalars(select(RiskReviewModel)).first()

    assert "GraphAnalystAgent" in agent_names
    assert risk_review is not None
    hard_rules = {row["rule"] for row in risk_review.hard_rule_results}
    assert "graph_correlated_cluster_concentration" in hard_rules


def test_graph_enabled_kite_paper_run_fails_fast_without_graph_nodes(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical,graph",
        graph_enabled=True,
        graph_risk_enabled=True,
    )

    run = PaperRunService(settings).run_once(
        symbols=["INFY"],
        strategy_config_path="configs/strategies/graph_aware_score_v1.yaml",
    )

    assert run.status == "FAILED"
    assert run.errors[0].stage == "data_update"
    assert run.errors[0].error_type == "GraphReadinessError"
    assert "make import-taurus-graph" in run.errors[0].message
    assert run.artifacts == {}


def test_paper_loop_records_manual_symbol_universe_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SYMBOLS", "infy")
    monkeypatch.setenv("SYMBOL", "")
    settings = _settings_for_temp_db(tmp_path)
    resolved = _resolve_symbols_from_env(settings)

    payload = run_paper_loop(
        symbols=resolved.symbols,
        settings=settings,
        iterations=1,
        universe=resolved.universe,
    )

    universe = payload[0]["universe"]
    assert universe["source"] == "manual_symbols"
    assert universe["provider"] == "kite"
    assert universe["selected_symbol_count"] == 1
    assert universe["symbols"] == ["INFY"]

    client = TestClient(create_app(settings))
    overview = client.get("/ui/overview")
    assert overview.status_code == 200
    assert overview.json()["latest_run"]["universe"]["source"] == "manual_symbols"


def _settings_for_temp_db(
    tmp_path: Path,
    *,
    enabled_analysts: str = "technical",
    graph_enabled: bool = False,
    graph_risk_enabled: bool = False,
) -> Settings:
    return Settings(
        taurus_paper_partial_fill_threshold=1,
        taurus_enabled_analysts=enabled_analysts,
        taurus_graph_enabled=graph_enabled,
        taurus_graph_risk_enabled=graph_risk_enabled,
    )


def _seed_paper_graph_fixture(settings: Settings) -> None:
    latest_candle_date = FakeKiteMarketDataProvider().get_daily_candles("INFY")[-1].trade_date
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        for instrument in TEST_INSTRUMENTS:
            instrument_repo.upsert(Instrument(symbol=instrument.symbol, name=instrument.name))
        graph_repo = GraphRepository(session)
        for symbol in ("INFY", "RELIANCE"):
            graph_repo.upsert_node(
                node_key=f"company:{symbol}",
                node_type="company",
                display_name=f"{symbol} Limited",
                symbol=symbol,
            )
        graph_repo.upsert_edge(
            edge_key="peer:INFY:RELIANCE",
            source_node_key="company:INFY",
            target_node_key="company:RELIANCE",
            edge_type="peer_momentum",
            direction="bidirectional",
            expected_sign="positive",
            strength=Decimal("0.8500"),
            confidence=Decimal("0.9000"),
            evidence_type="operator_reviewed",
            mechanism="Reviewed real-data paper graph relation.",
            tradability_relevance="signal",
            status="active",
            valid_from=date(2024, 1, 1),
        )
        graph_repo.upsert_edge_evidence(
            edge_key="peer:INFY:RELIANCE",
            evidence_id="evidence:peer:INFY:RELIANCE",
            claim_type="peer_mapping",
            claim_summary="Reviewed test fixture for paper graph path.",
            source_date=date(2024, 1, 1),
            confidence=Decimal("0.9000"),
        )
        graph_repo.upsert_edge_stats(
            edge_key="peer:INFY:RELIANCE",
            window="60d",
            as_of_date=latest_candle_date,
            sample_size=60,
            raw_correlation=Decimal("0.8200"),
            residual_correlation=Decimal("0.7600"),
            lead_lag_score=Decimal("0.4200"),
            stability_score=Decimal("0.9000"),
        )
        session.commit()
