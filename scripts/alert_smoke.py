from __future__ import annotations

import json
import os

from scripts.migrate import run_migrations
from taurus_core.alerts.service import AlertService, build_alert_adapter
from taurus_core.alerts.templates import alert_smoke_test_event
from taurus_core.config import Settings, get_settings
from taurus_core.db.session import build_session_factory
from taurus_core.logging import configure_logging


def send_alert_smoke(settings: Settings | None = None) -> dict[str, object]:
    settings = settings or get_settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        event = alert_smoke_test_event(run_id=os.environ.get("RUN_ID", "alert-smoke"))
        result = AlertService(session, settings, adapter=build_alert_adapter(settings)).send(event)
        return {
            "event": event.model_dump(mode="json"),
            "delivery": result.model_dump(mode="json"),
        }


if __name__ == "__main__":
    configure_logging()
    print(json.dumps(send_alert_smoke(), sort_keys=True))
