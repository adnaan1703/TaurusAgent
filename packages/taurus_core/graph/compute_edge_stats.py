from __future__ import annotations

import argparse
import json
from datetime import date

from scripts.migrate import run_migrations
from taurus_core.config import Settings, get_settings
from taurus_core.db.session import build_session_factory
from taurus_core.graph.stats import GraphStatsSummary, compute_graph_edge_stats
from taurus_core.logging import configure_logging


def run_compute_edge_stats(
    *,
    as_of_date: date | None = None,
    settings: Settings | None = None,
) -> GraphStatsSummary:
    settings = settings or get_settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        return compute_graph_edge_stats(
            session,
            settings=settings,
            as_of_date=as_of_date,
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute Taurus graph edge statistics.")
    parser.add_argument(
        "--as-of",
        dest="as_of",
        default=None,
        help="As-of date in YYYY-MM-DD format. Defaults to the latest candle date.",
    )
    return parser.parse_args()


def _parse_as_of(value: str | None) -> date | None:
    if value is None or not value.strip():
        return None
    return date.fromisoformat(value)


if __name__ == "__main__":
    configure_logging()
    args = _parse_args()
    summary = run_compute_edge_stats(as_of_date=_parse_as_of(args.as_of))
    print(json.dumps(summary.to_dict(include_results=False), sort_keys=True))
