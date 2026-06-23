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
from taurus_core.data.official_microstructure import (
    DEFAULT_OFFICIAL_MICROSTRUCTURE_FAMILIES,
    OfficialMicrostructureReadinessRequest,
    build_official_microstructure_readiness,
    import_official_microstructure_csv,
)
from taurus_core.db.session import build_session_factory


def run_import(args: argparse.Namespace, settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        summary = import_official_microstructure_csv(
            session,
            csv_path=Path(args.csv),
            source=args.source,
            source_url=args.source_url or None,
            timeframe=args.timeframe,
            impact_cost_source_kind=args.impact_cost_source_kind,
            impact_cost_proxy_name=args.impact_cost_proxy_name or None,
        )
    print(json.dumps(_jsonable(summary), indent=2, sort_keys=True, default=_json_default))


def run_readiness(
    args: argparse.Namespace, settings: Settings | None = None
) -> int:
    settings = settings or get_settings()
    run_migrations(settings)
    request = OfficialMicrostructureReadinessRequest(
        symbols=_symbols(args.symbols),
        required_families=_families(args.required_families)
        or DEFAULT_OFFICIAL_MICROSTRUCTURE_FAMILIES,
        start_date=_date_or_none(args.start_date),
        end_date=_date_or_none(args.end_date),
        timeframe=args.timeframe,
    )
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        readiness = build_official_microstructure_readiness(session, request)
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
        description=(
            "Import or verify official security-wise delivery, circuit, "
            "and tradability data."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    import_parser = subparsers.add_parser("import")
    import_parser.add_argument(
        "--csv", default=os.environ.get("OFFICIAL_MICROSTRUCTURE_CSV", "")
    )
    import_parser.add_argument(
        "--source",
        default=os.environ.get(
            "OFFICIAL_MICROSTRUCTURE_SOURCE", "nse_security_wise_csv"
        ),
    )
    import_parser.add_argument(
        "--source-url",
        default=os.environ.get("OFFICIAL_MICROSTRUCTURE_SOURCE_URL", ""),
    )
    import_parser.add_argument(
        "--timeframe",
        default=os.environ.get("OFFICIAL_MICROSTRUCTURE_TIMEFRAME", "1d"),
    )
    import_parser.add_argument(
        "--impact-cost-source-kind",
        default=os.environ.get(
            "OFFICIAL_MICROSTRUCTURE_IMPACT_COST_SOURCE_KIND", "unavailable"
        ),
    )
    import_parser.add_argument(
        "--impact-cost-proxy-name",
        default=os.environ.get(
            "OFFICIAL_MICROSTRUCTURE_IMPACT_COST_PROXY_NAME", ""
        ),
    )

    readiness_parser = subparsers.add_parser("readiness")
    readiness_parser.add_argument(
        "--symbols",
        default=os.environ.get("OFFICIAL_MICROSTRUCTURE_SYMBOLS", ""),
    )
    readiness_parser.add_argument(
        "--required-families",
        default=os.environ.get(
            "OFFICIAL_MICROSTRUCTURE_REQUIRED_FAMILIES",
            ",".join(DEFAULT_OFFICIAL_MICROSTRUCTURE_FAMILIES),
        ),
    )
    readiness_parser.add_argument(
        "--start-date",
        default=os.environ.get("OFFICIAL_MICROSTRUCTURE_START_DATE", ""),
    )
    readiness_parser.add_argument(
        "--end-date",
        default=os.environ.get("OFFICIAL_MICROSTRUCTURE_END_DATE", ""),
    )
    readiness_parser.add_argument(
        "--timeframe",
        default=os.environ.get("OFFICIAL_MICROSTRUCTURE_TIMEFRAME", "1d"),
    )
    readiness_parser.add_argument(
        "--output",
        default=os.environ.get("OFFICIAL_MICROSTRUCTURE_READINESS_OUTPUT", ""),
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if args.command == "import":
        if not args.csv:
            raise SystemExit("OFFICIAL_MICROSTRUCTURE_CSV or --csv is required.")
        run_import(args)
        return 0
    return run_readiness(args)


def _symbols(value: str) -> tuple[str, ...]:
    return tuple(symbol.strip().upper() for symbol in value.split(",") if symbol.strip())


def _families(value: str) -> tuple[str, ...]:
    return tuple(family.strip().lower() for family in value.split(",") if family.strip())


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
