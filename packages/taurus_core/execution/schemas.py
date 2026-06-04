from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taurus_core.intelligence.documents import stable_id

OrderSide = Literal["BUY", "SELL"]
OrderStatus = Literal[
    "CREATED",
    "ACCEPTED",
    "PENDING_NEXT_OPEN",
    "PARTIALLY_FILLED",
    "FILLED",
    "CANCELLED",
    "REJECTED",
]
ExecutionPolicy = Literal["immediate", "next_open"]
ScheduledFillSession = Literal["next_open"]


class PaperOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    final_decision_id: str
    decision_id: str
    run_id: str
    portfolio_id: str = "local-paper"
    symbol: str
    side: OrderSide
    quantity: int = Field(ge=0)
    order_type: str = "MARKET"
    status: OrderStatus
    execution_policy: ExecutionPolicy = "immediate"
    filled_quantity: int = Field(ge=0)
    remaining_quantity: int = Field(ge=0)
    average_fill_price_inr: Decimal = Field(ge=Decimal("0"))
    gross_value_inr: Decimal = Field(ge=Decimal("0"))
    total_cost_inr: Decimal = Field(ge=Decimal("0"))
    total_slippage_inr: Decimal = Field(ge=Decimal("0"))
    slippage_bps: Decimal = Field(ge=Decimal("0"))
    rejection_reason: str = ""
    status_history: list[OrderStatus] = Field(default_factory=list)
    signal_trade_date: date | None = None
    scheduled_fill_session: ScheduledFillSession | None = None
    filled_trade_date: date | None = None
    submitted_at: datetime
    updated_at: datetime
    model_version: str = "paper_broker_v1"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class PaperFill(BaseModel):
    model_config = ConfigDict(frozen=True)

    fill_id: str
    order_id: str
    final_decision_id: str
    run_id: str
    portfolio_id: str = "local-paper"
    symbol: str
    trade_date: date
    side: OrderSide
    quantity: int = Field(gt=0)
    reference_price_inr: Decimal = Field(gt=Decimal("0"))
    fill_price_inr: Decimal = Field(gt=Decimal("0"))
    gross_value_inr: Decimal = Field(ge=Decimal("0"))
    brokerage_inr: Decimal = Field(ge=Decimal("0"))
    exchange_txn_charge_inr: Decimal = Field(ge=Decimal("0"))
    tax_levy_inr: Decimal = Field(ge=Decimal("0"))
    cost_inr: Decimal = Field(ge=Decimal("0"))
    slippage_bps: Decimal = Field(ge=Decimal("0"))
    slippage_inr: Decimal = Field(ge=Decimal("0"))
    fill_sequence: int = Field(ge=1)
    filled_at: datetime
    model_version: str = "paper_broker_v1"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class PaperPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    portfolio_id: str = "local-paper"
    symbol: str
    quantity: int = Field(ge=0)
    average_cost_inr: Decimal = Field(ge=Decimal("0"))
    last_price_inr: Decimal = Field(ge=Decimal("0"))
    market_value_inr: Decimal = Field(ge=Decimal("0"))
    realized_pnl_inr: Decimal
    unrealized_pnl_inr: Decimal
    updated_at: datetime
    model_version: str = "paper_broker_v1"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class PaperAccount(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: str
    run_id: str
    portfolio_id: str = "local-paper"
    starting_cash_inr: Decimal = Field(gt=Decimal("0"))
    available_cash_inr: Decimal
    reserved_cash_inr: Decimal = Field(ge=Decimal("0"))
    realized_pnl_inr: Decimal
    unrealized_pnl_inr: Decimal
    gross_exposure_inr: Decimal = Field(ge=Decimal("0"))
    equity_inr: Decimal
    currency: str = "INR"
    updated_at: datetime
    model_version: str = "paper_broker_v1"


class NextOpenSettlementOrderDetail(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    symbol: str
    side: OrderSide
    signal_trade_date: date | None = None
    execution_trade_date: date | None = None
    reference_price_inr: Decimal | None = None
    fill_price_inr: Decimal | None = None
    quantity: int = Field(ge=0)
    status: OrderStatus
    rejection_reason: str = ""
    outcome_reason: str = ""

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class NextOpenSettlementSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    portfolio_id: str
    run_id: str
    settled: int = Field(ge=0)
    rejected: int = Field(ge=0)
    still_pending: int = Field(ge=0)
    skipped: int = Field(ge=0)
    details: list[NextOpenSettlementOrderDetail] = Field(default_factory=list)


def paper_account_id(*, portfolio_id: str, run_id: str) -> str:
    return stable_id("pa", portfolio_id, run_id)


def paper_order_id(*, final_decision_id: str, decision_id: str, quantity: int) -> str:
    return stable_id("po", final_decision_id, decision_id, quantity, "paper_broker_v1")


def paper_fill_id(*, order_id: str, fill_sequence: int, quantity: int, reference_price: Decimal) -> str:
    return stable_id("pf", order_id, fill_sequence, quantity, reference_price)
