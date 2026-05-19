from __future__ import annotations

import csv
import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from taurus_core.db.models import (
    FundamentalImportModel,
    FundamentalScoreModel,
    FundamentalSnapshotModel,
    InstrumentModel,
)
from taurus_core.db.repositories import FundamentalsRepository, InstrumentRepository
from taurus_core.fundamentals.scoring import score_fundamentals
from taurus_core.intelligence.documents import stable_id

REQUESTED_COLUMNS: dict[str, str] = {
    "symbol": "Symbol",
    "company_name": "Company Name",
    "market_cap": "Market Cap",
    "current_price": "Current Price",
    "stock_pe": "Stock P/E",
    "book_value": "Book Value",
    "dividend_yield": "Dividend Yield",
    "roce": "ROCE",
    "roe": "ROE",
    "debt_to_equity": "Debt to Equity",
    "eps": "EPS",
    "sales_growth": "Sales growth",
    "profit_growth": "Profit growth",
    "promoter_holding": "Promoter holding",
    "fii_holding": "FII holding",
    "dii_holding": "DII holding",
    "pledged_percentage": "Pledged percentage",
}

METRIC_COLUMNS = tuple(
    canonical for canonical in REQUESTED_COLUMNS if canonical not in {"symbol", "company_name"}
)

COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "symbol": (
        "symbol",
        "nse symbol",
        "nse code",
        "ticker",
        "ticker symbol",
        "code",
    ),
    "company_name": (
        "company name",
        "company",
        "name",
        "stock name",
        "security name",
    ),
    "market_cap": ("market cap", "market capitalization", "mcap", "mar cap rs cr"),
    "current_price": ("current price", "price", "cmp", "current market price"),
    "stock_pe": ("stock p/e", "stock pe", "pe", "p/e", "price to earning"),
    "book_value": ("book value", "book value per share", "bv"),
    "dividend_yield": ("dividend yield", "div yield", "dividend yield %"),
    "roce": ("roce", "return on capital employed"),
    "roe": ("roe", "return on equity"),
    "debt_to_equity": ("debt to equity", "debt/equity", "debt equity", "d/e"),
    "eps": ("eps", "earnings per share"),
    "sales_growth": ("sales growth", "sales growth %", "sales growth 3years"),
    "profit_growth": ("profit growth", "profit growth %", "profit growth 3years"),
    "promoter_holding": ("promoter holding", "promoters holding", "promoter holding %"),
    "fii_holding": ("fii holding", "fii holding %", "fiis holding"),
    "dii_holding": ("dii holding", "dii holding %", "diis holding"),
    "pledged_percentage": (
        "pledged percentage",
        "pledged %",
        "promoter pledge",
        "pledged promoter holding",
    ),
    "reporting_date": ("reporting date", "report date", "as of", "as_of", "date"),
}


class ScreenerImportError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ScreenerImportSummary:
    import_id: str
    source_file_hash: str
    rows_seen: int
    rows_imported: int
    rows_unmapped: int
    metrics_imported: int
    scores_imported: int
    missing_required_columns: tuple[str, ...]
    missing_optional_columns: tuple[str, ...]
    imported_symbols: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "import_id": self.import_id,
            "source_file_hash": self.source_file_hash,
            "rows_seen": self.rows_seen,
            "rows_imported": self.rows_imported,
            "rows_unmapped": self.rows_unmapped,
            "metrics_imported": self.metrics_imported,
            "scores_imported": self.scores_imported,
            "missing_required_columns": list(self.missing_required_columns),
            "missing_optional_columns": list(self.missing_optional_columns),
            "imported_symbols": list(self.imported_symbols),
        }


def import_screener_csv(
    session: Session,
    csv_path: str | Path,
    *,
    data_available_time: datetime | None = None,
) -> ScreenerImportSummary:
    path = Path(csv_path).expanduser()
    if not path.exists():
        raise ScreenerImportError(f"Screener CSV file not found: {path}")
    if not path.is_file():
        raise ScreenerImportError(f"Screener CSV path is not a file: {path}")

    file_bytes = path.read_bytes()
    source_file_hash = hashlib.sha256(file_bytes).hexdigest()
    import_id = stable_id("fi", source_file_hash)
    available_at = _as_utc(data_available_time or datetime.now(timezone.utc))
    import_date = available_at.date()

    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = [field for field in (reader.fieldnames or []) if field is not None]
        column_map = _map_columns(fieldnames)
        missing_required = _missing_required_columns(column_map)
        missing_optional = _missing_optional_columns(column_map)
        if missing_required:
            available = ", ".join(fieldnames) if fieldnames else "none"
            missing = ", ".join(missing_required)
            raise ScreenerImportError(
                f"Missing required Screener column(s): {missing}. "
                f"Available columns: {available}."
            )

        instruments = InstrumentRepository(session).list(active_only=True)
        resolver = _InstrumentResolver(instruments)
        snapshots: list[FundamentalSnapshotModel] = []
        scores: list[FundamentalScoreModel] = []
        imported_symbols: set[str] = set()
        rows_seen = 0
        rows_unmapped = 0

        for row in reader:
            rows_seen += 1
            symbol = resolver.resolve(
                symbol=_row_value(row, column_map.get("symbol")),
                company_name=_row_value(row, column_map.get("company_name")),
            )
            if symbol is None:
                rows_unmapped += 1
                continue

            company_name = _row_value(row, column_map.get("company_name")) or resolver.name_for(symbol)
            reporting_date = _parse_date(_row_value(row, column_map.get("reporting_date")))
            metrics = _row_metrics(row, column_map)
            if not metrics:
                continue

            imported_symbols.add(symbol)
            for metric_name, metric_value in sorted(metrics.items()):
                source_column = column_map[metric_name]
                snapshots.append(
                    FundamentalSnapshotModel(
                        import_id=import_id,
                        symbol=symbol,
                        company_name=company_name,
                        metric_name=metric_name,
                        metric_value=metric_value,
                        source_column=source_column,
                        raw_value=_row_value(row, source_column),
                        reporting_date=reporting_date,
                        import_date=import_date,
                        data_available_time=available_at,
                        source_file_hash=source_file_hash,
                    )
                )

            components = score_fundamentals(metrics)
            scores.append(
                FundamentalScoreModel(
                    score_id=stable_id("fs", import_id, symbol),
                    import_id=import_id,
                    symbol=symbol,
                    company_name=company_name,
                    as_of=reporting_date or import_date,
                    data_available_time=available_at,
                    quality_score=components.quality_score,
                    valuation_score=components.valuation_score,
                    leverage_risk_score=components.leverage_risk_score,
                    ownership_score=components.ownership_score,
                    composite_score=components.composite_score,
                    metrics={name: str(value) for name, value in sorted(metrics.items())},
                    source_file_hash=source_file_hash,
                    model_version="fundamental_score_v1",
                )
            )

    import_row = FundamentalImportModel(
        import_id=import_id,
        source="screener_csv",
        source_filename=path.name,
        source_file_hash=source_file_hash,
        rows_seen=rows_seen,
        rows_imported=len(imported_symbols),
        rows_unmapped=rows_unmapped,
        metrics_imported=len(snapshots),
        scores_imported=len(scores),
        missing_required_columns=list(missing_required),
        missing_optional_columns=list(missing_optional),
        imported_symbols=sorted(imported_symbols),
        status="IMPORTED",
        data_available_time=available_at,
    )
    FundamentalsRepository(session).replace_import(
        import_row=import_row,
        snapshots=snapshots,
        scores=scores,
    )
    session.commit()
    return ScreenerImportSummary(
        import_id=import_id,
        source_file_hash=source_file_hash,
        rows_seen=rows_seen,
        rows_imported=len(imported_symbols),
        rows_unmapped=rows_unmapped,
        metrics_imported=len(snapshots),
        scores_imported=len(scores),
        missing_required_columns=tuple(missing_required),
        missing_optional_columns=tuple(missing_optional),
        imported_symbols=tuple(sorted(imported_symbols)),
    )


class _InstrumentResolver:
    def __init__(self, instruments: Iterable[InstrumentModel]) -> None:
        self._by_symbol = {instrument.symbol.upper(): instrument for instrument in instruments}
        self._by_name: dict[str, InstrumentModel] = {}
        for instrument in instruments:
            key = _normalize_company_key(instrument.name)
            if key:
                self._by_name[key] = instrument

    def resolve(self, *, symbol: str, company_name: str) -> str | None:
        normalized_symbol = _normalize_symbol(symbol)
        if normalized_symbol in self._by_symbol:
            return normalized_symbol

        company_key = _normalize_company_key(company_name)
        if company_key in self._by_name:
            return self._by_name[company_key].symbol

        for instrument_key, instrument in self._by_name.items():
            if company_key and (company_key in instrument_key or instrument_key in company_key):
                return instrument.symbol
        return None

    def name_for(self, symbol: str) -> str:
        instrument = self._by_symbol.get(symbol.upper())
        return instrument.name if instrument is not None else symbol.upper()


def _map_columns(fieldnames: list[str]) -> dict[str, str]:
    normalized_to_original = {_normalize_header(name): name for name in fieldnames}
    column_map: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            normalized_alias = _normalize_header(alias)
            if normalized_alias in normalized_to_original:
                column_map[canonical] = normalized_to_original[normalized_alias]
                break
    return column_map


def _missing_required_columns(column_map: dict[str, str]) -> tuple[str, ...]:
    missing: list[str] = []
    if "symbol" not in column_map and "company_name" not in column_map:
        missing.append("Symbol or Company Name")
    if not any(metric in column_map for metric in METRIC_COLUMNS):
        missing.append("at least one requested fundamental metric")
    return tuple(missing)


def _missing_optional_columns(column_map: dict[str, str]) -> tuple[str, ...]:
    return tuple(
        label
        for canonical, label in REQUESTED_COLUMNS.items()
        if canonical not in column_map
    )


def _row_metrics(row: dict[str, str], column_map: dict[str, str]) -> dict[str, Decimal]:
    metrics: dict[str, Decimal] = {}
    for canonical in METRIC_COLUMNS:
        source_column = column_map.get(canonical)
        if source_column is None:
            continue
        value = _parse_decimal(_row_value(row, source_column))
        if value is not None:
            metrics[canonical] = value
    return metrics


def _row_value(row: dict[str, str], column: str | None) -> str:
    if column is None:
        return ""
    value = row.get(column, "")
    return str(value).strip() if value is not None else ""


def _parse_decimal(value: str) -> Decimal | None:
    text = value.strip()
    if not text or text.lower() in {"na", "n/a", "nan", "none", "null", "-"}:
        return None
    negative = text.startswith("(") and text.endswith(")")
    cleaned = re.sub(r"[^0-9.+-]", "", text.replace(",", ""))
    if cleaned in {"", ".", "+", "-", "+.", "-."}:
        return None
    try:
        parsed = Decimal(cleaned)
    except InvalidOperation:
        return None
    return -parsed if negative else parsed


def _parse_date(value: str) -> date | None:
    text = value.strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def _normalize_symbol(value: str) -> str:
    candidate = value.strip().upper()
    if ":" in candidate:
        candidate = candidate.rsplit(":", maxsplit=1)[-1]
    for suffix in (".NS", ".BO", "-EQ", " EQ"):
        if candidate.endswith(suffix):
            candidate = candidate[: -len(suffix)]
    return re.sub(r"[^A-Z0-9]", "", candidate)


def _normalize_company_key(value: str) -> str:
    cleaned = value.lower().replace("&", " and ")
    cleaned = re.sub(r"[^a-z0-9]+", " ", cleaned)
    suffixes = {"co", "company", "ltd", "limited", "the"}
    tokens = [token for token in cleaned.split() if token not in suffixes]
    return " ".join(tokens)
