from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle, MarketPriceSnapshot

MOCK_INSTRUMENTS: tuple[Instrument, ...] = (
    Instrument(symbol="RELIANCE", name="Reliance Industries Ltd"),
    Instrument(symbol="TCS", name="Tata Consultancy Services Ltd"),
    Instrument(symbol="INFY", name="Infosys Ltd"),
    Instrument(symbol="HDFCBANK", name="HDFC Bank Ltd"),
    Instrument(symbol="ICICIBANK", name="ICICI Bank Ltd"),
    Instrument(symbol="LT", name="Larsen & Toubro Ltd"),
    Instrument(symbol="SBIN", name="State Bank of India"),
    Instrument(symbol="BHARTIARTL", name="Bharti Airtel Ltd"),
    Instrument(symbol="ITC", name="ITC Ltd"),
    Instrument(symbol="HINDUNILVR", name="Hindustan Unilever Ltd"),
)


class MockMarketDataProvider:
    def __init__(
        self,
        *,
        seed: int = 42,
        candle_count: int = 252,
        start_date: date = date(2024, 1, 1),
    ) -> None:
        if candle_count < 1:
            raise ValueError("candle_count must be positive")
        self.seed = seed
        self.candle_count = candle_count
        self.start_date = start_date
        self._instruments = {instrument.symbol: instrument for instrument in MOCK_INSTRUMENTS}

    @property
    def provider_name(self) -> str:
        return "mock"

    @property
    def source(self) -> str:
        return "mock_market_data"

    def list_instruments(self) -> list[Instrument]:
        return list(self._instruments.values())

    def get_daily_candles(self, symbol: str) -> list[DailyCandle]:
        normalized_symbol = symbol.upper()
        if normalized_symbol not in self._instruments:
            return []

        symbol_index = list(self._instruments).index(normalized_symbol)
        rng = random.Random(_stable_seed(self.seed, normalized_symbol))
        base_price = 120.0 + (symbol_index * 85.0) + rng.uniform(-15.0, 15.0)
        base_volume = 700_000 + (symbol_index * 175_000)
        previous_close = base_price
        candles: list[DailyCandle] = []

        for trade_date in _trading_days(self.start_date, self.candle_count):
            open_price = max(10.0, previous_close * (1 + rng.uniform(-0.012, 0.012)))
            close_price = max(10.0, open_price * (1 + rng.gauss(0.0006, 0.018)))
            high_price = max(open_price, close_price) * (1 + rng.uniform(0.001, 0.022))
            low_price = min(open_price, close_price) * (1 - rng.uniform(0.001, 0.022))
            volume = int(base_volume * rng.uniform(0.75, 1.45))

            candles.append(
                DailyCandle(
                    symbol=normalized_symbol,
                    trade_date=trade_date,
                    open=_money(open_price),
                    high=_money(high_price),
                    low=_money(low_price),
                    close=_money(close_price),
                    volume=volume,
                    source=self.source,
                    data_available_time=datetime.combine(
                        trade_date,
                        time(18, 0),
                        tzinfo=timezone.utc,
                    ),
                )
            )
            previous_close = close_price

        return candles

    def get_historical_candles(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyCandle]:
        candles = self.get_daily_candles(symbol)
        if start_date is not None:
            candles = [candle for candle in candles if candle.trade_date >= start_date]
        if end_date is not None:
            candles = [candle for candle in candles if candle.trade_date <= end_date]
        return candles

    def get_latest_candle(self, symbol: str) -> DailyCandle | None:
        candles = self.get_daily_candles(symbol)
        return candles[-1] if candles else None

    def get_latest_snapshots(self, symbols: list[str]) -> list[MarketPriceSnapshot]:
        snapshots: list[MarketPriceSnapshot] = []
        for symbol in symbols:
            normalized_symbol = symbol.upper()
            candle = self.get_latest_candle(normalized_symbol)
            if candle is None:
                continue
            snapshots.append(
                MarketPriceSnapshot(
                    symbol=normalized_symbol,
                    provider=self.provider_name,
                    exchange=self._instruments[normalized_symbol].exchange,
                    provider_symbol=normalized_symbol,
                    instrument_token=None,
                    last_price=candle.close,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                    fetched_at=candle.data_available_time
                    or datetime.combine(candle.trade_date, time(18, 0), tzinfo=timezone.utc),
                    source=f"{self.source}:latest_candle",
                    raw=None,
                )
            )
        return snapshots


def _stable_seed(seed: int, symbol: str) -> int:
    digest = hashlib.sha256(f"{seed}:{symbol}".encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


def _trading_days(start_date: date, count: int) -> list[date]:
    days: list[date] = []
    current = start_date
    while len(days) < count:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def _money(value: float) -> Decimal:
    return Decimal(f"{value:.2f}")
