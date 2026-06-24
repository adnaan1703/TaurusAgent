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


def test_technical_validation_progress_line_includes_symbol_without_coverage() -> None:
    line = format_plain_progress_line(
        "validate-technical-v2",
        "technical_validation.readiness_symbol_completed",
        {
            "symbol": "INFY",
            "current": 12,
            "total": 50,
            "common_candle_count": 282,
            "required_common_candle_count": 1009,
            "selected_scoring_start_date": "2023-01-01",
            "selected_evaluation_end_date": "2026-01-01",
        },
        elapsed_seconds=24,
        eta_seconds=76,
    )

    assert line is not None
    assert "validate-technical-v2" in line
    assert "stage=readiness" in line
    assert "symbol=INFY" in line
    assert "symbols=12/50" in line
    assert "progress=12/50" in line
    assert "percent=24.0" in line
    assert "eta=1m16s" in line
    assert "common_candle_count" not in line
    assert "1009" not in line
    assert "2023-01-01" not in line
    assert "2026-01-01" not in line


def test_technical_validation_profile_progress_uses_short_labels() -> None:
    line = format_plain_progress_line(
        "validate-technical-v2",
        "technical_validation.backtest_profile_completed",
        {
            "profile_name": "graph_aware_score_v2_technical_only",
            "current": 4,
            "total": 4,
        },
        elapsed_seconds=40,
        eta_seconds=0,
    )

    assert line is not None
    assert "stage=backtest" in line
    assert "profile=v2A-tech" in line
    assert "profiles=4/4" in line
    assert "progress=4/4" in line
    assert "eta=0.0s" in line
    assert "graph_aware_score_v2_technical_only" not in line


def test_technical_validation_progress_snapshot_contract_for_harness_reuse() -> None:
    setup = format_rich_progress_snapshot(
        "validate-technical-v2",
        "technical_validation.setup_started",
        {"stage": "migrations"},
    )
    readiness = format_rich_progress_snapshot(
        "validate-technical-v2",
        "technical_validation.readiness_started",
        {"total": 3},
    )
    backtest = format_rich_progress_snapshot(
        "validate-technical-v2",
        "technical_validation.backtest_profile_completed",
        {"profile_name": "graph_aware_score_v1", "current": 1, "total": 4},
    )
    reports = format_rich_progress_snapshot(
        "validate-technical-v2",
        "technical_validation.reports_started",
        {"status": "complete"},
    )
    completed_line = format_plain_progress_line(
        "validate-technical-v2",
        "technical_validation.completed",
        {"status": "complete"},
        elapsed_seconds=125,
        eta_seconds=0,
    )

    assert setup is not None
    assert setup.details == "stage=migrations"
    assert setup.completed == 0
    assert setup.total == 1
    assert readiness is not None
    assert readiness.details == "stage=readiness symbols=0/3"
    assert readiness.completed == 0
    assert readiness.total == 3
    assert backtest is not None
    assert backtest.details == "stage=backtest profile=v1 profiles=1/4"
    assert backtest.completed == 1
    assert backtest.total == 4
    assert reports is not None
    assert reports.details == "stage=reports"
    assert reports.completed == 0
    assert reports.total == 1
    assert completed_line is not None
    assert "stage=complete status=complete" in completed_line
    assert "progress=1/1" in completed_line
    assert "percent=100.0" in completed_line
    assert "elapsed=2m05s" in completed_line
    assert "eta=0.0s" in completed_line


def test_technical_validation_progress_opt_out_suppresses_terminal_output() -> None:
    stream = io.StringIO()

    with create_progress_reporter(
        "validate-technical-v2",
        env={"TAURUS_PROGRESS": "false"},
        stream=stream,
    ) as progress:
        progress(
            "technical_validation.readiness_symbol_completed",
            {"symbol": "INFY", "current": 1, "total": 2},
        )

    assert stream.getvalue() == ""


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
    assert "source=AAA" in output
    assert "target=BBB" in output
    assert "window=60d" in output
    assert "progress=1/3" in output
    assert "edge=peer:AAA:BBB" not in output
    assert "current=1/3" not in output
    assert "validated=1" not in output
    assert "insufficient=0" not in output
    assert "promoted=0" not in output
    assert output.count("\n") == 1


def test_taurus_graph_import_progress_line_includes_file_counts_and_eta() -> None:
    line = format_plain_progress_line(
        "import-taurus-graph",
        "graph.import.file_completed",
        {
            "current": 2,
            "total": 8,
            "source_file": "company_edges.csv",
            "status": "imported",
            "rows_seen": 12,
            "rows_imported": 11,
            "nodes_upserted": 4,
            "edges_upserted": 9,
            "evidence_upserted": 1,
        },
        elapsed_seconds=10,
        eta_seconds=30,
    )

    assert line is not None
    assert "import-taurus-graph" in line
    assert "file=company_edges.csv" in line
    assert "status=imported" in line
    assert "rows_seen=12" in line
    assert "rows_imported=11" in line
    assert "nodes=4" in line
    assert "edges=9" in line
    assert "evidence=1" in line
    assert "progress=2/8" in line
    assert "percent=25.0" in line
    assert "eta=30s" in line


def test_plain_progress_redraws_instead_of_printing_each_event_on_new_line() -> None:
    stream = io.StringIO()

    with create_progress_reporter(
        "import-kite-candles",
        env={"TAURUS_PROGRESS": "plain"},
        stream=stream,
    ) as progress:
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
        progress(
            "import.symbol_completed",
            {
                "symbol": "TCS",
                "current": 2,
                "total": 2,
                "candles": 252,
                "cumulative_candles": 504,
            },
        )

    output = stream.getvalue()
    assert "symbol=INFY" in output
    assert "symbol=TCS" in output
    assert output.count("\n") == 1


def test_plain_progress_failure_does_not_add_extra_close_newline() -> None:
    stream = io.StringIO()

    try:
        with create_progress_reporter(
            "import-kite-candles",
            env={"TAURUS_PROGRESS": "plain"},
            stream=stream,
        ) as progress:
            progress("import.started", {"total": 2})
            raise RuntimeError("provider unavailable")
    except RuntimeError:
        pass

    output = stream.getvalue()
    assert "failed error_type=RuntimeError" in output
    assert output.count("\n") == 1


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
