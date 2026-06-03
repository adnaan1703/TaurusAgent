from __future__ import annotations

import io

from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.data.importers import import_market_data
from taurus_core.db.session import build_session_factory
from taurus_core.ops.progress import (
    create_progress_reporter,
    format_plain_progress_line,
    format_rich_progress_snapshot,
)
from tests.market_data_fixtures import FakeKiteMarketDataProvider


def test_progress_opt_out_suppresses_terminal_output() -> None:
    stream = io.StringIO()

    with create_progress_reporter(
        "import-kite-candles",
        env={"TAURUS_PROGRESS": "false"},
        stream=stream,
    ) as progress:
        progress("import.started", {"total": 2})
        progress(
            "import.symbol_completed",
            {
                "symbol": "INFY",
                "current": 1,
                "total": 2,
                "candles": 252,
                "cumulative_candles": 252,
            },
        )

    assert stream.getvalue() == ""


def test_plain_and_rich_progress_formatting_include_counts_and_eta() -> None:
    payload = {
        "symbol": "INFY",
        "current": 1,
        "total": 2,
        "candles": 252,
        "cumulative_candles": 252,
    }

    snapshot = format_rich_progress_snapshot(
        "import-kite-candles",
        "import.symbol_completed",
        payload,
    )
    line = format_plain_progress_line(
        "import-kite-candles",
        "import.symbol_completed",
        payload,
        elapsed_seconds=10,
        eta_seconds=10,
    )

    assert snapshot is not None
    assert snapshot.completed == 1
    assert snapshot.total == 2
    assert "symbol=INFY" in snapshot.details
    assert line is not None
    assert "progress=1/2" in line
    assert "percent=50.0" in line
    assert "eta=10s" in line


def test_auto_progress_uses_plain_stderr_for_non_tty_stream() -> None:
    stream = io.StringIO()

    with create_progress_reporter(
        "compute-graph-stats",
        env={"TAURUS_PROGRESS": "auto"},
        stream=stream,
    ) as progress:
        progress(
            "graph.stats.window_completed",
            {
                "current": 1,
                "total": 3,
                "edge_key": "peer:AAA:BBB",
                "source_symbol": "AAA",
                "target_symbol": "BBB",
                "window": "60d",
                "validated_count": 1,
                "insufficient_count": 0,
                "promoted_count": 0,
            },
        )

    output = stream.getvalue()
    assert "compute-graph-stats" in output
    assert "edge=peer:AAA:BBB" in output
    assert "progress=1/3" in output


def test_paper_loop_terminal_progress_prefers_terminal_stage_label() -> None:
    line = format_plain_progress_line(
        "paper-loop",
        "paper.symbol.stage_started",
        {
            "iteration": 1,
            "iterations": 1,
            "symbol_count": 1,
            "run_id": "pr-test",
            "symbol": "INFY",
            "symbol_index": 1,
            "stage": "risk_review",
            "terminal_stage": "risk",
            "succeeded_count": 0,
            "failed_count": 0,
        },
        elapsed_seconds=10,
        eta_seconds=None,
    )

    assert line is not None
    assert "stage=risk" in line
    assert "risk_review" not in line


def test_candle_import_emits_symbol_progress_events(
    postgres_test_settings: Settings,
) -> None:
    settings = postgres_test_settings
    assert settings is not None
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    events: list[tuple[str, dict[str, object]]] = []

    with session_factory() as session:
        summary = import_market_data(
            session,
            FakeKiteMarketDataProvider(),
            progress=lambda event, payload: events.append((event, dict(payload))),
        )

    event_names = [event for event, _payload in events]
    first_completed = next(
        payload for event, payload in events if event == "import.symbol_completed"
    )
    completed = events[-1]

    assert summary.instrument_count == 10
    assert event_names[0] == "import.started"
    assert event_names.count("import.symbol_started") == 10
    assert event_names.count("import.symbol_completed") == 10
    assert first_completed["symbol"] == "RELIANCE"
    assert first_completed["candles"] == 252
    assert first_completed["cumulative_candles"] == 252
    assert completed[0] == "import.completed"
    assert completed[1]["cumulative_candles"] == summary.candle_count
