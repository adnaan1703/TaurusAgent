from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from apps.dashboard.data import list_paper_runs
from taurus_core.config import Settings
from taurus_core.db.models import (
    AnalystReportModel,
    AuditLogModel,
    PaperOrderModel,
    PaperRunModel,
)
from taurus_core.db.session import build_session_factory
from taurus_core.paper_trading.service import PaperRunService


def test_paper_run_service_executes_full_chain_and_api_returns_runs(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["INFY"])

    assert run.run_id.startswith("pr-")
    assert run.status == "COMPLETED"
    assert run.succeeded_symbols == ["INFY"]
    assert run.failed_symbols == []
    assert run.completed_at is not None
    assert run.market_data_summary["provider_name"] == "mock"
    assert run.market_data_summary["candle_count"] >= 252
    assert run.artifacts["strategy"]["strategy_name"]
    assert run.artifacts["symbols"]["INFY"]["final_status"] == "APPROVED_FOR_PAPER"
    assert run.artifacts["symbols"]["INFY"]["order_status"] == "FILLED"
    assert run.artifacts["symbols"]["INFY"]["analyst_roster"] == {
        "enabled": ["technical"],
        "skipped": ["news", "sentiment", "fundamentals"],
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
        "skipped": ["fundamentals"],
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
        "skipped": ["news", "sentiment", "fundamentals"],
        "report_count": 1,
        "min_required": 1,
        "status": "enough_reports",
    }


def _settings_for_temp_db(
    tmp_path: Path,
    *,
    enabled_analysts: str = "technical",
) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'taurus.db'}",
        taurus_paper_partial_fill_threshold=1,
        taurus_enabled_analysts=enabled_analysts,
    )
