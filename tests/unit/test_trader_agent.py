from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID, run_analyst_suite
from taurus_core.agents.trader_agent import TraderAgent
from taurus_core.config import Settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.models import BacktestOrderModel, TraderProposalModel
from taurus_core.db.session import build_session_factory
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm.mock_provider import MockLLMProvider
from taurus_core.research.debate_service import ResearchDebateService


def test_trader_proposal_is_structured_deterministic_and_not_an_order(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_trader_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=MockLLMProvider(),
            run_id=DEFAULT_ANALYST_RUN_ID,
        )
    with session_factory() as session:
        debate = ResearchDebateService(session).run(symbol="INFY", rounds_requested=2)

    with session_factory() as session:
        first = TraderAgent(session).run(symbol="INFY", debate=debate)
    with session_factory() as session:
        second = TraderAgent(session).run(symbol="INFY", debate=debate)

    with session_factory() as session:
        proposal_count = session.scalar(select(func.count()).select_from(TraderProposalModel))
        order_count = session.scalar(select(func.count()).select_from(BacktestOrderModel))

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.debate_id == debate.debate_id
    assert first.source_report_ids == debate.source_report_ids
    assert first.action in {"BUY", "SELL", "HOLD", "NO_TRADE", "REDUCE", "EXIT"}
    assert first.confidence >= 0
    assert first.horizon in {"intraday", "short", "medium", "long"}
    assert first.entry_rule
    assert first.invalid_if
    assert first.is_order is False
    assert first.requires_risk_approval is True
    assert proposal_count == 1
    assert order_count == 0


def test_research_api_returns_trader_proposals(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_trader_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=MockLLMProvider(),
            run_id=DEFAULT_ANALYST_RUN_ID,
        )
    with session_factory() as session:
        debate = ResearchDebateService(session).run(symbol="INFY", rounds_requested=2)
    with session_factory() as session:
        proposal = TraderAgent(session).run(symbol="INFY", debate=debate)

    client = TestClient(create_app(settings))
    response = client.get("/trader-proposals?symbol=INFY")

    assert response.status_code == 200
    proposals = response.json()
    assert len(proposals) == 1
    assert proposals[0]["proposal_id"] == proposal.proposal_id
    assert proposals[0]["debate_id"] == debate.debate_id
    assert proposals[0]["is_order"] is False


def _prepare_trader_db(settings: Settings):
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_mock_data(session, MockMarketDataProvider(seed=42, candle_count=252))
        import_mock_news(session, MockNewsProvider())
    return session_factory


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
