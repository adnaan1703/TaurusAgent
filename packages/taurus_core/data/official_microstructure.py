from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from sqlalchemy.orm import Session

from taurus_core.db.repositories import OfficialSecurityMicrostructureRepository
from taurus_core.domain.official_market_data import OfficialSecurityMicrostructure

OFFICIAL_MICROSTRUCTURE_READINESS_ARTIFACT_VERSION = (
    "official_security_microstructure_readiness_v1"
)
DEFAULT_OFFICIAL_MICROSTRUCTURE_FAMILIES = ("delivery", "circuit", "tradability")


@dataclass(frozen=True, slots=True)
class OfficialMicrostructureImportSummary:
    source: str
    csv_path: str
    row_count: int
    symbol_count: int
    rows_by_symbol: dict[str, int]
    rows_by_available_family: dict[str, int]
    impact_cost_source_kinds: dict[str, int]
    start_date: date | None
    end_date: date | None


@dataclass(frozen=True, slots=True)
class OfficialMicrostructureReadinessRequest:
    symbols: tuple[str, ...]
    required_families: tuple[str, ...] = DEFAULT_OFFICIAL_MICROSTRUCTURE_FAMILIES
    start_date: date | None = None
    end_date: date | None = None
    timeframe: str = "1d"


@dataclass(frozen=True, slots=True)
class OfficialMicrostructureReadiness:
    status: str
    missing_requirements: tuple[dict[str, object], ...]
    family_rows: tuple[dict[str, object], ...]
    artifact: dict[str, object]

    @property
    def sufficient(self) -> bool:
        return self.status == "sufficient"


def import_official_microstructure_csv(
    session: Session,
    *,
    csv_path: Path,
    source: str = "nse_security_wise_csv",
    source_url: str | None = None,
    timeframe: str = "1d",
    impact_cost_source_kind: str = "unavailable",
    impact_cost_proxy_name: str | None = None,
) -> OfficialMicrostructureImportSummary:
    rows = parse_official_microstructure_csv(
        csv_path=csv_path,
        source=source,
        source_url=source_url,
        timeframe=timeframe,
        impact_cost_source_kind=impact_cost_source_kind,
        impact_cost_proxy_name=impact_cost_proxy_name,
    )
    OfficialSecurityMicrostructureRepository(session).upsert(rows)
    session.commit()
    return _import_summary(csv_path=csv_path, source=source, rows=rows)


def parse_official_microstructure_csv(
    *,
    csv_path: Path,
    source: str = "nse_security_wise_csv",
    source_url: str | None = None,
    timeframe: str = "1d",
    impact_cost_source_kind: str = "unavailable",
    impact_cost_proxy_name: str | None = None,
) -> list[OfficialSecurityMicrostructure]:
    with csv_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError(f"Official microstructure CSV {csv_path} has no header row.")
        rows = [
            _csv_row_to_microstructure(
                row,
                source=source,
                source_url=source_url,
                timeframe=timeframe,
                impact_cost_source_kind=impact_cost_source_kind,
                impact_cost_proxy_name=impact_cost_proxy_name,
            )
            for row in reader
            if any(str(value or "").strip() for value in row.values())
        ]
    if not rows:
        raise ValueError(f"Official microstructure CSV {csv_path} contained no data rows.")
    return rows


def build_official_microstructure_readiness(
    session: Session,
    request: OfficialMicrostructureReadinessRequest,
) -> OfficialMicrostructureReadiness:
    repo = OfficialSecurityMicrostructureRepository(session)
    symbols = tuple(symbol.upper() for symbol in request.symbols)
    families = tuple(_normalize_family(family) for family in request.required_families)
    family_rows: list[dict[str, object]] = []
    missing: list[dict[str, object]] = []

    if not symbols:
        for family in families:
            missing.append(
                {
                    "family": family,
                    "symbol": None,
                    "reason": "missing_required_symbols",
                }
            )

    for family in families:
        symbol_rows: list[dict[str, object]] = []
        for symbol in symbols:
            all_rows = repo.get_by_symbol_and_date_range(
                symbol=symbol,
                timeframe=request.timeframe,
            )
            coverage_rows = repo.get_by_symbol_and_date_range(
                symbol=symbol,
                timeframe=request.timeframe,
                start_date=request.start_date,
                end_date=request.end_date,
            )
            family_all = _rows_for_family(all_rows, family)
            family_coverage = _rows_for_family(coverage_rows, family)
            first_date = family_all[0].trade_date if family_all else None
            last_date = family_all[-1].trade_date if family_all else None
            row = {
                "symbol": symbol,
                "family": family,
                "row_count": len(family_coverage),
                "stored_row_count": len(family_all),
                "first_date": first_date.isoformat() if first_date else None,
                "last_date": last_date.isoformat() if last_date else None,
                "source": sorted({item.source for item in family_all}),
            }
            if family == "tradability":
                row["impact_cost_source_kinds"] = sorted(
                    {item.impact_cost_source_kind for item in family_all}
                )
                row["impact_cost_proxy_names"] = sorted(
                    {
                        item.impact_cost_proxy_name
                        for item in family_all
                        if item.impact_cost_proxy_name
                    }
                )
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
                        "symbol": symbol,
                        "reason": failure,
                    }
                )
        family_rows.append(
            {
                "family": family,
                "required": True,
                "required_symbols": list(symbols),
                "status": "ready"
                if symbol_rows and all(row["status"] == "ready" for row in symbol_rows)
                else "missing",
                "rows": symbol_rows,
            }
        )

    status = "sufficient" if not missing else "missing_official_microstructure_data"
    artifact: dict[str, object] = {
        "artifact_version": OFFICIAL_MICROSTRUCTURE_READINESS_ARTIFACT_VERSION,
        "status": status,
        "timeframe": request.timeframe,
        "window": {
            "start_date": request.start_date.isoformat()
            if request.start_date
            else None,
            "end_date": request.end_date.isoformat() if request.end_date else None,
        },
        "required": {
            "symbols": list(symbols),
            "families": list(families),
        },
        "families": family_rows,
        "missing_requirements": missing,
        "next_actions": [] if not missing else _readiness_next_actions(missing),
    }
    return OfficialMicrostructureReadiness(
        status=status,
        missing_requirements=tuple(missing),
        family_rows=tuple(family_rows),
        artifact=artifact,
    )


def _csv_row_to_microstructure(
    row: Mapping[str, str | None],
    *,
    source: str,
    source_url: str | None,
    timeframe: str,
    impact_cost_source_kind: str,
    impact_cost_proxy_name: str | None,
) -> OfficialSecurityMicrostructure:
    normalized = {_normalize_header(key): value for key, value in row.items()}
    row_source = _field(normalized, "source") or source
    row_source_url = _field(normalized, "source_url", "url") or source_url
    row_timeframe = _field(normalized, "timeframe", "interval") or timeframe
    available = _field(
        normalized,
        "data_available_time",
        "available_time",
        "available_at",
    )
    circuit_status = _field(normalized, "circuit_status", "price_band_status")
    circuit_hit = _parse_bool_or_none(
        _field(normalized, "circuit_hit", "hit_circuit", "circuit")
    )
    if circuit_hit is None and circuit_status is not None:
        circuit_hit = _infer_circuit_hit(circuit_status)
    impact_cost_bps = _optional_decimal(
        _field(
            normalized,
            "impact_cost_bps",
            "impact_cost",
            "impact_cost_basis_points",
            "implementation_cost_bps",
        )
    )
    row_impact_kind = _field(
        normalized,
        "impact_cost_source_kind",
        "impact_cost_kind",
    )
    row_proxy_name = (
        _field(normalized, "impact_cost_proxy_name", "proxy_name")
        or impact_cost_proxy_name
    )
    resolved_impact_kind = _resolve_impact_kind(
        row_kind=row_impact_kind,
        default_kind=impact_cost_source_kind,
        impact_cost_bps=impact_cost_bps,
        proxy_name=row_proxy_name,
    )
    if resolved_impact_kind == "proxy" and not row_proxy_name:
        raise ValueError(
            "Impact-cost proxy rows must name impact_cost_proxy_name."
        )

    return OfficialSecurityMicrostructure(
        symbol=_required_field(
            normalized,
            "symbol",
            "security_symbol",
            "tradingsymbol",
            "ticker",
        ).upper(),
        trade_date=_parse_date(_required_field(normalized, "trade_date", "date")),
        source=row_source,
        timeframe=row_timeframe,
        source_url=row_source_url,
        data_available_time=_parse_datetime(available) if available else None,
        delivery_quantity=_optional_int(
            _field(
                normalized,
                "delivery_quantity",
                "delivery_qty",
                "deliverable_quantity",
                "deliverable_qty",
                "deliv_qty",
            )
        ),
        delivery_percentage=_optional_decimal(
            _field(
                normalized,
                "delivery_percentage",
                "delivery_percent",
                "delivery_pct",
                "deliverable_percent",
                "deliverable_pct",
                "percent_deliverable_quantity_to_traded_quantity",
                "percent_deliverble_quantity_to_traded_quantity",
            )
        ),
        price_band_percent=_optional_decimal(
            _field(
                normalized,
                "price_band_percent",
                "price_band_pct",
                "price_band",
                "band_percent",
            )
        ),
        upper_circuit_price=_optional_decimal(
            _field(
                normalized,
                "upper_circuit_price",
                "upper_band",
                "upper_price_band",
            )
        ),
        lower_circuit_price=_optional_decimal(
            _field(
                normalized,
                "lower_circuit_price",
                "lower_band",
                "lower_price_band",
            )
        ),
        circuit_status=_normalize_circuit_status(circuit_status)
        if circuit_status
        else None,
        circuit_hit=circuit_hit,
        impact_cost_bps=impact_cost_bps,
        impact_cost_source_kind=resolved_impact_kind,
        impact_cost_proxy_name=row_proxy_name,
        average_trade_value=_optional_decimal(
            _field(
                normalized,
                "average_trade_value",
                "average_traded_value",
                "avg_trade_value",
                "avg_traded_value",
            )
        ),
        turnover=_optional_decimal(
            _field(
                normalized,
                "turnover",
                "turnover_value",
                "traded_value",
                "total_traded_value",
                "turnover_rs",
            )
        ),
        raw={key: value for key, value in row.items() if key is not None},
    )


def _import_summary(
    *,
    csv_path: Path,
    source: str,
    rows: list[OfficialSecurityMicrostructure],
) -> OfficialMicrostructureImportSummary:
    rows_by_symbol: dict[str, int] = {}
    rows_by_available_family = {family: 0 for family in DEFAULT_OFFICIAL_MICROSTRUCTURE_FAMILIES}
    impact_kinds: dict[str, int] = {}
    dates: list[date] = []
    for row in rows:
        rows_by_symbol[row.symbol] = rows_by_symbol.get(row.symbol, 0) + 1
        dates.append(row.trade_date)
        for family in DEFAULT_OFFICIAL_MICROSTRUCTURE_FAMILIES:
            if _domain_row_has_family(row, family):
                rows_by_available_family[family] += 1
        impact_kinds[row.impact_cost_source_kind] = (
            impact_kinds.get(row.impact_cost_source_kind, 0) + 1
        )
    return OfficialMicrostructureImportSummary(
        source=source,
        csv_path=str(csv_path),
        row_count=len(rows),
        symbol_count=len(rows_by_symbol),
        rows_by_symbol=rows_by_symbol,
        rows_by_available_family=rows_by_available_family,
        impact_cost_source_kinds=impact_kinds,
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
    symbols = sorted(
        {str(row["symbol"]) for row in missing if row.get("symbol") is not None}
    )
    families = sorted({str(row["family"]) for row in missing})
    return [
        "Import official NSE security-wise delivery, price-band/circuit, "
        "or documented tradability proxy CSVs with make import-official-microstructure-data.",
        "Re-run make check-official-microstructure-readiness after importing: "
        f"missing families include {', '.join(families)}"
        + (f"; symbols include {', '.join(symbols)}." if symbols else "."),
    ]


def _rows_for_family(rows: list[object], family: str) -> list[object]:
    return [row for row in rows if _model_row_has_family(row, family)]


def _model_row_has_family(row: object, family: str) -> bool:
    if family == "delivery":
        return (
            getattr(row, "delivery_quantity") is not None
            or getattr(row, "delivery_percentage") is not None
        )
    if family == "circuit":
        return (
            getattr(row, "price_band_percent") is not None
            or getattr(row, "upper_circuit_price") is not None
            or getattr(row, "lower_circuit_price") is not None
            or getattr(row, "circuit_status") is not None
            or getattr(row, "circuit_hit") is not None
        )
    if family == "tradability":
        return (
            getattr(row, "impact_cost_bps") is not None
            or getattr(row, "impact_cost_proxy_name") is not None
            or getattr(row, "average_trade_value") is not None
            or getattr(row, "turnover") is not None
        )
    raise ValueError(f"Unsupported official microstructure family: {family!r}")


def _domain_row_has_family(row: OfficialSecurityMicrostructure, family: str) -> bool:
    return _model_row_has_family(row, family)


def _normalize_family(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized in {"delivery", "circuit", "tradability"}:
        return normalized
    raise ValueError(f"Unsupported official microstructure family: {value!r}")


def _field(normalized: Mapping[str, str | None], *names: str) -> str | None:
    for name in names:
        value = normalized.get(_normalize_header(name))
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _required_field(normalized: Mapping[str, str | None], *names: str) -> str:
    value = _field(normalized, *names)
    if value is None:
        raise ValueError(f"Official microstructure CSV row is missing {names[0]}.")
    return value


def _normalize_header(value: str | None) -> str:
    return (
        str(value or "")
        .strip()
        .lower()
        .replace("%", "percent")
        .replace("/", "_")
        .replace(" ", "_")
        .replace("-", "_")
    )


def _normalize_circuit_status(value: str) -> str:
    normalized = value.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "upper": "upper_circuit",
        "upper_band": "upper_circuit",
        "lower": "lower_circuit",
        "lower_band": "lower_circuit",
        "normal": "none",
        "not_hit": "none",
        "no_circuit": "none",
        "na": "unknown",
        "n_a": "unknown",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in {
        "none",
        "upper_circuit",
        "lower_circuit",
        "near_upper",
        "near_lower",
        "no_band",
        "unknown",
        "other",
    }:
        raise ValueError(f"Unsupported circuit status: {value!r}")
    return normalized


def _resolve_impact_kind(
    *,
    row_kind: str | None,
    default_kind: str,
    impact_cost_bps: Decimal | None,
    proxy_name: str | None,
) -> str:
    raw = row_kind or default_kind
    if not raw or raw == "unavailable":
        if proxy_name:
            raw = "proxy"
        elif impact_cost_bps is not None:
            raw = "official"
        else:
            raw = "unavailable"
    normalized = raw.strip().lower().replace("-", "_").replace(" ", "_")
    if normalized not in {"official", "proxy", "unavailable"}:
        raise ValueError(f"Unsupported impact cost source kind: {raw!r}")
    return normalized


def _infer_circuit_hit(status: str) -> bool | None:
    normalized = _normalize_circuit_status(status)
    if normalized in {"upper_circuit", "lower_circuit"}:
        return True
    if normalized in {"none", "no_band"}:
        return False
    return None


def _parse_bool_or_none(value: str | None) -> bool | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    if normalized in {"1", "true", "t", "yes", "y", "hit"}:
        return True
    if normalized in {"0", "false", "f", "no", "n", "not_hit", "none"}:
        return False
    raise ValueError(f"Unsupported official microstructure boolean: {value!r}")


def _parse_date(value: str) -> date:
    raw = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Unsupported official microstructure date format: {value!r}")


def _parse_datetime(value: str) -> datetime:
    raw = value.strip()
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(
            "Unsupported official microstructure data_available_time format: "
            f"{value!r}"
        ) from error


def _optional_decimal(value: str | None) -> Decimal | None:
    if value is None:
        return None
    return Decimal(value.strip().replace(",", ""))


def _optional_int(value: str | None) -> int | None:
    if value is None:
        return None
    return int(value.strip().replace(",", ""))


def _date_or_none(value: object) -> date | None:
    if value is None:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        return date.fromisoformat(value)
    return None
