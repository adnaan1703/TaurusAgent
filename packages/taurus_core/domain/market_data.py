from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
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
    source: str = "mock_market_data"
    data_available_time: datetime | None = None


class MarketDataProvider(Protocol):
    @property
    def provider_name(self) -> str:
        ...

    @property
    def source(self) -> str:
        ...

    def list_instruments(self) -> list[Instrument]:
        ...

    def get_daily_candles(self, symbol: str) -> list[DailyCandle]:
        ...

    def get_historical_candles(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyCandle]:
        ...

    def get_latest_candle(self, symbol: str) -> DailyCandle | None:
        ...


class MarketDataProviderError(RuntimeError):
    """Raised when a market data provider cannot serve the requested data."""
