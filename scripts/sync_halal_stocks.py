from __future__ import annotations

import json

from scripts.migrate import run_migrations
from taurus_core.compliance import HalalStockSyncSummary, sync_halal_stocks
from taurus_core.config import Settings, get_settings
from taurus_core.logging import configure_logging


def run_sync(settings: Settings | None = None) -> HalalStockSyncSummary:
    settings = settings or get_settings()
    run_migrations(settings)
    return sync_halal_stocks(settings=settings)


if __name__ == "__main__":
    configure_logging()
    summary = run_sync()
    print(json.dumps(summary.to_dict(), sort_keys=True))
