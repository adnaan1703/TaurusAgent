from __future__ import annotations

import json
import os
from dataclasses import dataclass

from taurus_core.config import Settings, get_settings
from taurus_core.data.universe import load_market_data_universe
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


if __name__ == "__main__":
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
