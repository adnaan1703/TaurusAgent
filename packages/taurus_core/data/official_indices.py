from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from sqlalchemy.orm import Session

from taurus_core.db.repositories import OfficialIndexCandleRepository
from taurus_core.domain.official_market_data import OfficialIndexCandle

OFFICIAL_INDEX_READINESS_ARTIFACT_VERSION = "official_index_readiness_v1"
DEFAULT_BENCHMARK_INDEX_SYMBOLS = ("NIFTY_50",)
DEFAULT_VOLATILITY_INDEX_SYMBOLS = ("INDIA_VIX",)


@dataclass(frozen=True, slots=True)
class OfficialIndexImportSummary:
    source: str
    csv_path: str
    row_count: int
    index_count: int
    rows_by_family: dict[str, int]
    rows_by_symbol: dict[str, int]
    start_date: date | None
    end_date: date | None


@dataclass(frozen=True, slots=True)
class OfficialIndexReadinessRequest:
    benchmark_symbols: tuple[str, ...] = DEFAULT_BENCHMARK_INDEX_SYMBOLS
    volatility_symbols: tuple[str, ...] = DEFAULT_VOLATILITY_INDEX_SYMBOLS
    sector_symbols: tuple[str, ...] = ()
    start_date: date | None = None
    end_date: date | None = None
    timeframe: str = "1d"


@dataclass(frozen=True, slots=True)
class OfficialIndexReadiness:
    status: str
    missing_requirements: tuple[dict[str, object], ...]
    family_rows: tuple[dict[str, object], ...]
    artifact: dict[str, object]

    @property
    def sufficient(self) -> bool:
        return self.status == "sufficient"


def import_official_index_csv(
    session: Session,
    *,
    csv_path: Path,
    index_symbol: str | None = None,
    index_name: str | None = None,
    index_family: str | None = None,
    source: str = "nse_official_index_csv",
    source_url: str | None = None,
    timeframe: str = "1d",
) -> OfficialIndexImportSummary:
    rows = parse_official_index_csv(
        csv_path=csv_path,
        index_symbol=index_symbol,
        index_name=index_name,
        index_family=index_family,
        source=source,
        source_url=source_url,
        timeframe=timeframe,
    )
    OfficialIndexCandleRepository(session).upsert(rows)
    session.commit()
    return _import_summary(csv_path=csv_path, source=source, rows=rows)


def parse_official_index_csv(
    *,
    csv_path: Path,
    index_symbol: str | None = None,
    index_name: str | None = None,
    index_family: str | None = None,
    source: str = "nse_official_index_csv",
    source_url: str | None = None,
    timeframe: str = "1d",
) -> list[OfficialIndexCandle]:
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Official index CSV {csv_path} has no header row.")
        rows = [
            _csv_row_to_candle(
                row,
                index_symbol=index_symbol,
                index_name=index_name,
                index_family=index_family,
                source=source,
                source_url=source_url,
                timeframe=timeframe,
            )
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]
    if not rows:
        raise ValueError(f"Official index CSV {csv_path} contained no data rows.")
    return rows


def build_official_index_readiness(
    session: Session,
    request: OfficialIndexReadinessRequest,
) -> OfficialIndexReadiness:
    repo = OfficialIndexCandleRepository(session)
    family_rows: list[dict[str, object]] = []
    missing: list[dict[str, object]] = []
    families = (
        ("benchmark", request.benchmark_symbols),
        ("sector", request.sector_symbols),
        ("volatility", request.volatility_symbols),
    )

    for family, symbols in families:
        if not symbols:
            family_rows.append(
                {
                    "family": family,
                    "required": False,
                    "required_symbols": [],
                    "status": "not_required",
                    "rows": [],
                }
            )
            continue
        symbol_rows: list[dict[str, object]] = []
        for symbol in symbols:
            coverage = repo.get_by_index_and_date_range(
                index_symbol=symbol,
                index_family=family,
                timeframe=request.timeframe,
                start_date=request.start_date,
                end_date=request.end_date,
            )
            all_rows = repo.get_by_index_and_date_range(
                index_symbol=symbol,
                index_family=family,
                timeframe=request.timeframe,
            )
            first_date = all_rows[0].trade_date if all_rows else None
            last_date = all_rows[-1].trade_date if all_rows else None
            row = {
                "symbol": symbol.upper(),
                "family": family,
                "row_count": len(coverage),
                "stored_row_count": len(all_rows),
                "first_date": first_date.isoformat() if first_date else None,
                "last_date": last_date.isoformat() if last_date else None,
                "source": sorted({item.source for item in all_rows}),
            }
            failures = _coverage_failures(
                row=row,
                start_date=request.start_date,
                end_date=request.end_date,
            )
            row["status"] = "ready" if not failures else "missing"
            row["failures"] = failures
            symbol_rows.append(row)
            for failure in failures:
                missing.append(
                    {
                        "family": family,
                        "symbol": symbol.upper(),
                        "reason": failure,
                    }
                )
        family_rows.append(
            {
                "family": family,
                "required": True,
                "required_symbols": [symbol.upper() for symbol in symbols],
                "status": "ready"
                if all(row["status"] == "ready" for row in symbol_rows)
                else "missing",
                "rows": symbol_rows,
            }
        )

    status = "sufficient" if not missing else "missing_official_index_data"
    artifact: dict[str, object] = {
        "artifact_version": OFFICIAL_INDEX_READINESS_ARTIFACT_VERSION,
        "status": status,
        "timeframe": request.timeframe,
        "window": {
            "start_date": request.start_date.isoformat()
            if request.start_date
            else None,
            "end_date": request.end_date.isoformat() if request.end_date else None,
        },
        "required": {
            "benchmark_symbols": [symbol.upper() for symbol in request.benchmark_symbols],
            "sector_symbols": [symbol.upper() for symbol in request.sector_symbols],
            "volatility_symbols": [
                symbol.upper() for symbol in request.volatility_symbols
            ],
        },
        "families": family_rows,
        "missing_requirements": missing,
        "next_actions": [] if not missing else _readiness_next_actions(missing),
    }
    return OfficialIndexReadiness(
        status=status,
        missing_requirements=tuple(missing),
        family_rows=tuple(family_rows),
        artifact=artifact,
    )


def _csv_row_to_candle(
    row: Mapping[str, str | None],
    *,
    index_symbol: str | None,
    index_name: str | None,
    index_family: str | None,
    source: str,
    source_url: str | None,
    timeframe: str,
) -> OfficialIndexCandle:
    normalized = {_normalize_header(key): value for key, value in row.items()}
    row_symbol = _field(normalized, "index_symbol", "symbol", "index")
    resolved_symbol = (row_symbol or index_symbol or "").strip().upper()
    if not resolved_symbol:
        raise ValueError("Official index CSV row is missing index_symbol.")
    resolved_name = (
        _field(normalized, "index_name", "name", "index_name")
        or index_name
        or resolved_symbol
    )
    resolved_family = (
        _field(normalized, "index_family", "family", "type")
        or index_family
        or "other"
    )
    row_source = _field(normalized, "source") or source
    row_source_url = _field(normalized, "source_url", "url") or source_url
    row_timeframe = _field(normalized, "timeframe", "interval") or timeframe
    available = _field(
        normalized,
        "data_available_time",
        "available_time",
        "available_at",
    )
    return OfficialIndexCandle(
        index_symbol=resolved_symbol,
        index_name=resolved_name,
        index_family=_normalize_index_family(resolved_family),
        timeframe=row_timeframe,
        trade_date=_parse_date(_required_field(normalized, "trade_date", "date")),
        open=_parse_decimal(_required_field(normalized, "open")),
        high=_parse_decimal(_required_field(normalized, "high")),
        low=_parse_decimal(_required_field(normalized, "low")),
        close=_parse_decimal(_required_field(normalized, "close")),
        source=row_source,
        source_url=row_source_url,
        data_available_time=_parse_datetime(available) if available else None,
        raw={key: value for key, value in row.items() if key is not None},
    )


def _import_summary(
    *,
    csv_path: Path,
    source: str,
    rows: list[OfficialIndexCandle],
) -> OfficialIndexImportSummary:
    rows_by_family: dict[str, int] = {}
    rows_by_symbol: dict[str, int] = {}
    dates: list[date] = []
    for row in rows:
        rows_by_family[row.index_family] = rows_by_family.get(row.index_family, 0) + 1
        rows_by_symbol[row.index_symbol] = rows_by_symbol.get(row.index_symbol, 0) + 1
        dates.append(row.trade_date)
    return OfficialIndexImportSummary(
        source=source,
        csv_path=str(csv_path),
        row_count=len(rows),
        index_count=len(rows_by_symbol),
        rows_by_family=rows_by_family,
        rows_by_symbol=rows_by_symbol,
        start_date=min(dates) if dates else None,
        end_date=max(dates) if dates else None,
    )


def _coverage_failures(
    *,
    row: Mapping[str, object],
    start_date: date | None,
    end_date: date | None,
) -> list[str]:
    failures: list[str] = []
    first = _date_or_none(row.get("first_date"))
    last = _date_or_none(row.get("last_date"))
    if row.get("stored_row_count") == 0:
        failures.append("missing_history")
        return failures
    if start_date is not None and (first is None or first > start_date):
        failures.append("missing_start_coverage")
    if end_date is not None and (last is None or last < end_date):
        failures.append("missing_end_coverage")
    if row.get("row_count") == 0:
        failures.append("missing_rows_in_requested_window")
    return failures


def _readiness_next_actions(missing: list[dict[str, object]]) -> list[str]:
    symbols = sorted({str(row["symbol"]) for row in missing})
    return [
        "Import official NSE/NSE-derived index CSV history with "
        "make import-official-index-data OFFICIAL_INDEX_CSV=/path/to/file.csv.",
        "Re-run make check-official-index-readiness after importing: "
        f"missing symbols include {', '.join(symbols)}.",
    ]


def _normalize_index_family(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"bench", "benchmark_index", "market", "broad_market"}:
        return "benchmark"
    if normalized in {"sector_index", "sectoral"}:
        return "sector"
    if normalized in {"vix", "india_vix", "volatility_index"}:
        return "volatility"
    if normalized in {"benchmark", "sector", "volatility", "other"}:
        return normalized
    raise ValueError(f"Unsupported official index family: {value!r}")


def _field(normalized: Mapping[str, str | None], *names: str) -> str | None:
    for name in names:
        value = normalized.get(_normalize_header(name))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _required_field(normalized: Mapping[str, str | None], *names: str) -> str:
    value = _field(normalized, *names)
    if value is None:
        raise ValueError(f"Official index CSV row is missing {names[0]}.")
    return value


def _normalize_header(value: str | None) -> str:
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def _parse_date(value: str) -> date:
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported official index date format: {value!r}")


def _parse_datetime(value: str) -> datetime:
    raw = value.strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            f"Unsupported official index data_available_time format: {value!r}"
        ) from error


def _parse_decimal(value: str) -> Decimal:
    return Decimal(value.strip().replace(",", ""))


def _date_or_none(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return None
