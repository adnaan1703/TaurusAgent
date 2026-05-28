from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.agents.runner import run_analyst_suite
from taurus_core.agents.roster import ANALYST_KEYS
from taurus_core.agents.schemas import LLMAnalystOutput
from taurus_core.config import Settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.models import AnalystReportModel, BacktestOrderModel
from taurus_core.db.session import build_session_factory
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm.mock_provider import MockLLMProvider

FULL_ANALYST_ROSTER = ANALYST_KEYS


def test_analyst_suite_stores_full_roster_without_creating_orders(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)

    with session_factory() as session:
        reports = run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=MockLLMProvider(),
            run_id="test-run",
            enabled_analysts=FULL_ANALYST_ROSTER,
        )

    with session_factory() as session:
        report_count = session.scalar(select(func.count()).select_from(AnalystReportModel))
        order_count = session.scalar(select(func.count()).select_from(BacktestOrderModel))

    assert {report.agent_name for report in reports} == {
        "TechnicalAnalystAgent",
        "NewsAnalystAgent",
        "SentimentAnalystAgent",
        "FundamentalsAnalystAgent",
        "GraphAnalystAgent",
    }
    assert all(report.symbol == "INFY" for report in reports)
    assert all(report.key_points for report in reports)
    assert all(report.risks for report in reports)
    assert report_count == 5
    assert order_count == 0


def test_analyst_suite_falls_back_when_llm_provider_fails(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)

    with session_factory() as session:
        reports = run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FailingLLMProvider(),
            run_id="fallback-run",
            enabled_analysts=FULL_ANALYST_ROSTER,
        )

    assert len(reports) == 5
    llm_reports = [report for report in reports if report.agent_name != "GraphAnalystAgent"]
    graph_reports = [report for report in reports if report.agent_name == "GraphAnalystAgent"]
    assert all(report.model_version.endswith("+llm_fallback") for report in llm_reports)
    assert all("LLM provider fallback used" in " ".join(report.risks) for report in llm_reports)
    assert graph_reports[0].model_version == "graph_rule_v1"


def test_analyst_suite_can_skip_fundamentals(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)

    with session_factory() as session:
        reports = run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=MockLLMProvider(),
            run_id="no-fundamentals-run",
            enabled_analysts=("technical", "news", "sentiment"),
        )

    assert {report.agent_name for report in reports} == {
        "TechnicalAnalystAgent",
        "NewsAnalystAgent",
        "SentimentAnalystAgent",
    }
    assert all(report.agent_name != "FundamentalsAnalystAgent" for report in reports)


def test_analyst_suite_allows_technical_only_roster(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)

    with session_factory() as session:
        reports = run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=MockLLMProvider(),
            run_id="technical-only-run",
            enabled_analysts=("technical",),
        )

    assert len(reports) == 1
    assert reports[0].agent_name == "TechnicalAnalystAgent"


def test_intelligence_api_returns_events_and_agent_reports(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=MockLLMProvider(),
            run_id="api-run",
            enabled_analysts=FULL_ANALYST_ROSTER,
        )
    client = TestClient(create_app(settings))

    events_response = client.get("/events?symbol=INFY")
    reports_response = client.get("/agent-reports?symbol=INFY")

    assert events_response.status_code == 200
    assert reports_response.status_code == 200
    events = events_response.json()
    reports = reports_response.json()
    assert len(events) >= 1
    assert events[0]["symbol"] == "INFY"
    assert events[0]["event_score"] is not None
    assert len(reports) == 5
    assert {report["agent_name"] for report in reports} == {
        "TechnicalAnalystAgent",
        "NewsAnalystAgent",
        "SentimentAnalystAgent",
        "FundamentalsAnalystAgent",
        "GraphAnalystAgent",
    }


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


def _prepare_intelligence_db(settings: Settings):
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_mock_data(session, MockMarketDataProvider(seed=42, candle_count=252))
        import_mock_news(session, MockNewsProvider())
    return session_factory


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
