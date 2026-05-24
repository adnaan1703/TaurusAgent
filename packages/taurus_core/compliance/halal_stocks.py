from __future__ import annotations

import hashlib
import os
import re
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen

import yaml
from bs4 import BeautifulSoup
from bs4.element import Tag
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.config import Settings, get_settings
from taurus_core.data.universe import load_market_data_universe
from taurus_core.db.models import HalalStockImportModel
from taurus_core.db.repositories import HalalStockComplianceRepository
from taurus_core.db.session import build_session_factory
from taurus_core.intelligence.documents import stable_id

ComplianceStatus = Literal["halal", "haram"]

SOURCE_URL = "https://halalstock.in/halal-shariah-compliant-shares-list/"
TABLE_ID = "tablepress-24"
YES_ICON = "hs-yes.jpg"
NO_ICON = "hs-no.jpg"
ICON_STATUS_BY_BASENAME: dict[str, ComplianceStatus] = {
    YES_ICON: "halal",
    NO_ICON: "haram",
}
REQUIRED_HEADERS: dict[str, str] = {
    "halal": "Halal",
    "name": "NAME",
    "bse_code": "BSE-ID",
    "nse_code": "NSECode",
    "industry": "Industry",
    "more": "More",
}
FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36 TaurusAgent/0.1"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
}


class HalalStockComplianceError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class HalalStockFetchResult:
    source_url: str
    final_url: str
    html: str
    source_checksum: str
    fetched_at: datetime
    content_length: int


@dataclass(frozen=True, slots=True)
class HalalStockRow:
    source_key: str
    row_number: int
    name: str
    bse_code: str
    nse_code: str
    industry: str
    compliance_status: ComplianceStatus
    status_icon_url: str
    details_url: str
    source_url: str
    raw_metadata: dict[str, object]

    @property
    def identity_key(self) -> tuple[str, str, str, str]:
        return (
            _company_key(self.name),
            self.bse_code.upper(),
            self.nse_code.upper(),
            self.details_url,
        )

    @property
    def duplicate_payload(self) -> tuple[str, str, str, str, str, str, str]:
        return (
            self.name,
            self.bse_code,
            self.nse_code,
            self.industry,
            self.compliance_status,
            self.status_icon_url,
            self.details_url,
        )


@dataclass(frozen=True, slots=True)
class HalalStockParseResult:
    source_url: str
    table_id: str
    rows: tuple[HalalStockRow, ...]
    rows_seen: int
    rows_imported: int
    halal_count: int
    haram_count: int
    unknown_count: int
    duplicate_count: int


@dataclass(frozen=True, slots=True)
class HalalUniverseExportSummary:
    generated_yaml_path: str
    exported_symbol_count: int
    symbols: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class HalalStockSyncSummary:
    import_id: str
    source_url: str
    source_checksum: str
    fetched_at: datetime
    rows_seen: int
    rows_imported: int
    halal_count: int
    haram_count: int
    unknown_count: int
    duplicate_count: int
    active_count: int
    inactive_count: int
    generated_yaml_path: str
    exported_symbol_count: int

    def to_dict(self) -> dict[str, object]:
        return {
            "import_id": self.import_id,
            "source_url": self.source_url,
            "source_checksum": self.source_checksum,
            "fetched_at": self.fetched_at.isoformat(),
            "rows_seen": self.rows_seen,
            "rows_imported": self.rows_imported,
            "halal_count": self.halal_count,
            "haram_count": self.haram_count,
            "unknown_count": self.unknown_count,
            "duplicate_count": self.duplicate_count,
            "active_count": self.active_count,
            "inactive_count": self.inactive_count,
            "generated_yaml_path": self.generated_yaml_path,
            "exported_symbol_count": self.exported_symbol_count,
        }


def fetch_halal_stock_page(
    source_url: str = SOURCE_URL,
    *,
    timeout_seconds: float = 30,
    fetched_at: datetime | None = None,
) -> HalalStockFetchResult:
    request = Request(source_url, headers=FETCH_HEADERS, method="GET")
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            content = response.read()
            final_url = response.geturl()
            encoding = response.headers.get_content_charset() or "utf-8"
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise HalalStockComplianceError(
            f"Could not fetch HalalStock source page {source_url}: {exc}"
        ) from exc

    return HalalStockFetchResult(
        source_url=source_url,
        final_url=final_url,
        html=content.decode(encoding, errors="replace"),
        source_checksum=hashlib.sha256(content).hexdigest(),
        fetched_at=_as_utc(fetched_at or datetime.now(timezone.utc)),
        content_length=len(content),
    )


def parse_halal_stock_rows(
    html: str,
    *,
    source_url: str = SOURCE_URL,
    table_id: str = TABLE_ID,
) -> HalalStockParseResult:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", id=table_id)
    if not isinstance(table, Tag):
        raise HalalStockComplianceError(f"HalalStock table not found: #{table_id}")

    column_map = _column_map(table)
    body = table.find("tbody")
    if not isinstance(body, Tag):
        raise HalalStockComplianceError(f"HalalStock table #{table_id} has no tbody.")

    rows: list[HalalStockRow] = []
    unknown_icons: list[tuple[int, str]] = []
    status_counts = {"halal": 0, "haram": 0}
    rows_seen = 0
    for row_number, tr in enumerate(body.find_all("tr", recursive=False), start=1):
        cells = tr.find_all("td", recursive=False)
        if not cells:
            continue
        rows_seen += 1
        status, icon_url = _parse_icon_status(
            _cell(cells, column_map["halal"]),
            row_number=row_number,
            source_url=source_url,
        )
        if status is None:
            unknown_icons.append((row_number, icon_url))
            continue
        status_counts[status] += 1

        name = _clean_text(_cell(cells, column_map["name"]).get_text(" ", strip=True))
        bse_code = _clean_symbol(_cell(cells, column_map["bse_code"]).get_text(" ", strip=True))
        nse_code = _clean_symbol(_cell(cells, column_map["nse_code"]).get_text(" ", strip=True))
        industry = _clean_text(_cell(cells, column_map["industry"]).get_text(" ", strip=True))
        details_url = _details_url(_cell(cells, column_map["more"]), source_url=source_url)
        if not name:
            raise HalalStockComplianceError(f"HalalStock row {row_number} is missing NAME.")

        source_key = _source_key(
            name=name,
            bse_code=bse_code,
            nse_code=nse_code,
            details_url=details_url,
        )
        rows.append(
            HalalStockRow(
                source_key=source_key,
                row_number=row_number,
                name=name,
                bse_code=bse_code,
                nse_code=nse_code,
                industry=industry,
                compliance_status=status,
                status_icon_url=icon_url,
                details_url=details_url,
                source_url=source_url,
                raw_metadata={
                    "row_number": row_number,
                    "table_id": table_id,
                    "source_key_parts": {
                        "normalized_name": _company_key(name),
                        "bse_code": bse_code,
                        "nse_code": nse_code,
                        "details_url": details_url,
                    },
                },
            )
        )

    if unknown_icons:
        details = ", ".join(
            f"row {row_number}: {icon_url or '<missing>'}"
            for row_number, icon_url in unknown_icons[:20]
        )
        extra = "" if len(unknown_icons) <= 20 else f" and {len(unknown_icons) - 20} more"
        raise HalalStockComplianceError(
            "Unknown HalalStock status icon(s); refusing to write DB rows: "
            f"{details}{extra}"
        )

    deduped_rows, duplicate_count = _dedupe_rows(rows)
    return HalalStockParseResult(
        source_url=source_url,
        table_id=table_id,
        rows=tuple(deduped_rows),
        rows_seen=rows_seen,
        rows_imported=len(deduped_rows),
        halal_count=status_counts["halal"],
        haram_count=status_counts["haram"],
        unknown_count=len(unknown_icons),
        duplicate_count=duplicate_count,
    )


def import_halal_stock_compliance(
    session: Session,
    parse_result: HalalStockParseResult,
    *,
    source_checksum: str,
    fetched_at: datetime,
    generated_yaml_path: str = "",
) -> tuple[HalalStockImportModel, int, int]:
    seen_at = _as_utc(fetched_at)
    import_row = HalalStockImportModel(
        import_id=stable_id("hsi", source_checksum, seen_at.isoformat()),
        source_url=parse_result.source_url,
        source_checksum=source_checksum,
        fetched_at=seen_at,
        rows_seen=parse_result.rows_seen,
        rows_imported=parse_result.rows_imported,
        halal_count=parse_result.halal_count,
        haram_count=parse_result.haram_count,
        unknown_count=parse_result.unknown_count,
        duplicate_count=parse_result.duplicate_count,
        generated_yaml_path=generated_yaml_path,
        status="IMPORTED",
    )
    active_count, inactive_count = HalalStockComplianceRepository(session).replace_import(
        import_row=import_row,
        rows=list(parse_result.rows),
        seen_at=seen_at,
    )
    return import_row, active_count, inactive_count


def export_halal_nse_universe(
    session: Session,
    output_path: str | Path,
) -> HalalUniverseExportSummary:
    path = Path(output_path).expanduser()
    rows = HalalStockComplianceRepository(session).list_active(compliance_status="halal")
    entries: list[dict[str, object]] = []
    seen_symbols: dict[str, str] = {}
    duplicate_symbols: list[str] = []
    for row in rows:
        symbol = _clean_symbol(row.nse_code)
        if not symbol:
            continue
        if symbol in seen_symbols:
            duplicate_symbols.append(symbol)
            continue
        seen_symbols[symbol] = row.source_key
        entries.append(
            {
                "symbol": symbol,
                "name": row.name,
                "enabled": True,
                "providers": {
                    "kite": {
                        "exchange": "NSE",
                        "tradingsymbol": symbol,
                    }
                },
            }
        )

    if duplicate_symbols:
        symbols = ", ".join(sorted(set(duplicate_symbols)))
        raise HalalStockComplianceError(
            f"Cannot export halal NSE universe with duplicate NSE symbol(s): {symbols}"
        )

    entries.sort(key=lambda item: str(item["symbol"]))
    payload = {
        "universe_name": "halal_nse_cash",
        "default_exchange": "NSE",
        "default_segment": "EQUITY",
        "symbols": entries,
    }
    _atomic_write_validated_universe(path, payload)
    return HalalUniverseExportSummary(
        generated_yaml_path=str(path),
        exported_symbol_count=len(entries),
        symbols=tuple(str(entry["symbol"]) for entry in entries),
    )


def sync_halal_stocks(
    *,
    settings: Settings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    fetch_result: HalalStockFetchResult | None = None,
) -> HalalStockSyncSummary:
    settings = settings or get_settings()
    fetch = fetch_result or fetch_halal_stock_page(settings.taurus_halal_stock_source_url)
    parse_result = parse_halal_stock_rows(
        fetch.html,
        source_url=settings.taurus_halal_stock_source_url,
        table_id=settings.taurus_halal_stock_table_id,
    )
    if parse_result.rows_seen < settings.taurus_halal_stock_min_rows:
        raise HalalStockComplianceError(
            "HalalStock import row-count guard failed: "
            f"expected at least {settings.taurus_halal_stock_min_rows} rows, "
            f"found {parse_result.rows_seen}."
        )

    factory = session_factory or build_session_factory(settings)
    with factory() as session:
        import_row, active_count, inactive_count = import_halal_stock_compliance(
            session,
            parse_result,
            source_checksum=fetch.source_checksum,
            fetched_at=fetch.fetched_at,
            generated_yaml_path=settings.taurus_halal_stock_universe_path,
        )
        export_summary = export_halal_nse_universe(
            session,
            settings.taurus_halal_stock_universe_path,
        )
        import_row.generated_yaml_path = export_summary.generated_yaml_path
        session.commit()

    return HalalStockSyncSummary(
        import_id=import_row.import_id,
        source_url=parse_result.source_url,
        source_checksum=fetch.source_checksum,
        fetched_at=fetch.fetched_at,
        rows_seen=parse_result.rows_seen,
        rows_imported=parse_result.rows_imported,
        halal_count=parse_result.halal_count,
        haram_count=parse_result.haram_count,
        unknown_count=parse_result.unknown_count,
        duplicate_count=parse_result.duplicate_count,
        active_count=active_count,
        inactive_count=inactive_count,
        generated_yaml_path=export_summary.generated_yaml_path,
        exported_symbol_count=export_summary.exported_symbol_count,
    )


def _column_map(table: Tag) -> dict[str, int]:
    normalized_required_headers = {
        canonical: _header_key(label)
        for canonical, label in REQUIRED_HEADERS.items()
    }
    headers = table.find_all("th")
    available = [_clean_text(header.get_text(" ", strip=True)) for header in headers]
    by_key = {
        _header_key(label): index
        for index, label in enumerate(available)
    }
    missing = [
        REQUIRED_HEADERS[canonical]
        for canonical, key in normalized_required_headers.items()
        if key not in by_key
    ]
    if missing:
        raise HalalStockComplianceError(
            "Missing required HalalStock column(s): "
            f"{', '.join(missing)}. Available columns: {', '.join(available) or 'none'}."
        )
    return {
        canonical: by_key[key]
        for canonical, key in normalized_required_headers.items()
    }


def _parse_icon_status(
    cell: Tag,
    *,
    row_number: int,
    source_url: str,
) -> tuple[ComplianceStatus | None, str]:
    image = cell.find("img")
    if not isinstance(image, Tag):
        return None, ""
    src = str(image.get("src") or "").strip()
    icon_url = urljoin(source_url, src) if src else ""
    basename = Path(urlsplit(icon_url).path).name
    status = ICON_STATUS_BY_BASENAME.get(basename)
    if status is None:
        return None, icon_url
    return status, icon_url


def _dedupe_rows(rows: list[HalalStockRow]) -> tuple[list[HalalStockRow], int]:
    deduped: list[HalalStockRow] = []
    seen: dict[tuple[str, str, str, str], HalalStockRow] = {}
    duplicate_count = 0
    conflicts: list[str] = []
    for row in rows:
        existing = seen.get(row.identity_key)
        if existing is None:
            seen[row.identity_key] = row
            deduped.append(row)
            continue
        duplicate_count += 1
        if existing.duplicate_payload != row.duplicate_payload:
            conflicts.append(
                f"row {row.row_number} conflicts with row {existing.row_number} "
                f"for source key {row.source_key}"
            )

    if conflicts:
        raise HalalStockComplianceError(
            "Conflicting duplicate HalalStock row(s); refusing to write DB rows: "
            + "; ".join(conflicts[:20])
        )
    return deduped, duplicate_count


def _atomic_write_validated_universe(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serialized = yaml.safe_dump(
        payload,
        allow_unicode=False,
        sort_keys=False,
    )
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(serialized)
        load_market_data_universe(tmp_path)
        tmp_path.replace(path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _cell(cells: list[Tag], index: int) -> Tag:
    try:
        return cells[index]
    except IndexError as exc:
        raise HalalStockComplianceError(
            f"HalalStock row has {len(cells)} cells, expected at least {index + 1}."
        ) from exc


def _details_url(cell: Tag, *, source_url: str) -> str:
    anchor = cell.find("a")
    if not isinstance(anchor, Tag):
        return ""
    href = str(anchor.get("href") or "").strip()
    return urljoin(source_url, href) if href else ""


def _source_key(
    *,
    name: str,
    bse_code: str,
    nse_code: str,
    details_url: str,
) -> str:
    return stable_id(
        "hsc",
        _company_key(name),
        bse_code.upper(),
        nse_code.upper(),
        details_url,
    )


def _company_key(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", " ", value.upper()).strip()


def _clean_symbol(value: str) -> str:
    return _clean_text(value).upper()


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value)).strip()


def _header_key(value: str) -> str:
    return _clean_text(value).lower()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)
