from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from taurus_core.data.preflight import assert_no_legacy_mock_candles
from taurus_core.db.repositories import CandleRepository, InstrumentRepository
from taurus_core.domain.market_data import MarketDataProvider
from taurus_core.ops.progress import ProgressEventCallback, emit_progress


@dataclass(frozen=True, slots=True)
class MarketDataImportSummary:
    provider_name: str
    source: str
    instrument_count: int
    candle_count: int
    candles_per_symbol: dict[str, int]
    start_date: date | None
    end_date: date | None


def import_market_data(
    session: Session,
    provider: MarketDataProvider,
    *,
    progress: ProgressEventCallback | None = None,
) -> MarketDataImportSummary:
    if provider.provider_name == "kite":
        assert_no_legacy_mock_candles(session)

    instrument_repo = InstrumentRepository(session)
    candle_repo = CandleRepository(session)
    instruments = provider.list_instruments()
    emit_progress(progress, "import.started", total=len(instruments))

    for instrument in instruments:
        instrument_repo.upsert(instrument)

    candles_per_symbol: dict[str, int] = {}
    all_dates: list[date] = []
    cumulative_candles = 0
    for index, instrument in enumerate(instruments, start=1):
        emit_progress(
            progress,
            "import.symbol_started",
            symbol=instrument.symbol,
            current=index,
            total=len(instruments),
            candles=0,
            cumulative_candles=cumulative_candles,
        )
        candles = provider.get_daily_candles(instrument.symbol)
        candle_repo.upsert(candles)
        candles_per_symbol[instrument.symbol] = len(candles)
        all_dates.extend(candle.trade_date for candle in candles)
        cumulative_candles += len(candles)
        emit_progress(
            progress,
            "import.symbol_completed",
            symbol=instrument.symbol,
            current=index,
            total=len(instruments),
            candles=len(candles),
            cumulative_candles=cumulative_candles,
        )

    session.commit()
    emit_progress(
        progress,
        "import.completed",
        total=len(instruments),
        cumulative_candles=sum(candles_per_symbol.values()),
    )
    return MarketDataImportSummary(
        provider_name=provider.provider_name,
        source=provider.source,
        instrument_count=len(instruments),
        candle_count=sum(candles_per_symbol.values()),
        candles_per_symbol=candles_per_symbol,
        start_date=min(all_dates) if all_dates else None,
        end_date=max(all_dates) if all_dates else None,
    )
