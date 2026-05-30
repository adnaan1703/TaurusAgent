from __future__ import annotations

from scripts.migrate import run_migrations
from taurus_core.config import get_settings
from taurus_core.position_monitor import PositionMonitorService


def main() -> None:
    settings = get_settings()
    if not settings.taurus_position_monitor_enabled:
        print("Position monitor is disabled.")
        return
    run_migrations(settings)
    results = PositionMonitorService(settings).run()
    if not results:
        print("Position monitor is disabled.")
        return
    latest = results[-1]
    print(
        "Position monitor completed "
        f"{len(results)} iteration(s); latest status={latest.status}, "
        f"run_id={latest.run_id}, proposals_created={latest.proposals_created}, "
        f"quote_failures={latest.quote_failures}."
    )


if __name__ == "__main__":
    main()
