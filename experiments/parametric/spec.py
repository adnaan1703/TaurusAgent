from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

DEFAULT_MAX_VARIANTS = 500
STABLE_ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")

MatrixValue = str | int | float | Decimal | bool


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class BaseRequestSpec(_StrictModel):
    mode: Literal["standard", "strong"] = "standard"
    symbols: tuple[str, ...] = ()
    universe: str | None = None
    universe_path: str | None = None
    validation_years: int = Field(default=3, gt=0)
    evaluation_days: int | None = Field(default=None, gt=0)
    warmup_days: int = Field(default=252, ge=0)
    timeframe: str = "1d"
    artifact_root: Path | None = None
    report_root: Path | None = None
    initial_capital_inr: Decimal | None = Field(default=None, gt=0)
    portfolio_breadth: int = Field(default=5, gt=0)
    max_open_positions: int = Field(default=5, gt=0)
    rebalance_every_days: int = Field(default=21, gt=0)
    cost_bps: Decimal = Field(default=Decimal("10"), ge=0)
    slippage_bps: Decimal = Field(default=Decimal("5"), ge=0)
    strict_insufficient_data: bool = False
    include_v2b: bool = False

    @field_validator("symbols", mode="before")
    @classmethod
    def _normalize_symbols(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            raw_symbols = value.split(",")
        else:
            raw_symbols = value
        if not isinstance(raw_symbols, (list, tuple, set)):
            raise ValueError("symbols must be a list or comma-separated string")
        normalized = tuple(
            sorted({str(symbol).strip().upper() for symbol in raw_symbols if str(symbol).strip()})
        )
        return normalized

    @field_validator("timeframe")
    @classmethod
    def _timeframe_not_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("timeframe must not be empty")
        return cleaned

    @model_validator(mode="after")
    def _validate_universe_or_symbols(self) -> "BaseRequestSpec":
        if not self.symbols and not self.universe and not self.universe_path:
            raise ValueError("base_request requires symbols, universe, or universe_path")
        if self.include_v2b:
            raise ValueError("include_v2b must remain false for the M90-M95 v2A harness")
        if self.max_open_positions < self.portfolio_breadth:
            raise ValueError("max_open_positions must be greater than or equal to portfolio_breadth")
        return self


class BaselinesSpec(_StrictModel):
    include_v1: bool = True
    include_current_v2a: bool = True


def _clean_override_mapping(value: object, *, label: str) -> dict[str, object]:
    if not isinstance(value, dict) or not value:
        raise ValueError(f"{label} must be a non-empty mapping")
    cleaned: dict[str, object] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not key:
            raise ValueError(f"{label} contains an empty override path")
        cleaned[key] = raw_value
    return cleaned


def _clean_stable_id(value: str, *, label: str) -> str:
    cleaned = str(value).strip()
    if not cleaned:
        raise ValueError(f"{label} must not be empty")
    if STABLE_ID_PATTERN.fullmatch(cleaned) is None:
        raise ValueError(
            f"{label} must start with a letter or number and contain only letters, "
            "numbers, underscores, periods, or hyphens"
        )
    return cleaned


class AxisValueSpec(_StrictModel):
    id: str
    overrides: dict[str, MatrixValue]

    @field_validator("id")
    @classmethod
    def _id_must_be_stable(cls, value: str) -> str:
        return _clean_stable_id(value, label="variants.axes.values.id")

    @field_validator("overrides", mode="before")
    @classmethod
    def _overrides_must_be_mapping(cls, value: object) -> dict[str, object]:
        return _clean_override_mapping(
            value,
            label="variants.axes.values.overrides",
        )


class VariantAxisSpec(_StrictModel):
    name: str
    values: tuple[AxisValueSpec, ...]

    @field_validator("name")
    @classmethod
    def _name_must_be_stable(cls, value: str) -> str:
        return _clean_stable_id(value, label="variants.axes.name")

    @field_validator("values", mode="before")
    @classmethod
    def _values_must_be_non_empty_list(cls, value: object) -> object:
        if not isinstance(value, list) or not value:
            raise ValueError("variants.axes.values must be a non-empty list")
        return value

    @model_validator(mode="after")
    def _value_ids_must_be_unique(self) -> "VariantAxisSpec":
        value_ids = [value.id for value in self.values]
        if len(set(value_ids)) != len(value_ids):
            raise ValueError(f"variants.axes.{self.name} contains duplicate value ids")
        return self


class VariantsSpec(_StrictModel):
    matrix: dict[str, tuple[MatrixValue, ...]]
    axes: tuple[VariantAxisSpec, ...] = ()

    @field_validator("matrix", mode="before")
    @classmethod
    def _matrix_values_must_be_lists(cls, value: object) -> dict[str, object]:
        if not isinstance(value, dict) or not value:
            raise ValueError("variants.matrix must be a non-empty mapping")
        cleaned: dict[str, object] = {}
        for raw_key, raw_values in value.items():
            key = str(raw_key).strip()
            if not key:
                raise ValueError("variants.matrix contains an empty override path")
            if not isinstance(raw_values, list) or not raw_values:
                raise ValueError(f"variants.matrix.{key} must be a non-empty list")
            cleaned[key] = raw_values
        return cleaned

    @field_validator("axes", mode="before")
    @classmethod
    def _axes_must_be_list(cls, value: object) -> object:
        if value is None:
            return ()
        if not isinstance(value, list):
            raise ValueError("variants.axes must be a list")
        return value

    @model_validator(mode="after")
    def _axis_names_must_be_unique(self) -> "VariantsSpec":
        axis_names = [axis.name for axis in self.axes]
        if len(set(axis_names)) != len(axis_names):
            raise ValueError("variants.axes contains duplicate axis names")
        return self


class FoldsSpec(_StrictModel):
    mode: Literal["single_window", "v2a_yearly"] = "v2a_yearly"


class ExecutionSpec(_StrictModel):
    jobs: int = Field(default=1, gt=0)
    max_variants: int = Field(default=DEFAULT_MAX_VARIANTS, gt=0)


class OutputSpec(_StrictModel):
    root: Path = Path("experiments/runs")


class ExperimentSpec(_StrictModel):
    schema_version: Literal[1]
    experiment_id: str = Field(pattern=r"^[a-zA-Z0-9][a-zA-Z0-9_.-]*$")
    adapter: str
    description: str = ""
    base_request: BaseRequestSpec
    baselines: BaselinesSpec = Field(default_factory=BaselinesSpec)
    variants: VariantsSpec
    folds: FoldsSpec = Field(default_factory=FoldsSpec)
    metrics: tuple[str, ...]
    execution: ExecutionSpec = Field(default_factory=ExecutionSpec)
    output: OutputSpec = Field(default_factory=OutputSpec)

    @field_validator("adapter", "experiment_id")
    @classmethod
    def _required_strings(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("value must not be empty")
        return cleaned

    @field_validator("metrics", mode="before")
    @classmethod
    def _normalize_metrics(cls, value: object) -> tuple[str, ...]:
        if not isinstance(value, list) or not value:
            raise ValueError("metrics must be a non-empty list")
        metrics = tuple(str(metric).strip() for metric in value if str(metric).strip())
        if not metrics:
            raise ValueError("metrics must contain at least one metric id")
        if len(set(metrics)) != len(metrics):
            raise ValueError("metrics must not contain duplicates")
        return metrics
