from __future__ import annotations

from dataclasses import dataclass

from scripts.migrate import run_migrations
from taurus_core.config import Settings, get_settings
from taurus_core.data.providers.kite_market_data import KiteMarketDataProvider
from taurus_core.db.repositories import MarketPriceSnapshotRepository
from taurus_core.db.session import build_session_factory


@dataclass(frozen=True, slots=True)
class KiteLTPSmokeSummary:
    provider_name: str
    source: str
    snapshot_count: int
    symbols: list[str]


def run_smoke(settings: Settings | None = None) -> KiteLTPSmokeSummary:
    settings = settings or get_settings()
    run_migrations(settings)
    provider = KiteMarketDataProvider(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        provider.sync_instruments(session)
    symbols = provider.universe.enabled_symbols()
    snapshots = provider.get_latest_snapshots(symbols)
    with session_factory() as session:
        MarketPriceSnapshotRepository(session).insert_many(snapshots)
        session.commit()
    return KiteLTPSmokeSummary(
        provider_name=provider.provider_name,
        source="kite:quote",
        snapshot_count=len(snapshots),
        symbols=[snapshot.symbol for snapshot in snapshots],
    )


if __name__ == "__main__":
    summary = run_smoke()
    print(
        f"Stored {summary.snapshot_count} Kite quote snapshots "
        f"for {', '.join(summary.symbols)}."
    )
