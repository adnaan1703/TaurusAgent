from __future__ import annotations

from scripts.migrate import run_migrations
from taurus_core.config import Settings, get_settings
from taurus_core.data.providers.kite_market_data import KiteMarketDataProvider, KiteInstrumentSyncSummary
from taurus_core.db.session import build_session_factory


def run_sync(settings: Settings | None = None) -> KiteInstrumentSyncSummary:
    settings = settings or get_settings()
    run_migrations(settings)
    provider = KiteMarketDataProvider(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        return provider.sync_instruments(session)


if __name__ == "__main__":
    summary = run_sync()
    print(
        "Synced "
        f"{summary.instrument_count} Kite instrument mappings "
        f"from {summary.universe_path}: {', '.join(summary.symbols)}"
    )
