from __future__ import annotations

import json
import os

from taurus_core.config import Settings, get_settings
from taurus_core.data.universe import load_market_data_universe
from taurus_core.logging import configure_logging
from taurus_core.paper_trading.service import PaperRunService, SimplePaperScheduler


def run_paper_loop(
    *,
    symbols: list[str],
    settings: Settings | None = None,
    iterations: int = 1,
    interval_seconds: float = 0,
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
    raw = os.environ.get("SYMBOLS") or os.environ.get("SYMBOL")
    if raw is None and settings.taurus_market_data_provider == "kite":
        return load_market_data_universe(settings.taurus_market_data_universe_path).enabled_symbols()
    raw = raw or "INFY"
    symbols = [symbol.strip().upper() for symbol in raw.split(",") if symbol.strip()]
    return symbols or ["INFY"]


if __name__ == "__main__":
    configure_logging()
    settings = get_settings()
    symbols = _symbols_from_env(settings)
    iterations = int(os.environ.get("PAPER_LOOP_ITERATIONS", "1"))
    interval_seconds = float(os.environ.get("PAPER_LOOP_INTERVAL_SECONDS", "0"))
    payload = run_paper_loop(
        symbols=symbols,
        settings=settings,
        iterations=iterations,
        interval_seconds=interval_seconds,
        csv_path=os.environ.get("CSV") or None,
        directory=os.environ.get("DIR") or None,
        strategy_config_path=os.environ.get("STRATEGY") or None,
    )
    print(json.dumps({"symbols": symbols, "runs": payload}, sort_keys=True))
