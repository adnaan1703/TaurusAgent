from __future__ import annotations

import os

from scripts.migrate import run_migrations
from taurus_core.config import Settings, get_settings
from taurus_core.data.importers import MarketDataImportSummary, import_market_data
from taurus_core.data.providers.csv_market_data import CSVMarketDataProvider
from taurus_core.db.session import build_session_factory


def run_import(settings: Settings | None = None) -> MarketDataImportSummary:
    settings = settings or get_settings()
    csv_path = os.environ.get("CSV") or settings.taurus_price_csv_path or None
    directory = os.environ.get("DIR") or settings.taurus_price_csv_dir or None
    run_migrations(settings)
    provider = CSVMarketDataProvider(csv_path=csv_path, directory=directory)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        return import_market_data(session, provider)


if __name__ == "__main__":
    summary = run_import()
    dates = ""
    if summary.start_date is not None and summary.end_date is not None:
        dates = f", dates={summary.start_date.isoformat()}..{summary.end_date.isoformat()}"
    print(
        f"Imported {summary.candle_count} candles for "
        f"{summary.instrument_count} instruments from {summary.source}{dates}."
    )
