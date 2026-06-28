from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping

from taurus_core.features.store import (
    FeatureSnapshot,
    TECHNICAL_OHLCV_V2_FEATURE_VERSION,
)
from taurus_core.features.technical_params import (
    DEFAULT_OHLCV_V2_SCORING_PARAMS,
    DEFAULT_OHLCV_V2A_SH_SCORING_PARAMS,
    OhlcvV2ScoringParams,
)
from taurus_core.features.technical_context import (
    DEFAULT_TECHNICAL_CONTEXT_FEATURES,
    OfficialTechnicalContext,
    OfficialTechnicalSymbolContext,
    TECHNICAL_OFFICIAL_V2B_PROFILE,
    TechnicalFeatureContext,
    TechnicalSymbolContext,
    UniverseTechnicalContext,
)

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
OHLCV_V2_PROFILE = TECHNICAL_OHLCV_V2_FEATURE_VERSION
OHLCV_V2A_SH_PROFILE = "technical_ohlcv_v2a_sh"
OFFICIAL_V2B_PROFILE = TECHNICAL_OFFICIAL_V2B_PROFILE
OHLCV_V2_SCORE_VALUE = Decimal("0.0001")
OHLCV_V2_COMPONENT_VALUE = Decimal("0.00000001")
OHLCV_V2_TOP_CONTRIBUTOR_LIMIT = 8
ZERO = Decimal("0")
ONE = Decimal("1")

OHLCV_V2_REQUIRED_FEATURES = (
    "return_20d",
    "return_63d",
    "return_126d",
    "return_252d",
    "vol_adjusted_return_63d",
    "vol_adjusted_return_126d",
    "vol_adjusted_return_252d",
    "ema_12",
    "ema_26",
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
OHLCV_V2_TRADABILITY_FEATURES = (
    "turnover",
    "avg_traded_value_20",
    "avg_traded_value_63",
    "turnover_z_score_20",
    "volume_z_score_20",
)
OHLCV_V2_FAMILY_WEIGHTS: Mapping[str, Decimal] = (
    DEFAULT_OHLCV_V2_SCORING_PARAMS.family_weights
)


@dataclass(frozen=True, slots=True)
class _ScoredFeature:
    feature_name: str
    family: str
    label: str
    value: Decimal | None
    score: Decimal
    weight: Decimal
    source: str


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


@dataclass(frozen=True, slots=True)
class TechnicalOhlcvSignalResult:
    profile_name: str
    available: bool
    alpha_score: Decimal
    risk_score: Decimal
    tradability_score: Decimal
    confidence: Decimal
    composite_score: Decimal
    coverage: Decimal
    score_source: str
    components: Mapping[str, Decimal] = field(default_factory=dict)
    top_contributors: tuple[Mapping[str, object], ...] = ()
    missing_features: tuple[str, ...] = ()
    source_ids: tuple[str, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "components", MappingProxyType(dict(self.components)))
        object.__setattr__(
            self,
            "top_contributors",
            tuple(
                MappingProxyType(dict(contributor))
                for contributor in self.top_contributors
            ),
        )
        object.__setattr__(self, "missing_features", tuple(self.missing_features))
        object.__setattr__(self, "source_ids", tuple(self.source_ids))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    @property
    def raw_score(self) -> Decimal:
        return self.composite_score

    @property
    def score(self) -> Decimal:
        return self.composite_score


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
        missing_features = tuple(
            name for name in ANALYST_FEATURE_NAMES if name not in values
        )
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
                "as_of_date": snapshot.as_of_date.isoformat()
                if snapshot is not None
                else None,
                "signal_id": latest_signal.signal_id
                if latest_signal is not None
                else None,
                "signal_action": latest_signal.action
                if latest_signal is not None
                else None,
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

    def score_ohlcv_v2(
        self,
        snapshot: FeatureSnapshot | None,
        *,
        universe_context: UniverseTechnicalContext | None = None,
        symbol: str | None = None,
        scoring_params: OhlcvV2ScoringParams | Mapping[str, object] | None = None,
        is_new_buy: bool = False,
        candidate_breadth: int | None = None,
        target_breadth: int | None = None,
        top_contributor_limit: int = OHLCV_V2_TOP_CONTRIBUTOR_LIMIT,
    ) -> TechnicalOhlcvSignalResult:
        params = _resolve_ohlcv_v2_params(scoring_params)
        resolved_symbol = _ohlcv_symbol(snapshot=snapshot, symbol=symbol)
        if snapshot is None:
            return _empty_ohlcv_result(
                symbol=resolved_symbol,
                unavailable_reason="missing_feature_snapshot",
            )

        values = snapshot.values
        missing_features = tuple(
            feature for feature in OHLCV_V2_REQUIRED_FEATURES if feature not in values
        )
        coverage = _coverage_ratio(
            available_count=len(OHLCV_V2_REQUIRED_FEATURES) - len(missing_features),
            total_count=len(OHLCV_V2_REQUIRED_FEATURES),
        )
        symbol_context = (
            universe_context.for_symbol(resolved_symbol)
            if universe_context is not None
            else None
        )

        alpha_features = _alpha_contributors(values, symbol_context, params)
        risk_features = _risk_contributors(values, symbol_context, params)
        tradability_features = _tradability_contributors(values, symbol_context, params)

        alpha_score, alpha_components = _family_score("alpha", alpha_features)
        risk_score, risk_components = _family_score("risk", risk_features)
        tradability_score, tradability_components = _family_score(
            "tradability",
            tradability_features,
        )
        composite_raw = (
            (alpha_score * params.family_weights["alpha"])
            + (risk_score * params.family_weights["risk"])
            + (tradability_score * params.family_weights["tradability"])
        )
        guardrail = _ohlcv_guardrail(
            params,
            risk_score=risk_score,
            is_new_buy=is_new_buy,
            candidate_breadth=candidate_breadth
            if candidate_breadth is not None
            else universe_context.universe_size
            if universe_context is not None
            else None,
            target_breadth=target_breadth,
        )
        adjusted_composite_raw = _apply_negative_risk_penalty(
            composite_raw,
            risk_score=risk_score,
            params=params,
        )
        compressed_composite_raw = _compress_ohlcv_score(
            adjusted_composite_raw,
            params=params,
        )
        composite_score = _bounded_score(compressed_composite_raw)
        lookback_quality = _lookback_quality(values)
        universe_breadth = _universe_breadth(universe_context)
        context_coverage = _context_coverage(symbol_context)
        family_agreement = _family_agreement(
            (alpha_score, risk_score, tradability_score),
            composite_raw,
        )
        tradability_quality = _feature_group_quality(
            values, OHLCV_V2_TRADABILITY_FEATURES
        )
        confidence = _ohlcv_confidence(
            coverage=coverage,
            lookback_quality=lookback_quality,
            universe_breadth=universe_breadth,
            context_coverage=context_coverage,
            family_agreement=family_agreement,
            tradability_quality=tradability_quality,
            weights=params.confidence_weights,
        )
        composite_contributions = _composite_contributions(
            {
                "alpha": alpha_features,
                "risk": risk_features,
                "tradability": tradability_features,
            },
            family_weights=params.family_weights,
        )
        components: dict[str, Decimal] = {
            "alpha_score": alpha_score,
            "risk_score": risk_score,
            "tradability_score": tradability_score,
            "composite_raw_score": composite_raw.quantize(OHLCV_V2_COMPONENT_VALUE),
            "composite_score": composite_score,
            "coverage": coverage,
            "lookback_quality": lookback_quality,
            "universe_breadth": universe_breadth,
            "context_coverage": context_coverage,
            "family_agreement": family_agreement,
            "tradability_feature_quality": tradability_quality,
            **alpha_components,
            **risk_components,
            **tradability_components,
        }
        if not params.is_default:
            components.update(
                _parameterized_ohlcv_components(
                    params,
                    composite_raw=composite_raw,
                    adjusted_composite_raw=adjusted_composite_raw,
                    compressed_composite_raw=compressed_composite_raw,
                )
            )
        top_contributors = _top_contributors(
            composite_contributions,
            limit=top_contributor_limit,
        )
        metadata = {
            "snapshot_id": snapshot.snapshot_id,
            "symbol": resolved_symbol,
            "feature_time": snapshot.feature_time.isoformat(),
            "as_of_date": snapshot.as_of_date.isoformat(),
            "score_precision": str(OHLCV_V2_SCORE_VALUE),
            "component_precision": str(OHLCV_V2_COMPONENT_VALUE),
            "required_feature_count": len(OHLCV_V2_REQUIRED_FEATURES),
            "available_feature_count": len(OHLCV_V2_REQUIRED_FEATURES)
            - len(missing_features),
            "family_weights": {
                family: str(weight) for family, weight in params.family_weights.items()
            },
            "universe_context_available": universe_context is not None,
            "symbol_context_available": symbol_context is not None,
            "universe_size": universe_context.universe_size
            if universe_context is not None
            else 0,
            "missing_context_features": _missing_context_features(symbol_context),
            "score_contract": (
                "alpha, risk, and tradability scores are bounded [-1, 1]; "
                "positive risk_score means lower measured OHLCV risk."
            ),
        }
        if not params.is_default:
            metadata["scoring_params"] = params.to_dict()
            metadata["guardrail"] = guardrail
            metadata["score_compression"] = params.score_compression.to_dict()
        return TechnicalOhlcvSignalResult(
            profile_name=OHLCV_V2_PROFILE,
            available=bool(values) and not guardrail["blocked"],
            alpha_score=alpha_score,
            risk_score=risk_score,
            tradability_score=tradability_score,
            confidence=confidence,
            composite_score=composite_score,
            coverage=coverage,
            score_source=OHLCV_V2_PROFILE,
            components=components,
            top_contributors=top_contributors,
            missing_features=missing_features,
            source_ids=(snapshot.snapshot_id,),
            metadata=metadata,
        )

    def score_ohlcv_v2a_sh(
        self,
        snapshot: FeatureSnapshot | None,
        *,
        universe_context: UniverseTechnicalContext | None = None,
        symbol: str | None = None,
        scoring_params: OhlcvV2ScoringParams | Mapping[str, object] | None = None,
        is_new_buy: bool = False,
        candidate_breadth: int | None = None,
        target_breadth: int | None = None,
        top_contributor_limit: int = OHLCV_V2_TOP_CONTRIBUTOR_LIMIT,
    ) -> TechnicalOhlcvSignalResult:
        result = self.score_ohlcv_v2(
            snapshot,
            universe_context=universe_context,
            symbol=symbol,
            scoring_params=scoring_params or DEFAULT_OHLCV_V2A_SH_SCORING_PARAMS,
            is_new_buy=is_new_buy,
            candidate_breadth=candidate_breadth,
            target_breadth=target_breadth,
            top_contributor_limit=top_contributor_limit,
        )
        return replace(
            result,
            profile_name=OHLCV_V2A_SH_PROFILE,
            score_source=OHLCV_V2A_SH_PROFILE,
            metadata={
                **dict(result.metadata),
                "profile_name": OHLCV_V2A_SH_PROFILE,
                "base_feature_version": OHLCV_V2_PROFILE,
                "profile_horizon": "short",
            },
        )

    def score_official_v2b(
        self,
        snapshot: FeatureSnapshot | None,
        *,
        universe_context: UniverseTechnicalContext | None = None,
        official_context: OfficialTechnicalContext | None = None,
        symbol: str | None = None,
        top_contributor_limit: int = OHLCV_V2_TOP_CONTRIBUTOR_LIMIT,
    ) -> TechnicalOhlcvSignalResult:
        resolved_symbol = _ohlcv_symbol(snapshot=snapshot, symbol=symbol)
        base_result = self.score_ohlcv_v2(
            snapshot,
            universe_context=universe_context,
            symbol=resolved_symbol,
            top_contributor_limit=top_contributor_limit,
        )
        if not base_result.available:
            return _official_unavailable_result(
                symbol=resolved_symbol,
                base_result=base_result,
                official_context=official_context,
                unavailable_reason="missing_ohlcv_v2_base",
            )
        symbol_context = (
            official_context.for_symbol(resolved_symbol)
            if official_context is not None
            else None
        )
        if symbol_context is None:
            return _official_unavailable_result(
                symbol=resolved_symbol,
                base_result=base_result,
                official_context=official_context,
                unavailable_reason="missing_official_context",
            )

        official_coverage = symbol_context.coverage_ratio
        official_alpha_features = _official_alpha_contributors(symbol_context)
        official_risk_features = _official_risk_contributors(symbol_context)
        official_tradability_features = _official_tradability_contributors(
            symbol_context
        )
        official_alpha_score, official_alpha_components = _family_score(
            "official_alpha",
            official_alpha_features,
        )
        official_risk_score, official_risk_components = _family_score(
            "official_risk",
            official_risk_features,
        )
        official_tradability_score, official_tradability_components = _family_score(
            "official_tradability",
            official_tradability_features,
        )
        alpha_score = _bounded_score(
            (base_result.alpha_score * Decimal("0.75"))
            + (official_alpha_score * Decimal("0.25"))
        )
        risk_score = _bounded_score(
            (base_result.risk_score * Decimal("0.70"))
            + (official_risk_score * Decimal("0.30"))
        )
        tradability_score = _bounded_score(
            (base_result.tradability_score * Decimal("0.55"))
            + (official_tradability_score * Decimal("0.45"))
        )
        composite_raw = (
            (alpha_score * OHLCV_V2_FAMILY_WEIGHTS["alpha"])
            + (risk_score * OHLCV_V2_FAMILY_WEIGHTS["risk"])
            + (tradability_score * OHLCV_V2_FAMILY_WEIGHTS["tradability"])
        )
        composite_score = _bounded_score(composite_raw)
        coverage = _bounded_score(
            (base_result.coverage * Decimal("0.70"))
            + (official_coverage * Decimal("0.30"))
        )
        family_agreement = _family_agreement(
            (alpha_score, risk_score, tradability_score),
            composite_raw,
        )
        confidence = _official_confidence(
            base_confidence=base_result.confidence,
            official_coverage=official_coverage,
            family_agreement=family_agreement,
        )
        official_contributions = _composite_contributions(
            {
                "alpha": official_alpha_features,
                "risk": official_risk_features,
                "tradability": official_tradability_features,
            },
            family_weights=OHLCV_V2_FAMILY_WEIGHTS,
        )
        top_contributors = _official_top_contributors(
            official_contributions,
            base_result=base_result,
            limit=top_contributor_limit,
        )
        missing_features = tuple(
            [
                *base_result.missing_features,
                *[
                    f"official.{feature}"
                    for feature in symbol_context.missing_features
                ],
            ]
        )
        components = {
            "alpha_score": alpha_score,
            "risk_score": risk_score,
            "tradability_score": tradability_score,
            "composite_raw_score": composite_raw.quantize(OHLCV_V2_COMPONENT_VALUE),
            "composite_score": composite_score,
            "coverage": coverage,
            "base_alpha_score": base_result.alpha_score,
            "base_risk_score": base_result.risk_score,
            "base_tradability_score": base_result.tradability_score,
            "base_composite_score": base_result.composite_score,
            "base_confidence": base_result.confidence,
            "official_alpha_score": official_alpha_score,
            "official_risk_score": official_risk_score,
            "official_tradability_score": official_tradability_score,
            "official_coverage": official_coverage,
            "family_agreement": family_agreement,
            **official_alpha_components,
            **official_risk_components,
            **official_tradability_components,
        }
        return TechnicalOhlcvSignalResult(
            profile_name=OFFICIAL_V2B_PROFILE,
            available=official_coverage > ZERO,
            alpha_score=alpha_score,
            risk_score=risk_score,
            tradability_score=tradability_score,
            confidence=confidence,
            composite_score=composite_score,
            coverage=coverage,
            score_source=OFFICIAL_V2B_PROFILE,
            components=components,
            top_contributors=top_contributors,
            missing_features=missing_features,
            source_ids=_official_source_ids(base_result, symbol_context),
            metadata={
                **dict(base_result.metadata),
                "profile_name": OFFICIAL_V2B_PROFILE,
                "base_profile_name": base_result.profile_name,
                "official_context_available": official_context is not None,
                "official_symbol_context_available": True,
                "official_context_as_of_date": official_context.as_of_date.isoformat()
                if official_context is not None
                else None,
                "source_coverage": {
                    key: bool(value)
                    for key, value in symbol_context.source_coverage.items()
                },
                "official_coverage": str(official_coverage),
                "official_missing_features": list(symbol_context.missing_features),
                "official_feature_metadata": dict(symbol_context.metadata),
                "score_contract": (
                    "technical_official_v2b extends technical_ohlcv_v2 with "
                    "official benchmark, sector, India VIX, delivery, circuit, "
                    "and implementability evidence; missing official families "
                    "reduce confidence or make the profile unavailable."
                ),
            },
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


def _resolve_ohlcv_v2_params(
    scoring_params: OhlcvV2ScoringParams | Mapping[str, object] | None,
) -> OhlcvV2ScoringParams:
    if scoring_params is None:
        return DEFAULT_OHLCV_V2_SCORING_PARAMS
    if isinstance(scoring_params, OhlcvV2ScoringParams):
        return scoring_params
    if isinstance(scoring_params, Mapping):
        return OhlcvV2ScoringParams.from_mapping(scoring_params)
    raise TypeError("scoring_params must be OhlcvV2ScoringParams or a mapping.")


def _ohlcv_guardrail(
    params: OhlcvV2ScoringParams,
    *,
    risk_score: Decimal,
    is_new_buy: bool,
    candidate_breadth: int | None,
    target_breadth: int | None,
) -> dict[str, object]:
    reasons: list[str] = []
    eligibility = params.eligibility
    if (
        eligibility.min_risk_score_for_new_buys is not None
        and is_new_buy
        and risk_score < eligibility.min_risk_score_for_new_buys
    ):
        reasons.append("risk_score_below_new_buy_minimum")

    required_candidate_breadth: Decimal | None = None
    if (
        eligibility.min_candidate_breadth_multiple is not None
        and candidate_breadth is not None
        and target_breadth is not None
        and target_breadth > 0
    ):
        required_candidate_breadth = (
            Decimal(target_breadth) * eligibility.min_candidate_breadth_multiple
        )
        if Decimal(candidate_breadth) < required_candidate_breadth:
            reasons.append("candidate_breadth_below_minimum_multiple")

    return {
        "blocked": bool(reasons),
        "reasons": reasons,
        "is_new_buy": is_new_buy,
        "risk_score": str(risk_score),
        "min_risk_score_for_new_buys": (
            str(eligibility.min_risk_score_for_new_buys)
            if eligibility.min_risk_score_for_new_buys is not None
            else None
        ),
        "candidate_breadth": candidate_breadth,
        "target_breadth": target_breadth,
        "min_candidate_breadth_multiple": (
            str(eligibility.min_candidate_breadth_multiple)
            if eligibility.min_candidate_breadth_multiple is not None
            else None
        ),
        "required_candidate_breadth": (
            str(required_candidate_breadth)
            if required_candidate_breadth is not None
            else None
        ),
    }


def _apply_negative_risk_penalty(
    composite_raw: Decimal,
    *,
    risk_score: Decimal,
    params: OhlcvV2ScoringParams,
) -> Decimal:
    penalty = params.eligibility.negative_risk_penalty
    if penalty <= ZERO or risk_score >= ZERO:
        return composite_raw
    return composite_raw - (abs(risk_score) * penalty)


def _compress_ohlcv_score(
    value: Decimal,
    *,
    params: OhlcvV2ScoringParams,
) -> Decimal:
    compression = params.score_compression
    if compression.mode == "none":
        return value
    lower = compression.lower_bound
    upper = compression.upper_bound
    bounded_value = _bounded(value)
    if compression.mode == "tanh":
        bounded_value = Decimal(str(math.tanh(float(value))))
    return lower + (((bounded_value + ONE) / Decimal("2")) * (upper - lower))


def _parameterized_ohlcv_components(
    params: OhlcvV2ScoringParams,
    *,
    composite_raw: Decimal,
    adjusted_composite_raw: Decimal,
    compressed_composite_raw: Decimal,
) -> dict[str, Decimal]:
    components = {
        "composite_adjusted_raw_score": adjusted_composite_raw.quantize(
            OHLCV_V2_COMPONENT_VALUE
        ),
        "composite_compressed_raw_score": compressed_composite_raw.quantize(
            OHLCV_V2_COMPONENT_VALUE
        ),
    }
    penalty = composite_raw - adjusted_composite_raw
    if penalty != ZERO:
        components["risk_negative_penalty"] = penalty.quantize(
            OHLCV_V2_COMPONENT_VALUE
        )
    if params.score_compression.mode != "none":
        components["score_compression.lower_bound"] = (
            params.score_compression.lower_bound
        )
        components["score_compression.upper_bound"] = (
            params.score_compression.upper_bound
        )
    return components


def _empty_ohlcv_result(
    *,
    symbol: str,
    unavailable_reason: str,
) -> TechnicalOhlcvSignalResult:
    return TechnicalOhlcvSignalResult(
        profile_name=OHLCV_V2_PROFILE,
        available=False,
        alpha_score=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        risk_score=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        tradability_score=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        confidence=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        composite_score=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        coverage=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        score_source=OHLCV_V2_PROFILE,
        missing_features=OHLCV_V2_REQUIRED_FEATURES,
        source_ids=("technical:none",),
        metadata={
            "symbol": symbol,
            "score_precision": str(OHLCV_V2_SCORE_VALUE),
            "component_precision": str(OHLCV_V2_COMPONENT_VALUE),
            "unavailable_reason": unavailable_reason,
            "required_feature_count": len(OHLCV_V2_REQUIRED_FEATURES),
            "available_feature_count": 0,
            "universe_context_available": False,
            "symbol_context_available": False,
        },
    )


def _official_unavailable_result(
    *,
    symbol: str,
    base_result: TechnicalOhlcvSignalResult,
    official_context: OfficialTechnicalContext | None,
    unavailable_reason: str,
) -> TechnicalOhlcvSignalResult:
    return TechnicalOhlcvSignalResult(
        profile_name=OFFICIAL_V2B_PROFILE,
        available=False,
        alpha_score=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        risk_score=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        tradability_score=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        confidence=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        composite_score=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        coverage=ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        score_source=OFFICIAL_V2B_PROFILE,
        components={
            "base_alpha_score": base_result.alpha_score,
            "base_risk_score": base_result.risk_score,
            "base_tradability_score": base_result.tradability_score,
            "base_composite_score": base_result.composite_score,
            "base_confidence": base_result.confidence,
            "official_coverage": ZERO.quantize(OHLCV_V2_SCORE_VALUE),
        },
        top_contributors=base_result.top_contributors,
        missing_features=tuple(
            [
                *base_result.missing_features,
                "official.benchmark",
                "official.volatility",
                "official.delivery",
                "official.circuit",
                "official.tradability",
            ]
        ),
        source_ids=base_result.source_ids,
        metadata={
            **dict(base_result.metadata),
            "profile_name": OFFICIAL_V2B_PROFILE,
            "base_profile_name": base_result.profile_name,
            "symbol": symbol,
            "unavailable_reason": unavailable_reason,
            "official_context_available": official_context is not None,
            "official_symbol_context_available": False,
            "official_context_as_of_date": official_context.as_of_date.isoformat()
            if official_context is not None
            else None,
            "official_coverage": "0.0000",
        },
    )


def _official_alpha_contributors(
    symbol_context: OfficialTechnicalSymbolContext,
) -> list[_ScoredFeature]:
    contributors = [
        _official_feature(
            feature_name="market_relative_return_20d",
            family="alpha",
            label="20-day return relative to official benchmark",
            value=symbol_context.market_relative_return_20d,
            weight=Decimal("0.35"),
            raw_transform=lambda value: _bounded(value / Decimal("0.08")),
        ),
        _official_feature(
            feature_name="sector_relative_return_20d",
            family="alpha",
            label="20-day return relative to mapped official sector index",
            value=symbol_context.sector_relative_return_20d,
            weight=Decimal("0.20"),
            raw_transform=lambda value: _bounded(value / Decimal("0.08")),
        ),
        _official_feature(
            feature_name="market_regime_state",
            family="alpha",
            label="Official benchmark regime",
            value=_regime_score(
                symbol_context.benchmark_index.regime_state
                if symbol_context.benchmark_index is not None
                else None
            ),
            weight=Decimal("0.15"),
            raw_transform=lambda value: value,
        ),
        _official_feature(
            feature_name="sector_regime_state",
            family="alpha",
            label="Mapped official sector regime",
            value=_regime_score(
                symbol_context.sector_index.regime_state
                if symbol_context.sector_index is not None
                else None
            ),
            weight=Decimal("0.10"),
            raw_transform=lambda value: value,
        ),
    ]
    return [contributor for contributor in contributors if contributor is not None]


def _official_risk_contributors(
    symbol_context: OfficialTechnicalSymbolContext,
) -> list[_ScoredFeature]:
    volatility = symbol_context.volatility_index
    microstructure = symbol_context.microstructure
    contributors = [
        _official_feature(
            feature_name="india_vix_regime",
            family="risk",
            label="India VIX regime",
            value=_vix_regime_score(volatility.regime_state if volatility else None),
            weight=Decimal("0.30"),
            raw_transform=lambda value: value,
        ),
        _official_feature(
            feature_name="india_vix_change_20d",
            family="risk",
            label="India VIX 20-day change",
            value=volatility.return_20d if volatility is not None else None,
            weight=Decimal("0.20"),
            raw_transform=lambda value: _bounded(-(value / Decimal("0.25"))),
        ),
        _official_feature(
            feature_name="circuit_hit_or_near_band",
            family="risk",
            label="Official circuit-hit or near-band status",
            value=_circuit_score(microstructure),
            weight=Decimal("0.30"),
            raw_transform=lambda value: value,
        ),
    ]
    return [contributor for contributor in contributors if contributor is not None]


def _official_tradability_contributors(
    symbol_context: OfficialTechnicalSymbolContext,
) -> list[_ScoredFeature]:
    microstructure = symbol_context.microstructure
    contributors = [
        _official_feature(
            feature_name="delivery_participation",
            family="tradability",
            label="Official delivery participation",
            value=_delivery_score(microstructure),
            weight=Decimal("0.35"),
            raw_transform=lambda value: value,
        ),
        _official_feature(
            feature_name="implementability_proxy",
            family="tradability",
            label="Official impact-cost or labeled implementability proxy",
            value=microstructure.implementability_score
            if microstructure is not None
            else None,
            weight=Decimal("0.45"),
            raw_transform=lambda value: value,
        ),
    ]
    return [contributor for contributor in contributors if contributor is not None]


def _official_feature(
    *,
    feature_name: str,
    family: str,
    label: str,
    value: Decimal | None,
    weight: Decimal,
    raw_transform: Callable[[Decimal], Decimal],
) -> _ScoredFeature | None:
    if value is None:
        return None
    return _ScoredFeature(
        feature_name=feature_name,
        family=family,
        label=label,
        value=value,
        score=_bounded(raw_transform(value)),
        weight=weight,
        source="official_data",
    )


def _regime_score(regime_state: str | None) -> Decimal | None:
    if regime_state == "bullish":
        return Decimal("0.4000")
    if regime_state == "bearish":
        return Decimal("-0.4000")
    if regime_state == "neutral":
        return ZERO
    return None


def _vix_regime_score(regime_state: str | None) -> Decimal | None:
    if regime_state == "calm":
        return Decimal("0.5000")
    if regime_state == "normal":
        return ZERO
    if regime_state == "stress":
        return Decimal("-0.7000")
    return None


def _circuit_score(
    symbol_context: object,
) -> Decimal | None:
    if symbol_context is None:
        return None
    circuit_hit = getattr(symbol_context, "circuit_hit", None)
    near_circuit = bool(getattr(symbol_context, "near_circuit", False))
    circuit_status = getattr(symbol_context, "circuit_status", None)
    if circuit_hit is True:
        return Decimal("-1.0000")
    if near_circuit or circuit_status in {"near_upper", "near_lower"}:
        return Decimal("-0.5000")
    if circuit_hit is False or circuit_status in {"none", "no_band"}:
        return Decimal("0.4000")
    return None


def _delivery_score(
    symbol_context: object,
) -> Decimal | None:
    if symbol_context is None:
        return None
    z_score = getattr(symbol_context, "delivery_z_score", None)
    delivery_state = getattr(symbol_context, "delivery_state", "unknown")
    if z_score is not None:
        return _bounded(z_score / Decimal("2"))
    if delivery_state == "high_participation":
        return Decimal("0.4000")
    if delivery_state == "normal":
        return Decimal("0.1000")
    if delivery_state == "low_participation":
        return Decimal("-0.4000")
    return None


def _official_confidence(
    *,
    base_confidence: Decimal,
    official_coverage: Decimal,
    family_agreement: Decimal,
) -> Decimal:
    raw = (
        (base_confidence * Decimal("0.55"))
        + (official_coverage * Decimal("0.30"))
        + (family_agreement * Decimal("0.15"))
    )
    return _clamp(raw, Decimal("0.0500"), Decimal("0.9500")).quantize(
        OHLCV_V2_SCORE_VALUE
    )


def _official_top_contributors(
    official_contributions: list[tuple[_ScoredFeature, Decimal]],
    *,
    base_result: TechnicalOhlcvSignalResult,
    limit: int,
) -> tuple[Mapping[str, object], ...]:
    official_top = [dict(contributor) for contributor in _top_contributors(
        official_contributions,
        limit=limit,
    )]
    for contributor in official_top:
        contributor["profile_layer"] = "official_v2b"
    base_top = [dict(contributor) for contributor in base_result.top_contributors]
    for contributor in base_top:
        contributor["profile_layer"] = "ohlcv_v2_base"
    combined = [*official_top, *base_top]
    return tuple(combined[: max(0, limit)])


def _official_source_ids(
    base_result: TechnicalOhlcvSignalResult,
    symbol_context: OfficialTechnicalSymbolContext,
) -> tuple[str, ...]:
    source_ids = list(base_result.source_ids)
    if symbol_context.benchmark_index is not None:
        source_ids.append(
            _official_index_source_id("benchmark", symbol_context.benchmark_index)
        )
    if symbol_context.sector_index is not None:
        source_ids.append(_official_index_source_id("sector", symbol_context.sector_index))
    if symbol_context.volatility_index is not None:
        source_ids.append(
            _official_index_source_id("volatility", symbol_context.volatility_index)
        )
    if symbol_context.microstructure is not None:
        source_ids.append(
            "official_microstructure:"
            f"{symbol_context.microstructure.symbol}:"
            f"{symbol_context.microstructure.trade_date.isoformat()}:"
            f"{symbol_context.microstructure.source}"
        )
    return tuple(source_ids)


def _official_index_source_id(label: str, index_feature: object) -> str:
    return (
        f"official_index:{label}:"
        f"{getattr(index_feature, 'index_symbol')}:"
        f"{getattr(index_feature, 'trade_date').isoformat()}:"
        f"{getattr(index_feature, 'source')}"
    )


def _ohlcv_symbol(*, snapshot: FeatureSnapshot | None, symbol: str | None) -> str:
    if symbol is not None:
        return symbol.upper()
    if snapshot is not None:
        return snapshot.symbol.upper()
    return "UNKNOWN"


def _alpha_contributors(
    values: Mapping[str, Decimal],
    symbol_context: TechnicalSymbolContext | None,
    params: OhlcvV2ScoringParams,
) -> list[_ScoredFeature]:
    contributors = [
        _context_feature(
            values,
            symbol_context,
            feature_name="return_20d",
            family="alpha",
            label="20-day absolute momentum",
            weight=params.alpha_weights["return_20d"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["return_20d"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="vol_adjusted_return_63d",
            family="alpha",
            label="63-day volatility-adjusted momentum",
            weight=params.alpha_weights["vol_adjusted_return_63d"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["vol_adjusted_return_63d"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="vol_adjusted_return_126d",
            family="alpha",
            label="126-day volatility-adjusted momentum",
            weight=params.alpha_weights["vol_adjusted_return_126d"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["vol_adjusted_return_126d"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="vol_adjusted_return_252d",
            family="alpha",
            label="252-day volatility-adjusted momentum",
            weight=params.alpha_weights["vol_adjusted_return_252d"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["vol_adjusted_return_252d"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="return_126d",
            family="alpha",
            label="126-day absolute momentum",
            weight=params.alpha_weights["return_126d"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["return_126d"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="return_63d",
            family="alpha",
            label="63-day absolute momentum",
            weight=params.alpha_weights["return_63d"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["return_63d"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="return_252d",
            family="alpha",
            label="252-day absolute momentum",
            weight=params.alpha_weights["return_252d"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["return_252d"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="macd_histogram_12_26_9",
            family="alpha",
            label="MACD histogram",
            weight=params.alpha_weights["macd_histogram_12_26_9"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["macd_histogram_12_26_9"]
            ),
            context_weights=params.context_weights,
        ),
        _derived_feature(
            feature_name="ema_spread_12_26",
            family="alpha",
            label="EMA 12/26 spread",
            value=_ema_spread(values),
            weight=params.alpha_weights["ema_spread_12_26"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["ema_spread_12_26"]
            ),
        ),
        _derived_feature(
            feature_name="adx_directional_strength_14",
            family="alpha",
            label="ADX-weighted directional trend",
            value=_adx_directional_strength(values),
            weight=params.alpha_weights["adx_directional_strength_14"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["adx_directional_strength_14"]
            ),
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="breakout_high_distance_20d",
            family="alpha",
            label="20-day breakout distance",
            weight=params.alpha_weights["breakout_high_distance_20d"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["breakout_high_distance_20d"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="breakout_high_distance_50d",
            family="alpha",
            label="50-day breakout distance",
            weight=params.alpha_weights["breakout_high_distance_50d"],
            raw_transform=lambda value: _scaled_score(
                value, params.alpha_transform_scales["breakout_high_distance_50d"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="distance_from_52w_high",
            family="alpha",
            label="Distance from 52-week high",
            weight=params.alpha_weights["distance_from_52w_high"],
            raw_transform=lambda value: _distance_from_high_score(
                value,
                params.alpha_transform_scales["distance_from_52w_high"],
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="rsi_14",
            family="alpha",
            label="RSI-14 momentum balance",
            weight=params.alpha_weights["rsi_14"],
            raw_transform=lambda value: _bounded(
                _safe_divide(
                    value - Decimal("50"),
                    params.alpha_transform_scales["rsi_14"],
                )
            ),
            context_weights=params.context_weights,
        ),
    ]
    return [contributor for contributor in contributors if contributor is not None]


def _risk_contributors(
    values: Mapping[str, Decimal],
    symbol_context: TechnicalSymbolContext | None,
    params: OhlcvV2ScoringParams,
) -> list[_ScoredFeature]:
    contributors = [
        _context_feature(
            values,
            symbol_context,
            feature_name="atr_percent_14",
            family="risk",
            label="ATR percent risk",
            weight=params.risk_weights["atr_percent_14"],
            raw_transform=lambda value: _lower_is_better_score(
                value, params.risk_transform_scales["atr_percent_14"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="volatility_20",
            family="risk",
            label="20-day realized volatility",
            weight=params.risk_weights["volatility_20"],
            raw_transform=lambda value: _lower_is_better_score(
                value, params.risk_transform_scales["volatility_20"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="volatility_63",
            family="risk",
            label="63-day realized volatility",
            weight=params.risk_weights["volatility_63"],
            raw_transform=lambda value: _lower_is_better_score(
                value, params.risk_transform_scales["volatility_63"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="volatility_126",
            family="risk",
            label="126-day realized volatility",
            weight=params.risk_weights["volatility_126"],
            raw_transform=lambda value: _lower_is_better_score(
                value, params.risk_transform_scales["volatility_126"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="volatility_252",
            family="risk",
            label="252-day realized volatility",
            weight=params.risk_weights["volatility_252"],
            raw_transform=lambda value: _lower_is_better_score(
                value, params.risk_transform_scales["volatility_252"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="bollinger_bandwidth_20",
            family="risk",
            label="Bollinger bandwidth risk",
            weight=params.risk_weights["bollinger_bandwidth_20"],
            raw_transform=lambda value: _lower_is_better_score(
                value, params.risk_transform_scales["bollinger_bandwidth_20"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="minus_di_14",
            family="risk",
            label="Negative directional pressure",
            weight=params.risk_weights["minus_di_14"],
            raw_transform=lambda value: _lower_is_better_score(
                value, params.risk_transform_scales["minus_di_14"]
            ),
            context_weights=params.context_weights,
        ),
        _derived_feature(
            feature_name="bollinger_percent_b_extension",
            family="risk",
            label="Bollinger percent-B extension",
            value=values.get("bollinger_percent_b_20"),
            weight=params.risk_weights["bollinger_percent_b_extension"],
            raw_transform=lambda value: _bollinger_extension_score(
                value,
                params.risk_transform_scales["bollinger_percent_b_extension"],
            ),
        ),
        _derived_feature(
            feature_name="return_20d_instability",
            family="risk",
            label="20-day return instability",
            value=values.get("return_20d"),
            weight=params.risk_weights["return_20d_instability"],
            raw_transform=lambda value: _bounded(
                ONE
                - (
                    _safe_divide(
                        abs(value),
                        params.risk_transform_scales["return_20d_instability"],
                    )
                    * 2
                )
            ),
        ),
    ]
    return [contributor for contributor in contributors if contributor is not None]


def _tradability_contributors(
    values: Mapping[str, Decimal],
    symbol_context: TechnicalSymbolContext | None,
    params: OhlcvV2ScoringParams,
) -> list[_ScoredFeature]:
    contributors = [
        _context_feature(
            values,
            symbol_context,
            feature_name="turnover",
            family="tradability",
            label="Latest traded value proxy",
            weight=params.tradability_weights["turnover"],
            raw_transform=lambda _value: ZERO,
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="avg_traded_value_20",
            family="tradability",
            label="20-day average traded value",
            weight=params.tradability_weights["avg_traded_value_20"],
            raw_transform=lambda _value: ZERO,
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="avg_traded_value_63",
            family="tradability",
            label="63-day average traded value",
            weight=params.tradability_weights["avg_traded_value_63"],
            raw_transform=lambda _value: ZERO,
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="turnover_z_score_20",
            family="tradability",
            label="20-day turnover z-score",
            weight=params.tradability_weights["turnover_z_score_20"],
            raw_transform=lambda value: _scaled_score(
                value, params.tradability_transform_scales["turnover_z_score_20"]
            ),
            context_weights=params.context_weights,
        ),
        _context_feature(
            values,
            symbol_context,
            feature_name="volume_z_score_20",
            family="tradability",
            label="20-day volume z-score",
            weight=params.tradability_weights["volume_z_score_20"],
            raw_transform=lambda value: _scaled_score(
                value, params.tradability_transform_scales["volume_z_score_20"]
            ),
            context_weights=params.context_weights,
        ),
    ]
    return [contributor for contributor in contributors if contributor is not None]


def _context_feature(
    values: Mapping[str, Decimal],
    symbol_context: TechnicalSymbolContext | None,
    *,
    feature_name: str,
    family: str,
    label: str,
    weight: Decimal,
    raw_transform: Callable[[Decimal], Decimal],
    context_weights: Mapping[str, Decimal],
) -> _ScoredFeature | None:
    value = values.get(feature_name)
    if value is None:
        return None
    context_feature = (
        symbol_context.get(feature_name) if symbol_context is not None else None
    )
    if context_feature is not None:
        score = _context_feature_score(context_feature, weights=context_weights)
        source = "universe_context"
    else:
        score = raw_transform(value)
        source = "raw_feature"
    return _ScoredFeature(
        feature_name=feature_name,
        family=family,
        label=label,
        value=value,
        score=_bounded(score),
        weight=weight,
        source=source,
    )


def _derived_feature(
    *,
    feature_name: str,
    family: str,
    label: str,
    value: Decimal | None,
    weight: Decimal,
    raw_transform: Callable[[Decimal], Decimal],
) -> _ScoredFeature | None:
    if value is None:
        return None
    return _ScoredFeature(
        feature_name=feature_name,
        family=family,
        label=label,
        value=value,
        score=_bounded(raw_transform(value)),
        weight=weight,
        source="derived_feature",
    )


def _context_feature_score(
    context_feature: TechnicalFeatureContext,
    *,
    weights: Mapping[str, Decimal],
) -> Decimal:
    z_component = _bounded(context_feature.directional_z_score / Decimal("2"))
    percentile_component = (context_feature.percentile - Decimal("0.5")) * Decimal("2")
    total_weight = sum(weights.values(), ZERO)
    if total_weight <= ZERO:
        return ZERO
    return _bounded(
        (
            (z_component * weights["z_score"])
            + (percentile_component * weights["percentile"])
        )
        / total_weight
    )


def _family_score(
    family: str,
    contributors: list[_ScoredFeature],
) -> tuple[Decimal, dict[str, Decimal]]:
    if not contributors:
        return ZERO.quantize(OHLCV_V2_SCORE_VALUE), {}
    total_weight = sum((contributor.weight for contributor in contributors), ZERO)
    if total_weight <= ZERO:
        components: dict[str, Decimal] = {}
        for contributor in contributors:
            components[f"{family}.{contributor.feature_name}.score"] = (
                contributor.score.quantize(OHLCV_V2_COMPONENT_VALUE)
            )
            components[f"{family}.{contributor.feature_name}.weight"] = (
                contributor.weight.quantize(OHLCV_V2_COMPONENT_VALUE)
            )
            components[f"{family}.{contributor.feature_name}.contribution"] = (
                ZERO.quantize(OHLCV_V2_COMPONENT_VALUE)
            )
        return ZERO.quantize(OHLCV_V2_SCORE_VALUE), components
    score = (
        sum(
            (contributor.score * contributor.weight for contributor in contributors),
            ZERO,
        )
        / total_weight
    )
    components: dict[str, Decimal] = {}
    for contributor in contributors:
        components[f"{family}.{contributor.feature_name}.score"] = (
            contributor.score.quantize(OHLCV_V2_COMPONENT_VALUE)
        )
        components[f"{family}.{contributor.feature_name}.weight"] = (
            contributor.weight.quantize(OHLCV_V2_COMPONENT_VALUE)
        )
        components[f"{family}.{contributor.feature_name}.contribution"] = (
            (contributor.score * contributor.weight) / total_weight
        ).quantize(OHLCV_V2_COMPONENT_VALUE)
    return _bounded_score(score), components


def _composite_contributions(
    features_by_family: Mapping[str, list[_ScoredFeature]],
    *,
    family_weights: Mapping[str, Decimal],
) -> list[tuple[_ScoredFeature, Decimal]]:
    contributions: list[tuple[_ScoredFeature, Decimal]] = []
    for family, contributors in features_by_family.items():
        if not contributors:
            continue
        total_weight = sum((contributor.weight for contributor in contributors), ZERO)
        family_weight = family_weights[family]
        for contributor in contributors:
            composite_contribution = (
                contributor.score * contributor.weight / total_weight * family_weight
            )
            contributions.append((contributor, composite_contribution))
    return contributions


def _top_contributors(
    contributions: list[tuple[_ScoredFeature, Decimal]],
    *,
    limit: int,
) -> tuple[Mapping[str, object], ...]:
    ordered = sorted(
        contributions,
        key=lambda item: (-abs(item[1]), item[0].family, item[0].feature_name),
    )
    return tuple(
        {
            "feature": contributor.feature_name,
            "family": contributor.family,
            "label": contributor.label,
            "direction": _contributor_direction(contributor.family, contribution),
            "value": str(contributor.value) if contributor.value is not None else None,
            "score": str(contributor.score.quantize(OHLCV_V2_SCORE_VALUE)),
            "weight": str(contributor.weight),
            "contribution": str(contribution.quantize(OHLCV_V2_COMPONENT_VALUE)),
            "source": contributor.source,
        }
        for contributor, contribution in ordered[: max(0, limit)]
    )


def _contributor_direction(family: str, contribution: Decimal) -> str:
    if contribution == ZERO:
        return "neutral"
    if family == "alpha":
        return "bullish" if contribution > ZERO else "bearish"
    if family == "risk":
        return "risk_support" if contribution > ZERO else "risk_penalty"
    return "tradability_support" if contribution > ZERO else "tradability_penalty"


def _coverage_ratio(*, available_count: int, total_count: int) -> Decimal:
    if total_count <= 0:
        return ZERO.quantize(OHLCV_V2_SCORE_VALUE)
    return (Decimal(available_count) / Decimal(total_count)).quantize(
        OHLCV_V2_SCORE_VALUE
    )


def _lookback_quality(values: Mapping[str, Decimal]) -> Decimal:
    if all(
        feature in values
        for feature in (
            "return_252d",
            "vol_adjusted_return_252d",
            "distance_from_52w_high",
        )
    ):
        return Decimal("1.0000")
    if all(
        feature in values for feature in ("return_126d", "vol_adjusted_return_126d")
    ):
        return Decimal("0.8000")
    if all(feature in values for feature in ("return_63d", "vol_adjusted_return_63d")):
        return Decimal("0.6500")
    if "return_20d" in values:
        return Decimal("0.4500")
    return Decimal("0.2500")


def _universe_breadth(universe_context: UniverseTechnicalContext | None) -> Decimal:
    if universe_context is None:
        return Decimal("0.2500")
    size = universe_context.universe_size
    if size >= 30:
        return Decimal("1.0000")
    if size >= 10:
        return Decimal("0.8500")
    if size >= 5:
        return Decimal("0.7000")
    if size >= 2:
        return Decimal("0.5000")
    return Decimal("0.3500")


def _context_coverage(symbol_context: TechnicalSymbolContext | None) -> Decimal:
    if symbol_context is None:
        return ZERO.quantize(OHLCV_V2_SCORE_VALUE)
    available_count = sum(
        1
        for feature in DEFAULT_TECHNICAL_CONTEXT_FEATURES
        if symbol_context.get(feature)
    )
    return _coverage_ratio(
        available_count=available_count,
        total_count=len(DEFAULT_TECHNICAL_CONTEXT_FEATURES),
    )


def _family_agreement(scores: tuple[Decimal, ...], composite_raw: Decimal) -> Decimal:
    non_zero_scores = [score for score in scores if score != ZERO]
    if not non_zero_scores or composite_raw == ZERO:
        return Decimal("0.5000")
    composite_sign = ONE if composite_raw > ZERO else Decimal("-1")
    aligned = sum(
        1 for score in non_zero_scores if _score_sign(score) == composite_sign
    )
    return (Decimal(aligned) / Decimal(len(non_zero_scores))).quantize(
        OHLCV_V2_SCORE_VALUE
    )


def _score_sign(score: Decimal) -> Decimal:
    return ONE if score > ZERO else Decimal("-1")


def _feature_group_quality(
    values: Mapping[str, Decimal],
    feature_names: tuple[str, ...],
) -> Decimal:
    available_count = sum(1 for feature in feature_names if feature in values)
    return _coverage_ratio(
        available_count=available_count, total_count=len(feature_names)
    )


def _ohlcv_confidence(
    *,
    coverage: Decimal,
    lookback_quality: Decimal,
    universe_breadth: Decimal,
    context_coverage: Decimal,
    family_agreement: Decimal,
    tradability_quality: Decimal,
    weights: Mapping[str, Decimal],
) -> Decimal:
    total_weight = sum(weights.values(), ZERO)
    if total_weight <= ZERO:
        return Decimal("0.0500")
    raw = (
        (coverage * weights["coverage"])
        + (lookback_quality * weights["lookback_quality"])
        + (universe_breadth * weights["universe_breadth"])
        + (context_coverage * weights["context_coverage"])
        + (family_agreement * weights["family_agreement"])
        + (tradability_quality * weights["tradability_quality"])
    ) / total_weight
    return _clamp(raw, Decimal("0.0500"), Decimal("0.9500")).quantize(
        OHLCV_V2_SCORE_VALUE
    )


def _missing_context_features(
    symbol_context: TechnicalSymbolContext | None,
) -> list[str]:
    if symbol_context is None:
        return list(DEFAULT_TECHNICAL_CONTEXT_FEATURES)
    return [
        feature
        for feature in DEFAULT_TECHNICAL_CONTEXT_FEATURES
        if symbol_context.get(feature) is None
    ]


def _ema_spread(values: Mapping[str, Decimal]) -> Decimal | None:
    ema_12 = values.get("ema_12")
    ema_26 = values.get("ema_26")
    if ema_12 is None or ema_26 in (None, ZERO):
        return None
    return (ema_12 / ema_26) - ONE


def _adx_directional_strength(values: Mapping[str, Decimal]) -> Decimal | None:
    adx = values.get("adx_14")
    plus_di = values.get("plus_di_14")
    minus_di = values.get("minus_di_14")
    if adx is None or plus_di is None or minus_di is None:
        return None
    direction = _bounded((plus_di - minus_di) / Decimal("100"))
    strength = _clamp((adx - Decimal("15")) / Decimal("35"), ZERO, ONE)
    return _bounded(direction * strength)


def _distance_from_high_score(value: Decimal, scale: Decimal) -> Decimal:
    return _bounded(ONE + _safe_divide(value, scale))


def _lower_is_better_score(value: Decimal, scale: Decimal) -> Decimal:
    if scale == ZERO:
        return ZERO
    return _bounded(ONE - ((value / scale) * Decimal("2")))


def _bollinger_extension_score(value: Decimal, scale: Decimal) -> Decimal:
    return _bounded(
        ONE - (_safe_divide(abs(value - Decimal("0.5")), scale) * Decimal("2"))
    )


def _bounded_score(value: Decimal) -> Decimal:
    return _bounded(value).quantize(OHLCV_V2_SCORE_VALUE)


def _scaled_score(value: Decimal, scale: Decimal) -> Decimal:
    return _bounded(_safe_divide(value, scale))


def _safe_divide(value: Decimal, denominator: Decimal) -> Decimal:
    if denominator == ZERO:
        return ZERO
    return value / denominator


def _bounded(value: Decimal) -> Decimal:
    return _clamp(value, Decimal("-1"), ONE)


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(upper, value))
