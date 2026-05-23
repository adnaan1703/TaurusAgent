from __future__ import annotations

import json
import os

from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID, run_analyst_suite
from taurus_core.agents.trader_agent import TraderAgent
from taurus_core.config import Settings, get_settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.repositories import AnalystReportRepository, ResearchRepository
from taurus_core.db.session import build_session_factory
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm import build_llm_provider
from taurus_core.logging import configure_logging
from taurus_core.research.debate_service import DEFAULT_DEBATE_ROUNDS, ResearchDebateService
from taurus_core.research.schemas import DebateReport


def run_mock_trader_proposal(
    *,
    symbol: str,
    settings: Settings | None = None,
    run_id: str = DEFAULT_ANALYST_RUN_ID,
    rounds_requested: int = DEFAULT_DEBATE_ROUNDS,
) -> dict[str, object]:
    settings = settings or get_settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    _prepare_mock_inputs(session_factory, settings)

    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol=symbol,
            run_id=run_id,
            llm_provider=build_llm_provider(settings),
            enabled_analysts=settings.enabled_analyst_keys,
        )

    with session_factory() as session:
        reports = AnalystReportRepository(session).list_for_run_symbol(
            symbol=symbol,
            run_id=run_id,
        )
        source_report_ids = sorted(report.report_id for report in reports)
        debate_model = ResearchRepository(session).latest_debate(symbol=symbol, run_id=run_id)
        debate = None
        if debate_model is not None:
            candidate = DebateReport.model_validate(debate_model.payload)
            if candidate.source_report_ids == source_report_ids:
                debate = candidate
        if debate is None:
            debate = ResearchDebateService(session).run(
                symbol=symbol,
                run_id=run_id,
                rounds_requested=rounds_requested,
            )

    with session_factory() as session:
        proposal = TraderAgent(session).run(symbol=symbol, run_id=run_id, debate=debate)
        return proposal.model_dump(mode="json")


def _prepare_mock_inputs(session_factory, settings: Settings) -> None:
    market_data_provider = MockMarketDataProvider(
        seed=settings.taurus_mock_seed,
        candle_count=settings.taurus_mock_candle_count,
    )
    with session_factory() as session:
        seed_mock_data(session, market_data_provider)
    with session_factory() as session:
        import_mock_news(session, MockNewsProvider())


if __name__ == "__main__":
    configure_logging()
    symbol = os.environ.get("SYMBOL", "INFY")
    rounds = int(os.environ.get("ROUNDS", str(DEFAULT_DEBATE_ROUNDS)))
    payload = run_mock_trader_proposal(symbol=symbol, rounds_requested=rounds)
    print(json.dumps(payload, sort_keys=True))
