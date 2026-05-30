from __future__ import annotations

from taurus_core.config import Settings
from taurus_core.data.providers.kite_market_data import KiteMarketDataProvider
from taurus_core.domain.market_data import MarketDataProvider, MarketDataProviderError

ProviderBuilder = type[KiteMarketDataProvider]

REAL_MARKET_DATA_PROVIDERS: dict[str, ProviderBuilder] = {
    "kite": KiteMarketDataProvider,
}


def build_market_data_provider(settings: Settings) -> MarketDataProvider:
    provider = settings.taurus_market_data_provider.lower()
    builder = REAL_MARKET_DATA_PROVIDERS.get(provider)
    if builder is not None:
        return builder(settings)
    raise MarketDataProviderError(
        "Unsupported market data provider: "
        f"{provider}. Supported real providers: {', '.join(sorted(REAL_MARKET_DATA_PROVIDERS))}."
    )
