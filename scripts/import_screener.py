from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from scripts.migrate import run_migrations
from taurus_core.config import Settings, get_settings
from taurus_core.data.preflight import assert_active_instruments_available
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
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        assert_active_instruments_available(session)
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
