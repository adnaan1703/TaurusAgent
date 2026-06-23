from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from taurus_core.features.store import (
    FeatureSnapshot,
    TECHNICAL_OHLCV_V2_FEATURE_VERSION,
)

TECHNICAL_CONTEXT_VALUE = Decimal("0.00000001")
HIGHER_IS_BETTER = "higher_is_better"
LOWER_IS_BETTER = "lower_is_better"

DEFAULT_TECHNICAL_CONTEXT_FEATURES = (
    "return_20d",
    "return_63d",
    "return_126d",
    "return_252d",
    "vol_adjusted_return_63d",
    "vol_adjusted_return_126d",
    "vol_adjusted_return_252d",
    "macd_histogram_12_26_9",
    "adx_14",
    "plus_di_14",
    "minus_di_14",
    "rsi_14",
    "bollinger_percent_b_20",
    "bollinger_bandwidth_20",
    "breakout_high_distance_20d",
    "breakout_high_distance_50d",
    "breakout_high_distance_252d",
    "distance_from_52w_high",
    "atr_percent_14",
    "volatility_20",
    "volatility_63",
    "volatility_126",
    "volatility_252",
    "volume_z_score_20",
    "turnover",
    "avg_traded_value_20",
    "avg_traded_value_63",
    "turnover_z_score_20",
)

DEFAULT_TECHNICAL_CONTEXT_RANK_DIRECTIONS: Mapping[str, str] = MappingProxyType(
    {
        "minus_di_14": LOWER_IS_BETTER,
        "atr_percent_14": LOWER_IS_BETTER,
        "volatility_20": LOWER_IS_BETTER,
        "volatility_63": LOWER_IS_BETTER,
        "volatility_126": LOWER_IS_BETTER,
        "volatility_252": LOWER_IS_BETTER,
        "bollinger_bandwidth_20": LOWER_IS_BETTER,
    }
)


@dataclass(frozen=True, slots=True)
class TechnicalFeatureContext:
    feature_name: str
    value: Decimal
    rank: int
    percentile: Decimal
    z_score: Decimal
    directional_z_score: Decimal
    eligible_count: int
    rank_direction: str


@dataclass(frozen=True, slots=True)
class TechnicalSymbolContext:
    symbol: str
    snapshot_id: str | None
    as_of_date: date | None
    feature_time: date | None
    features: Mapping[str, TechnicalFeatureContext] = field(default_factory=dict)
    missing_features: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "features", MappingProxyType(dict(self.features)))
        object.__setattr__(self, "missing_features", tuple(self.missing_features))

    def get(self, feature_name: str) -> TechnicalFeatureContext | None:
        return self.features.get(feature_name)


@dataclass(frozen=True, slots=True)
class UniverseTechnicalContext:
    profile_name: str
    as_of_date: date | None
    feature_names: tuple[str, ...]
    symbols: tuple[str, ...]
    universe_size: int
    symbols_by_feature: Mapping[str, tuple[str, ...]]
    missing_symbols_by_feature: Mapping[str, tuple[str, ...]]
    rank_directions: Mapping[str, str]
    symbol_contexts: Mapping[str, TechnicalSymbolContext]
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_names", tuple(self.feature_names))
        object.__setattr__(self, "symbols", tuple(self.symbols))
        object.__setattr__(
            self,
            "symbols_by_feature",
            MappingProxyType(
                {feature: tuple(symbols) for feature, symbols in self.symbols_by_feature.items()}
            ),
        )
        object.__setattr__(
            self,
            "missing_symbols_by_feature",
            MappingProxyType(
                {
                    feature: tuple(symbols)
                    for feature, symbols in self.missing_symbols_by_feature.items()
                }
            ),
        )
        object.__setattr__(self, "rank_directions", MappingProxyType(dict(self.rank_directions)))
        object.__setattr__(
            self,
            "symbol_contexts",
            MappingProxyType(dict(self.symbol_contexts)),
        )
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def for_symbol(self, symbol: str) -> TechnicalSymbolContext | None:
        return self.symbol_contexts.get(symbol.upper())

    def feature_for_symbol(
        self,
        symbol: str,
        feature_name: str,
    ) -> TechnicalFeatureContext | None:
        symbol_context = self.for_symbol(symbol)
        if symbol_context is None:
            return None
        return symbol_context.get(feature_name)


def build_universe_technical_context(
    features_by_symbol: Mapping[str, FeatureSnapshot],
    *,
    feature_names: tuple[str, ...] | None = None,
    rank_directions: Mapping[str, str] | None = None,
    profile_name: str = TECHNICAL_OHLCV_V2_FEATURE_VERSION,
    as_of_date: date | None = None,
) -> UniverseTechnicalContext:
    selected_features = tuple(feature_names or DEFAULT_TECHNICAL_CONTEXT_FEATURES)
    directions = _rank_directions(selected_features, rank_directions)
    snapshots = _normalized_snapshots(features_by_symbol)
    symbols = tuple(sorted(snapshots))
    resolved_as_of_date = as_of_date or _latest_as_of_date(snapshots)

    symbol_feature_contexts: dict[str, dict[str, TechnicalFeatureContext]] = {
        symbol: {} for symbol in symbols
    }
    missing_features_by_symbol: dict[str, list[str]] = {symbol: [] for symbol in symbols}
    symbols_by_feature: dict[str, tuple[str, ...]] = {}
    missing_symbols_by_feature: dict[str, tuple[str, ...]] = {}

    for feature_name in selected_features:
        available = {
            symbol: snapshot.values[feature_name]
            for symbol, snapshot in snapshots.items()
            if feature_name in snapshot.values
        }
        available_symbols = tuple(sorted(available))
        missing_symbols = tuple(symbol for symbol in symbols if symbol not in available)
        symbols_by_feature[feature_name] = available_symbols
        missing_symbols_by_feature[feature_name] = missing_symbols
        for symbol in missing_symbols:
            missing_features_by_symbol[symbol].append(feature_name)
        if not available:
            continue

        stats = _feature_stats(available)
        direction = directions[feature_name]
        ranks = _feature_ranks(available, direction)
        percentiles = _feature_percentiles(available, direction)
        for symbol, value in available.items():
            z_score = _z_score(value, stats)
            directional_z_score = z_score if direction == HIGHER_IS_BETTER else -z_score
            symbol_feature_contexts[symbol][feature_name] = TechnicalFeatureContext(
                feature_name=feature_name,
                value=value,
                rank=ranks[symbol],
                percentile=percentiles[symbol],
                z_score=z_score.quantize(TECHNICAL_CONTEXT_VALUE),
                directional_z_score=directional_z_score.quantize(TECHNICAL_CONTEXT_VALUE),
                eligible_count=len(available),
                rank_direction=direction,
            )

    symbol_contexts = {
        symbol: TechnicalSymbolContext(
            symbol=symbol,
            snapshot_id=snapshots[symbol].snapshot_id,
            as_of_date=snapshots[symbol].as_of_date,
            feature_time=snapshots[symbol].feature_time,
            features=symbol_feature_contexts[symbol],
            missing_features=tuple(sorted(missing_features_by_symbol[symbol])),
        )
        for symbol in symbols
    }
    return UniverseTechnicalContext(
        profile_name=profile_name,
        as_of_date=resolved_as_of_date,
        feature_names=selected_features,
        symbols=symbols,
        universe_size=len(symbols),
        symbols_by_feature=symbols_by_feature,
        missing_symbols_by_feature=missing_symbols_by_feature,
        rank_directions=directions,
        symbol_contexts=symbol_contexts,
        metadata=_metadata(
            profile_name=profile_name,
            as_of_date=resolved_as_of_date,
            selected_features=selected_features,
            symbols=symbols,
            symbols_by_feature=symbols_by_feature,
            missing_symbols_by_feature=missing_symbols_by_feature,
            directions=directions,
            snapshots=snapshots,
        ),
    )


def _normalized_snapshots(
    features_by_symbol: Mapping[str, FeatureSnapshot],
) -> dict[str, FeatureSnapshot]:
    return {
        symbol.upper(): snapshot
        for symbol, snapshot in features_by_symbol.items()
        if snapshot is not None
    }


def _rank_directions(
    feature_names: tuple[str, ...],
    rank_directions: Mapping[str, str] | None,
) -> dict[str, str]:
    overrides = dict(DEFAULT_TECHNICAL_CONTEXT_RANK_DIRECTIONS)
    overrides.update(rank_directions or {})
    directions: dict[str, str] = {}
    for feature_name in feature_names:
        direction = overrides.get(feature_name, HIGHER_IS_BETTER)
        if direction not in {HIGHER_IS_BETTER, LOWER_IS_BETTER}:
            raise ValueError(
                f"Unsupported rank direction {direction!r} for feature {feature_name!r}."
            )
        directions[feature_name] = direction
    return directions


def _latest_as_of_date(snapshots: Mapping[str, FeatureSnapshot]) -> date | None:
    dates = [snapshot.as_of_date for snapshot in snapshots.values()]
    if not dates:
        return None
    return max(dates)


def _feature_ranks(values_by_symbol: Mapping[str, Decimal], direction: str) -> dict[str, int]:
    ranks: dict[str, int] = {}
    for symbol, value in values_by_symbol.items():
        if direction == HIGHER_IS_BETTER:
            better_count = sum(1 for other in values_by_symbol.values() if other > value)
        else:
            better_count = sum(1 for other in values_by_symbol.values() if other < value)
        ranks[symbol] = better_count + 1
    return ranks


def _feature_percentiles(
    values_by_symbol: Mapping[str, Decimal],
    direction: str,
) -> dict[str, Decimal]:
    count = len(values_by_symbol)
    if count == 1:
        symbol = next(iter(values_by_symbol))
        return {symbol: Decimal("0.50000000")}

    ordered = sorted(
        values_by_symbol.items(),
        key=lambda item: (
            -item[1] if direction == HIGHER_IS_BETTER else item[1],
            item[0],
        ),
    )
    position_by_symbol = {
        symbol: Decimal(index + 1) for index, (symbol, _value) in enumerate(ordered)
    }
    percentiles: dict[str, Decimal] = {}
    for _value, tied_symbols in _tie_groups(ordered):
        average_position = sum(
            (position_by_symbol[symbol] for symbol in tied_symbols),
            Decimal("0"),
        ) / Decimal(len(tied_symbols))
        percentile = Decimal("1") - (
            (average_position - Decimal("1")) / Decimal(count - 1)
        )
        quantized = percentile.quantize(TECHNICAL_CONTEXT_VALUE)
        for symbol in tied_symbols:
            percentiles[symbol] = quantized
    return percentiles


def _tie_groups(
    ordered: list[tuple[str, Decimal]],
) -> list[tuple[Decimal, tuple[str, ...]]]:
    groups: dict[Decimal, list[str]] = {}
    for symbol, value in ordered:
        groups.setdefault(value, []).append(symbol)
    return [(value, tuple(symbols)) for value, symbols in groups.items()]


def _feature_stats(values_by_symbol: Mapping[str, Decimal]) -> tuple[Decimal, Decimal]:
    values = list(values_by_symbol.values())
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values))
    return mean, variance.sqrt()


def _z_score(value: Decimal, stats: tuple[Decimal, Decimal]) -> Decimal:
    mean, stddev = stats
    if stddev == 0:
        return Decimal("0")
    return (value - mean) / stddev


def _metadata(
    *,
    profile_name: str,
    as_of_date: date | None,
    selected_features: tuple[str, ...],
    symbols: tuple[str, ...],
    symbols_by_feature: Mapping[str, tuple[str, ...]],
    missing_symbols_by_feature: Mapping[str, tuple[str, ...]],
    directions: Mapping[str, str],
    snapshots: Mapping[str, FeatureSnapshot],
) -> dict[str, object]:
    return {
        "profile_name": profile_name,
        "as_of_date": as_of_date.isoformat() if as_of_date is not None else None,
        "universe_size": len(symbols),
        "feature_names": list(selected_features),
        "eligible_symbol_count_by_feature": {
            feature: len(symbols_by_feature[feature]) for feature in selected_features
        },
        "missing_symbols_by_feature": {
            feature: list(missing_symbols_by_feature[feature]) for feature in selected_features
        },
        "rank_direction_by_feature": {
            feature: directions[feature] for feature in selected_features
        },
        "snapshot_id_by_symbol": {
            symbol: snapshots[symbol].snapshot_id for symbol in symbols
        },
        "snapshot_as_of_date_by_symbol": {
            symbol: snapshots[symbol].as_of_date.isoformat() for symbol in symbols
        },
        "feature_time_by_symbol": {
            symbol: snapshots[symbol].feature_time.isoformat() for symbol in symbols
        },
    }
