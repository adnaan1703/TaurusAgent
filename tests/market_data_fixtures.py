from __future__ import annotations

import hashlib
import random
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.db.repositories import CandleRepository, InstrumentRepository
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle

TEST_MARKET_DATA_SOURCE = "test_market_data_fixture"

TEST_INSTRUMENTS: tuple[Instrument, ...] = (
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


class FakeKiteMarketDataProvider:
    provider_name = "kite"
    source = "kite:test_fixture"

    def list_instruments(self) -> list[Instrument]:
        return list(TEST_INSTRUMENTS)

    def get_daily_candles(self, symbol: str) -> list[DailyCandle]:
        symbols = [instrument.symbol for instrument in TEST_INSTRUMENTS]
        symbol_index = symbols.index(symbol.upper())
        return build_test_candles_for_symbol(
            symbol=symbol.upper(),
            symbol_index=symbol_index,
            candle_count=252,
            source="kite:historical:NSE",
        )

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


def seed_test_market_data(
    session: Session,
    *,
    candle_count: int = 252,
    source: str = TEST_MARKET_DATA_SOURCE,
) -> None:
    instrument_repo = InstrumentRepository(session)
    candle_repo = CandleRepository(session)
    for instrument in TEST_INSTRUMENTS:
        instrument_repo.upsert(instrument)
    for index, instrument in enumerate(TEST_INSTRUMENTS):
        candle_repo.upsert(
            build_test_candles_for_symbol(
                symbol=instrument.symbol,
                symbol_index=index,
                candle_count=candle_count,
                source=source,
            )
        )
    session.commit()


def build_test_candles_for_symbol(
    *,
    symbol: str,
    symbol_index: int,
    candle_count: int,
    source: str,
) -> list[DailyCandle]:
    rng = random.Random(_stable_seed(42, symbol))
    base_price = 120.0 + (symbol_index * 85.0) + rng.uniform(-15.0, 15.0)
    base_volume = 700_000 + (symbol_index * 175_000)
    previous_close = base_price
    candles: list[DailyCandle] = []
    for trade_date in _trading_days(date(2024, 1, 1), candle_count):
        open_price = max(10.0, previous_close * (1 + rng.uniform(-0.012, 0.012)))
        close_price = max(10.0, open_price * (1 + rng.gauss(0.0006, 0.018)))
        high_price = max(open_price, close_price) * (1 + rng.uniform(0.001, 0.022))
        low_price = min(open_price, close_price) * (1 - rng.uniform(0.001, 0.022))
        candles.append(
            DailyCandle(
                symbol=symbol,
                trade_date=trade_date,
                open=_money(open_price),
                high=_money(high_price),
                low=_money(low_price),
                close=_money(close_price),
                volume=int(base_volume * rng.uniform(0.75, 1.45)),
                source=source,
                data_available_time=datetime.combine(trade_date, time(18, 0), tzinfo=timezone.utc),
            )
        )
        previous_close = close_price
    return candles


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
