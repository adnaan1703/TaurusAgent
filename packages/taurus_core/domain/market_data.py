from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from taurus_core.domain.instruments import Instrument


@dataclass(frozen=True, slots=True)
class DailyCandle:
    symbol: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    timeframe: str = "1d"


class MarketDataProvider(Protocol):
    def list_instruments(self) -> list[Instrument]:
        ...

    def get_daily_candles(self, symbol: str) -> list[DailyCandle]:
        ...
