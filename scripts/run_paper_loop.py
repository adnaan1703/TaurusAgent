from __future__ import annotations

import json
import os
from dataclasses import dataclass

from taurus_core.config import Settings, get_settings
from taurus_core.data.universe import load_market_data_universe
from taurus_core.logging import configure_logging
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
    csv_path: str | None = None,
    directory: str | None = None,
    strategy_config_path: str | None = None,
) -> list[dict[str, object]]:
    settings = settings or get_settings()
    service = PaperRunService(
        settings,
        schedule_name=settings.taurus_paper_schedule,
        timezone_name=settings.taurus_paper_timezone,
        run_after_market_close=settings.taurus_paper_after_market_close,
    )
    scheduler = SimplePaperScheduler(
        service,
        symbols=symbols,
        iterations=iterations,
        interval_seconds=interval_seconds,
        universe=universe,
        csv_path=csv_path,
        directory=directory,
        strategy_config_path=strategy_config_path,
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
    if raw is None and settings.taurus_market_data_provider == "kite":
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


if __name__ == "__main__":
    configure_logging()
    settings = get_settings()
    resolved = _resolve_symbols_from_env(settings)
    iterations = int(os.environ.get("PAPER_LOOP_ITERATIONS", "1"))
    interval_seconds = float(os.environ.get("PAPER_LOOP_INTERVAL_SECONDS", "0"))
    payload = run_paper_loop(
        symbols=resolved.symbols,
        settings=settings,
        iterations=iterations,
        interval_seconds=interval_seconds,
        universe=resolved.universe,
        csv_path=os.environ.get("CSV") or None,
        directory=os.environ.get("DIR") or None,
        strategy_config_path=os.environ.get("STRATEGY") or None,
    )
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
