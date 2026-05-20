from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any, TypeVar

from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.db.models import (
    AnalystReportModel,
    BacktestEquityPointModel,
    BacktestRunModel,
    CompanyEventModel,
    DailyCandleModel,
    DebateReportModel,
    FeatureValueModel,
    FinalDecisionModel,
    FundamentalImportModel,
    FundamentalScoreModel,
    FundamentalSnapshotModel,
    InstrumentModel,
    PaperRunModel,
    PaperAccountModel,
    PaperFillModel,
    PaperOrderModel,
    PaperPositionModel,
    RawDocumentModel,
    RiskReviewModel,
    SentimentScoreModel,
    TraderProposalModel,
)
from taurus_core.db.session import build_session_factory

T = TypeVar("T")


class DashboardDataError(RuntimeError):
    """Raised when dashboard data cannot be loaded."""


def read_dashboard_data(settings: Settings, reader: Callable[[Session], T]) -> T:
    try:
        run_migrations(settings)
        session_factory = build_session_factory(settings)
        with session_factory() as session:
            return reader(session)
    except SQLAlchemyError as exc:
        raise DashboardDataError(str(exc)) from exc


def overview_snapshot(session: Session, *, symbol: str | None = None) -> dict[str, Any]:
    account = latest_paper_account(session)
    decision = list_final_decisions(session, symbol=symbol, limit=1)
    order = list_paper_orders(session, symbol=symbol, limit=1)
    backtest = list_backtest_runs(session, limit=1)
    paper_run = list_paper_runs(session, limit=1)
    return {
        "counts": table_counts(session),
        "freshness": data_freshness(session, symbol=symbol),
        "latest_account": account,
        "latest_final_decision": decision[0] if decision else None,
        "latest_order": order[0] if order else None,
        "latest_backtest": backtest[0] if backtest else None,
        "latest_paper_run": paper_run[0] if paper_run else None,
    }


def list_symbols(session: Session) -> list[str]:
    statement = (
        select(InstrumentModel.symbol)
        .where(InstrumentModel.active.is_(True))
        .order_by(InstrumentModel.symbol)
    )
    return list(session.scalars(statement))


def table_counts(session: Session) -> dict[str, int]:
    models = {
        "instruments": InstrumentModel,
        "daily_candles": DailyCandleModel,
        "raw_documents": RawDocumentModel,
        "company_events": CompanyEventModel,
        "sentiment_scores": SentimentScoreModel,
        "fundamental_imports": FundamentalImportModel,
        "fundamental_scores": FundamentalScoreModel,
        "analyst_reports": AnalystReportModel,
        "debates": DebateReportModel,
        "trader_proposals": TraderProposalModel,
        "risk_reviews": RiskReviewModel,
        "final_decisions": FinalDecisionModel,
        "paper_orders": PaperOrderModel,
        "paper_fills": PaperFillModel,
        "paper_positions": PaperPositionModel,
        "paper_runs": PaperRunModel,
        "backtests": BacktestRunModel,
    }
    return {
        name: int(session.scalar(select(func.count()).select_from(model)) or 0)
        for name, model in models.items()
    }


def data_freshness(session: Session, *, symbol: str | None = None) -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    candle_statement = (
        select(
            DailyCandleModel.symbol,
            DailyCandleModel.timeframe,
            DailyCandleModel.source,
            func.max(DailyCandleModel.data_available_time),
            func.count(),
        )
        .group_by(DailyCandleModel.symbol, DailyCandleModel.timeframe, DailyCandleModel.source)
        .order_by(DailyCandleModel.symbol, DailyCandleModel.timeframe, DailyCandleModel.source)
    )
    if symbol is not None:
        candle_statement = candle_statement.where(DailyCandleModel.symbol == symbol.upper())

    rows: list[dict[str, Any]] = []
    for row_symbol, timeframe, source, latest_available_at, count in session.execute(candle_statement):
        latest_at = _as_utc_datetime(latest_available_at)
        rows.append(
            {
                "source": source,
                "symbol": row_symbol,
                "timeframe": timeframe,
                "latest_at": _display_time(latest_at),
                "age_hours": round((now - latest_at).total_seconds() / 3600, 2),
                "rows": int(count),
            }
        )

    feature_statement = (
        select(
            FeatureValueModel.symbol,
            FeatureValueModel.source,
            func.max(FeatureValueModel.data_available_time),
            func.count(),
        )
        .group_by(FeatureValueModel.symbol, FeatureValueModel.source)
        .order_by(FeatureValueModel.symbol, FeatureValueModel.source)
    )
    if symbol is not None:
        feature_statement = feature_statement.where(FeatureValueModel.symbol == symbol.upper())

    for row_symbol, source, latest_at, count in session.execute(feature_statement):
        latest_utc = _as_utc_datetime(latest_at)
        rows.append(
            {
                "source": source,
                "symbol": row_symbol,
                "timeframe": "feature",
                "latest_at": _display_time(latest_utc),
                "age_hours": round((now - latest_utc).total_seconds() / 3600, 2),
                "rows": int(count),
            }
        )

    fundamental_statement = (
        select(
            FundamentalScoreModel.symbol,
            func.max(FundamentalScoreModel.data_available_time),
            func.count(),
        )
        .group_by(FundamentalScoreModel.symbol)
        .order_by(FundamentalScoreModel.symbol)
    )
    if symbol is not None:
        fundamental_statement = fundamental_statement.where(
            FundamentalScoreModel.symbol == symbol.upper()
        )

    for row_symbol, latest_at, count in session.execute(fundamental_statement):
        latest_utc = _as_utc_datetime(latest_at)
        rows.append(
            {
                "source": "screener_fundamentals",
                "symbol": row_symbol,
                "timeframe": "fundamental",
                "latest_at": _display_time(latest_utc),
                "age_hours": round((now - latest_utc).total_seconds() / 3600, 2),
                "rows": int(count),
            }
        )
    return rows


def list_backtest_runs(session: Session, *, limit: int = 25) -> list[dict[str, Any]]:
    statement = select(BacktestRunModel).order_by(BacktestRunModel.created_at.desc()).limit(limit)
    rows = []
    for run in session.scalars(statement):
        metrics = run.metrics or {}
        rows.append(
            {
                "run_id": run.run_id,
                "strategy": run.strategy_name,
                "start": run.start_date.isoformat(),
                "end": run.end_date.isoformat(),
                "initial_inr": _number(run.initial_capital_inr),
                "final_inr": _number(run.final_equity_inr),
                "total_return_pct": _metric_pct(metrics, "total_return"),
                "sharpe": _metric_number(metrics, "sharpe"),
                "max_drawdown_pct": _metric_pct(metrics, "max_drawdown"),
                "created_at": _display_time(run.created_at),
            }
        )
    return rows


def latest_backtest_run_id(session: Session) -> str | None:
    return session.scalar(
        select(BacktestRunModel.run_id).order_by(BacktestRunModel.created_at.desc()).limit(1)
    )


def list_backtest_equity(
    session: Session,
    *,
    run_id: str | None = None,
    limit: int = 1000,
) -> list[dict[str, Any]]:
    run_id = run_id or latest_backtest_run_id(session)
    if run_id is None:
        return []
    statement = (
        select(BacktestEquityPointModel)
        .where(BacktestEquityPointModel.run_id == run_id)
        .order_by(BacktestEquityPointModel.trade_date)
        .limit(limit)
    )
    return [
        {
            "run_id": point.run_id,
            "trade_date": point.trade_date.isoformat(),
            "cash_inr": _number(point.cash_inr),
            "holdings_inr": _number(point.holdings_value_inr),
            "total_equity_inr": _number(point.total_equity_inr),
            "drawdown_pct": _number(point.drawdown_pct) * 100,
        }
        for point in session.scalars(statement)
    ]


def latest_paper_account(session: Session) -> dict[str, Any] | None:
    account = session.scalar(
        select(PaperAccountModel)
        .order_by(PaperAccountModel.updated_at.desc(), PaperAccountModel.account_id)
        .limit(1)
    )
    if account is None:
        return None
    return {
        "account_id": account.account_id,
        "run_id": account.run_id,
        "cash_inr": _number(account.available_cash_inr),
        "gross_exposure_inr": _number(account.gross_exposure_inr),
        "equity_inr": _number(account.equity_inr),
        "realized_pnl_inr": _number(account.realized_pnl_inr),
        "unrealized_pnl_inr": _number(account.unrealized_pnl_inr),
        "updated_at": _display_time(account.updated_at),
    }


def list_paper_runs(session: Session, *, limit: int = 50) -> list[dict[str, Any]]:
    statement = (
        select(PaperRunModel)
        .order_by(PaperRunModel.started_at.desc(), PaperRunModel.run_id)
        .limit(limit)
    )
    return [
        {
            "run_id": run.run_id,
            "status": run.status,
            "schedule": run.schedule_name,
            "symbols": _join_items(run.symbols or [], limit=8),
            "succeeded": _join_items(run.succeeded_symbols or [], limit=8),
            "failed": _join_items(run.failed_symbols or [], limit=8),
            "error_count": len(run.errors or []),
            "provider": (run.market_data_summary or {}).get("provider_name", ""),
            "candles": (run.market_data_summary or {}).get("candle_count", 0),
            "started_at": _display_time(run.started_at),
            "completed_at": _display_time(run.completed_at),
        }
        for run in session.scalars(statement)
    ]


def list_paper_positions(
    session: Session,
    *,
    symbol: str | None = None,
) -> list[dict[str, Any]]:
    statement = select(PaperPositionModel).order_by(PaperPositionModel.symbol)
    if symbol is not None:
        statement = statement.where(PaperPositionModel.symbol == symbol.upper())
    return [
        {
            "run_id": position.run_id,
            "symbol": position.symbol,
            "quantity": position.quantity,
            "average_cost_inr": _number(position.average_cost_inr),
            "last_price_inr": _number(position.last_price_inr),
            "market_value_inr": _number(position.market_value_inr),
            "unrealized_pnl_inr": _number(position.unrealized_pnl_inr),
            "updated_at": _display_time(position.updated_at),
        }
        for position in session.scalars(statement)
    ]


def list_paper_orders(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    statement = (
        select(PaperOrderModel)
        .order_by(PaperOrderModel.submitted_at.desc(), PaperOrderModel.order_id)
        .limit(limit)
    )
    if symbol is not None:
        statement = statement.where(PaperOrderModel.symbol == symbol.upper())
    return [
        {
            "order_id": order.order_id,
            "run_id": order.run_id,
            "decision_id": order.decision_id,
            "final_decision_id": order.final_decision_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "filled": order.filled_quantity,
            "status": order.status,
            "avg_fill_inr": _number(order.average_fill_price_inr),
            "gross_value_inr": _number(order.gross_value_inr),
            "cost_inr": _number(order.total_cost_inr),
            "slippage_inr": _number(order.total_slippage_inr),
            "submitted_at": _display_time(order.submitted_at),
        }
        for order in session.scalars(statement)
    ]


def list_paper_fills(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    statement = (
        select(PaperFillModel)
        .order_by(PaperFillModel.filled_at.desc(), PaperFillModel.fill_sequence)
        .limit(limit)
    )
    if symbol is not None:
        statement = statement.where(PaperFillModel.symbol == symbol.upper())
    return [
        {
            "fill_id": fill.fill_id,
            "order_id": fill.order_id,
            "run_id": fill.run_id,
            "symbol": fill.symbol,
            "side": fill.side,
            "quantity": fill.quantity,
            "reference_inr": _number(fill.reference_price_inr),
            "fill_price_inr": _number(fill.fill_price_inr),
            "cost_inr": _number(fill.cost_inr),
            "slippage_bps": _number(fill.slippage_bps),
            "filled_at": _display_time(fill.filled_at),
        }
        for fill in session.scalars(statement)
    ]


def list_events(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    event_statement = (
        select(CompanyEventModel)
        .order_by(CompanyEventModel.event_time.desc(), CompanyEventModel.event_id)
        .limit(limit)
    )
    if symbol is not None:
        event_statement = event_statement.where(CompanyEventModel.symbol == symbol.upper())
    events = list(session.scalars(event_statement))
    if not events:
        return []
    score_statement = select(SentimentScoreModel).where(
        SentimentScoreModel.event_id.in_([event.event_id for event in events])
    )
    score_by_event = {score.event_id: score for score in session.scalars(score_statement)}
    rows = []
    for event in events:
        score = score_by_event.get(event.event_id)
        rows.append(
            {
                "event_time": _display_time(event.event_time),
                "symbol": event.symbol,
                "event_type": event.event_type,
                "headline": event.headline,
                "severity": _number(event.severity),
                "sentiment": _number(score.sentiment_score) if score is not None else None,
                "decayed_score": _number(score.decayed_score) if score is not None else None,
                "document_id": event.document_id,
            }
        )
    return rows


def news_ingestion_summary(session: Session) -> list[dict[str, Any]]:
    statement = (
        select(RawDocumentModel.source, func.count(), func.max(RawDocumentModel.ingested_at))
        .group_by(RawDocumentModel.source)
        .order_by(RawDocumentModel.source)
    )
    return [
        {
            "source": source,
            "documents": int(count),
            "latest_ingested_at": _display_time(latest),
        }
        for source, count, latest in session.execute(statement)
    ]


def list_fundamental_scores(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    statement = (
        select(FundamentalScoreModel)
        .order_by(FundamentalScoreModel.data_available_time.desc(), FundamentalScoreModel.symbol)
        .limit(limit)
    )
    if symbol is not None:
        statement = statement.where(FundamentalScoreModel.symbol == symbol.upper())
    return [
        {
            "score_id": score.score_id,
            "import_id": score.import_id,
            "symbol": score.symbol,
            "company": score.company_name,
            "quality": _number_or_none(score.quality_score),
            "valuation": _number_or_none(score.valuation_score),
            "leverage_risk": _number_or_none(score.leverage_risk_score),
            "ownership": _number_or_none(score.ownership_score),
            "composite": _number(score.composite_score),
            "metrics": len(score.metrics or {}),
            "as_of": _display_time(score.as_of),
            "available_at": _display_time(score.data_available_time),
        }
        for score in session.scalars(statement)
    ]


def list_fundamental_snapshots(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 250,
) -> list[dict[str, Any]]:
    statement = (
        select(FundamentalSnapshotModel)
        .order_by(
            FundamentalSnapshotModel.data_available_time.desc(),
            FundamentalSnapshotModel.symbol,
            FundamentalSnapshotModel.metric_name,
        )
        .limit(limit)
    )
    if symbol is not None:
        statement = statement.where(FundamentalSnapshotModel.symbol == symbol.upper())
    return [
        {
            "symbol": snapshot.symbol,
            "company": snapshot.company_name,
            "metric": snapshot.metric_name,
            "value": _number(snapshot.metric_value),
            "source_column": snapshot.source_column,
            "reporting_date": _display_time(snapshot.reporting_date),
            "available_at": _display_time(snapshot.data_available_time),
        }
        for snapshot in session.scalars(statement)
    ]


def list_analyst_reports(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    statement = (
        select(AnalystReportModel)
        .order_by(AnalystReportModel.as_of.desc(), AnalystReportModel.agent_name)
        .limit(limit)
    )
    if symbol is not None:
        statement = statement.where(AnalystReportModel.symbol == symbol.upper())
    return [
        {
            "report_id": report.report_id,
            "run_id": report.run_id,
            "decision_id": report.decision_id,
            "symbol": report.symbol,
            "agent": report.agent_name,
            "stance": report.stance,
            "score": _number(report.score),
            "confidence": _number(report.confidence),
            "horizon": report.horizon,
            "key_points": _join_items(report.key_points),
            "risks": _join_items(report.risks),
            "model_version": report.model_version,
            "as_of": _display_time(report.as_of),
        }
        for report in session.scalars(statement)
    ]


def list_debates(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    statement = (
        select(DebateReportModel)
        .order_by(DebateReportModel.as_of.desc(), DebateReportModel.debate_id)
        .limit(limit)
    )
    if symbol is not None:
        statement = statement.where(DebateReportModel.symbol == symbol.upper())
    return [
        {
            "debate_id": debate.debate_id,
            "run_id": debate.run_id,
            "symbol": debate.symbol,
            "consensus": debate.consensus_label,
            "consensus_score": _number(debate.consensus_score),
            "confidence": _number(debate.confidence),
            "bull_score": _number((debate.bull_thesis or {}).get("score")),
            "bear_score": _number((debate.bear_thesis or {}).get("score")),
            "rounds": debate.rounds_requested,
            "summary": (debate.manager_summary or {}).get("summary", ""),
            "as_of": _display_time(debate.as_of),
        }
        for debate in session.scalars(statement)
    ]


def list_trader_proposals(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    statement = (
        select(TraderProposalModel)
        .order_by(TraderProposalModel.as_of.desc(), TraderProposalModel.proposal_id)
        .limit(limit)
    )
    if symbol is not None:
        statement = statement.where(TraderProposalModel.symbol == symbol.upper())
    return [
        {
            "proposal_id": proposal.proposal_id,
            "run_id": proposal.run_id,
            "symbol": proposal.symbol,
            "debate_id": proposal.debate_id,
            "action": proposal.action,
            "confidence": _number(proposal.confidence),
            "requested_pct_nav": _number(proposal.requested_position_pct_nav),
            "stop_loss_pct": _number(proposal.stop_loss_pct),
            "take_profit_pct": _number(proposal.take_profit_pct),
            "reason": proposal.reason_summary,
            "invalid_if": _join_items(proposal.invalid_if),
            "as_of": _display_time(proposal.as_of),
        }
        for proposal in session.scalars(statement)
    ]


def list_risk_reviews(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    statement = (
        select(RiskReviewModel)
        .order_by(RiskReviewModel.as_of.desc(), RiskReviewModel.risk_check_id)
        .limit(limit)
    )
    if symbol is not None:
        statement = statement.where(RiskReviewModel.symbol == symbol.upper())
    return [
        {
            "risk_check_id": review.risk_check_id,
            "decision_id": review.decision_id,
            "run_id": review.run_id,
            "symbol": review.symbol,
            "proposal_id": review.proposal_id,
            "status": review.status,
            "requested_pct_nav": _number(review.requested_position_pct_nav),
            "approved_pct_nav": _number(review.approved_position_pct_nav),
            "hard_rules": len(review.hard_rule_results or []),
            "summary": review.risk_committee_summary,
            "as_of": _display_time(review.as_of),
        }
        for review in session.scalars(statement)
    ]


def list_hard_rule_results(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 20,
) -> list[dict[str, Any]]:
    statement = (
        select(RiskReviewModel)
        .order_by(RiskReviewModel.as_of.desc(), RiskReviewModel.risk_check_id)
        .limit(limit)
    )
    if symbol is not None:
        statement = statement.where(RiskReviewModel.symbol == symbol.upper())
    rows: list[dict[str, Any]] = []
    for review in session.scalars(statement):
        for result in review.hard_rule_results or []:
            rows.append(
                {
                    "risk_check_id": review.risk_check_id,
                    "symbol": review.symbol,
                    "rule": result.get("rule"),
                    "status": result.get("status"),
                    "details": result.get("details"),
                }
            )
    return rows


def list_final_decisions(
    session: Session,
    *,
    symbol: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    statement = (
        select(FinalDecisionModel)
        .order_by(FinalDecisionModel.as_of.desc(), FinalDecisionModel.final_decision_id)
        .limit(limit)
    )
    if symbol is not None:
        statement = statement.where(FinalDecisionModel.symbol == symbol.upper())
    return [
        {
            "final_decision_id": decision.final_decision_id,
            "decision_id": decision.decision_id,
            "run_id": decision.run_id,
            "symbol": decision.symbol,
            "proposal_id": decision.proposal_id,
            "risk_check_id": decision.risk_check_id,
            "action": decision.final_action,
            "status": decision.status,
            "approved_quantity": decision.approved_quantity,
            "approved_pct_nav": _number(decision.approved_position_pct_nav),
            "can_send_to_broker": decision.can_send_to_broker,
            "reason": decision.reason,
            "as_of": _display_time(decision.as_of),
        }
        for decision in session.scalars(statement)
    ]


def _join_items(items: list[Any], *, limit: int = 3) -> str:
    cleaned = [str(item) for item in items if str(item).strip()]
    if len(cleaned) <= limit:
        return "; ".join(cleaned)
    return "; ".join(cleaned[:limit]) + f"; +{len(cleaned) - limit} more"


def _metric_number(metrics: dict[str, Any], key: str) -> float | None:
    value = metrics.get(key)
    return _number(value) if value is not None else None


def _metric_pct(metrics: dict[str, Any], key: str) -> float | None:
    value = _metric_number(metrics, key)
    return round(value * 100, 4) if value is not None else None


def _number(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _number_or_none(value: Any) -> float | None:
    if value is None:
        return None
    return _number(value)


def _display_time(value: date | datetime | None) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return _as_utc_datetime(value).isoformat()
    return value.isoformat()


def _as_utc_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return datetime.combine(value, time.min, tzinfo=timezone.utc)
