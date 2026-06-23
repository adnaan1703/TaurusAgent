from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import inspect

from taurus_core.config import Settings
from taurus_core.data.official_indices import (
    OfficialIndexReadinessRequest,
    build_official_index_readiness,
    import_official_index_csv,
)
from taurus_core.db.repositories import OfficialIndexCandleRepository
from taurus_core.db.session import build_session_factory, create_engine_from_url
from taurus_core.domain.official_market_data import OfficialIndexCandle


def test_official_index_schema_created(postgres_test_settings: Settings) -> None:
    engine = create_engine_from_url(postgres_test_settings.database_url)

    inspector = inspect(engine)

    assert "official_index_candles" in inspector.get_table_names()
    columns = {
        column["name"] for column in inspector.get_columns("official_index_candles")
    }
    assert {
        "index_symbol",
        "index_name",
        "index_family",
        "timeframe",
        "trade_date",
        "open",
        "high",
        "low",
        "close",
        "source",
        "source_url",
        "data_available_time",
        "raw",
    } <= columns


def test_official_index_repository_upserts_and_queries_without_lookahead(
    postgres_test_settings: Settings,
) -> None:
    session_factory = build_session_factory(postgres_test_settings)
    with session_factory() as session:
        repo = OfficialIndexCandleRepository(session)
        repo.upsert(
            [
                _index_candle(
                    trade_date=date(2024, 1, 2),
                    close=Decimal("101"),
                    available=datetime(2024, 1, 3, 9, tzinfo=timezone.utc),
                ),
                _index_candle(
                    trade_date=date(2024, 1, 3),
                    close=Decimal("102"),
                    available=datetime(2024, 1, 4, 9, tzinfo=timezone.utc),
                ),
            ]
        )
        session.commit()

    with session_factory() as session:
        repo = OfficialIndexCandleRepository(session)
        first_available = repo.latest_as_of(
            index_symbol="NIFTY_50",
            as_of=datetime(2024, 1, 3, 12, tzinfo=timezone.utc),
        )
        future_blocked = repo.latest_as_of(
            index_symbol="NIFTY_50",
            as_of=datetime(2024, 1, 4, 8, tzinfo=timezone.utc),
        )
        second_available = repo.latest_as_of(
            index_symbol="NIFTY_50",
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
                _index_candle(
                    trade_date=date(2024, 1, 2),
                    close=Decimal("111"),
                    available=datetime(2024, 1, 3, 9, tzinfo=timezone.utc),
                )
            ]
        )
        session.commit()
        rows = repo.get_by_index_and_date_range(index_symbol="NIFTY_50")

        assert len(rows) == 2
        assert rows[0].close == Decimal("111.0000")


def test_official_index_csv_import_persists_benchmark_sector_and_vix(
    tmp_path: Path,
    postgres_test_settings: Settings,
) -> None:
    csv_path = tmp_path / "official_indices.csv"
    csv_path.write_text(
        "\n".join(
            [
                "index_symbol,index_name,index_family,trade_date,open,high,low,close,source,data_available_time",
                "NIFTY_50,Nifty 50,benchmark,2024-01-02,100,104,99,103,nse,2024-01-03T09:00:00+00:00",
                "NIFTY_IT,Nifty IT,sector,2024-01-02,200,205,198,204,nse,2024-01-03T09:00:00+00:00",
                "INDIA_VIX,India VIX,volatility,2024-01-02,12,13,11,12.5,nse,2024-01-03T09:00:00+00:00",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    session_factory = build_session_factory(postgres_test_settings)
    with session_factory() as session:
        summary = import_official_index_csv(
            session,
            csv_path=csv_path,
            source="nse",
        )

    with session_factory() as session:
        repo = OfficialIndexCandleRepository(session)
        sector_rows = repo.get_by_index_and_date_range(
            index_symbol="NIFTY_IT",
            index_family="sector",
        )
        vix_rows = repo.get_by_index_and_date_range(
            index_symbol="INDIA_VIX",
            index_family="volatility",
        )

    assert summary.row_count == 3
    assert summary.rows_by_family == {
        "benchmark": 1,
        "sector": 1,
        "volatility": 1,
    }
    assert len(sector_rows) == 1
    assert len(vix_rows) == 1
    assert vix_rows[0].close == Decimal("12.5000")


def test_official_index_readiness_reports_missing_and_ready_families(
    postgres_test_settings: Settings,
) -> None:
    session_factory = build_session_factory(postgres_test_settings)
    with session_factory() as session:
        repo = OfficialIndexCandleRepository(session)
        repo.upsert(
            [
                _index_candle(trade_date=date(2024, 1, 1), close=Decimal("100")),
                _index_candle(trade_date=date(2024, 1, 2), close=Decimal("101")),
                _index_candle(
                    index_symbol="INDIA_VIX",
                    index_name="India VIX",
                    index_family="volatility",
                    trade_date=date(2024, 1, 1),
                    close=Decimal("12"),
                ),
                _index_candle(
                    index_symbol="INDIA_VIX",
                    index_name="India VIX",
                    index_family="volatility",
                    trade_date=date(2024, 1, 2),
                    close=Decimal("11"),
                ),
            ]
        )
        session.commit()

        request = OfficialIndexReadinessRequest(
            benchmark_symbols=("NIFTY_50",),
            sector_symbols=("NIFTY_IT",),
            volatility_symbols=("INDIA_VIX",),
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 2),
        )
        missing = build_official_index_readiness(session, request)

        repo.upsert(
            [
                _index_candle(
                    index_symbol="NIFTY_IT",
                    index_name="Nifty IT",
                    index_family="sector",
                    trade_date=date(2024, 1, 1),
                    close=Decimal("200"),
                ),
                _index_candle(
                    index_symbol="NIFTY_IT",
                    index_name="Nifty IT",
                    index_family="sector",
                    trade_date=date(2024, 1, 2),
                    close=Decimal("201"),
                ),
            ]
        )
        session.commit()
        ready = build_official_index_readiness(session, request)

    assert missing.status == "missing_official_index_data"
    assert missing.missing_requirements == (
        {"family": "sector", "symbol": "NIFTY_IT", "reason": "missing_history"},
    )
    assert missing.artifact["next_actions"]
    assert ready.status == "sufficient"
    assert ready.missing_requirements == ()


def _index_candle(
    *,
    trade_date: date,
    close: Decimal,
    index_symbol: str = "NIFTY_50",
    index_name: str = "Nifty 50",
    index_family: str = "benchmark",
    available: datetime | None = None,
) -> OfficialIndexCandle:
    return OfficialIndexCandle(
        index_symbol=index_symbol,
        index_name=index_name,
        index_family=index_family,
        trade_date=trade_date,
        open=close,
        high=close,
        low=close,
        close=close,
        source="nse",
        data_available_time=available,
        raw={"fixture": True},
    )
