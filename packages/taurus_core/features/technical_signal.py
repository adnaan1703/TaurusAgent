from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from taurus_core.features.store import FeatureSnapshot

ANALYST_RULE_PROFILE = "technical_rule_v1"
ANALYST_SCORE_VALUE = Decimal("0.0001")
ANALYST_FEATURE_NAMES = (
    "return_20d",
    "return_5d",
    "ema_12",
    "ema_26",
    "rsi_14",
    "volatility_20",
)
SMA_SPREAD_PROFILE = "sma_spread"
SMA_SCORE_VALUE = Decimal("0.00000001")
ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class TechnicalBacktestSignal:
    signal_id: int | str
    action: str
    score: Decimal


@dataclass(frozen=True, slots=True)
class TechnicalSignalResult:
    profile_name: str
    available: bool
    raw_score: Decimal | None
    score: Decimal | None
    confidence: Decimal | None
    score_source: str
    components: Mapping[str, Decimal] = field(default_factory=dict)
    missing_features: tuple[str, ...] = ()
    key_points: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "components", MappingProxyType(dict(self.components)))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))
        object.__setattr__(self, "missing_features", tuple(self.missing_features))
        object.__setattr__(self, "key_points", tuple(self.key_points))
        object.__setattr__(self, "source_ids", tuple(self.source_ids))


class TechnicalSignalService:
    def score_analyst_rule(
        self,
        snapshot: FeatureSnapshot | None,
        latest_signal: TechnicalBacktestSignal | None,
        *,
        symbol: str | None = None,
    ) -> TechnicalSignalResult:
        values = snapshot.values if snapshot is not None else {}
        raw_score = self._analyst_raw_score(values, latest_signal)
        score = _bounded_analyst_score(raw_score)
        source_ids = _analyst_source_ids(snapshot, latest_signal)
        resolved_symbol = _analyst_symbol(snapshot=snapshot, symbol=symbol)
        key_points = _analyst_key_points(
            symbol=resolved_symbol,
            values=values,
            latest_signal=latest_signal,
        )
        confidence = Decimal("0.6800") if values else Decimal("0.3500")
        components = _analyst_components(values, latest_signal)
        missing_features = tuple(name for name in ANALYST_FEATURE_NAMES if name not in values)
        return TechnicalSignalResult(
            profile_name=ANALYST_RULE_PROFILE,
            available=True,
            raw_score=raw_score,
            score=score,
            confidence=confidence,
            score_source=ANALYST_RULE_PROFILE,
            components=components,
            missing_features=missing_features,
            key_points=tuple(key_points),
            source_ids=tuple(source_ids or ["technical:none"]),
            metadata={
                "snapshot_id": snapshot.snapshot_id if snapshot is not None else None,
                "symbol": resolved_symbol,
                "feature_time": snapshot.feature_time.isoformat()
                if snapshot is not None
                else None,
                "as_of_date": snapshot.as_of_date.isoformat() if snapshot is not None else None,
                "signal_id": latest_signal.signal_id if latest_signal is not None else None,
                "signal_action": latest_signal.action if latest_signal is not None else None,
                "score_precision": ANALYST_SCORE_VALUE,
            },
        )

    def score_sma_spread(
        self,
        snapshot: FeatureSnapshot | None,
        fast_window: int,
        slow_window: int,
    ) -> TechnicalSignalResult:
        fast_feature = f"sma_{fast_window}"
        slow_feature = f"sma_{slow_window}"
        source_ids = (snapshot.snapshot_id,) if snapshot is not None else ()
        values = snapshot.values if snapshot is not None else {}
        fast = values.get(fast_feature)
        slow = values.get(slow_feature)
        missing_features = tuple(
            feature
            for feature, value in ((fast_feature, fast), (slow_feature, slow))
            if value is None
        )
        metadata: dict[str, object] = {
            "snapshot_id": snapshot.snapshot_id if snapshot is not None else None,
            "symbol": snapshot.symbol if snapshot is not None else None,
            "fast_window": fast_window,
            "slow_window": slow_window,
            "fast_feature": fast_feature,
            "slow_feature": slow_feature,
            "score_precision": SMA_SCORE_VALUE,
        }
        if missing_features:
            metadata["unavailable_reason"] = "missing_sma_feature"
            return TechnicalSignalResult(
                profile_name=SMA_SPREAD_PROFILE,
                available=False,
                raw_score=None,
                score=None,
                confidence=None,
                score_source=SMA_SPREAD_PROFILE,
                missing_features=missing_features,
                source_ids=source_ids,
                metadata=metadata,
            )
        if slow == ZERO:
            metadata["unavailable_reason"] = "invalid_slow_sma"
            metadata["invalid_features"] = [slow_feature]
            return TechnicalSignalResult(
                profile_name=SMA_SPREAD_PROFILE,
                available=False,
                raw_score=None,
                score=None,
                confidence=None,
                score_source=SMA_SPREAD_PROFILE,
                source_ids=source_ids,
                metadata=metadata,
            )

        assert fast is not None
        assert slow is not None
        raw_score = (fast / slow) - Decimal("1")
        score = raw_score.quantize(SMA_SCORE_VALUE)
        return TechnicalSignalResult(
            profile_name=SMA_SPREAD_PROFILE,
            available=True,
            raw_score=raw_score,
            score=score,
            confidence=None,
            score_source=SMA_SPREAD_PROFILE,
            components={
                "fast_sma": fast,
                "slow_sma": slow,
                "sma_spread": raw_score,
            },
            source_ids=source_ids,
            metadata=metadata,
        )

    def _analyst_raw_score(
        self,
        values: Mapping[str, Decimal],
        latest_signal: TechnicalBacktestSignal | None,
    ) -> Decimal:
        if latest_signal is not None:
            return (
                latest_signal.score
                if latest_signal.action == "BUY"
                else -latest_signal.score
            )

        return_20d = values.get("return_20d", ZERO)
        return_5d = values.get("return_5d", ZERO)
        ema_12 = values.get("ema_12")
        ema_26 = values.get("ema_26")
        rsi = values.get("rsi_14", Decimal("50"))
        volatility = values.get("volatility_20", ZERO)
        ema_trend = ZERO
        if ema_12 is not None and ema_26 not in (None, ZERO):
            ema_trend = (ema_12 / ema_26) - Decimal("1")
        return (
            (return_20d * Decimal("1.8"))
            + (return_5d * Decimal("0.8"))
            + (ema_trend * Decimal("1.2"))
            + (((rsi - Decimal("50")) / Decimal("50")) * Decimal("0.30"))
            - (volatility * Decimal("0.75"))
        )


def _bounded_analyst_score(value: Decimal) -> Decimal:
    return max(Decimal("-1"), min(Decimal("1"), value)).quantize(ANALYST_SCORE_VALUE)


def _analyst_source_ids(
    snapshot: FeatureSnapshot | None,
    latest_signal: TechnicalBacktestSignal | None,
) -> list[str]:
    source_ids: list[str] = []
    if snapshot is not None:
        source_ids.append(snapshot.snapshot_id)
    if latest_signal is not None:
        source_ids.append(f"signal:{latest_signal.signal_id}")
    return source_ids


def _analyst_symbol(*, snapshot: FeatureSnapshot | None, symbol: str | None) -> str:
    if symbol is not None:
        return symbol.upper()
    if snapshot is not None:
        return snapshot.symbol.upper()
    return "UNKNOWN"


def _analyst_key_points(
    *,
    symbol: str,
    values: Mapping[str, Decimal],
    latest_signal: TechnicalBacktestSignal | None,
) -> list[str]:
    points: list[str] = []
    if latest_signal is not None:
        points.append(
            f"Latest strategy signal for {symbol} was {latest_signal.action} "
            f"with score {latest_signal.score}."
        )
    if "return_20d" in values:
        points.append(f"20-day return feature is {values['return_20d']}.")
    if "rsi_14" in values:
        points.append(f"RSI-14 feature is {values['rsi_14']}.")
    if "volatility_20" in values:
        points.append(f"20-day volatility feature is {values['volatility_20']}.")
    return points or [
        f"No persisted technical features were available for {symbol}; neutral fallback used."
    ]


def _analyst_components(
    values: Mapping[str, Decimal],
    latest_signal: TechnicalBacktestSignal | None,
) -> dict[str, Decimal]:
    if latest_signal is not None:
        direction = Decimal("1") if latest_signal.action == "BUY" else Decimal("-1")
        return {
            "signal_score": latest_signal.score,
            "signal_direction": direction,
        }

    return_20d = values.get("return_20d", ZERO)
    return_5d = values.get("return_5d", ZERO)
    ema_12 = values.get("ema_12")
    ema_26 = values.get("ema_26")
    rsi = values.get("rsi_14", Decimal("50"))
    volatility = values.get("volatility_20", ZERO)
    ema_trend = ZERO
    if ema_12 is not None and ema_26 not in (None, ZERO):
        ema_trend = (ema_12 / ema_26) - Decimal("1")
    return {
        "return_20d": return_20d,
        "return_5d": return_5d,
        "ema_trend": ema_trend,
        "rsi": rsi,
        "volatility_20": volatility,
        "return_20d_component": return_20d * Decimal("1.8"),
        "return_5d_component": return_5d * Decimal("0.8"),
        "ema_trend_component": ema_trend * Decimal("1.2"),
        "rsi_component": ((rsi - Decimal("50")) / Decimal("50")) * Decimal("0.30"),
        "volatility_component": -(volatility * Decimal("0.75")),
    }
