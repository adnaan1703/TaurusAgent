from __future__ import annotations

from scripts.migrate import run_migrations
from taurus_core.config import get_settings
from taurus_core.db.session import build_session_factory
from taurus_core.position_monitor import PositionMonitorService
from taurus_core.profiles.runtime import resolve_runtime_profile


def main() -> None:
    settings = get_settings()
    if not settings.taurus_position_monitor_enabled:
        print("Position monitor is disabled.")
        return
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        runtime_profile = resolve_runtime_profile(session, settings)
    print(
        "Position monitor profile "
        f"profile_id={runtime_profile.profile_id} "
        f"starting_corpus_inr={runtime_profile.starting_corpus_inr}."
    )
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
