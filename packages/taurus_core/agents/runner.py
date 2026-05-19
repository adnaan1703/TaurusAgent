from __future__ import annotations

from sqlalchemy.orm import Session

from taurus_core.agents.fundamentals_analyst import FundamentalsAnalystAgent
from taurus_core.agents.news_analyst import NewsAnalystAgent
from taurus_core.agents.schemas import AnalystReport
from taurus_core.agents.sentiment_analyst import SentimentAnalystAgent
from taurus_core.agents.technical_analyst import TechnicalAnalystAgent
from taurus_core.db.repositories import AnalystReportRepository, InstrumentRepository
from taurus_core.llm.base import LLMProvider

DEFAULT_ANALYST_RUN_ID = "analyst-mock-latest"


def run_analyst_suite(
    session: Session,
    *,
    symbol: str,
    llm_provider: LLMProvider,
    run_id: str = DEFAULT_ANALYST_RUN_ID,
) -> list[AnalystReport]:
    symbol = symbol.upper()
    if InstrumentRepository(session).get(symbol) is None:
        raise ValueError(f"Instrument {symbol} is not available. Run make seed-mock first.")

    agents = (
        TechnicalAnalystAgent(session, llm_provider),
        NewsAnalystAgent(session, llm_provider),
        SentimentAnalystAgent(session, llm_provider),
        FundamentalsAnalystAgent(session, llm_provider),
    )
    reports = [agent.run(symbol=symbol, run_id=run_id) for agent in agents]
    AnalystReportRepository(session).replace_for_run_symbol(
        run_id=run_id,
        symbol=symbol,
        reports=reports,
    )
    session.commit()
    return reports
