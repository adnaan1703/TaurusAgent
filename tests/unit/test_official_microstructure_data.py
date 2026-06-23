from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import inspect

from taurus_core.config import Settings
from taurus_core.data.official_microstructure import (
    OfficialMicrostructureReadinessRequest,
    build_official_microstructure_readiness,
    import_official_microstructure_csv,
    parse_official_microstructure_csv,
)
from taurus_core.db.repositories import OfficialSecurityMicrostructureRepository
from taurus_core.db.session import build_session_factory, create_engine_from_url
from taurus_core.domain.official_market_data import OfficialSecurityMicrostructure


def test_official_microstructure_schema_created(
    postgres_test_settings: Settings,
) -> None:
    engine = create_engine_from_url(postgres_test_settings.database_url)

    inspector = inspect(engine)

    assert "official_security_microstructure" in inspector.get_table_names()
    columns = {
        column["name"]
        for column in inspector.get_columns("official_security_microstructure")
    }
    assert {
        "symbol",
        "timeframe",
        "trade_date",
        "source",
        "source_url",
        "data_available_time",
        "delivery_quantity",
        "delivery_percentage",
        "price_band_percent",
        "upper_circuit_price",
        "lower_circuit_price",
        "circuit_status",
        "circuit_hit",
        "impact_cost_bps",
        "impact_cost_source_kind",
        "impact_cost_proxy_name",
        "average_trade_value",
        "turnover",
        "raw",
    } <= columns


def test_official_microstructure_repository_queries_without_lookahead(
    postgres_test_settings: Settings,
) -> None:
    session_factory = build_session_factory(postgres_test_settings)
    with session_factory() as session:
        repo = OfficialSecurityMicrostructureRepository(session)
        repo.upsert(
            [
                _microstructure_row(
                    trade_date=date(2024, 1, 2),
                    delivery_quantity=1000,
                    available=datetime(2024, 1, 3, 9, tzinfo=timezone.utc),
                ),
                _microstructure_row(
                    trade_date=date(2024, 1, 3),
                    delivery_quantity=2000,
                    available=datetime(2024, 1, 4, 9, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

    with session_factory() as session:
        repo = OfficialSecurityMicrostructureRepository(session)
        first_available = repo.latest_as_of(
            symbol="INFY",
            as_of=datetime(2024, 1, 3, 12, tzinfo=timezone.utc),
        )
        future_blocked = repo.latest_as_of(
            symbol="INFY",
            as_of=datetime(2024, 1, 4, 8, tzinfo=timezone.utc),
        )
        second_available = repo.latest_as_of(
            symbol="INFY",
            as_of=datetime(2024, 1, 4, 10, tzinfo=timezone.utc),
        )

        assert first_available is not None
        assert first_available.trade_date == date(2024, 1, 2)
        assert future_blocked is not None
        assert future_blocked.trade_date == date(2024, 1, 2)
        assert second_available is not None
        assert second_available.trade_date == date(2024, 1, 3)

        repo.upsert(
            [
                _microstructure_row(
                    trade_date=date(2024, 1, 2),
                    delivery_quantity=1500,
                    available=datetime(2024, 1, 3, 9, tzinfo=timezone.utc),
                )
            ]
        )
        session.commit()
        rows = repo.get_by_symbol_and_date_range(symbol="INFY")

        assert len(rows) == 2
        assert rows[0].delivery_quantity == 1500
        assert rows[0].price_band_percent == Decimal("20.00000000")


def test_official_microstructure_csv_import_persists_v2b_inputs(
    tmp_path: Path,
    postgres_test_settings: Settings,
) -> None:
    csv_path = tmp_path / "official_microstructure.csv"
    csv_path.write_text(
        "\n".join(
            [
                "symbol,trade_date,delivery_qty,delivery_pct,price_band_percent,"
                "circuit_status,circuit_hit,impact_cost_bps,impact_cost_source_kind,"
                "impact_cost_proxy_name,average_trade_value,turnover,source,"
                "data_available_time",
                "INFY,2024-01-02,12345,51.25,20,upper_circuit,true,25,proxy,"
                "avg_trade_value_proxy,12500000,25000000,nse,"
                "2024-01-03T09:00:00+00:00",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    session_factory = build_session_factory(postgres_test_settings)
    with session_factory() as session:
        summary = import_official_microstructure_csv(
            session,
            csv_path=csv_path,
            source="nse",
        )

    with session_factory() as session:
        repo = OfficialSecurityMicrostructureRepository(session)
        rows = repo.get_by_symbol_and_date_range(symbol="INFY")

    assert summary.row_count == 1
    assert summary.rows_by_available_family == {
        "delivery": 1,
        "circuit": 1,
        "tradability": 1,
    }
    assert summary.impact_cost_source_kinds == {"proxy": 1}
    assert len(rows) == 1
    assert rows[0].delivery_quantity == 12345
    assert rows[0].circuit_status == "upper_circuit"
    assert rows[0].circuit_hit is True
    assert rows[0].impact_cost_source_kind == "proxy"
    assert rows[0].impact_cost_proxy_name == "avg_trade_value_proxy"


def test_official_microstructure_readiness_reports_missing_family(
    postgres_test_settings: Settings,
) -> None:
    session_factory = build_session_factory(postgres_test_settings)
    with session_factory() as session:
        repo = OfficialSecurityMicrostructureRepository(session)
        repo.upsert(
            [
                _microstructure_row(
                    trade_date=date(2024, 1, 1),
                    price_band_percent=None,
                ),
                _microstructure_row(
                    trade_date=date(2024, 1, 2),
                    price_band_percent=None,
                ),
            ]
        )
        session.commit()

        request = OfficialMicrostructureReadinessRequest(
            symbols=("INFY",),
            required_families=("delivery", "circuit", "tradability"),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
        )
        missing = build_official_microstructure_readiness(session, request)

        repo.upsert(
            [
                _microstructure_row(
                    trade_date=date(2024, 1, 1),
                    source="nse_price_band_csv",
                    delivery_quantity=None,
                    delivery_percentage=None,
                    circuit_status="none",
                ),
                _microstructure_row(
                    trade_date=date(2024, 1, 2),
                    source="nse_price_band_csv",
                    delivery_quantity=None,
                    delivery_percentage=None,
                    circuit_status="none",
                ),
            ]
        )
        session.commit()
        ready = build_official_microstructure_readiness(session, request)

    assert missing.status == "missing_official_microstructure_data"
    assert missing.missing_requirements == (
        {"family": "circuit", "symbol": "INFY", "reason": "missing_history"},
    )
    assert missing.artifact["next_actions"]
    assert ready.status == "sufficient"
    assert ready.missing_requirements == ()


def test_official_microstructure_proxy_rows_must_name_proxy(
    tmp_path: Path,
) -> None:
    csv_path = tmp_path / "official_microstructure_proxy.csv"
    csv_path.write_text(
        "\n".join(
            [
                "symbol,trade_date,impact_cost_bps,impact_cost_source_kind",
                "INFY,2024-01-02,25,proxy",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="impact_cost_proxy_name"):
        parse_official_microstructure_csv(csv_path=csv_path)


def _microstructure_row(
    *,
    trade_date: date,
    symbol: str = "INFY",
    source: str = "nse_security_wise_csv",
    available: datetime | None = None,
    delivery_quantity: int | None = 1000,
    delivery_percentage: Decimal | None = Decimal("51.25"),
    price_band_percent: Decimal | None = Decimal("20"),
    circuit_status: str | None = None,
) -> OfficialSecurityMicrostructure:
    return OfficialSecurityMicrostructure(
        symbol=symbol,
        trade_date=trade_date,
        source=source,
        data_available_time=available,
        delivery_quantity=delivery_quantity,
        delivery_percentage=delivery_percentage,
        price_band_percent=price_band_percent,
        circuit_status=circuit_status,
        impact_cost_bps=Decimal("25"),
        impact_cost_source_kind="proxy",
        impact_cost_proxy_name="avg_trade_value_proxy",
        average_trade_value=Decimal("12500000"),
        turnover=Decimal("25000000"),
        raw={"fixture": True},
    )
