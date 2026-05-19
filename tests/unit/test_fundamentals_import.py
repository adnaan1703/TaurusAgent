from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from apps.dashboard.data import data_freshness, list_fundamental_scores, list_fundamental_snapshots
from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.agents.fundamentals_analyst import FundamentalsAnalystAgent
from taurus_core.config import Settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.models import FundamentalScoreModel, FundamentalSnapshotModel
from taurus_core.db.repositories import FundamentalsRepository
from taurus_core.db.session import build_session_factory
from taurus_core.fundamentals import ScreenerImportError, import_screener_csv
from taurus_core.llm.mock_provider import MockLLMProvider

FIXTURE = Path("tests/fixtures/screener_sample.csv")
AVAILABLE_AT = datetime(2026, 5, 19, 15, 30, tzinfo=timezone.utc)


def test_screener_import_maps_metrics_and_scores(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_db(settings)

    with session_factory() as session:
        summary = import_screener_csv(session, FIXTURE, data_available_time=AVAILABLE_AT)

    with session_factory() as session:
        score_count = session.scalar(select(func.count()).select_from(FundamentalScoreModel))
        snapshot_count = session.scalar(select(func.count()).select_from(FundamentalSnapshotModel))
        latest = FundamentalsRepository(session).latest_score(symbol="INFY")

    assert summary.rows_seen == 4
    assert summary.rows_imported == 3
    assert summary.rows_unmapped == 1
    assert summary.scores_imported == 3
    assert summary.metrics_imported == 45
    assert score_count == 3
    assert snapshot_count == 45
    assert latest is not None
    assert latest.symbol == "INFY"
    assert latest.quality_score is not None
    assert latest.composite_score > 0
    assert latest.metrics["roce"] == "32"


def test_screener_import_reports_missing_required_columns(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_db(settings)
    bad_csv = tmp_path / "bad_screener.csv"
    bad_csv.write_text("Market Cap,Current Price\n1000,100\n")

    with session_factory() as session:
        with pytest.raises(ScreenerImportError) as exc:
            import_screener_csv(session, bad_csv, data_available_time=AVAILABLE_AT)

    assert "Missing required Screener column(s): Symbol or Company Name" in str(exc.value)
    assert "Market Cap, Current Price" in str(exc.value)


def test_fundamentals_api_and_dashboard_queries_return_imported_scores(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_db(settings)
    with session_factory() as session:
        import_screener_csv(session, FIXTURE, data_available_time=AVAILABLE_AT)

    with session_factory() as session:
        dashboard_scores = list_fundamental_scores(session, symbol="INFY")
        dashboard_metrics = list_fundamental_snapshots(session, symbol="INFY")
        freshness = data_freshness(session, symbol="INFY")

    client = TestClient(create_app(settings))
    fundamentals_response = client.get("/fundamentals?symbol=INFY")
    imports_response = client.get("/fundamentals/imports")

    assert fundamentals_response.status_code == 200
    assert imports_response.status_code == 200
    fundamentals = fundamentals_response.json()
    imports = imports_response.json()
    assert fundamentals[0]["symbol"] == "INFY"
    assert fundamentals[0]["metrics"]["stock_pe"] == "24.5"
    assert imports[0]["rows_unmapped"] == 1
    assert dashboard_scores[0]["symbol"] == "INFY"
    assert any(row["metric"] == "roce" for row in dashboard_metrics)
    assert any(row["source"] == "screener_fundamentals" for row in freshness)


def test_fundamentals_analyst_uses_imported_screener_data(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_db(settings)
    with session_factory() as session:
        import_screener_csv(session, FIXTURE, data_available_time=AVAILABLE_AT)
        report = FundamentalsAnalystAgent(session, MockLLMProvider()).run(
            symbol="INFY",
            run_id="fundamentals-test",
        )

    assert report.agent_name == "FundamentalsAnalystAgent"
    assert report.score > 0
    assert any(source_id.startswith("fundamental_score:") for source_id in report.source_ids)
    assert "Screener fundamentals composite score" in report.key_points[0]


def _prepare_db(settings: Settings):
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_mock_data(session, MockMarketDataProvider(seed=42, candle_count=252))
    return session_factory


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
