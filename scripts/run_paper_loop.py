from __future__ import annotations

import json
import os
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import TextIO

from taurus_core.config import Settings, get_settings
from taurus_core.data.universe import load_market_data_universe
from taurus_core.llm.base import aggregate_llm_usage_summaries
from taurus_core.logging import configure_logging
from taurus_core.ops.progress import ProgressEventCallback, create_progress_reporter
from taurus_core.paper_trading.schemas import PaperRunUniverse
from taurus_core.paper_trading.service import PaperRunService, SimplePaperScheduler


@dataclass(frozen=True, slots=True)
class ResolvedPaperLoopSymbols:
    symbols: list[str]
    universe: PaperRunUniverse


def run_paper_loop(
    *,
    symbols: list[str],
    settings: Settings | None = None,
    iterations: int = 1,
    interval_seconds: float = 0,
    universe: PaperRunUniverse | None = None,
    strategy_config_path: str | None = None,
    progress: ProgressEventCallback | None = None,
) -> list[dict[str, object]]:
    settings = settings or get_settings()
    service = PaperRunService(
        settings,
        schedule_name=settings.taurus_paper_schedule,
        timezone_name=settings.taurus_paper_timezone,
        run_after_market_close=settings.taurus_paper_after_market_close,
        progress=progress,
    )
    scheduler = SimplePaperScheduler(
        service,
        symbols=symbols,
        iterations=iterations,
        interval_seconds=interval_seconds,
        universe=universe,
        strategy_config_path=strategy_config_path,
        progress=progress,
    )
    return [run.model_dump(mode="json") for run in scheduler.run()]


def run_mock_paper_loop(
    *,
    symbol: str,
    iterations: int = 1,
    interval_seconds: float = 0,
) -> list[dict[str, object]]:
    return run_paper_loop(
        symbols=[symbol],
        iterations=iterations,
        interval_seconds=interval_seconds,
    )


def _symbols_from_env(settings: Settings) -> list[str]:
    return _resolve_symbols_from_env(settings).symbols


def _resolve_symbols_from_env(settings: Settings) -> ResolvedPaperLoopSymbols:
    raw = _non_empty_env("SYMBOLS") or _non_empty_env("SYMBOL")
    if raw is None:
        universe = load_market_data_universe(settings.taurus_market_data_universe_path)
        symbols = universe.enabled_symbols()
        return ResolvedPaperLoopSymbols(
            symbols=symbols,
            universe=PaperRunUniverse(
                source="market_data_universe",
                provider=settings.taurus_market_data_provider,
                universe_name=universe.universe_name,
                yaml_path=str(universe.source_path),
                available_symbol_count=len(universe.symbols),
                selected_symbol_count=len(symbols),
                symbols=symbols,
            ),
        )
    raw = raw or "INFY"
    symbols = [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]
    if not symbols:
        symbols = ["INFY"]
    return ResolvedPaperLoopSymbols(
        symbols=symbols,
        universe=PaperRunUniverse(
            source="manual_symbols",
            provider=settings.taurus_market_data_provider,
            selected_symbol_count=len(symbols),
            symbols=symbols,
        ),
    )


def _non_empty_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None or not value.strip():
        return None
    return value


def _progress_command_from_env() -> str:
    provider = os.environ.get("TAURUS_MARKET_DATA_PROVIDER", "").strip().lower()
    graph_enabled = os.environ.get("TAURUS_GRAPH_ENABLED", "").strip().lower()
    if provider == "kite" and graph_enabled in {"1", "true", "yes", "on"}:
        return "paper-loop-kite"
    return "paper-loop"


def _paper_loop_json_enabled(value: str | None = None) -> bool:
    raw = os.environ.get("TAURUS_PAPER_LOOP_JSON", "true") if value is None else value
    return raw.strip().lower() not in {"0", "false", "no", "off", "none", "disabled"}


def llm_usage_summary_from_runs(runs: Iterable[Mapping[str, object]]) -> dict[str, object]:
    summaries: list[Mapping[str, object]] = []
    for run in runs:
        artifacts = run.get("artifacts")
        if not isinstance(artifacts, Mapping):
            continue
        llm_usage = artifacts.get("llm_usage")
        if isinstance(llm_usage, Mapping):
            summaries.append(llm_usage)
    return aggregate_llm_usage_summaries(summaries)


def format_llm_usage_summary(summary: Mapping[str, object]) -> str:
    lines = [
        "LLM Usage Summary",
        "-----------------",
    ]
    request_count = _int_value(summary.get("request_count")) or 0
    if request_count <= 0:
        lines.extend(
            [
                "No successful LLM usage records captured.",
                "Tokens: input n/a | output n/a | total n/a | cached n/a | reasoning n/a",
            ]
        )
        return "\n".join(lines)

    provider = str(summary.get("provider") or "n/a")
    model_versions = _display_list(summary.get("model_versions"))
    lines.extend(
        [
            f"Provider: {provider} | Models: {model_versions}",
            (
                f"Requests: {_format_compact_number(request_count)} | "
                f"LLM elapsed: {_format_duration(summary.get('elapsed_seconds'))}"
            ),
            (
                "Tokens: "
                f"input {_format_compact_number(summary.get('input_tokens'))} | "
                f"output {_format_compact_number(summary.get('output_tokens'))} | "
                f"total {_format_compact_number(summary.get('total_tokens'))} | "
                f"cached {_format_compact_number(summary.get('cached_input_tokens'))} | "
                f"reasoning {_format_compact_number(summary.get('reasoning_tokens'))}"
            ),
            (
                "Speed: "
                f"output {_format_rate(summary.get('output_tokens_per_second'))} | "
                f"total {_format_rate(summary.get('total_tokens_per_second'))}"
            ),
        ]
    )

    by_agent = [row for row in _list_value(summary.get("by_agent")) if isinstance(row, Mapping)]
    if by_agent:
        lines.extend(["", "By agent:"])
        agent_width = max(
            len("Agent"),
            *(len(str(row.get("agent_name") or "n/a")) for row in by_agent),
        )
        header = _agent_usage_row(
            "Agent",
            "Requests",
            "Input",
            "Output",
            "Total",
            "Out/s",
            agent_width=agent_width,
        )
        lines.append(header)
        lines.append("-" * len(header))
        for row in by_agent:
            lines.append(
                _agent_usage_row(
                    str(row.get("agent_name") or "n/a"),
                    _format_compact_number(row.get("request_count")),
                    _format_compact_number(row.get("input_tokens")),
                    _format_compact_number(row.get("output_tokens")),
                    _format_compact_number(row.get("total_tokens")),
                    _format_rate(row.get("output_tokens_per_second")),
                    agent_width=agent_width,
                )
            )
    return "\n".join(lines)


def print_llm_usage_summary(
    runs: Iterable[Mapping[str, object]],
    *,
    stream: TextIO = sys.stderr,
) -> None:
    stream.write(format_llm_usage_summary(llm_usage_summary_from_runs(runs)))
    stream.write("\n")
    stream.flush()


def _agent_usage_row(
    agent: str,
    requests: str,
    input_tokens: str,
    output_tokens: str,
    total_tokens: str,
    output_rate: str,
    *,
    agent_width: int,
) -> str:
    return (
        f"{agent:<{agent_width}}  "
        f"{requests:>8}  "
        f"{input_tokens:>8}  "
        f"{output_tokens:>8}  "
        f"{total_tokens:>8}  "
        f"{output_rate:>8}"
    )


def _format_compact_number(value: object) -> str:
    number = _float_value(value)
    if number is None:
        return "n/a"
    absolute = abs(number)
    if absolute < 1000:
        return _trim_number(number, decimals=1 if not number.is_integer() else 0)
    for divisor, suffix in (
        (1_000_000_000_000, "T"),
        (1_000_000_000, "B"),
        (1_000_000, "M"),
        (1_000, "K"),
    ):
        if absolute >= divisor:
            scaled = number / divisor
            if abs(scaled) >= 100:
                decimals = 0
            elif abs(scaled) >= 10:
                decimals = 1
            else:
                decimals = 2
            return f"{_trim_number(scaled, decimals=decimals)}{suffix}"
    return _trim_number(number, decimals=0)


def _format_rate(value: object) -> str:
    formatted = _format_compact_number(value)
    return "n/a" if formatted == "n/a" else f"{formatted}/s"


def _format_duration(value: object) -> str:
    seconds = _float_value(value)
    if seconds is None:
        return "n/a"
    if seconds < 60:
        return f"{_trim_number(seconds, decimals=1)}s"
    minutes, remaining_seconds = divmod(int(round(seconds)), 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{remaining_seconds:02d}s"
    return f"{minutes}m{remaining_seconds:02d}s"


def _trim_number(value: float, *, decimals: int) -> str:
    if decimals <= 0:
        return str(int(round(value)))
    return f"{value:.{decimals}f}".rstrip("0").rstrip(".")


def _display_list(value: object) -> str:
    items = [str(item) for item in _list_value(value) if str(item)]
    if not items:
        return "n/a"
    if len(items) <= 2:
        return ", ".join(items)
    return f"{', '.join(items[:2])}, +{len(items) - 2} more"


def _int_value(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _float_value(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _list_value(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def main() -> None:
    configure_logging()
    settings = get_settings()
    resolved = _resolve_symbols_from_env(settings)
    iterations = int(os.environ.get("PAPER_LOOP_ITERATIONS", "1"))
    interval_seconds = float(os.environ.get("PAPER_LOOP_INTERVAL_SECONDS", "0"))
    with create_progress_reporter(_progress_command_from_env()) as progress:
        payload = run_paper_loop(
            symbols=resolved.symbols,
            settings=settings,
            iterations=iterations,
            interval_seconds=interval_seconds,
            universe=resolved.universe,
            strategy_config_path=os.environ.get("STRATEGY") or None,
            progress=progress,
        )
    print_llm_usage_summary(payload)
    if _paper_loop_json_enabled():
        print(
            json.dumps(
                {
                    "symbols": resolved.symbols,
                    "universe": resolved.universe.model_dump(mode="json"),
                    "runs": payload,
                },
                sort_keys=True,
            )
        )


if __name__ == "__main__":
    main()
