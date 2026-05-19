from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class InstrumentModel(Base):
    __tablename__ = "instruments"

    symbol: Mapped[str] = mapped_column(String(32), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    exchange: Mapped[str] = mapped_column(String(32), nullable=False, default="NSE")
    segment: Mapped[str] = mapped_column(String(32), nullable=False, default="EQUITY")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    lot_size: Mapped[int] = mapped_column(nullable=False, default=1)
    tick_size: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        default=Decimal("0.05"),
    )
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class DailyCandleModel(Base):
    __tablename__ = "daily_candles"
    __table_args__ = (
        UniqueConstraint(
            "symbol",
            "timeframe",
            "trade_date",
            name="uq_daily_candles_symbol_timeframe_date",
        ),
        Index("ix_daily_candles_symbol_timeframe_date", "symbol", "timeframe", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    timeframe: Mapped[str] = mapped_column(String(8), nullable=False, default="1d")
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class PortfolioSnapshotModel(Base):
    __tablename__ = "portfolio_snapshots"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    cash_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    holdings_value_inr: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
    )
    total_value_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class FeatureValueModel(Base):
    __tablename__ = "feature_values"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "snapshot_id",
            "feature_name",
            name="uq_feature_values_run_snapshot_feature",
        ),
        Index("ix_feature_values_run_symbol_time", "run_id", "symbol", "feature_time"),
        Index("ix_feature_values_snapshot", "snapshot_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("backtest_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    feature_name: Mapped[str] = mapped_column(String(128), nullable=False)
    feature_value: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    feature_time: Mapped[date] = mapped_column(Date, nullable=False)
    data_available_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="daily_candles")
    feature_version: Mapped[str] = mapped_column(String(128), nullable=False, default="technical_v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class BacktestRunModel(Base):
    __tablename__ = "backtest_runs"

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    strategy_name: Mapped[str] = mapped_column(String(128), nullable=False)
    seed: Mapped[int] = mapped_column(nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    initial_capital_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    final_equity_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    parameters: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class BacktestSignalModel(Base):
    __tablename__ = "backtest_signals"
    __table_args__ = (
        Index("ix_backtest_signals_run_date_symbol", "run_id", "trade_date", "symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("backtest_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    feature_snapshot_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    explanation: Mapped[dict[str, object] | None] = mapped_column(JSON, nullable=True, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class BacktestOrderModel(Base):
    __tablename__ = "backtest_orders"
    __table_args__ = (
        Index("ix_backtest_orders_run_date_symbol", "run_id", "trade_date", "symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("backtest_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False, default="MARKET")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="FILLED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class BacktestFillModel(Base):
    __tablename__ = "backtest_fills"
    __table_args__ = (
        Index("ix_backtest_fills_run_date_symbol", "run_id", "trade_date", "symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("backtest_orders.id", ondelete="CASCADE"),
        nullable=False,
    )
    run_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("backtest_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    fill_price_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    gross_value_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cost_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    slippage_bps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class BacktestPositionModel(Base):
    __tablename__ = "backtest_positions"
    __table_args__ = (
        UniqueConstraint("run_id", "symbol", name="uq_backtest_positions_run_symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("backtest_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(String(32), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    average_cost_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    market_value_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    realized_pnl_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    unrealized_pnl_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class BacktestEquityPointModel(Base):
    __tablename__ = "backtest_equity_points"
    __table_args__ = (
        UniqueConstraint("run_id", "trade_date", name="uq_backtest_equity_run_date"),
        Index("ix_backtest_equity_run_date", "run_id", "trade_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("backtest_runs.run_id", ondelete="CASCADE"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    cash_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    holdings_value_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    total_equity_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    drawdown_pct: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AuditLogModel(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="system")
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class RawDocumentModel(Base):
    __tablename__ = "raw_documents"
    __table_args__ = (
        UniqueConstraint("checksum", name="uq_raw_documents_checksum"),
        Index("ix_raw_documents_published_at", "published_at"),
    )

    document_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    entities: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    document_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class CompanyEventModel(Base):
    __tablename__ = "company_events"
    __table_args__ = (
        UniqueConstraint("document_id", "symbol", "event_type", name="uq_company_events_doc_symbol_type"),
        Index("ix_company_events_symbol_time", "symbol", "event_time"),
    )

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("raw_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    event_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    headline: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    severity: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    source_confidence: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    event_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class SentimentScoreModel(Base):
    __tablename__ = "sentiment_scores"
    __table_args__ = (
        UniqueConstraint("event_id", "model_version", name="uq_sentiment_scores_event_model"),
        Index("ix_sentiment_scores_symbol_as_of", "symbol", "as_of"),
    )

    score_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("company_events.event_id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    sentiment_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    event_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    decayed_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    severity: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model_version: Mapped[str] = mapped_column(String(128), nullable=False, default="event_scoring_v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class AnalystReportModel(Base):
    __tablename__ = "analyst_reports"
    __table_args__ = (
        UniqueConstraint("run_id", "symbol", "agent_name", name="uq_analyst_reports_run_symbol_agent"),
        Index("ix_analyst_reports_symbol_as_of", "symbol", "as_of"),
    )

    report_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    decision_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    agent_name: Mapped[str] = mapped_column(String(128), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    stance: Mapped[str] = mapped_column(String(32), nullable=False)
    horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    key_points: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    risks: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class DebateReportModel(Base):
    __tablename__ = "debate_reports"
    __table_args__ = (
        UniqueConstraint("run_id", "symbol", name="uq_debate_reports_run_symbol"),
        Index("ix_debate_reports_symbol_as_of", "symbol", "as_of"),
    )

    debate_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rounds_requested: Mapped[int] = mapped_column(nullable=False, default=2)
    consensus_label: Mapped[str] = mapped_column(String(32), nullable=False)
    consensus_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    bull_thesis: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    bear_thesis: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    rounds: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    manager_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    source_report_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class TraderProposalModel(Base):
    __tablename__ = "trader_proposals"
    __table_args__ = (
        UniqueConstraint("run_id", "symbol", name="uq_trader_proposals_run_symbol"),
        Index("ix_trader_proposals_symbol_as_of", "symbol", "as_of"),
    )

    proposal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    debate_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("debate_reports.debate_id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    action: Mapped[str] = mapped_column(String(16), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    horizon: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_position_pct_nav: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    order_type: Mapped[str] = mapped_column(String(16), nullable=False)
    entry_rule: Mapped[str] = mapped_column(Text, nullable=False)
    stop_loss_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    take_profit_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    reason_summary: Mapped[str] = mapped_column(Text, nullable=False)
    invalid_if: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source_report_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_order: Mapped[bool] = mapped_column(nullable=False, default=False)
    requires_risk_approval: Mapped[bool] = mapped_column(nullable=False, default=True)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class RiskReviewModel(Base):
    __tablename__ = "risk_reviews"
    __table_args__ = (
        UniqueConstraint("run_id", "symbol", name="uq_risk_reviews_run_symbol"),
        Index("ix_risk_reviews_symbol_as_of", "symbol", "as_of"),
    )

    risk_check_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    proposal_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("trader_proposals.proposal_id", ondelete="CASCADE"),
        nullable=False,
    )
    debate_id: Mapped[str] = mapped_column(String(128), nullable=False)
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    requested_position_pct_nav: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    approved_position_pct_nav: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    hard_rule_results: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    persona_reviews: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    risk_committee_summary: Mapped[str] = mapped_column(Text, nullable=False)
    source_report_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    is_order: Mapped[bool] = mapped_column(nullable=False, default=False)
    can_send_to_broker: Mapped[bool] = mapped_column(nullable=False, default=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class FinalDecisionModel(Base):
    __tablename__ = "final_decisions"
    __table_args__ = (
        UniqueConstraint("run_id", "symbol", name="uq_final_decisions_run_symbol"),
        Index("ix_final_decisions_symbol_as_of", "symbol", "as_of"),
    )

    final_decision_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    proposal_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("trader_proposals.proposal_id", ondelete="CASCADE"),
        nullable=False,
    )
    risk_check_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("risk_reviews.risk_check_id", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    final_action: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    approved_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    approved_position_pct_nav: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    is_order: Mapped[bool] = mapped_column(nullable=False, default=False)
    can_send_to_broker: Mapped[bool] = mapped_column(nullable=False, default=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
