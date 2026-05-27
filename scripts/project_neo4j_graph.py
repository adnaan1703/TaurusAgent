from __future__ import annotations

import json

from taurus_core.config import get_settings
from taurus_core.db.session import build_session_factory
from taurus_core.graph import rebuild_neo4j_projection
from taurus_core.logging import configure_logging


def run_projection() -> dict[str, object]:
    settings = get_settings()
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        summary = rebuild_neo4j_projection(session, settings=settings)
        return summary.to_dict()


if __name__ == "__main__":
    configure_logging()
    print(json.dumps(run_projection(), sort_keys=True))
