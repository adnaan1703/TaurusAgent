from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Mapping

ZERO = Decimal("0")
ONE = Decimal("1")

OHLCV_V2_ALPHA_FEATURES = (
    "return_20d",
    "vol_adjusted_return_63d",
    "vol_adjusted_return_126d",
    "vol_adjusted_return_252d",
    "return_126d",
    "return_63d",
    "return_252d",
    "macd_histogram_12_26_9",
    "ema_spread_12_26",
    "adx_directional_strength_14",
    "breakout_high_distance_20d",
    "breakout_high_distance_50d",
    "distance_from_52w_high",
    "rsi_14",
)
OHLCV_V2_RISK_FEATURES = (
    "atr_percent_14",
    "volatility_20",
    "volatility_63",
    "volatility_126",
    "volatility_252",
    "bollinger_bandwidth_20",
    "minus_di_14",
    "bollinger_percent_b_extension",
    "return_20d_instability",
)
OHLCV_V2_TRADABILITY_FEATURES = (
    "turnover",
    "avg_traded_value_20",
    "avg_traded_value_63",
    "turnover_z_score_20",
    "volume_z_score_20",
)
OHLCV_V2_CONTEXT_COMPONENTS = ("z_score", "percentile")
OHLCV_V2_CONFIDENCE_COMPONENTS = (
    "coverage",
    "lookback_quality",
    "universe_breadth",
    "context_coverage",
    "family_agreement",
    "tradability_quality",
)


@dataclass(frozen=True, slots=True)
class OhlcvV2EligibilityParams:
    min_risk_score_for_new_buys: Decimal | None = None
    negative_risk_penalty: Decimal = ZERO
    min_candidate_breadth_multiple: Decimal | None = None

    def __post_init__(self) -> None:
        if self.min_risk_score_for_new_buys is not None:
            _validate_range(
                "eligibility.min_risk_score_for_new_buys",
                self.min_risk_score_for_new_buys,
                lower=Decimal("-1"),
                upper=ONE,
            )
        _validate_non_negative(
            "eligibility.negative_risk_penalty",
            self.negative_risk_penalty,
        )
        if self.min_candidate_breadth_multiple is not None:
            _validate_non_negative(
                "eligibility.min_candidate_breadth_multiple",
                self.min_candidate_breadth_multiple,
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "min_risk_score_for_new_buys": _optional_decimal_text(
                self.min_risk_score_for_new_buys
            ),
            "negative_risk_penalty": str(self.negative_risk_penalty),
            "min_candidate_breadth_multiple": _optional_decimal_text(
                self.min_candidate_breadth_multiple
            ),
        }


@dataclass(frozen=True, slots=True)
class OhlcvV2ScoreCompressionParams:
    mode: str = "none"
    lower_bound: Decimal = Decimal("-1")
    upper_bound: Decimal = ONE

    def __post_init__(self) -> None:
        if self.mode not in {"none", "linear", "tanh"}:
            raise ValueError(
                "score_compression.mode must be one of none, linear, or tanh."
            )
        _validate_range(
            "score_compression.lower_bound",
            self.lower_bound,
            lower=Decimal("-1"),
            upper=ONE,
        )
        _validate_range(
            "score_compression.upper_bound",
            self.upper_bound,
            lower=Decimal("-1"),
            upper=ONE,
        )
        if self.lower_bound > self.upper_bound:
            raise ValueError(
                "score_compression.lower_bound must be <= "
                "score_compression.upper_bound."
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "mode": self.mode,
            "lower_bound": str(self.lower_bound),
            "upper_bound": str(self.upper_bound),
        }


@dataclass(frozen=True, slots=True)
class OhlcvV2ScoringParams:
    family_weights: Mapping[str, Decimal]
    alpha_weights: Mapping[str, Decimal]
    risk_weights: Mapping[str, Decimal]
    tradability_weights: Mapping[str, Decimal]
    alpha_transform_scales: Mapping[str, Decimal]
    risk_transform_scales: Mapping[str, Decimal]
    tradability_transform_scales: Mapping[str, Decimal]
    context_weights: Mapping[str, Decimal]
    confidence_weights: Mapping[str, Decimal]
    eligibility: OhlcvV2EligibilityParams
    score_compression: OhlcvV2ScoreCompressionParams

    def __post_init__(self) -> None:
        _validate_key_set(
            "family_weights",
            self.family_weights,
            ("alpha", "risk", "tradability"),
        )
        _validate_key_set("alpha_weights", self.alpha_weights, OHLCV_V2_ALPHA_FEATURES)
        _validate_key_set("risk_weights", self.risk_weights, OHLCV_V2_RISK_FEATURES)
        _validate_key_set(
            "tradability_weights",
            self.tradability_weights,
            OHLCV_V2_TRADABILITY_FEATURES,
        )
        _validate_key_set(
            "alpha_transforms",
            self.alpha_transform_scales,
            OHLCV_V2_ALPHA_FEATURES,
        )
        _validate_key_set(
            "risk_transforms",
            self.risk_transform_scales,
            OHLCV_V2_RISK_FEATURES,
        )
        _validate_key_set(
            "tradability_transforms",
            self.tradability_transform_scales,
            OHLCV_V2_TRADABILITY_FEATURES,
        )
        _validate_key_set(
            "context_weights",
            self.context_weights,
            OHLCV_V2_CONTEXT_COMPONENTS,
        )
        _validate_key_set(
            "confidence_weights",
            self.confidence_weights,
            OHLCV_V2_CONFIDENCE_COMPONENTS,
        )
        _validate_decimal_map("family_weights", self.family_weights)
        _validate_decimal_map("alpha_weights", self.alpha_weights)
        _validate_decimal_map("risk_weights", self.risk_weights)
        _validate_decimal_map("tradability_weights", self.tradability_weights)
        _validate_decimal_map("alpha_transforms", self.alpha_transform_scales)
        _validate_decimal_map("risk_transforms", self.risk_transform_scales)
        _validate_decimal_map(
            "tradability_transforms",
            self.tradability_transform_scales,
        )
        _validate_decimal_map("context_weights", self.context_weights)
        _validate_decimal_map("confidence_weights", self.confidence_weights)
        family_total = sum(self.family_weights.values(), ZERO)
        if family_total != ONE:
            raise ValueError(f"family_weights must sum to 1; got {family_total}.")
        if sum(self.context_weights.values(), ZERO) <= ZERO:
            raise ValueError("context_weights must include a positive total weight.")
        if sum(self.confidence_weights.values(), ZERO) <= ZERO:
            raise ValueError("confidence_weights must include a positive total weight.")

        object.__setattr__(
            self,
            "family_weights",
            MappingProxyType(dict(self.family_weights)),
        )
        object.__setattr__(
            self,
            "alpha_weights",
            MappingProxyType(dict(self.alpha_weights)),
        )
        object.__setattr__(
            self,
            "risk_weights",
            MappingProxyType(dict(self.risk_weights)),
        )
        object.__setattr__(
            self,
            "tradability_weights",
            MappingProxyType(dict(self.tradability_weights)),
        )
        object.__setattr__(
            self,
            "alpha_transform_scales",
            MappingProxyType(dict(self.alpha_transform_scales)),
        )
        object.__setattr__(
            self,
            "risk_transform_scales",
            MappingProxyType(dict(self.risk_transform_scales)),
        )
        object.__setattr__(
            self,
            "tradability_transform_scales",
            MappingProxyType(dict(self.tradability_transform_scales)),
        )
        object.__setattr__(
            self,
            "context_weights",
            MappingProxyType(dict(self.context_weights)),
        )
        object.__setattr__(
            self,
            "confidence_weights",
            MappingProxyType(dict(self.confidence_weights)),
        )

    @classmethod
    def from_mapping(
        cls,
        values: Mapping[str, object] | None,
    ) -> "OhlcvV2ScoringParams":
        params = default_ohlcv_v2_scoring_params()
        if not values:
            return params
        return params.with_overrides(_flatten_mapping(values))

    def with_overrides(
        self,
        overrides: Mapping[str, object],
    ) -> "OhlcvV2ScoringParams":
        family_weights = dict(self.family_weights)
        alpha_weights = dict(self.alpha_weights)
        risk_weights = dict(self.risk_weights)
        tradability_weights = dict(self.tradability_weights)
        alpha_scales = dict(self.alpha_transform_scales)
        risk_scales = dict(self.risk_transform_scales)
        tradability_scales = dict(self.tradability_transform_scales)
        context_weights = dict(self.context_weights)
        confidence_weights = dict(self.confidence_weights)
        eligibility = {
            "min_risk_score_for_new_buys": (
                self.eligibility.min_risk_score_for_new_buys
            ),
            "negative_risk_penalty": self.eligibility.negative_risk_penalty,
            "min_candidate_breadth_multiple": (
                self.eligibility.min_candidate_breadth_multiple
            ),
        }
        compression = {
            "mode": self.score_compression.mode,
            "lower_bound": self.score_compression.lower_bound,
            "upper_bound": self.score_compression.upper_bound,
        }

        for path, raw_value in overrides.items():
            parts = path.split(".")
            if len(parts) == 2 and parts[0] == "family_weights":
                _set_decimal(family_weights, "family_weights", parts[1], raw_value)
            elif len(parts) == 2 and parts[0] == "alpha_weights":
                _set_decimal(alpha_weights, "alpha_weights", parts[1], raw_value)
            elif len(parts) == 2 and parts[0] == "risk_weights":
                _set_decimal(risk_weights, "risk_weights", parts[1], raw_value)
            elif len(parts) == 2 and parts[0] == "tradability_weights":
                _set_decimal(
                    tradability_weights,
                    "tradability_weights",
                    parts[1],
                    raw_value,
                )
            elif (
                len(parts) == 3
                and parts[0] == "alpha_transforms"
                and parts[2] == "scale"
            ):
                _set_decimal(alpha_scales, "alpha_transforms", parts[1], raw_value)
            elif (
                len(parts) == 3
                and parts[0] == "risk_transforms"
                and parts[2] == "scale"
            ):
                _set_decimal(risk_scales, "risk_transforms", parts[1], raw_value)
            elif (
                len(parts) == 3
                and parts[0] == "tradability_transforms"
                and parts[2] == "scale"
            ):
                _set_decimal(
                    tradability_scales,
                    "tradability_transforms",
                    parts[1],
                    raw_value,
                )
            elif len(parts) == 2 and parts[0] == "context_weights":
                _set_decimal(context_weights, "context_weights", parts[1], raw_value)
            elif len(parts) == 2 and parts[0] == "confidence_weights":
                _set_decimal(
                    confidence_weights,
                    "confidence_weights",
                    parts[1],
                    raw_value,
                )
            elif len(parts) == 2 and parts[0] == "eligibility":
                if parts[1] not in eligibility:
                    _raise_unknown_path(path)
                if parts[1] in {
                    "min_risk_score_for_new_buys",
                    "min_candidate_breadth_multiple",
                }:
                    eligibility[parts[1]] = _optional_decimal(raw_value, path)
                else:
                    eligibility[parts[1]] = _decimal(raw_value, path)
            elif len(parts) == 2 and parts[0] == "score_compression":
                if parts[1] == "mode":
                    compression["mode"] = str(raw_value).strip()
                elif parts[1] in {"lower_bound", "upper_bound"}:
                    compression[parts[1]] = _decimal(raw_value, path)
                else:
                    _raise_unknown_path(path)
            else:
                _raise_unknown_path(path)

        return OhlcvV2ScoringParams(
            family_weights=family_weights,
            alpha_weights=alpha_weights,
            risk_weights=risk_weights,
            tradability_weights=tradability_weights,
            alpha_transform_scales=alpha_scales,
            risk_transform_scales=risk_scales,
            tradability_transform_scales=tradability_scales,
            context_weights=context_weights,
            confidence_weights=confidence_weights,
            eligibility=OhlcvV2EligibilityParams(
                min_risk_score_for_new_buys=eligibility[
                    "min_risk_score_for_new_buys"
                ],
                negative_risk_penalty=eligibility["negative_risk_penalty"],
                min_candidate_breadth_multiple=eligibility[
                    "min_candidate_breadth_multiple"
                ],
            ),
            score_compression=OhlcvV2ScoreCompressionParams(
                mode=str(compression["mode"]),
                lower_bound=compression["lower_bound"],
                upper_bound=compression["upper_bound"],
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "family_weights": _decimal_text_map(self.family_weights),
            "alpha_weights": _decimal_text_map(self.alpha_weights),
            "risk_weights": _decimal_text_map(self.risk_weights),
            "tradability_weights": _decimal_text_map(self.tradability_weights),
            "alpha_transforms": _scale_map(self.alpha_transform_scales),
            "risk_transforms": _scale_map(self.risk_transform_scales),
            "tradability_transforms": _scale_map(self.tradability_transform_scales),
            "context_weights": _decimal_text_map(self.context_weights),
            "confidence_weights": _decimal_text_map(self.confidence_weights),
            "eligibility": self.eligibility.to_dict(),
            "score_compression": self.score_compression.to_dict(),
        }

    @property
    def is_default(self) -> bool:
        return self == DEFAULT_OHLCV_V2_SCORING_PARAMS


def default_ohlcv_v2_scoring_params() -> OhlcvV2ScoringParams:
    return OhlcvV2ScoringParams(
        family_weights={
            "alpha": Decimal("0.65"),
            "risk": Decimal("0.20"),
            "tradability": Decimal("0.15"),
        },
        alpha_weights={
            "return_20d": ZERO,
            "vol_adjusted_return_63d": ZERO,
            "vol_adjusted_return_126d": Decimal("0.16"),
            "vol_adjusted_return_252d": Decimal("0.14"),
            "return_126d": Decimal("0.11"),
            "return_63d": Decimal("0.10"),
            "return_252d": Decimal("0.08"),
            "macd_histogram_12_26_9": Decimal("0.09"),
            "ema_spread_12_26": Decimal("0.08"),
            "adx_directional_strength_14": Decimal("0.08"),
            "breakout_high_distance_20d": ZERO,
            "breakout_high_distance_50d": Decimal("0.06"),
            "distance_from_52w_high": Decimal("0.05"),
            "rsi_14": Decimal("0.05"),
        },
        risk_weights={
            "atr_percent_14": Decimal("0.18"),
            "volatility_20": Decimal("0.16"),
            "volatility_63": Decimal("0.14"),
            "volatility_126": Decimal("0.10"),
            "volatility_252": Decimal("0.08"),
            "bollinger_bandwidth_20": Decimal("0.10"),
            "minus_di_14": Decimal("0.08"),
            "bollinger_percent_b_extension": Decimal("0.08"),
            "return_20d_instability": Decimal("0.08"),
        },
        tradability_weights={
            "turnover": Decimal("0.24"),
            "avg_traded_value_20": Decimal("0.24"),
            "avg_traded_value_63": Decimal("0.20"),
            "turnover_z_score_20": Decimal("0.17"),
            "volume_z_score_20": Decimal("0.15"),
        },
        alpha_transform_scales={
            "return_20d": Decimal("0.08"),
            "vol_adjusted_return_63d": Decimal("4"),
            "vol_adjusted_return_126d": Decimal("4"),
            "vol_adjusted_return_252d": Decimal("4"),
            "return_126d": Decimal("0.30"),
            "return_63d": Decimal("0.20"),
            "return_252d": Decimal("0.45"),
            "macd_histogram_12_26_9": ONE,
            "ema_spread_12_26": Decimal("0.08"),
            "adx_directional_strength_14": ONE,
            "breakout_high_distance_20d": Decimal("0.08"),
            "breakout_high_distance_50d": Decimal("0.10"),
            "distance_from_52w_high": Decimal("0.25"),
            "rsi_14": Decimal("25"),
        },
        risk_transform_scales={
            "atr_percent_14": Decimal("0.045"),
            "volatility_20": Decimal("0.050"),
            "volatility_63": Decimal("0.045"),
            "volatility_126": Decimal("0.045"),
            "volatility_252": Decimal("0.045"),
            "bollinger_bandwidth_20": Decimal("0.18"),
            "minus_di_14": Decimal("45"),
            "bollinger_percent_b_extension": Decimal("0.25"),
            "return_20d_instability": Decimal("0.18"),
        },
        tradability_transform_scales={
            "turnover": ONE,
            "avg_traded_value_20": ONE,
            "avg_traded_value_63": ONE,
            "turnover_z_score_20": Decimal("3"),
            "volume_z_score_20": Decimal("3"),
        },
        context_weights={
            "z_score": Decimal("0.60"),
            "percentile": Decimal("0.40"),
        },
        confidence_weights={
            "coverage": Decimal("0.35"),
            "lookback_quality": Decimal("0.20"),
            "universe_breadth": Decimal("0.15"),
            "context_coverage": Decimal("0.05"),
            "family_agreement": Decimal("0.15"),
            "tradability_quality": Decimal("0.10"),
        },
        eligibility=OhlcvV2EligibilityParams(),
        score_compression=OhlcvV2ScoreCompressionParams(),
    )


def short_horizon_ohlcv_v2a_scoring_params() -> OhlcvV2ScoringParams:
    return default_ohlcv_v2_scoring_params().with_overrides(
        {
            "family_weights.alpha": "0.70",
            "family_weights.risk": "0.15",
            "family_weights.tradability": "0.15",
            "alpha_weights.return_20d": "0.18",
            "alpha_weights.vol_adjusted_return_63d": "0.16",
            "alpha_weights.vol_adjusted_return_126d": "0",
            "alpha_weights.vol_adjusted_return_252d": "0",
            "alpha_weights.return_126d": "0",
            "alpha_weights.return_63d": "0.14",
            "alpha_weights.return_252d": "0",
            "alpha_weights.macd_histogram_12_26_9": "0.13",
            "alpha_weights.ema_spread_12_26": "0.12",
            "alpha_weights.adx_directional_strength_14": "0",
            "alpha_weights.breakout_high_distance_20d": "0.10",
            "alpha_weights.breakout_high_distance_50d": "0.07",
            "alpha_weights.distance_from_52w_high": "0",
            "alpha_weights.rsi_14": "0.10",
            "risk_weights.atr_percent_14": "0.50",
            "risk_weights.volatility_20": "0.50",
            "risk_weights.volatility_63": "0",
            "risk_weights.volatility_126": "0",
            "risk_weights.volatility_252": "0",
            "risk_weights.bollinger_bandwidth_20": "0",
            "risk_weights.minus_di_14": "0",
            "risk_weights.bollinger_percent_b_extension": "0",
            "risk_weights.return_20d_instability": "0",
            "tradability_weights.turnover": "0.15",
            "tradability_weights.avg_traded_value_20": "0.25",
            "tradability_weights.avg_traded_value_63": "0.15",
            "tradability_weights.turnover_z_score_20": "0.20",
            "tradability_weights.volume_z_score_20": "0.25",
        }
    )


def ohlcv_v2_parameter_paths() -> tuple[str, ...]:
    paths: list[str] = []
    paths.extend(
        f"family_weights.{family}" for family in ("alpha", "risk", "tradability")
    )
    for family, features in (
        ("alpha", OHLCV_V2_ALPHA_FEATURES),
        ("risk", OHLCV_V2_RISK_FEATURES),
        ("tradability", OHLCV_V2_TRADABILITY_FEATURES),
    ):
        paths.extend(f"{family}_weights.{feature}" for feature in features)
        paths.extend(f"{family}_transforms.{feature}.scale" for feature in features)
    paths.extend(
        f"context_weights.{component}" for component in OHLCV_V2_CONTEXT_COMPONENTS
    )
    paths.extend(
        f"confidence_weights.{component}"
        for component in OHLCV_V2_CONFIDENCE_COMPONENTS
    )
    paths.extend(
        (
            "eligibility.min_risk_score_for_new_buys",
            "eligibility.negative_risk_penalty",
            "eligibility.min_candidate_breadth_multiple",
            "score_compression.mode",
            "score_compression.lower_bound",
            "score_compression.upper_bound",
        )
    )
    return tuple(paths)


def _flatten_mapping(values: Mapping[str, object]) -> dict[str, object]:
    flattened: dict[str, object] = {}

    def walk(prefix: str, value: object) -> None:
        if isinstance(value, Mapping):
            for nested_key, nested_value in value.items():
                key = str(nested_key).strip()
                if not key:
                    raise ValueError("v2A scoring parameter names must not be empty.")
                walk(f"{prefix}.{key}" if prefix else key, nested_value)
            return
        if not prefix:
            raise ValueError("v2A scoring parameter names must not be empty.")
        flattened[prefix] = value

    walk("", values)
    return flattened


def _set_decimal(
    target: dict[str, Decimal],
    section: str,
    key: str,
    value: object,
) -> None:
    if key not in target:
        _raise_unknown_path(f"{section}.{key}")
    target[key] = _decimal(value, f"{section}.{key}")


def _decimal(value: object, path: str) -> Decimal:
    if isinstance(value, bool):
        raise ValueError(f"{path} must be decimal-compatible, not boolean.")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{path} must be decimal-compatible.") from exc


def _optional_decimal(value: object, path: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return _decimal(value, path)


def _validate_key_set(
    section: str,
    values: Mapping[str, Decimal],
    expected: tuple[str, ...],
) -> None:
    expected_set = set(expected)
    actual_set = set(values)
    unknown = sorted(actual_set - expected_set)
    missing = sorted(expected_set - actual_set)
    if unknown:
        raise ValueError(
            f"Unknown v2A scoring parameter(s) in {section}: {', '.join(unknown)}."
        )
    if missing:
        raise ValueError(
            f"Missing v2A scoring parameter(s) in {section}: {', '.join(missing)}."
        )


def _validate_decimal_map(section: str, values: Mapping[str, Decimal]) -> None:
    for key, value in values.items():
        _validate_non_negative(f"{section}.{key}", value)


def _validate_non_negative(path: str, value: Decimal) -> None:
    if value < ZERO:
        raise ValueError(f"{path} must be non-negative; got {value}.")


def _validate_range(
    path: str,
    value: Decimal,
    *,
    lower: Decimal,
    upper: Decimal,
) -> None:
    if value < lower or value > upper:
        raise ValueError(f"{path} must be between {lower} and {upper}; got {value}.")


def _raise_unknown_path(path: str) -> None:
    raise ValueError(f"Unknown v2A scoring parameter path: {path}.")


def _decimal_text_map(values: Mapping[str, Decimal]) -> dict[str, str]:
    return {key: str(value) for key, value in values.items()}


def _scale_map(values: Mapping[str, Decimal]) -> dict[str, dict[str, str]]:
    return {key: {"scale": str(value)} for key, value in values.items()}


def _optional_decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


DEFAULT_OHLCV_V2_SCORING_PARAMS = default_ohlcv_v2_scoring_params()
DEFAULT_OHLCV_V2A_SH_SCORING_PARAMS = short_horizon_ohlcv_v2a_scoring_params()
