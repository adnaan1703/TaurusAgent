from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.config import Settings, get_settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.session import build_session_factory
from taurus_core.fundamentals import ScreenerImportSummary, import_screener_csv
from taurus_core.logging import configure_logging


def run_import(
    csv_path: str | Path,
    *,
    settings: Settings | None = None,
) -> ScreenerImportSummary:
    settings = settings or get_settings()
    run_migrations(settings)
    provider = MockMarketDataProvider(
        seed=settings.taurus_mock_seed,
        candle_count=settings.taurus_mock_candle_count,
    )
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_mock_data(session, provider)
    with session_factory() as session:
        return import_screener_csv(session, csv_path)


def _csv_path_from_args() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    csv_path = os.environ.get("CSV")
    if csv_path:
        return csv_path
    raise SystemExit("CSV=/path/to/screener.csv is required.")


if __name__ == "__main__":
    configure_logging()
    summary = run_import(_csv_path_from_args())
    print(json.dumps(summary.to_dict(), sort_keys=True))
