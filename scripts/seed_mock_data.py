from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from scripts.migrate import run_migrations
from taurus_core.config import Settings, get_settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.repositories import CandleRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.market_data import MarketDataProvider


@dataclass(frozen=True, slots=True)
class SeedSummary:
    instrument_count: int
    candle_count: int
    candles_per_symbol: dict[str, int]


def seed_mock_data(session: Session, provider: MarketDataProvider) -> SeedSummary:
    instrument_repo = InstrumentRepository(session)
    candle_repo = CandleRepository(session)
    instruments = provider.list_instruments()

    for instrument in instruments:
        instrument_repo.upsert(instrument)

    candles_per_symbol: dict[str, int] = {}
    for instrument in instruments:
        candles = provider.get_daily_candles(instrument.symbol)
        candle_repo.upsert(candles)
        candles_per_symbol[instrument.symbol] = len(candles)

    session.commit()
    return SeedSummary(
        instrument_count=len(instruments),
        candle_count=sum(candles_per_symbol.values()),
        candles_per_symbol=candles_per_symbol,
    )


def run_seed(settings: Settings | None = None) -> SeedSummary:
    settings = settings or get_settings()
    run_migrations(settings)
    provider = MockMarketDataProvider(
        seed=settings.taurus_mock_seed,
        candle_count=settings.taurus_mock_candle_count,
    )
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        return seed_mock_data(session, provider)


if __name__ == "__main__":
    summary = run_seed()
    print(
        "Seeded "
        f"{summary.instrument_count} instruments and "
        f"{summary.candle_count} daily candles."
    )
