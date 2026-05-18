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
