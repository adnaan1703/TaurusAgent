from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml
from sqlalchemy import select

from scripts.migrate import run_migrations
from taurus_core.compliance import (
    HalalStockComplianceError,
    HalalStockFetchResult,
    export_halal_nse_universe,
    import_halal_stock_compliance,
    parse_halal_stock_rows,
    sync_halal_stocks,
)
from taurus_core.config import Settings
from taurus_core.data.universe import load_market_data_universe
from taurus_core.db.models import HalalStockComplianceModel, HalalStockImportModel
from taurus_core.db.session import build_session_factory

SOURCE_URL = "https://example.test/halal-list/"
FETCHED_AT = datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc)


def test_halal_parser_maps_icons_dedupes_and_ignores_duplicate_table() -> None:
    html = _table_html(
        [
            _row("yes", "Alpha Foods Ltd", "ALPHA", "ALPHA", "Food Products", "/alpha"),
            _row("no", "Beta Finance Ltd", "BETA", "BETA", "Finance", "/beta"),
            _row("yes", "Gamma Tools Ltd", "GAMMA", "", "Engineering", "/gamma"),
            _row("yes", "Alpha Foods Ltd", "ALPHA", "ALPHA", "Food Products", "/alpha"),
        ],
        trailing_html=_table_html(
            [_row("unknown", "Should Be Ignored Ltd", "IGN", "IGN", "Other", "/ignored")]
        ),
    )

    result = parse_halal_stock_rows(html, source_url=SOURCE_URL)

    assert result.rows_seen == 4
    assert result.rows_imported == 3
    assert result.halal_count == 3
    assert result.haram_count == 1
    assert result.duplicate_count == 1
    assert [row.compliance_status for row in result.rows] == ["halal", "haram", "halal"]
    assert result.rows[0].details_url == "https://example.test/alpha"


def test_halal_parser_rejects_unknown_status_icons() -> None:
    html = _table_html(
        [_row("unknown", "Alpha Foods Ltd", "ALPHA", "ALPHA", "Food Products", "/alpha")]
    )

    with pytest.raises(HalalStockComplianceError, match="Unknown HalalStock status icon"):
        parse_halal_stock_rows(html, source_url=SOURCE_URL)


def test_halal_parser_rejects_missing_or_renamed_required_columns() -> None:
    html = _table_html(
        [_row("yes", "Alpha Foods Ltd", "ALPHA", "ALPHA", "Food Products", "/alpha")],
        headers=("Halal", "NAME", "BSE Code", "NSECode", "Industry", "More"),
    )

    with pytest.raises(HalalStockComplianceError, match="BSE-ID"):
        parse_halal_stock_rows(html, source_url=SOURCE_URL)


def test_halal_import_upserts_rows_marks_missing_inactive_and_tracks_status_changes(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    session_factory = _prepare_db(settings)
    first = parse_halal_stock_rows(
        _table_html(
            [
                _row("yes", "Alpha Foods Ltd", "ALPHA", "ALPHA", "Food Products", "/alpha"),
                _row("no", "Beta Finance Ltd", "BETA", "BETA", "Finance", "/beta"),
                _row("yes", "Gamma Tools Ltd", "GAMMA", "", "Engineering", "/gamma"),
            ]
        ),
        source_url=SOURCE_URL,
    )
    second_fetched_at = datetime(2026, 5, 25, 9, 0, tzinfo=timezone.utc)
    second = parse_halal_stock_rows(
        _table_html(
            [
                _row("no", "Alpha Foods Ltd", "ALPHA", "ALPHA", "Food Products", "/alpha"),
                _row("yes", "Gamma Tools Ltd", "GAMMA", "", "Engineering", "/gamma"),
                _row("yes", "Delta Health Ltd", "DELTA", "DELTA", "Healthcare", "/delta"),
            ]
        ),
        source_url=SOURCE_URL,
    )

    with session_factory() as session:
        import_halal_stock_compliance(
            session,
            first,
            source_checksum="first",
            fetched_at=FETCHED_AT,
        )
        session.commit()

    with session_factory() as session:
        _, active_count, inactive_count = import_halal_stock_compliance(
            session,
            second,
            source_checksum="second",
            fetched_at=second_fetched_at,
        )
        session.commit()

    with session_factory() as session:
        rows = {
            row.name: row
            for row in session.scalars(select(HalalStockComplianceModel))
        }
        import_count = len(list(session.scalars(select(HalalStockImportModel))))

    assert active_count == 3
    assert inactive_count == 1
    assert import_count == 2
    assert rows["Alpha Foods Ltd"].compliance_status == "haram"
    assert _iso(rows["Alpha Foods Ltd"].status_changed_at).startswith("2026-05-25T09:00:00")
    assert rows["Gamma Tools Ltd"].active is True
    assert _iso(rows["Gamma Tools Ltd"].status_changed_at).startswith("2026-05-24T09:00:00")
    assert rows["Beta Finance Ltd"].active is False


def test_halal_export_excludes_haram_and_missing_nse_and_loads_universe(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    session_factory = _prepare_db(settings)
    parse_result = parse_halal_stock_rows(
        _table_html(
            [
                _row("yes", "Alpha Foods Ltd", "ALPHA", "ALPHA", "Food Products", "/alpha"),
                _row("no", "Beta Finance Ltd", "BETA", "BETA", "Finance", "/beta"),
                _row("yes", "Gamma Tools Ltd", "GAMMA", "", "Engineering", "/gamma"),
            ]
        ),
        source_url=SOURCE_URL,
    )
    output_path = tmp_path / "halal_nse_cash.yaml"

    with session_factory() as session:
        import_halal_stock_compliance(
            session,
            parse_result,
            source_checksum="export",
            fetched_at=FETCHED_AT,
        )
        export = export_halal_nse_universe(session, output_path)
        session.commit()

    universe = load_market_data_universe(output_path)
    payload = yaml.safe_load(output_path.read_text(encoding="utf-8"))

    assert export.exported_symbol_count == 1
    assert universe.enabled_symbols() == ["ALPHA"]
    assert payload["symbols"][0]["providers"]["kite"]["tradingsymbol"] == "ALPHA"


def test_halal_export_rejects_duplicate_nse_symbols(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    session_factory = _prepare_db(settings)
    parse_result = parse_halal_stock_rows(
        _table_html(
            [
                _row("yes", "Alpha Foods Ltd", "ALPHA", "DUPL", "Food Products", "/alpha"),
                _row("yes", "Alpha Foods New Ltd", "ALPHAN", "DUPL", "Food Products", "/alpha-new"),
            ]
        ),
        source_url=SOURCE_URL,
    )

    with session_factory() as session:
        import_halal_stock_compliance(
            session,
            parse_result,
            source_checksum="dupe",
            fetched_at=FETCHED_AT,
        )
        with pytest.raises(HalalStockComplianceError, match="duplicate NSE symbol"):
            export_halal_nse_universe(session, tmp_path / "dupe.yaml")


def test_halal_sync_uses_fetch_result_and_row_guard(tmp_path: Path) -> None:
    settings = _settings(tmp_path, min_rows=2)
    session_factory = _prepare_db(settings)
    fetch = HalalStockFetchResult(
        source_url=SOURCE_URL,
        final_url=SOURCE_URL,
        html=_table_html(
            [
                _row("yes", "Alpha Foods Ltd", "ALPHA", "ALPHA", "Food Products", "/alpha"),
                _row("no", "Beta Finance Ltd", "BETA", "BETA", "Finance", "/beta"),
            ]
        ),
        source_checksum="fetch-checksum",
        fetched_at=FETCHED_AT,
        content_length=100,
    )

    summary = sync_halal_stocks(
        settings=settings,
        session_factory=session_factory,
        fetch_result=fetch,
    )

    assert summary.rows_seen == 2
    assert summary.exported_symbol_count == 1
    assert Path(summary.generated_yaml_path).exists()


def _prepare_db(settings: Settings):
    run_migrations(settings)
    return build_session_factory(settings)


def _settings(tmp_path: Path, *, min_rows: int = 1) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'taurus.db'}",
        taurus_halal_stock_min_rows=min_rows,
        taurus_halal_stock_universe_path=str(tmp_path / "halal_nse_cash.yaml"),
    )


def _row(
    status: str,
    name: str,
    bse_code: str,
    nse_code: str,
    industry: str,
    href: str,
) -> str:
    icon = {
        "yes": "https://halalstock.in/wp-content/uploads/2021/06/hs-yes.jpg",
        "no": "https://halalstock.in/wp-content/uploads/2021/06/hs-no.jpg",
        "unknown": "https://halalstock.in/wp-content/uploads/2021/06/hs-maybe.jpg",
    }[status]
    return (
        "<tr>"
        f'<td><img src="{icon}" /></td>'
        f"<td>{name}</td>"
        f"<td>{bse_code}</td>"
        f"<td>{nse_code}</td>"
        f"<td>{industry}</td>"
        f'<td><a href="{href}">More</a></td>'
        "</tr>"
    )


def _table_html(
    rows: list[str],
    *,
    headers: tuple[str, ...] = ("Halal", "NAME", "BSE-ID", "NSECode", "Industry", "More"),
    trailing_html: str = "",
) -> str:
    header_html = "".join(f"<th>{header}</th>" for header in headers)
    return (
        '<table id="tablepress-24">'
        f"<thead><tr>{header_html}</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
        f"{trailing_html}"
    )


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
