from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from scripts import run_paper_loop as run_paper_loop_module
from scripts.run_paper_loop import (
    _format_compact_number,
    _paper_loop_json_enabled,
    _resolve_symbols_from_env,
    format_llm_usage_summary,
)
from taurus_core.config import Settings
from taurus_core.paper_trading.schemas import PaperRunUniverse


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_paper_loop_kite_profile_enables_full_universe_allocated_execution() -> None:
    output = _make_dry_run("paper-loop-kite")

    assert 'TAURUS_MARKET_DATA_PROVIDER="kite"' in output
    assert 'TAURUS_ENABLED_ANALYSTS="technical,graph"' in output
    assert 'TAURUS_GRAPH_ENABLED="true"' in output
    assert 'TAURUS_GRAPH_RISK_ENABLED="true"' in output
    assert 'TAURUS_PAPER_ANALYSIS_SCOPE="full_universe"' in output
    assert 'TAURUS_PAPER_EXECUTION_SCOPE="allocated_only"' in output
    assert 'TAURUS_PROFILE_ID="local-paper"' in output
    assert 'TAURUS_LOG_LEVEL="WARNING"' in output
    assert 'TAURUS_PAPER_LOOP_JSON="false"' in output
    assert 'STRATEGY="configs/strategies/graph_aware_score_v1.yaml"' in output
    assert 'SYMBOL=""' in output
    assert 'SYMBOLS=""' in output


def test_paper_loop_kite_profile_allows_json_override() -> None:
    output = _make_dry_run("paper-loop-kite", "PAPER_LOOP_KITE_JSON=true")

    assert 'TAURUS_PAPER_LOOP_JSON="true"' in output


def test_paper_loop_kite_profile_id_override_sets_runtime_profile() -> None:
    output = _make_dry_run("paper-loop-kite", "PROFILE_ID=client-a")

    assert 'TAURUS_PROFILE_ID="client-a"' in output


def test_paper_loop_kite_profile_allows_log_level_override() -> None:
    output = _make_dry_run("paper-loop-kite", "PAPER_LOOP_KITE_LOG_LEVEL=INFO")

    assert 'TAURUS_LOG_LEVEL="INFO"' in output


def test_paper_loop_kite_profile_uses_makefile_fallback_without_dotenv(
    tmp_path: Path,
) -> None:
    output = _make_dry_run("paper-loop-kite", cwd=tmp_path)

    assert (
        'TAURUS_TARGET_MARKET_UNIVERSE_PATH="configs/market_data/nifty_500_shariah.yaml"'
        in output
    )
    assert 'TAURUS_GRAPH_ENABLED="true"' in output
    assert 'TAURUS_ENABLED_ANALYSTS="technical,graph"' in output


def test_paper_loop_kite_profile_prefers_dotenv_over_makefile_fallback(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "TAURUS_TARGET_MARKET_UNIVERSE_PATH=configs/market_data/nifty_50_shariah.yaml",
                "TAURUS_GRAPH_ENABLED=false",
                "TAURUS_ENABLED_ANALYSTS=technical",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    output = _make_dry_run("paper-loop-kite", cwd=tmp_path)

    assert (
        'TAURUS_TARGET_MARKET_UNIVERSE_PATH="configs/market_data/nifty_50_shariah.yaml"'
        in output
    )
    assert 'TAURUS_GRAPH_ENABLED="false"' in output
    assert 'TAURUS_ENABLED_ANALYSTS="technical"' in output


def test_paper_loop_kite_profile_prefers_command_line_over_dotenv(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "TAURUS_TARGET_MARKET_UNIVERSE_PATH=configs/market_data/nifty_50_shariah.yaml\n",
        encoding="utf-8",
    )

    output = _make_dry_run(
        "paper-loop-kite",
        "TAURUS_TARGET_MARKET_UNIVERSE_PATH=configs/market_data/custom.yaml",
        cwd=tmp_path,
    )

    assert (
        'TAURUS_TARGET_MARKET_UNIVERSE_PATH="configs/market_data/custom.yaml"' in output
    )


def test_paper_loop_kite_profile_prefers_shell_env_over_dotenv(
    tmp_path: Path,
) -> None:
    (tmp_path / ".env").write_text(
        "TAURUS_TARGET_MARKET_UNIVERSE_PATH=configs/market_data/nifty_50_shariah.yaml\n",
        encoding="utf-8",
    )
    env = {
        **os.environ,
        "TAURUS_TARGET_MARKET_UNIVERSE_PATH": "configs/market_data/shell.yaml",
    }

    output = _make_dry_run("paper-loop-kite", cwd=tmp_path, env=env)

    assert (
        'TAURUS_TARGET_MARKET_UNIVERSE_PATH="configs/market_data/shell.yaml"' in output
    )


def test_paper_loop_json_flag_defaults_on_and_accepts_false_values() -> None:
    assert _paper_loop_json_enabled()
    assert _paper_loop_json_enabled("true")
    assert not _paper_loop_json_enabled("false")
    assert not _paper_loop_json_enabled("0")


def test_llm_usage_compact_number_formatting() -> None:
    assert _format_compact_number(1_550_000) == "1.55M"
    assert _format_compact_number(842_000) == "842K"
    assert _format_compact_number(12_400) == "12.4K"
    assert _format_compact_number(950) == "950"
    assert _format_compact_number(None) == "n/a"


def test_format_llm_usage_summary_is_human_readable() -> None:
    summary = format_llm_usage_summary(
        {
            "provider": "lmstudio",
            "profile_id": "client-a",
            "model_versions": ["lmstudio:qwen/qwq-32b"],
            "request_count": 2,
            "input_tokens": 1_550_000,
            "output_tokens": 12_400,
            "total_tokens": 1_562_400,
            "cached_input_tokens": 842_000,
            "reasoning_tokens": None,
            "elapsed_seconds": 10.0,
            "output_tokens_per_second": 1240.0,
            "total_tokens_per_second": 156240.0,
            "by_agent": [
                {
                    "agent_name": "TraderAgent",
                    "request_count": 2,
                    "input_tokens": 1_550_000,
                    "output_tokens": 12_400,
                    "total_tokens": 1_562_400,
                    "output_tokens_per_second": 1240.0,
                }
            ],
        }
    )

    assert "LLM Usage Summary" in summary
    assert "Profile: client-a" in summary
    assert "input 1.55M" in summary
    assert "output 12.4K" in summary
    assert "cached 842K" in summary
    assert "reasoning n/a" in summary
    assert "TraderAgent" in summary


def test_paper_loop_summary_prints_after_progress_context_closes(
    monkeypatch,
) -> None:
    events: list[str] = []

    class FakeProgressContext:
        def __enter__(self):
            events.append("progress_enter")
            return lambda event, payload: None

        def __exit__(self, *args: object) -> bool:
            events.append("progress_exit")
            return False

    def fake_print_llm_usage_summary(payload, *, stream=sys.stderr) -> None:
        events.append("summary_print")
        assert events == ["progress_enter", "progress_exit", "summary_print"]

    monkeypatch.setattr(run_paper_loop_module, "configure_logging", lambda: None)
    monkeypatch.setattr(run_paper_loop_module, "get_settings", lambda: Settings())
    monkeypatch.setattr(
        run_paper_loop_module,
        "_resolve_symbols_from_env",
        lambda settings: run_paper_loop_module.ResolvedPaperLoopSymbols(
            symbols=["INFY"],
            universe=PaperRunUniverse(
                source="manual_symbols",
                provider="kite",
                selected_symbol_count=1,
                symbols=["INFY"],
            ),
        ),
    )
    monkeypatch.setattr(
        run_paper_loop_module,
        "create_progress_reporter",
        lambda command: FakeProgressContext(),
    )
    monkeypatch.setattr(
        run_paper_loop_module,
        "run_paper_loop",
        lambda **kwargs: [
            {
                "artifacts": {
                    "llm_usage": {
                        "request_count": 1,
                        "input_tokens": 1000,
                        "output_tokens": 250,
                        "total_tokens": 1250,
                        "elapsed_seconds": 0.5,
                        "by_agent": [],
                    }
                }
            }
        ],
    )
    monkeypatch.setattr(
        run_paper_loop_module,
        "print_llm_usage_summary",
        fake_print_llm_usage_summary,
    )
    monkeypatch.setenv("TAURUS_PAPER_LOOP_JSON", "false")

    run_paper_loop_module.main()

    assert events == ["progress_enter", "progress_exit", "summary_print"]


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


def test_paper_loop_kite_profile_passes_manual_symbols_without_universe_expansion() -> (
    None
):
    output = _make_dry_run("paper-loop-kite", "SYMBOLS=INFY,TCS")

    assert 'SYMBOL=""' in output
    assert 'SYMBOLS="INFY,TCS"' in output
    assert 'TAURUS_PAPER_ANALYSIS_SCOPE="full_universe"' in output


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


def test_manual_env_resolution_does_not_require_target_universe_outside_pytest() -> (
    None
):
    script = """
import json

from scripts.run_paper_loop import _resolve_symbols_from_env
from taurus_core.config import Settings

resolved = _resolve_symbols_from_env(Settings(taurus_target_market_universe_path=""))
print(json.dumps({"symbols": resolved.symbols, "source": resolved.universe.source}))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env={
            "PYTHONPATH": "packages:.",
            "SYMBOL": "",
            "SYMBOLS": "infy,tcs",
            "TAURUS_TARGET_MARKET_UNIVERSE_PATH": "",
        },
        capture_output=True,
        check=True,
        text=True,
    )

    assert json.loads(result.stdout) == {
        "symbols": ["INFY", "TCS"],
        "source": "manual_symbols",
    }


def test_default_env_resolution_requires_target_universe_outside_pytest() -> None:
    script = """
from scripts.run_paper_loop import _resolve_symbols_from_env
from taurus_core.config import Settings

_resolve_symbols_from_env(Settings(taurus_target_market_universe_path=""))
"""

    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PROJECT_ROOT,
        env={
            "PYTHONPATH": "packages:.",
            "SYMBOL": "",
            "SYMBOLS": "",
            "TAURUS_TARGET_MARKET_UNIVERSE_PATH": "",
        },
        capture_output=True,
        check=False,
        text=True,
    )

    assert result.returncode != 0
    assert (
        "TAURUS_TARGET_MARKET_UNIVERSE_PATH must be set for paper loop execution."
        in result.stderr
    )


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


def _make_dry_run(
    *args: str,
    cwd: Path = PROJECT_ROOT,
    env: dict[str, str] | None = None,
) -> str:
    result = subprocess.run(
        ["make", "-f", str(PROJECT_ROOT / "Makefile"), "-n", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        check=True,
        text=True,
    )
    return result.stdout
