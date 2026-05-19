from __future__ import annotations

from pathlib import Path

from taurus_core.config import Settings
from taurus_core.data.providers.csv_market_data import (
    CSVMarketDataProvider,
    DisabledExternalMarketDataProvider,
)
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.domain.market_data import MarketDataProvider, MarketDataProviderError


def build_market_data_provider(
    settings: Settings,
    *,
    csv_path: str | Path | None = None,
    directory: str | Path | None = None,
) -> MarketDataProvider:
    provider = settings.taurus_market_data_provider.lower()
    if provider == "mock":
        return MockMarketDataProvider(
            seed=settings.taurus_mock_seed,
            candle_count=settings.taurus_mock_candle_count,
        )
    if provider == "csv":
        csv_path = csv_path or settings.taurus_price_csv_path or None
        directory = directory or settings.taurus_price_csv_dir or None
        return CSVMarketDataProvider(csv_path=csv_path, directory=directory)
    if provider == "external":
        return DisabledExternalMarketDataProvider()
    raise MarketDataProviderError(f"Unsupported market data provider: {provider}")
