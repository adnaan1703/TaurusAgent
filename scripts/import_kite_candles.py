from __future__ import annotations

from scripts.migrate import run_migrations
from taurus_core.config import Settings, get_settings
from taurus_core.data.importers import MarketDataImportSummary, import_market_data
from taurus_core.data.providers.kite_market_data import KiteMarketDataProvider
from taurus_core.db.session import build_session_factory
from taurus_core.ops.progress import (
    ProgressEventCallback,
    create_progress_reporter,
    emit_progress,
)


def run_import(
    settings: Settings | None = None,
    *,
    progress: ProgressEventCallback | None = None,
) -> MarketDataImportSummary:
    settings = settings or get_settings()
    emit_progress(progress, "import.setup_started", stage="migrations")
    run_migrations(settings)
    provider = KiteMarketDataProvider(settings)
    session_factory = build_session_factory(settings)
    emit_progress(progress, "import.setup_started", stage="sync_instruments")
    with session_factory() as session:
        provider.sync_instruments(session)
    with session_factory() as session:
        return import_market_data(session, provider, progress=progress)


if __name__ == "__main__":
    with create_progress_reporter("import-kite-candles") as progress:
        summary = run_import(progress=progress)
    dates = ""
    if summary.start_date is not None and summary.end_date is not None:
        dates = f", dates={summary.start_date.isoformat()}..{summary.end_date.isoformat()}"
    print(
        f"Imported {summary.candle_count} Kite candles for "
        f"{summary.instrument_count} instruments from {summary.source}{dates}."
    )
