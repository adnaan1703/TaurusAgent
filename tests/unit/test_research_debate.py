from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID, run_analyst_suite
from taurus_core.config import Settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.models import BacktestOrderModel, DebateReportModel
from taurus_core.db.session import build_session_factory
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm.mock_provider import MockLLMProvider
from taurus_core.research.debate_service import ResearchDebateService


def test_research_debate_is_deterministic_and_does_not_create_orders(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_research_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=MockLLMProvider(),
            run_id=DEFAULT_ANALYST_RUN_ID,
        )

    with session_factory() as session:
        first = ResearchDebateService(session).run(symbol="INFY", rounds_requested=2)
    with session_factory() as session:
        second = ResearchDebateService(session).run(symbol="INFY", rounds_requested=2)

    with session_factory() as session:
        debate_count = session.scalar(select(func.count()).select_from(DebateReportModel))
        order_count = session.scalar(select(func.count()).select_from(BacktestOrderModel))

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.bull_thesis.key_points
    assert first.bear_thesis.key_points
    assert len(first.rounds) == 2
    assert first.manager_summary.summary
    assert first.manager_summary.consensus_label in {
        "bullish",
        "mild_bullish",
        "neutral",
        "mild_bearish",
        "bearish",
    }
    assert debate_count == 1
    assert order_count == 0


def test_research_api_returns_debates(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_research_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=MockLLMProvider(),
            run_id=DEFAULT_ANALYST_RUN_ID,
        )
    with session_factory() as session:
        debate = ResearchDebateService(session).run(symbol="INFY", rounds_requested=2)

    client = TestClient(create_app(settings))
    list_response = client.get("/debates?symbol=INFY")
    detail_response = client.get(f"/debates/{debate.debate_id}")

    assert list_response.status_code == 200
    assert detail_response.status_code == 200
    debates = list_response.json()
    assert len(debates) == 1
    assert debates[0]["debate_id"] == debate.debate_id
    assert detail_response.json()["manager_summary"]["summary"]


def _prepare_research_db(settings: Settings):
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_mock_data(session, MockMarketDataProvider(seed=42, candle_count=252))
        import_mock_news(session, MockNewsProvider())
    return session_factory


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
