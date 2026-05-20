from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Gauge, Histogram, generate_latest
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from taurus_core.config import Settings
from taurus_core.db.models import (
    AnalystReportModel,
    BacktestRunModel,
    CompanyEventModel,
    DailyCandleModel,
    DebateReportModel,
    FeatureValueModel,
    FinalDecisionModel,
    FundamentalImportModel,
    FundamentalScoreModel,
    InstrumentModel,
    PaperAccountModel,
    PaperFillModel,
    PaperOrderModel,
    PaperPositionModel,
    PaperRunModel,
    RawDocumentModel,
    RiskReviewModel,
    SentimentScoreModel,
    TraderProposalModel,
)

APP_INFO = Gauge(
    "taurus_app_info",
    "Static Taurus API metadata.",
    ["service", "version", "environment", "mode"],
)

LIVE_TRADING_ENABLED = Gauge(
    "taurus_live_trading_enabled",
    "Whether live trading is enabled. This must report 0 until live trading is explicitly approved.",
)

HTTP_REQUESTS = Counter(
    "taurus_http_requests_total",
    "Total HTTP requests served by the Taurus API.",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_SECONDS = Histogram(
    "taurus_http_request_duration_seconds",
    "HTTP request duration in seconds for the Taurus API.",
    ["method", "path"],
)

OBSERVABILITY_DB_AVAILABLE = Gauge(
    "taurus_observability_db_available",
    "Whether database-backed Taurus observability metrics were refreshed successfully.",
)

DB_TABLE_ROWS = Gauge(
    "taurus_db_table_rows",
    "Current Taurus database row counts by table.",
    ["table"],
)

DATA_LATEST_AVAILABLE = Gauge(
    "taurus_data_latest_available_timestamp_seconds",
    "Latest available timestamp for market data and feature data.",
    ["source", "symbol", "timeframe"],
)

DATA_FRESHNESS = Gauge(
    "taurus_data_freshness_seconds",
    "Age in seconds of the latest available market data and feature data.",
    ["source", "symbol", "timeframe"],
)

NEWS_DOCUMENTS = Gauge(
    "taurus_news_documents_total",
    "Current ingested news document count by source.",
    ["source"],
)

NEWS_EVENTS = Gauge(
    "taurus_news_events_total",
    "Current company event count by symbol and event type.",
    ["symbol", "event_type"],
)

LLM_PROVIDER_INFO = Gauge(
    "taurus_llm_provider_info",
    "Configured Taurus LLM provider.",
    ["provider", "model_version"],
)

LLM_FAILURES = Counter(
    "taurus_llm_failures_total",
    "LLM provider failures that used deterministic fallback output.",
    ["provider", "agent_name", "symbol", "error_type"],
)

AGENT_RUN_SECONDS = Histogram(
    "taurus_agent_run_duration_seconds",
    "Agent run duration in seconds.",
    ["agent_name", "symbol", "provider"],
)

AGENT_REPORTS = Gauge(
    "taurus_agent_reports_total",
    "Current analyst report count by agent, symbol, and model version.",
    ["agent_name", "symbol", "model_version"],
)

AGENT_ARTIFACT_AGE = Gauge(
    "taurus_agent_artifact_age_seconds",
    "Age in seconds of the latest agent workflow artifact.",
    ["artifact", "symbol"],
)

TRADING_ARTIFACTS = Gauge(
    "taurus_trading_artifacts_total",
    "Current trading workflow artifact count by type, symbol, and status.",
    ["artifact", "symbol", "status"],
)

PAPER_ACCOUNT_EQUITY = Gauge(
    "taurus_paper_account_equity_inr",
    "Latest PaperBroker account equity by run.",
    ["run_id"],
)

PAPER_POSITION_VALUE = Gauge(
    "taurus_paper_position_market_value_inr",
    "Latest PaperBroker position market value by run and symbol.",
    ["run_id", "symbol"],
)


def configure_runtime_metrics(settings: Settings) -> None:
    APP_INFO.labels(
        service=settings.service_name,
        version=settings.service_version,
        environment=settings.taurus_env,
        mode=settings.taurus_mode,
    ).set(1)
    LIVE_TRADING_ENABLED.set(1 if settings.live_trading_enabled else 0)
    LLM_PROVIDER_INFO.labels(
        provider=settings.taurus_llm_provider,
        model_version=settings.taurus_llm_provider,
    ).set(1)


def record_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    HTTP_REQUESTS.labels(
        method=method,
        path=path,
        status_code=str(status_code),
    ).inc()
    HTTP_REQUEST_SECONDS.labels(method=method, path=path).observe(duration_seconds)


def record_llm_failure(
    *,
    provider: str,
    agent_name: str,
    symbol: str,
    error_type: str,
) -> None:
    LLM_FAILURES.labels(
        provider=provider,
        agent_name=agent_name,
        symbol=symbol.upper(),
        error_type=error_type,
    ).inc()


def record_agent_run(
    *,
    agent_name: str,
    symbol: str,
    provider: str,
    duration_seconds: float,
) -> None:
    AGENT_RUN_SECONDS.labels(
        agent_name=agent_name,
        symbol=symbol.upper(),
        provider=provider,
    ).observe(duration_seconds)


def refresh_database_metrics(session: Session) -> bool:
    now = datetime.now(timezone.utc)
    try:
        _clear_database_gauges()
        OBSERVABILITY_DB_AVAILABLE.set(1)
        _refresh_table_counts(session)
        _refresh_data_freshness(session, now=now)
        _refresh_news_metrics(session)
        _refresh_agent_metrics(session, now=now)
        _refresh_trading_metrics(session, now=now)
        _refresh_paper_metrics(session)
    except SQLAlchemyError:
        OBSERVABILITY_DB_AVAILABLE.set(0)
        return False
    return True


def metrics_response_body() -> bytes:
    return generate_latest(REGISTRY)


def metrics_response_type() -> str:
    return CONTENT_TYPE_LATEST


def _refresh_table_counts(session: Session) -> None:
    models = {
        "instruments": InstrumentModel,
        "daily_candles": DailyCandleModel,
        "feature_values": FeatureValueModel,
        "raw_documents": RawDocumentModel,
        "company_events": CompanyEventModel,
        "sentiment_scores": SentimentScoreModel,
        "fundamental_imports": FundamentalImportModel,
        "fundamental_scores": FundamentalScoreModel,
        "analyst_reports": AnalystReportModel,
        "debate_reports": DebateReportModel,
        "trader_proposals": TraderProposalModel,
        "risk_reviews": RiskReviewModel,
        "final_decisions": FinalDecisionModel,
        "paper_orders": PaperOrderModel,
        "paper_fills": PaperFillModel,
        "paper_positions": PaperPositionModel,
        "paper_accounts": PaperAccountModel,
        "paper_runs": PaperRunModel,
        "backtest_runs": BacktestRunModel,
    }
    for table, model in models.items():
        count = int(session.scalar(select(func.count()).select_from(model)) or 0)
        DB_TABLE_ROWS.labels(table=table).set(count)


def _refresh_data_freshness(session: Session, *, now: datetime) -> None:
    candle_statement = (
        select(
            DailyCandleModel.symbol,
            DailyCandleModel.timeframe,
            func.max(DailyCandleModel.trade_date),
        )
        .group_by(DailyCandleModel.symbol, DailyCandleModel.timeframe)
        .order_by(DailyCandleModel.symbol, DailyCandleModel.timeframe)
    )
    for symbol, timeframe, latest_date in session.execute(candle_statement):
        latest_at = _as_utc_datetime(latest_date)
        _set_freshness(
            source="daily_candles",
            symbol=symbol,
            timeframe=timeframe,
            latest_at=latest_at,
            now=now,
        )

    feature_statement = (
        select(
            FeatureValueModel.symbol,
            FeatureValueModel.source,
            func.max(FeatureValueModel.data_available_time),
        )
        .group_by(FeatureValueModel.symbol, FeatureValueModel.source)
        .order_by(FeatureValueModel.symbol, FeatureValueModel.source)
    )
    for symbol, source, latest_at in session.execute(feature_statement):
        _set_freshness(
            source=source,
            symbol=symbol,
            timeframe="feature",
            latest_at=_as_utc_datetime(latest_at),
            now=now,
        )

    fundamental_statement = (
        select(
            FundamentalScoreModel.symbol,
            func.max(FundamentalScoreModel.data_available_time),
        )
        .group_by(FundamentalScoreModel.symbol)
        .order_by(FundamentalScoreModel.symbol)
    )
    for symbol, latest_at in session.execute(fundamental_statement):
        _set_freshness(
            source="screener_fundamentals",
            symbol=symbol,
            timeframe="fundamental",
            latest_at=_as_utc_datetime(latest_at),
            now=now,
        )


def _refresh_news_metrics(session: Session) -> None:
    document_statement = (
        select(RawDocumentModel.source, func.count())
        .group_by(RawDocumentModel.source)
        .order_by(RawDocumentModel.source)
    )
    for source, count in session.execute(document_statement):
        NEWS_DOCUMENTS.labels(source=source).set(int(count))

    event_statement = (
        select(CompanyEventModel.symbol, CompanyEventModel.event_type, func.count())
        .group_by(CompanyEventModel.symbol, CompanyEventModel.event_type)
        .order_by(CompanyEventModel.symbol, CompanyEventModel.event_type)
    )
    for symbol, event_type, count in session.execute(event_statement):
        NEWS_EVENTS.labels(symbol=symbol, event_type=event_type).set(int(count))


def _refresh_agent_metrics(session: Session, *, now: datetime) -> None:
    report_statement = (
        select(
            AnalystReportModel.agent_name,
            AnalystReportModel.symbol,
            AnalystReportModel.model_version,
            func.count(),
        )
        .group_by(
            AnalystReportModel.agent_name,
            AnalystReportModel.symbol,
            AnalystReportModel.model_version,
        )
        .order_by(AnalystReportModel.agent_name, AnalystReportModel.symbol)
    )
    for agent_name, symbol, model_version, count in session.execute(report_statement):
        AGENT_REPORTS.labels(
            agent_name=agent_name,
            symbol=symbol,
            model_version=model_version,
        ).set(int(count))

    _set_latest_artifact_age(
        session,
        artifact="analyst_report",
        symbol_column=AnalystReportModel.symbol,
        timestamp_column=AnalystReportModel.as_of,
        model=AnalystReportModel,
        now=now,
    )
    _set_latest_artifact_age(
        session,
        artifact="debate",
        symbol_column=DebateReportModel.symbol,
        timestamp_column=DebateReportModel.as_of,
        model=DebateReportModel,
        now=now,
    )
    _set_latest_artifact_age(
        session,
        artifact="trader_proposal",
        symbol_column=TraderProposalModel.symbol,
        timestamp_column=TraderProposalModel.as_of,
        model=TraderProposalModel,
        now=now,
    )
    _set_latest_artifact_age(
        session,
        artifact="risk_review",
        symbol_column=RiskReviewModel.symbol,
        timestamp_column=RiskReviewModel.as_of,
        model=RiskReviewModel,
        now=now,
    )
    _set_latest_artifact_age(
        session,
        artifact="final_decision",
        symbol_column=FinalDecisionModel.symbol,
        timestamp_column=FinalDecisionModel.as_of,
        model=FinalDecisionModel,
        now=now,
    )


def _refresh_trading_metrics(session: Session, *, now: datetime) -> None:
    _set_status_counts(
        session,
        artifact="debate",
        model=DebateReportModel,
        symbol_column=DebateReportModel.symbol,
        status_column=DebateReportModel.consensus_label,
    )
    _set_status_counts(
        session,
        artifact="trader_proposal",
        model=TraderProposalModel,
        symbol_column=TraderProposalModel.symbol,
        status_column=TraderProposalModel.action,
    )
    _set_status_counts(
        session,
        artifact="risk_review",
        model=RiskReviewModel,
        symbol_column=RiskReviewModel.symbol,
        status_column=RiskReviewModel.status,
    )
    _set_status_counts(
        session,
        artifact="final_decision",
        model=FinalDecisionModel,
        symbol_column=FinalDecisionModel.symbol,
        status_column=FinalDecisionModel.status,
    )
    _set_status_counts(
        session,
        artifact="paper_order",
        model=PaperOrderModel,
        symbol_column=PaperOrderModel.symbol,
        status_column=PaperOrderModel.status,
    )
    _set_latest_artifact_age(
        session,
        artifact="paper_order",
        symbol_column=PaperOrderModel.symbol,
        timestamp_column=PaperOrderModel.submitted_at,
        model=PaperOrderModel,
        now=now,
    )
    _set_latest_artifact_age(
        session,
        artifact="paper_fill",
        symbol_column=PaperFillModel.symbol,
        timestamp_column=PaperFillModel.filled_at,
        model=PaperFillModel,
        now=now,
    )


def _refresh_paper_metrics(session: Session) -> None:
    accounts = session.scalars(select(PaperAccountModel).order_by(PaperAccountModel.run_id))
    for account in accounts:
        PAPER_ACCOUNT_EQUITY.labels(run_id=account.run_id).set(float(account.equity_inr))

    positions = session.scalars(
        select(PaperPositionModel).order_by(PaperPositionModel.run_id, PaperPositionModel.symbol)
    )
    for position in positions:
        PAPER_POSITION_VALUE.labels(
            run_id=position.run_id,
            symbol=position.symbol,
        ).set(float(position.market_value_inr))


def _set_status_counts(
    session: Session,
    *,
    artifact: str,
    model: Any,
    symbol_column: Any,
    status_column: Any,
) -> None:
    statement = (
        select(symbol_column, status_column, func.count())
        .select_from(model)
        .group_by(symbol_column, status_column)
        .order_by(symbol_column, status_column)
    )
    for symbol, status, count in session.execute(statement):
        TRADING_ARTIFACTS.labels(
            artifact=artifact,
            symbol=symbol,
            status=str(status),
        ).set(int(count))


def _set_latest_artifact_age(
    session: Session,
    *,
    artifact: str,
    symbol_column: Any,
    timestamp_column: Any,
    model: Any,
    now: datetime,
) -> None:
    statement = (
        select(symbol_column, func.max(timestamp_column))
        .select_from(model)
        .group_by(symbol_column)
        .order_by(symbol_column)
    )
    for symbol, latest_at in session.execute(statement):
        latest = _as_utc_datetime(latest_at)
        AGENT_ARTIFACT_AGE.labels(artifact=artifact, symbol=symbol).set(
            max(0.0, (now - latest).total_seconds())
        )


def _set_freshness(
    *,
    source: str,
    symbol: str,
    timeframe: str,
    latest_at: datetime,
    now: datetime,
) -> None:
    DATA_LATEST_AVAILABLE.labels(
        source=source,
        symbol=symbol,
        timeframe=timeframe,
    ).set(latest_at.timestamp())
    DATA_FRESHNESS.labels(
        source=source,
        symbol=symbol,
        timeframe=timeframe,
    ).set(max(0.0, (now - latest_at).total_seconds()))


def _clear_database_gauges() -> None:
    for metric in (
        DB_TABLE_ROWS,
        DATA_LATEST_AVAILABLE,
        DATA_FRESHNESS,
        NEWS_DOCUMENTS,
        NEWS_EVENTS,
        AGENT_REPORTS,
        AGENT_ARTIFACT_AGE,
        TRADING_ARTIFACTS,
        PAPER_ACCOUNT_EQUITY,
        PAPER_POSITION_VALUE,
    ):
        metric.clear()


def _as_utc_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)
