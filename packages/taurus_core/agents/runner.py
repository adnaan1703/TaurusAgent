from __future__ import annotations

import time

from sqlalchemy.orm import Session

from taurus_core.agents.fundamentals_analyst import FundamentalsAnalystAgent
from taurus_core.agents.news_analyst import NewsAnalystAgent
from taurus_core.agents.schemas import AnalystReport
from taurus_core.agents.sentiment_analyst import SentimentAnalystAgent
from taurus_core.agents.technical_analyst import TechnicalAnalystAgent
from taurus_core.db.repositories import AnalystReportRepository, InstrumentRepository
from taurus_core.llm.base import LLMProvider
from taurus_core.logging import get_logger
from taurus_core.observability.metrics import record_agent_run
from taurus_core.observability.tracing import bound_trace_context

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
    logger = get_logger(__name__)
    reports: list[AnalystReport] = []
    for agent in agents:
        started_at = time.perf_counter()
        report = agent.run(symbol=symbol, run_id=run_id)
        duration_seconds = time.perf_counter() - started_at
        record_agent_run(
            agent_name=agent.agent_name,
            symbol=symbol,
            provider=_provider_label(llm_provider),
            duration_seconds=duration_seconds,
        )
        with bound_trace_context(run_id=run_id, decision_id=report.decision_id):
            logger.info(
                "agent.report.created",
                report_id=report.report_id,
                symbol=symbol,
                agent_name=agent.agent_name,
                model_version=report.model_version,
                duration_seconds=round(duration_seconds, 6),
            )
        reports.append(report)
    AnalystReportRepository(session).replace_for_run_symbol(
        run_id=run_id,
        symbol=symbol,
        reports=reports,
    )
    session.commit()
    return reports


def _provider_label(provider: LLMProvider) -> str:
    model_version = getattr(provider, "model_version", provider.__class__.__name__)
    return str(model_version).split(":", maxsplit=1)[0]
