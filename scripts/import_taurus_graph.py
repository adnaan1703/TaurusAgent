from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from scripts.migrate import run_migrations
from taurus_core.config import Settings, get_settings
from taurus_core.db.session import build_session_factory
from taurus_core.graph import TaurusGraphImportSummary, import_taurus_graph_csvs
from taurus_core.logging import configure_logging


def run_import(
    data_dir: str | Path = "configs/taurus_data",
    *,
    settings: Settings | None = None,
) -> TaurusGraphImportSummary:
    settings = settings or get_settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        return import_taurus_graph_csvs(session, data_dir=data_dir)


def _data_dir_from_args() -> str:
    if len(sys.argv) > 1:
        return sys.argv[1]
    return os.environ.get("DATA_DIR", "configs/taurus_data")


if __name__ == "__main__":
    configure_logging()
    summary = run_import(_data_dir_from_args())
    print(json.dumps(summary.to_dict(), sort_keys=True))
