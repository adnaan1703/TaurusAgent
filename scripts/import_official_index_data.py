from __future__ import annotations

import argparse
import json
import os
from dataclasses import asdict, is_dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, Sequence

from scripts.migrate import run_migrations
from taurus_core.config import Settings, get_settings
from taurus_core.data.official_indices import (
    DEFAULT_BENCHMARK_INDEX_SYMBOLS,
    DEFAULT_VOLATILITY_INDEX_SYMBOLS,
    OfficialIndexReadinessRequest,
    build_official_index_readiness,
    import_official_index_csv,
)
from taurus_core.db.session import build_session_factory


def run_import(args: argparse.Namespace, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        summary = import_official_index_csv(
            session,
            csv_path=Path(args.csv),
            index_symbol=args.index_symbol or None,
            index_name=args.index_name or None,
            index_family=args.index_family or None,
            source=args.source,
            source_url=args.source_url or None,
            timeframe=args.timeframe,
        )
    print(json.dumps(_jsonable(summary), indent=2, sort_keys=True, default=_json_default))


def run_readiness(
    args: argparse.Namespace, settings: Settings | None = None
) -> int:
    settings = settings or get_settings()
    run_migrations(settings)
    request = OfficialIndexReadinessRequest(
        benchmark_symbols=_symbols(args.benchmark_symbols)
        or DEFAULT_BENCHMARK_INDEX_SYMBOLS,
        volatility_symbols=_symbols(args.volatility_symbols)
        or DEFAULT_VOLATILITY_INDEX_SYMBOLS,
        sector_symbols=_symbols(args.sector_symbols),
        start_date=_date_or_none(args.start_date),
        end_date=_date_or_none(args.end_date),
        timeframe=args.timeframe,
    )
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        readiness = build_official_index_readiness(session, request)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(
                readiness.artifact,
                indent=2,
                sort_keys=True,
                default=_json_default,
            )
            + "\n",
            encoding="utf-8",
        )
    print(json.dumps(readiness.artifact, indent=2, sort_keys=True, default=_json_default))
    return 0 if readiness.sufficient else 1


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import or verify official benchmark, sector-index, and India VIX history."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument("--csv", default=os.environ.get("OFFICIAL_INDEX_CSV", ""))
    import_parser.add_argument(
        "--index-symbol", default=os.environ.get("OFFICIAL_INDEX_SYMBOL", "")
    )
    import_parser.add_argument(
        "--index-name", default=os.environ.get("OFFICIAL_INDEX_NAME", "")
    )
    import_parser.add_argument(
        "--index-family", default=os.environ.get("OFFICIAL_INDEX_FAMILY", "")
    )
    import_parser.add_argument(
        "--source",
        default=os.environ.get("OFFICIAL_INDEX_SOURCE", "nse_official_index_csv"),
    )
    import_parser.add_argument(
        "--source-url", default=os.environ.get("OFFICIAL_INDEX_SOURCE_URL", "")
    )
    import_parser.add_argument(
        "--timeframe", default=os.environ.get("OFFICIAL_INDEX_TIMEFRAME", "1d")
    )

    readiness_parser = subparsers.add_parser("readiness")
    readiness_parser.add_argument(
        "--benchmark-symbols",
        default=os.environ.get("OFFICIAL_INDEX_BENCHMARK_SYMBOLS", "NIFTY_50"),
    )
    readiness_parser.add_argument(
        "--sector-symbols",
        default=os.environ.get("OFFICIAL_INDEX_SECTOR_SYMBOLS", ""),
    )
    readiness_parser.add_argument(
        "--volatility-symbols",
        default=os.environ.get("OFFICIAL_INDEX_VOLATILITY_SYMBOLS", "INDIA_VIX"),
    )
    readiness_parser.add_argument(
        "--start-date", default=os.environ.get("OFFICIAL_INDEX_START_DATE", "")
    )
    readiness_parser.add_argument(
        "--end-date", default=os.environ.get("OFFICIAL_INDEX_END_DATE", "")
    )
    readiness_parser.add_argument(
        "--timeframe", default=os.environ.get("OFFICIAL_INDEX_TIMEFRAME", "1d")
    )
    readiness_parser.add_argument(
        "--output", default=os.environ.get("OFFICIAL_INDEX_READINESS_OUTPUT", "")
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "import":
        if not args.csv:
            raise SystemExit("OFFICIAL_INDEX_CSV or --csv is required.")
        run_import(args)
        return 0
    return run_readiness(args)


def _symbols(value: str) -> tuple[str, ...]:
    return tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())


def _date_or_none(value: str) -> date | None:
    return date.fromisoformat(value) if value else None


def _jsonable(value: object) -> dict[str, object]:
    if is_dataclass(value):
        return asdict(value)
    raise TypeError(f"Unsupported JSON value: {value!r}")


def _json_default(value: Any) -> str:
    if isinstance(value, (date, Decimal)):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


if __name__ == "__main__":
    raise SystemExit(main())
