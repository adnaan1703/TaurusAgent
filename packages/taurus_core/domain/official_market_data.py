from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True, slots=True)
class OfficialIndexCandle:
    index_symbol: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    source: str
    index_family: str
    index_name: str = ""
    timeframe: str = "1d"
    source_url: str | None = None
    data_available_time: datetime | None = None
    raw: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class OfficialSecurityMicrostructure:
    symbol: str
    trade_date: date
    source: str
    timeframe: str = "1d"
    source_url: str | None = None
    data_available_time: datetime | None = None
    delivery_quantity: int | None = None
    delivery_percentage: Decimal | None = None
    price_band_percent: Decimal | None = None
    upper_circuit_price: Decimal | None = None
    lower_circuit_price: Decimal | None = None
    circuit_status: str | None = None
    circuit_hit: bool | None = None
    impact_cost_bps: Decimal | None = None
    impact_cost_source_kind: str = "unavailable"
    impact_cost_proxy_name: str | None = None
    average_trade_value: Decimal | None = None
    turnover: Decimal | None = None
    raw: dict[str, Any] | None = None
