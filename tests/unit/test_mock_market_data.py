from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.config import Settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.repositories import CandleRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory


def test_mock_market_data_provider_is_deterministic() -> None:
    first_provider = MockMarketDataProvider(seed=7, candle_count=252)
    second_provider = MockMarketDataProvider(seed=7, candle_count=252)

    assert first_provider.list_instruments() == second_provider.list_instruments()
    assert len(first_provider.list_instruments()) == 10
    assert first_provider.get_daily_candles("INFY") == second_provider.get_daily_candles(
        "INFY"
    )
    assert len(first_provider.get_daily_candles("INFY")) == 252


def test_mock_market_data_provider_returns_quote_snapshots() -> None:
    provider = MockMarketDataProvider(seed=7, candle_count=252)

    snapshots = provider.get_latest_snapshots(["infy"])
    latest = provider.get_latest_candle("INFY")

    assert latest is not None
    assert len(snapshots) == 1
    assert snapshots[0].symbol == "INFY"
    assert snapshots[0].provider == "mock"
    assert snapshots[0].last_price == latest.close
    assert snapshots[0].source == "mock_market_data:latest_candle"


def test_seed_mock_data_is_idempotent_and_repositories_can_read(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    provider = MockMarketDataProvider(seed=42, candle_count=252)

    with session_factory() as session:
        first_summary = seed_mock_data(session, provider)

    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        candle_repo = CandleRepository(session)
        instruments = instrument_repo.list(active_only=True)
        infy_candles = candle_repo.get_by_symbol_and_date_range(symbol="INFY")
        first_snapshot = [
            (candle.trade_date, candle.open, candle.high, candle.low, candle.close, candle.volume)
            for candle in infy_candles
        ]

    with session_factory() as session:
        second_summary = seed_mock_data(session, provider)

    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        candle_repo = CandleRepository(session)
        instruments_after_second_seed = instrument_repo.list(active_only=True)
        infy_candles_after_second_seed = candle_repo.get_by_symbol_and_date_range(symbol="INFY")
        second_snapshot = [
            (candle.trade_date, candle.open, candle.high, candle.low, candle.close, candle.volume)
            for candle in infy_candles_after_second_seed
        ]

    assert first_summary == second_summary
    assert len(instruments) == 10
    assert len(instruments_after_second_seed) == 10
    assert all(
        first_summary.candles_per_symbol[symbol] == 252
        for symbol in first_summary.candles_per_symbol
    )
    assert len(infy_candles) == 252
    assert len(infy_candles_after_second_seed) == 252
    assert first_snapshot == second_snapshot


def test_data_api_returns_seeded_instruments_and_candles(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_mock_data(session, MockMarketDataProvider(seed=42, candle_count=252))

    client = TestClient(create_app(settings))

    instruments_response = client.get("/data/instruments")
    assert instruments_response.status_code == 200
    instruments = instruments_response.json()
    assert len(instruments) == 10
    assert {instrument["symbol"] for instrument in instruments} >= {"INFY", "RELIANCE", "TCS"}

    instrument_response = client.get("/data/instruments/infy")
    assert instrument_response.status_code == 200
    assert instrument_response.json()["symbol"] == "INFY"

    candles_response = client.get("/data/candles?symbol=INFY&timeframe=1d")
    assert candles_response.status_code == 200
    candles = candles_response.json()
    assert len(candles) == 252
    assert candles[0]["symbol"] == "INFY"
    assert candles[0]["timeframe"] == "1d"


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
