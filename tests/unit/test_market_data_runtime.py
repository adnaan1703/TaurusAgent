from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.data.preflight import assert_kite_runtime_preflight
from taurus_core.data.providers.factory import REAL_MARKET_DATA_PROVIDERS, build_market_data_provider
from taurus_core.db.repositories import CandleRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle, MarketDataProviderError


def test_runtime_provider_registry_contains_only_kite() -> None:
    assert sorted(REAL_MARKET_DATA_PROVIDERS) == ["kite"]


def test_provider_factory_lists_supported_real_providers_for_unsupported_provider() -> None:
    settings = Settings.model_construct(taurus_market_data_provider="mock")

    with pytest.raises(MarketDataProviderError, match="Supported real providers: kite"):
        build_market_data_provider(settings)


def test_kite_preflight_rejects_legacy_mock_candles() -> None:
    settings = Settings()
    run_migrations(settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        InstrumentRepository(session).upsert(Instrument(symbol="INFY", name="Infosys Ltd"))
        CandleRepository(session).upsert(
            [
                DailyCandle(
                    symbol="INFY",
                    trade_date=date(2026, 5, 1),
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100.5"),
                    volume=1_000,
                    source="mock_market_data",
                )
            ]
        )
        session.commit()

    with session_factory() as session:
        with pytest.raises(MarketDataProviderError, match="legacy mock_market_data candle rows"):
            assert_kite_runtime_preflight(session)
