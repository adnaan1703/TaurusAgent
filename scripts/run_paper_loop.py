from __future__ import annotations

import json
import os
import time

from scripts.run_paper_once import run_mock_paper_once


def run_mock_paper_loop(
    *,
    symbol: str,
    iterations: int = 1,
    interval_seconds: float = 0,
) -> list[dict[str, object]]:
    if iterations < 1:
        raise ValueError("iterations must be at least 1")

    results: list[dict[str, object]] = []
    for index in range(iterations):
        results.append(run_mock_paper_once(symbol=symbol))
        if index < iterations - 1 and interval_seconds > 0:
            time.sleep(interval_seconds)
    return results


if __name__ == "__main__":
    symbol = os.environ.get("SYMBOL", "INFY")
    iterations = int(os.environ.get("PAPER_LOOP_ITERATIONS", "1"))
    interval_seconds = float(os.environ.get("PAPER_LOOP_INTERVAL_SECONDS", "0"))
    payload = run_mock_paper_loop(
        symbol=symbol,
        iterations=iterations,
        interval_seconds=interval_seconds,
    )
    print(json.dumps({"symbol": symbol.upper(), "runs": payload}, sort_keys=True))
