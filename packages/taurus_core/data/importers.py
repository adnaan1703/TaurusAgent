from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from taurus_core.db.repositories import CandleRepository, InstrumentRepository
from taurus_core.domain.market_data import MarketDataProvider


@dataclass(frozen=True, slots=True)
class MarketDataImportSummary:
    provider_name: str
    source: str
    instrument_count: int
    candle_count: int
    candles_per_symbol: dict[str, int]
    start_date: date | None
    end_date: date | None


def import_market_data(session: Session, provider: MarketDataProvider) -> MarketDataImportSummary:
    instrument_repo = InstrumentRepository(session)
    candle_repo = CandleRepository(session)
    instruments = provider.list_instruments()

    for instrument in instruments:
        instrument_repo.upsert(instrument)

    candles_per_symbol: dict[str, int] = {}
    all_dates: list[date] = []
    for instrument in instruments:
        candles = provider.get_daily_candles(instrument.symbol)
        candle_repo.upsert(candles)
        candles_per_symbol[instrument.symbol] = len(candles)
        all_dates.extend(candle.trade_date for candle in candles)

    session.commit()
    return MarketDataImportSummary(
        provider_name=provider.provider_name,
        source=provider.source,
        instrument_count=len(instruments),
        candle_count=sum(candles_per_symbol.values()),
        candles_per_symbol=candles_per_symbol,
        start_date=min(all_dates) if all_dates else None,
        end_date=max(all_dates) if all_dates else None,
    )
