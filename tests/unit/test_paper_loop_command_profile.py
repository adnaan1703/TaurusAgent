from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from scripts.run_paper_loop import _paper_loop_json_enabled, _resolve_symbols_from_env
from taurus_core.config import Settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_paper_loop_kite_profile_enables_full_universe_allocated_execution() -> None:
    output = _make_dry_run("paper-loop-kite")

    assert "TAURUS_MARKET_DATA_PROVIDER=kite" in output
    assert "TAURUS_ENABLED_ANALYSTS=technical,graph" in output
    assert "TAURUS_GRAPH_ENABLED=true" in output
    assert "TAURUS_GRAPH_RISK_ENABLED=true" in output
    assert "TAURUS_PAPER_ANALYSIS_SCOPE=full_universe" in output
    assert "TAURUS_PAPER_EXECUTION_SCOPE=allocated_only" in output
    assert 'TAURUS_LOG_LEVEL="WARNING"' in output
    assert 'TAURUS_PAPER_LOOP_JSON="false"' in output
    assert "STRATEGY=configs/strategies/graph_aware_score_v1.yaml" in output
    assert 'SYMBOL=""' in output
    assert 'SYMBOLS=""' in output


def test_paper_loop_kite_profile_allows_json_override() -> None:
    output = _make_dry_run("paper-loop-kite", "PAPER_LOOP_KITE_JSON=true")

    assert 'TAURUS_PAPER_LOOP_JSON="true"' in output


def test_paper_loop_kite_profile_allows_log_level_override() -> None:
    output = _make_dry_run("paper-loop-kite", "PAPER_LOOP_KITE_LOG_LEVEL=INFO")

    assert 'TAURUS_LOG_LEVEL="INFO"' in output


def test_paper_loop_json_flag_defaults_on_and_accepts_false_values() -> None:
    assert _paper_loop_json_enabled()
    assert _paper_loop_json_enabled("true")
    assert not _paper_loop_json_enabled("false")
    assert not _paper_loop_json_enabled("0")


def test_taurus_log_level_warning_suppresses_info_json_logs() -> None:
    script = """
from taurus_core.logging import configure_logging, get_logger

configure_logging()
logger = get_logger("test.paper_loop_logs")
logger.info("paper_run.symbol.started", symbol="INFY")
logger.warning("paper_run.warning", symbol="INFY")
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env={"PYTHONPATH": "packages:.", "TAURUS_LOG_LEVEL": "WARNING"},
        capture_output=True,
        check=True,
        text=True,
    )

    assert "paper_run.symbol.started" not in result.stdout
    assert "paper_run.warning" in result.stdout


def test_paper_loop_kite_profile_passes_manual_symbols_without_universe_expansion() -> None:
    output = _make_dry_run("paper-loop-kite", "SYMBOLS=INFY,TCS")

    assert 'SYMBOL=""' in output
    assert 'SYMBOLS="INFY,TCS"' in output
    assert "TAURUS_PAPER_ANALYSIS_SCOPE=full_universe" in output


def test_full_universe_manual_env_resolution_stays_explicit(
    monkeypatch,
) -> None:
    monkeypatch.setenv("SYMBOL", "")
    monkeypatch.setenv("SYMBOLS", "infy,tcs")
    settings = Settings(
        taurus_paper_analysis_scope="full_universe",
        taurus_paper_execution_scope="allocated_only",
    )

    resolved = _resolve_symbols_from_env(settings)

    assert resolved.symbols == ["INFY", "TCS"]
    assert resolved.universe.source == "manual_symbols"
    assert resolved.universe.symbols == ["INFY", "TCS"]


def test_full_universe_default_env_resolution_uses_market_data_universe(
    monkeypatch,
) -> None:
    monkeypatch.delenv("SYMBOL", raising=False)
    monkeypatch.delenv("SYMBOLS", raising=False)
    settings = Settings(
        taurus_paper_analysis_scope="full_universe",
        taurus_paper_execution_scope="allocated_only",
    )

    resolved = _resolve_symbols_from_env(settings)

    assert resolved.universe.source == "market_data_universe"
    assert resolved.symbols == resolved.universe.symbols
    assert resolved.universe.selected_symbol_count == len(resolved.symbols)
    assert resolved.universe.available_symbol_count is not None
    assert resolved.universe.available_symbol_count >= len(resolved.symbols)


def _make_dry_run(*args: str) -> str:
    result = subprocess.run(
        ["make", "-n", *args],
        cwd=PROJECT_ROOT,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout
