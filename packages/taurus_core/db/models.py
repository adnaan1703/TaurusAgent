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
    source: Mapped[str] = mapped_column(String(128), nullable=False, default="mock_market_data")
    data_available_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class InstrumentProviderMappingModel(Base):
    __tablename__ = "instrument_provider_mappings"
    __table_args__ = (
        UniqueConstraint("provider", "symbol", name="uq_provider_mappings_provider_symbol"),
        Index("ix_provider_mappings_provider_symbol", "provider", "symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    instrument_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    segment: Mapped[str] = mapped_column(String(32), nullable=False, default="EQUITY")
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    lot_size: Mapped[int] = mapped_column(nullable=False, default=1)
    tick_size: Mapped[Decimal] = mapped_column(
        Numeric(10, 4),
        nullable=False,
        default=Decimal("0.05"),
    )
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    raw: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class MarketPriceSnapshotModel(Base):
    __tablename__ = "market_price_snapshots"
    __table_args__ = (
        Index("ix_market_price_snapshots_provider_symbol_time", "provider", "symbol", "fetched_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    exchange: Mapped[str] = mapped_column(String(32), nullable=False)
    provider_symbol: Mapped[str] = mapped_column(String(128), nullable=False)
    instrument_token: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_price: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source: Mapped[str] = mapped_column(String(128), nullable=False)
    raw: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


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


class GraphNodeModel(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (
        UniqueConstraint("node_key", name="uq_graph_nodes_node_key"),
        Index("ix_graph_nodes_type_symbol", "node_type", "symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    node_key: Mapped[str] = mapped_column(String(128), nullable=False)
    node_type: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    symbol: Mapped[str | None] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="SET NULL"),
        nullable=True,
    )
    isin: Mapped[str | None] = mapped_column(String(32), nullable=True)
    node_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class GraphEdgeModel(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint("edge_key", name="uq_graph_edges_edge_key"),
        Index("ix_graph_edges_source_target", "source_node_id", "target_node_id"),
        Index("ix_graph_edges_type_status", "edge_type", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    edge_key: Mapped[str] = mapped_column(String(160), nullable=False)
    source_node_id: Mapped[int] = mapped_column(
        ForeignKey("graph_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    target_node_id: Mapped[int] = mapped_column(
        ForeignKey("graph_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    edge_type: Mapped[str] = mapped_column(String(64), nullable=False)
    direction: Mapped[str] = mapped_column(String(32), nullable=False, default="directed")
    expected_sign: Mapped[str] = mapped_column(String(16), nullable=False, default="unknown")
    strength: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    evidence_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, default=Decimal("0"))
    inferred: Mapped[bool] = mapped_column(nullable=False, default=False)
    mechanism: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tradability_relevance: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="candidate")
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_file: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    edge_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class GraphEdgeEvidenceModel(Base):
    __tablename__ = "graph_edge_evidence"
    __table_args__ = (
        Index("ix_graph_edge_evidence_edge", "edge_id"),
        Index("ix_graph_edge_evidence_claim_type", "claim_type"),
    )

    evidence_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    edge_id: Mapped[int] = mapped_column(
        ForeignKey("graph_edges.id", ondelete="CASCADE"),
        nullable=False,
    )
    claim_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    claim_summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_title: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    source_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    source_url_or_reference: Mapped[str] = mapped_column(Text, nullable=False, default="")
    page_or_section: Mapped[str] = mapped_column(Text, nullable=False, default="")
    verbatim_excerpt_short: Mapped[str] = mapped_column(Text, nullable=False, default="")
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, default=Decimal("0"))
    source_file: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_row_hash: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    evidence_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class GraphEdgeStatsModel(Base):
    __tablename__ = "graph_edge_stats"
    __table_args__ = (
        UniqueConstraint(
            "edge_id",
            "stat_window",
            "as_of_date",
            "model_version",
            name="uq_graph_edge_stats_edge_window_as_of_model",
        ),
        Index("ix_graph_edge_stats_as_of", "as_of_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    edge_id: Mapped[int] = mapped_column(
        ForeignKey("graph_edges.id", ondelete="CASCADE"),
        nullable=False,
    )
    stat_window: Mapped[str] = mapped_column(String(32), nullable=False)
    as_of_date: Mapped[date] = mapped_column(Date, nullable=False)
    sample_size: Mapped[int] = mapped_column(nullable=False, default=0)
    raw_correlation: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    residual_correlation: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    lead_lag_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    stability_score: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    p_value: Mapped[Decimal | None] = mapped_column(Numeric(12, 8), nullable=True)
    insufficient_data_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    model_version: Mapped[str] = mapped_column(String(128), nullable=False, default="graph_stats_v1")
    stats_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class GraphSignalModel(Base):
    __tablename__ = "graph_signals"
    __table_args__ = (
        Index("ix_graph_signals_symbol_as_of", "symbol", "as_of"),
        Index("ix_graph_signals_source_agent", "source_agent"),
    )

    signal_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    confidence: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    horizon: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_agent: Mapped[str] = mapped_column(String(128), nullable=False, default="GraphAnalystAgent")
    signal_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class GraphSignalContributionModel(Base):
    __tablename__ = "graph_signal_contributions"
    __table_args__ = (
        Index("ix_graph_signal_contributions_signal", "signal_id"),
        Index("ix_graph_signal_contributions_edge", "edge_id"),
        Index("ix_graph_signal_contributions_node", "node_id"),
    )

    contribution_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    signal_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("graph_signals.signal_id", ondelete="CASCADE"),
        nullable=False,
    )
    edge_id: Mapped[int | None] = mapped_column(
        ForeignKey("graph_edges.id", ondelete="SET NULL"),
        nullable=True,
    )
    node_id: Mapped[int | None] = mapped_column(
        ForeignKey("graph_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    contribution_type: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    direction: Mapped[str] = mapped_column(String(16), nullable=False, default="")
    score_contribution: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False, default=Decimal("1"))
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    contribution_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON,
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


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


class FundamentalImportModel(Base):
    __tablename__ = "fundamental_imports"
    __table_args__ = (
        UniqueConstraint("source_file_hash", name="uq_fundamental_imports_source_file_hash"),
        Index("ix_fundamental_imports_imported_at", "imported_at"),
    )

    import_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="screener_csv")
    source_filename: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    rows_seen: Mapped[int] = mapped_column(nullable=False, default=0)
    rows_imported: Mapped[int] = mapped_column(nullable=False, default=0)
    rows_unmapped: Mapped[int] = mapped_column(nullable=False, default=0)
    metrics_imported: Mapped[int] = mapped_column(nullable=False, default=0)
    scores_imported: Mapped[int] = mapped_column(nullable=False, default=0)
    missing_required_columns: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    missing_optional_columns: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    imported_symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="IMPORTED")
    data_available_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class FundamentalSnapshotModel(Base):
    __tablename__ = "fundamental_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "import_id",
            "symbol",
            "metric_name",
            name="uq_fundamental_snapshots_import_symbol_metric",
        ),
        Index("ix_fundamental_snapshots_symbol_time", "symbol", "data_available_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    import_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("fundamental_imports.import_id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    metric_name: Mapped[str] = mapped_column(String(64), nullable=False)
    metric_value: Mapped[Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    source_column: Mapped[str] = mapped_column(String(128), nullable=False)
    raw_value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    reporting_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    import_date: Mapped[date] = mapped_column(Date, nullable=False)
    data_available_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class FundamentalScoreModel(Base):
    __tablename__ = "fundamental_scores"
    __table_args__ = (
        UniqueConstraint("import_id", "symbol", name="uq_fundamental_scores_import_symbol"),
        Index("ix_fundamental_scores_symbol_as_of", "symbol", "as_of"),
    )

    score_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    import_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("fundamental_imports.import_id", ondelete="CASCADE"),
        nullable=False,
    )
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    company_name: Mapped[str] = mapped_column(Text, nullable=False, default="")
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    data_available_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    quality_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    valuation_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    leverage_risk_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    ownership_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    composite_score: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    metrics: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    source_file_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False, default="fundamental_score_v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class HalalStockImportModel(Base):
    __tablename__ = "halal_stock_imports"
    __table_args__ = (
        Index("ix_halal_stock_imports_fetched_at", "fetched_at"),
    )

    import_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    source_checksum: Mapped[str] = mapped_column(String(128), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rows_seen: Mapped[int] = mapped_column(nullable=False, default=0)
    rows_imported: Mapped[int] = mapped_column(nullable=False, default=0)
    halal_count: Mapped[int] = mapped_column(nullable=False, default=0)
    haram_count: Mapped[int] = mapped_column(nullable=False, default=0)
    unknown_count: Mapped[int] = mapped_column(nullable=False, default=0)
    duplicate_count: Mapped[int] = mapped_column(nullable=False, default=0)
    generated_yaml_path: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="IMPORTED")
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class HalalStockComplianceModel(Base):
    __tablename__ = "halal_stock_compliance"
    __table_args__ = (
        Index("ix_halal_stock_compliance_active_status", "active", "compliance_status"),
        Index("ix_halal_stock_compliance_nse_code", "nse_code"),
    )

    source_key: Mapped[str] = mapped_column(String(128), primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    bse_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    nse_code: Mapped[str] = mapped_column(String(64), nullable=False, default="")
    industry: Mapped[str] = mapped_column(Text, nullable=False, default="")
    compliance_status: Mapped[str] = mapped_column(String(16), nullable=False)
    status_icon_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    details_url: Mapped[str] = mapped_column(Text, nullable=False, default="")
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(nullable=False, default=True)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    raw_metadata: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


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


class PaperRunModel(Base):
    __tablename__ = "paper_runs"
    __table_args__ = (
        Index("ix_paper_runs_started_at", "started_at"),
        Index("ix_paper_runs_status", "status"),
    )

    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    schedule_name: Mapped[str] = mapped_column(String(128), nullable=False, default="daily_after_close")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    succeeded_symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    failed_symbols: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    errors: Mapped[list[dict[str, object]]] = mapped_column(JSON, nullable=False, default=list)
    market_data_summary: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    artifacts: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Kolkata")
    run_after_market_close: Mapped[bool] = mapped_column(nullable=False, default=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
    )


class PaperOrderModel(Base):
    __tablename__ = "paper_orders"
    __table_args__ = (
        UniqueConstraint("final_decision_id", name="uq_paper_orders_final_decision"),
        Index("ix_paper_orders_run_symbol_time", "run_id", "symbol", "submitted_at"),
    )

    order_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    final_decision_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("final_decisions.final_decision_id", ondelete="CASCADE"),
        nullable=False,
    )
    decision_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    order_type: Mapped[str] = mapped_column(String(32), nullable=False, default="MARKET")
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="CREATED")
    filled_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    remaining_quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    average_fill_price_inr: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
    )
    gross_value_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    total_cost_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    total_slippage_inr: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
    )
    slippage_bps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False, default=Decimal("0"))
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PaperFillModel(Base):
    __tablename__ = "paper_fills"
    __table_args__ = (
        UniqueConstraint("order_id", "fill_sequence", name="uq_paper_fills_order_sequence"),
        Index("ix_paper_fills_run_symbol_time", "run_id", "symbol", "filled_at"),
    )

    fill_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    order_id: Mapped[str] = mapped_column(
        String(128),
        ForeignKey("paper_orders.order_id", ondelete="CASCADE"),
        nullable=False,
    )
    final_decision_id: Mapped[str] = mapped_column(String(128), nullable=False)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    trade_date: Mapped[date] = mapped_column(Date, nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[int] = mapped_column(nullable=False)
    reference_price_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fill_price_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    gross_value_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    brokerage_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    exchange_txn_charge_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    tax_levy_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    cost_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    slippage_bps: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    slippage_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    fill_sequence: Mapped[int] = mapped_column(nullable=False)
    filled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PaperPositionModel(Base):
    __tablename__ = "paper_positions"
    __table_args__ = (
        UniqueConstraint("run_id", "symbol", name="uq_paper_positions_run_symbol"),
        Index("ix_paper_positions_run_symbol", "run_id", "symbol"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    symbol: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("instruments.symbol", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[int] = mapped_column(nullable=False, default=0)
    average_cost_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    last_price_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    market_value_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    realized_pnl_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    unrealized_pnl_inr: Mapped[Decimal] = mapped_column(
        Numeric(18, 4),
        nullable=False,
        default=Decimal("0"),
    )
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)


class PaperAccountModel(Base):
    __tablename__ = "paper_accounts"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_paper_accounts_run_id"),
        Index("ix_paper_accounts_updated_at", "updated_at"),
    )

    account_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), nullable=False)
    starting_cash_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    available_cash_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    reserved_cash_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    realized_pnl_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    unrealized_pnl_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    gross_exposure_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False, default=Decimal("0"))
    equity_inr: Mapped[Decimal] = mapped_column(Numeric(18, 4), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), nullable=False, default="INR")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
