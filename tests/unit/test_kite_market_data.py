from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from textwrap import dedent

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.data.providers.factory import build_market_data_provider
from taurus_core.data.providers.kite_market_data import KiteMarketDataProvider
from taurus_core.data.universe import load_market_data_universe
from taurus_core.db.repositories import (
    InstrumentProviderMappingRepository,
    InstrumentRepository,
    MarketPriceSnapshotRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.market_data import MarketDataProviderError


class TokenException(Exception):
    pass


class NetworkException(Exception):
    pass


class FakeKiteClient:
    def __init__(self) -> None:
        self.instrument_calls = 0
        self.historical_calls = 0
        self.ohlc_calls = 0
        self.fail_instruments_once = False
        self.historical_error: Exception | None = None

    def instruments(self, exchange: str | None = None) -> list[dict[str, object]]:
        self.instrument_calls += 1
        if self.fail_instruments_once and self.instrument_calls == 1:
            raise NetworkException("temporary network failure")
        return [
            {
                "instrument_token": 408065,
                "exchange": exchange or "NSE",
                "tradingsymbol": "INFY",
                "name": "Infosys Ltd",
                "segment": "NSE",
                "currency": "INR",
                "lot_size": 1,
                "tick_size": 0.05,
            },
            {
                "instrument_token": 2953217,
                "exchange": exchange or "NSE",
                "tradingsymbol": "TCS",
                "name": "Tata Consultancy Services Ltd",
                "segment": "NSE",
                "currency": "INR",
                "lot_size": 1,
                "tick_size": 0.05,
            },
        ]

    def historical_data(
        self,
        instrument_token: int | str,
        from_date: date,
        to_date: date,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict[str, object]]:
        self.historical_calls += 1
        if self.historical_error is not None:
            raise self.historical_error
        assert str(instrument_token) == "408065"
        assert interval == "day"
        return [
            {
                "date": date(2026, 5, 21),
                "open": 1500.1,
                "high": 1510.2,
                "low": 1495.3,
                "close": 1506.4,
                "volume": 1234567,
            }
        ]

    def ohlc(self, *instruments: object) -> dict[str, dict[str, object]]:
        self.ohlc_calls += 1
        keys = instruments[0] if instruments and isinstance(instruments[0], list) else list(instruments)
        assert keys == ["NSE:INFY"]
        return {
            "NSE:INFY": {
                "instrument_token": 408065,
                "last_price": 1507.5,
                "ohlc": {
                    "open": 1500.1,
                    "high": 1512.0,
                    "low": 1498.2,
                    "close": 1506.4,
                },
            }
        }


def test_kite_universe_loader_validates_and_normalizes(tmp_path: Path) -> None:
    path = _write_universe(
        tmp_path,
        """
        universe_name: custom
        default_exchange: NSE
        default_segment: EQUITY
        symbols:
          - symbol: infy
            name: Infosys Ltd
            enabled: true
            providers:
              kite:
                tradingsymbol: INFY
          - symbol: disabled
            enabled: false
          - symbol: tcs
            name: TCS Ltd
            enabled: true
        """,
    )

    universe = load_market_data_universe(path)

    assert universe.universe_name == "custom"
    assert universe.enabled_symbols() == ["INFY", "TCS"]
    assert universe.symbols[0].provider_value("kite", "exchange", universe.default_exchange) == "NSE"
    assert universe.symbols[1].providers == {}


def test_kite_universe_loader_rejects_empty_and_duplicate_symbols(tmp_path: Path) -> None:
    empty_path = _write_universe(tmp_path, "symbols: []")
    duplicate_path = _write_universe(
        tmp_path,
        """
        symbols:
          - symbol: infy
          - symbol: INFY
        """,
        filename="duplicate.yaml",
    )

    with pytest.raises(MarketDataProviderError, match="non-empty symbols"):
        load_market_data_universe(empty_path)
    with pytest.raises(MarketDataProviderError, match="Duplicate universe symbol"):
        load_market_data_universe(duplicate_path)


def test_kite_provider_requires_credentials_when_real_client_is_built(tmp_path: Path) -> None:
    settings = _settings(tmp_path, kite_api_key="", kite_access_token="")

    with pytest.raises(MarketDataProviderError, match="KITE_API_KEY and KITE_ACCESS_TOKEN"):
        build_market_data_provider(settings)


def test_fake_kite_client_maps_instruments_and_historical_candles(tmp_path: Path) -> None:
    provider = KiteMarketDataProvider(
        _settings(tmp_path),
        client=FakeKiteClient(),
        request_interval_seconds=0,
    )

    instruments = provider.list_instruments()
    candles = provider.get_historical_candles("infy", start_date=date(2026, 5, 1), end_date=date(2026, 5, 22))

    assert [instrument.symbol for instrument in instruments] == ["INFY", "TCS"]
    assert instruments[0].exchange == "NSE"
    assert candles[0].symbol == "INFY"
    assert candles[0].open == Decimal("1500.1")
    assert candles[0].source == "kite:historical:NSE"
    assert candles[0].data_available_time == datetime(2026, 5, 21, 18, tzinfo=timezone.utc)


def test_kite_sync_persists_provider_mappings(tmp_path: Path) -> None:
    settings = _settings(tmp_path, database_url=f"sqlite:///{tmp_path / 'sync.db'}")
    run_migrations(settings)
    provider = KiteMarketDataProvider(
        settings,
        client=FakeKiteClient(),
        request_interval_seconds=0,
    )
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        summary = provider.sync_instruments(session)

    with session_factory() as session:
        mapping = InstrumentProviderMappingRepository(session).get(provider="kite", symbol="infy")

    assert summary.instrument_count == 2
    assert mapping is not None
    assert mapping.provider_symbol == "INFY"
    assert mapping.instrument_token == "408065"


def test_fake_kite_client_maps_ohlc_snapshots_and_repository_latest(tmp_path: Path) -> None:
    settings = _settings(tmp_path, database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
    run_migrations(settings)
    provider = KiteMarketDataProvider(
        settings,
        client=FakeKiteClient(),
        request_interval_seconds=0,
    )
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        for instrument in provider.list_instruments():
            InstrumentRepository(session).upsert(instrument)
        snapshots = provider.get_latest_snapshots(["infy"])
        MarketPriceSnapshotRepository(session).insert_many(snapshots)
        session.commit()

    with session_factory() as session:
        latest = MarketPriceSnapshotRepository(session).latest(symbol="INFY")

    assert latest is not None
    assert latest.provider == "kite"
    assert latest.symbol == "INFY"
    assert latest.last_price == Decimal("1507.5000")
    assert latest.source == "kite:quote:NSE"


def test_data_api_returns_latest_persisted_quote_snapshot(tmp_path: Path) -> None:
    settings = _settings(tmp_path, database_url=f"sqlite:///{tmp_path / 'quotes.db'}")
    run_migrations(settings)
    provider = KiteMarketDataProvider(
        settings,
        client=FakeKiteClient(),
        request_interval_seconds=0,
    )
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        for instrument in provider.list_instruments():
            InstrumentRepository(session).upsert(instrument)
        MarketPriceSnapshotRepository(session).insert_many(provider.get_latest_snapshots(["INFY"]))
        session.commit()

    client = TestClient(create_app(settings))
    found = client.get("/data/quotes/latest?symbol=INFY")
    missing = client.get("/data/quotes/latest?symbol=RELIANCE")

    assert found.status_code == 200
    assert found.json()["symbol"] == "INFY"
    assert found.json()["provider"] == "kite"
    assert found.json()["source"] == "kite:quote:NSE"
    assert missing.status_code == 404


def test_kite_auth_failure_becomes_clear_provider_error(tmp_path: Path) -> None:
    client = FakeKiteClient()
    client.historical_error = TokenException("token expired")
    provider = KiteMarketDataProvider(
        _settings(tmp_path),
        client=client,
        request_interval_seconds=0,
    )

    with pytest.raises(MarketDataProviderError, match="access token is invalid or expired"):
        provider.get_historical_candles("INFY")


def test_kite_retry_uses_injected_sleeper_for_transient_errors(tmp_path: Path) -> None:
    client = FakeKiteClient()
    client.fail_instruments_once = True
    sleeps: list[float] = []
    provider = KiteMarketDataProvider(
        _settings(tmp_path),
        client=client,
        request_interval_seconds=0,
        retry_delay_seconds=0.25,
        sleep_func=sleeps.append,
    )

    instruments = provider.list_instruments()

    assert [instrument.symbol for instrument in instruments] == ["INFY", "TCS"]
    assert client.instrument_calls == 2
    assert sleeps == [0.25]


def _settings(tmp_path: Path, **overrides: object) -> Settings:
    values = {
        "taurus_market_data_provider": "kite",
        "taurus_market_data_universe_path": str(_write_universe(tmp_path)),
        "kite_api_key": "test-key",
        "kite_access_token": "test-token",
    }
    values.update(overrides)
    return Settings(**values)


def _write_universe(
    tmp_path: Path,
    content: str | None = None,
    *,
    filename: str = "universe.yaml",
) -> Path:
    path = tmp_path / filename
    path.write_text(
        dedent(
            content
            or """
            universe_name: kite_test
            default_exchange: NSE
            default_segment: EQUITY
            symbols:
              - symbol: INFY
                name: Infosys Ltd
                enabled: true
                providers:
                  kite:
                    exchange: NSE
                    tradingsymbol: INFY
              - symbol: TCS
                name: Tata Consultancy Services Ltd
                enabled: true
                providers:
                  kite:
                    exchange: NSE
                    tradingsymbol: TCS
            """
        ),
        encoding="utf-8",
    )
    return path
