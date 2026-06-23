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
