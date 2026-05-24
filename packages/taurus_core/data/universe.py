from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from taurus_core.domain.market_data import MarketDataProviderError


@dataclass(frozen=True, slots=True)
class UniverseProviderHint:
    provider: str
    values: dict[str, Any]


@dataclass(frozen=True, slots=True)
class UniverseSymbol:
    symbol: str
    name: str
    exchange: str
    segment: str
    providers: dict[str, UniverseProviderHint]

    def provider_value(self, provider: str, key: str, default: str | None = None) -> str | None:
        hint = self.providers.get(provider)
        if hint is None:
            return default
        value = hint.values.get(key)
        if value is None:
            return default
        return str(value).strip() or default


@dataclass(frozen=True, slots=True)
class MarketDataUniverse:
    universe_name: str
    default_exchange: str
    default_segment: str
    symbols: tuple[UniverseSymbol, ...]
    source_path: Path

    def enabled_symbols(self) -> list[str]:
        return [entry.symbol for entry in self.symbols]


def load_market_data_universe(path: str | Path) -> MarketDataUniverse:
    source_path = Path(path).expanduser()
    if not source_path.exists():
        raise MarketDataProviderError(f"Market data universe file not found: {source_path}")
    if not source_path.is_file():
        raise MarketDataProviderError(f"Market data universe path is not a file: {source_path}")

    with source_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    if not isinstance(payload, dict):
        raise MarketDataProviderError(f"Market data universe must be a YAML mapping: {source_path}")

    universe_name = _optional_str(payload.get("universe_name")) or source_path.stem
    default_exchange = (_optional_str(payload.get("default_exchange")) or "NSE").upper()
    default_segment = (_optional_str(payload.get("default_segment")) or "EQUITY").upper()
    raw_symbols = payload.get("symbols")
    if not isinstance(raw_symbols, list) or not raw_symbols:
        raise MarketDataProviderError("Market data universe requires a non-empty symbols list.")

    symbols: list[UniverseSymbol] = []
    seen: set[str] = set()
    for index, raw_entry in enumerate(raw_symbols, start=1):
        if not isinstance(raw_entry, dict):
            raise MarketDataProviderError(f"Universe symbol entry {index} must be a mapping.")
        if raw_entry.get("enabled", True) is False:
            continue

        symbol = _optional_str(raw_entry.get("symbol"))
        if symbol is None:
            raise MarketDataProviderError(f"Universe symbol entry {index} is missing symbol.")
        canonical_symbol = symbol.upper()
        if canonical_symbol in seen:
            raise MarketDataProviderError(f"Duplicate universe symbol: {canonical_symbol}")
        seen.add(canonical_symbol)

        raw_providers = raw_entry.get("providers", {})
        if raw_providers is None:
            raw_providers = {}
        if not isinstance(raw_providers, dict):
            raise MarketDataProviderError(
                f"Universe symbol {canonical_symbol} providers must be a mapping."
            )

        providers = {
            str(provider).lower(): UniverseProviderHint(
                provider=str(provider).lower(),
                values=dict(values or {}),
            )
            for provider, values in raw_providers.items()
            if isinstance(values, dict)
        }
        symbols.append(
            UniverseSymbol(
                symbol=canonical_symbol,
                name=_optional_str(raw_entry.get("name")) or f"{canonical_symbol} Equity",
                exchange=(_optional_str(raw_entry.get("exchange")) or default_exchange).upper(),
                segment=(_optional_str(raw_entry.get("segment")) or default_segment).upper(),
                providers=providers,
            )
        )

    if not symbols:
        raise MarketDataProviderError("Market data universe has no enabled symbols.")

    return MarketDataUniverse(
        universe_name=universe_name,
        default_exchange=default_exchange,
        default_segment=default_segment,
        symbols=tuple(symbols),
        source_path=source_path,
    )


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
