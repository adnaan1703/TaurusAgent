from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from experiments.parametric.errors import ExperimentSpecError

DECIMAL_ZERO = Decimal("0")
DECIMAL_ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class ParameterDefinition:
    path: str
    value_kind: str
    min_value: Decimal | None = None
    max_value: Decimal | None = None
    allowed_values: tuple[str, ...] = ()

    def normalize(self, value: object) -> object:
        if self.value_kind == "decimal":
            normalized = _decimal(value, self.path)
            if self.min_value is not None and normalized < self.min_value:
                raise ExperimentSpecError(
                    f"Override {self.path} must be >= {self.min_value}; got {normalized}."
                )
            if self.max_value is not None and normalized > self.max_value:
                raise ExperimentSpecError(
                    f"Override {self.path} must be <= {self.max_value}; got {normalized}."
                )
            return normalized
        if self.value_kind == "positive_int":
            normalized = _int(value, self.path)
            if normalized <= 0:
                raise ExperimentSpecError(
                    f"Override {self.path} must be a positive integer; got {normalized}."
                )
            return normalized
        if self.value_kind == "non_negative_int":
            normalized = _int(value, self.path)
            if normalized < 0:
                raise ExperimentSpecError(
                    f"Override {self.path} must be a non-negative integer; got {normalized}."
                )
            return normalized
        if self.value_kind == "bool":
            return _bool(value, self.path)
        if self.value_kind == "choice":
            cleaned = str(value).strip()
            if cleaned not in self.allowed_values:
                allowed = ", ".join(self.allowed_values)
                raise ExperimentSpecError(
                    f"Override {self.path} must be one of {allowed}; got {cleaned!r}."
                )
            return cleaned
        if self.value_kind == "symbol_csv":
            symbols = tuple(
                symbol.strip().upper()
                for symbol in str(value).split(",")
                if symbol.strip()
            )
            if not symbols:
                raise ExperimentSpecError(f"Override {self.path} requires at least one symbol.")
            return symbols
        cleaned = str(value).strip()
        if not cleaned:
            raise ExperimentSpecError(f"Override {self.path} must not be empty.")
        return cleaned


@dataclass(frozen=True, slots=True)
class AdapterDefinition:
    adapter_id: str
    override_parameters: Mapping[str, ParameterDefinition]
    default_family_weights: Mapping[str, Decimal]

    def normalize_override(self, path: str, value: object) -> object:
        definition = self.override_parameters.get(path)
        if definition is None:
            raise ExperimentSpecError(
                f"Unknown override path {path!r} for adapter {self.adapter_id!r}."
            )
        return definition.normalize(value)


class AdapterRegistry:
    def __init__(self, adapters: Mapping[str, AdapterDefinition]) -> None:
        self._adapters = dict(adapters)

    def get(self, adapter_id: str) -> AdapterDefinition:
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            known = ", ".join(sorted(self._adapters)) or "none"
            raise ExperimentSpecError(f"Unknown adapter {adapter_id!r}. Known adapters: {known}.")
        return adapter

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._adapters))


ALPHA_FEATURES = (
    "vol_adjusted_return_126d",
    "vol_adjusted_return_252d",
    "return_126d",
    "return_63d",
    "return_252d",
    "macd_histogram_12_26_9",
    "ema_spread_12_26",
    "adx_directional_strength_14",
    "breakout_high_distance_50d",
    "distance_from_52w_high",
    "rsi_14",
)
RISK_FEATURES = (
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
TRADABILITY_FEATURES = (
    "turnover",
    "avg_traded_value_20",
    "avg_traded_value_63",
    "turnover_z_score_20",
    "volume_z_score_20",
)
CONFIDENCE_COMPONENTS = (
    "coverage",
    "lookback_quality",
    "universe_breadth",
    "context_coverage",
    "family_agreement",
    "tradability_quality",
)


def default_adapter_registry() -> AdapterRegistry:
    return AdapterRegistry(
        {
            "technical_validation_v2a": AdapterDefinition(
                adapter_id="technical_validation_v2a",
                override_parameters=_technical_validation_v2a_parameters(),
                default_family_weights={
                    "alpha": Decimal("0.65"),
                    "risk": Decimal("0.20"),
                    "tradability": Decimal("0.15"),
                },
            )
        }
    )


def _technical_validation_v2a_parameters() -> dict[str, ParameterDefinition]:
    params: dict[str, ParameterDefinition] = {}
    for family in ("alpha", "risk", "tradability"):
        params[f"family_weights.{family}"] = ParameterDefinition(
            f"family_weights.{family}",
            "decimal",
            min_value=DECIMAL_ZERO,
            max_value=DECIMAL_ONE,
        )
    for family, features in (
        ("alpha", ALPHA_FEATURES),
        ("risk", RISK_FEATURES),
        ("tradability", TRADABILITY_FEATURES),
    ):
        for feature in features:
            params[f"{family}_weights.{feature}"] = ParameterDefinition(
                f"{family}_weights.{feature}",
                "decimal",
                min_value=DECIMAL_ZERO,
            )
            params[f"{family}_transforms.{feature}.scale"] = ParameterDefinition(
                f"{family}_transforms.{feature}.scale",
                "decimal",
                min_value=DECIMAL_ZERO,
            )
    for component in ("z_score", "percentile"):
        params[f"context_weights.{component}"] = ParameterDefinition(
            f"context_weights.{component}",
            "decimal",
            min_value=DECIMAL_ZERO,
        )
    for component in CONFIDENCE_COMPONENTS:
        params[f"confidence_weights.{component}"] = ParameterDefinition(
            f"confidence_weights.{component}",
            "decimal",
            min_value=DECIMAL_ZERO,
        )
    params.update(
        {
            "eligibility.min_risk_score_for_new_buys": ParameterDefinition(
                "eligibility.min_risk_score_for_new_buys",
                "decimal",
                min_value=Decimal("-1"),
                max_value=DECIMAL_ONE,
            ),
            "eligibility.negative_risk_penalty": ParameterDefinition(
                "eligibility.negative_risk_penalty",
                "decimal",
                min_value=DECIMAL_ZERO,
            ),
            "eligibility.min_candidate_breadth_multiple": ParameterDefinition(
                "eligibility.min_candidate_breadth_multiple",
                "decimal",
                min_value=DECIMAL_ZERO,
            ),
            "score_compression.mode": ParameterDefinition(
                "score_compression.mode",
                "choice",
                allowed_values=("none", "linear", "tanh"),
            ),
            "score_compression.lower_bound": ParameterDefinition(
                "score_compression.lower_bound",
                "decimal",
                min_value=Decimal("-1"),
                max_value=DECIMAL_ONE,
            ),
            "score_compression.upper_bound": ParameterDefinition(
                "score_compression.upper_bound",
                "decimal",
                min_value=Decimal("-1"),
                max_value=DECIMAL_ONE,
            ),
            "backtest.portfolio_breadth": ParameterDefinition(
                "backtest.portfolio_breadth",
                "positive_int",
            ),
            "backtest.max_open_positions": ParameterDefinition(
                "backtest.max_open_positions",
                "positive_int",
            ),
            "backtest.rebalance_every_days": ParameterDefinition(
                "backtest.rebalance_every_days",
                "positive_int",
            ),
            "backtest.cost_bps": ParameterDefinition(
                "backtest.cost_bps",
                "decimal",
                min_value=DECIMAL_ZERO,
            ),
            "backtest.slippage_bps": ParameterDefinition(
                "backtest.slippage_bps",
                "decimal",
                min_value=DECIMAL_ZERO,
            ),
            "backtest.validation_mode": ParameterDefinition(
                "backtest.validation_mode",
                "choice",
                allowed_values=("standard", "strong"),
            ),
            "backtest.symbols": ParameterDefinition("backtest.symbols", "symbol_csv"),
            "backtest.universe": ParameterDefinition("backtest.universe", "string"),
            "backtest.warmup_days": ParameterDefinition(
                "backtest.warmup_days",
                "non_negative_int",
            ),
            "backtest.validation_years": ParameterDefinition(
                "backtest.validation_years",
                "positive_int",
            ),
        }
    )
    return params


def _decimal(value: object, path: str) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ExperimentSpecError(f"Override {path} must be decimal-compatible.") from exc


def _int(value: object, path: str) -> int:
    if isinstance(value, bool):
        raise ExperimentSpecError(f"Override {path} must be an integer, not a boolean.")
    try:
        return int(str(value))
    except ValueError as exc:
        raise ExperimentSpecError(f"Override {path} must be an integer.") from exc


def _bool(value: object, path: str) -> bool:
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ExperimentSpecError(f"Override {path} must be boolean-compatible.")

