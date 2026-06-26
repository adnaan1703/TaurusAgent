from __future__ import annotations

import hashlib
import itertools
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Mapping

from experiments.parametric.adapters import AdapterDefinition, default_adapter_registry
from experiments.parametric.errors import ExperimentSpecError
from experiments.parametric.metrics import MetricDefinition, default_metric_registry
from experiments.parametric.spec import DEFAULT_MAX_VARIANTS, ExperimentSpec

TRADING_DAYS_PER_YEAR = 252
_MISSING = object()


@dataclass(frozen=True, slots=True)
class FoldPlan:
    fold_id: str
    mode: str
    index: int
    evaluation_days: int | None = None
    evaluation_end_offset_days: int = 0


@dataclass(frozen=True, slots=True)
class PlannedOutputPaths:
    variant_dir: Path
    manifest_path: Path
    comparison_csv_path: Path


@dataclass(frozen=True, slots=True)
class AxisSelection:
    axis: str
    value_id: str


@dataclass(frozen=True, slots=True)
class VariantPlan:
    variant_id: str
    fingerprint: str
    variant_index: int
    work_unit_index: int
    overrides: Mapping[str, object]
    axis_selections: tuple[AxisSelection, ...]
    fold: FoldPlan
    output_paths: PlannedOutputPaths


@dataclass(frozen=True, slots=True)
class ExperimentPlan:
    spec: ExperimentSpec
    adapter: AdapterDefinition
    metrics: tuple[MetricDefinition, ...]
    folds: tuple[FoldPlan, ...]
    variants: tuple[VariantPlan, ...]
    output_root: Path
    run_id: str
    spec_fingerprint: str
    jobs: int
    max_variants: int

    @property
    def variant_count(self) -> int:
        return len({variant.variant_id for variant in self.variants})

    @property
    def fold_count(self) -> int:
        return len(self.folds)

    @property
    def total_work_units(self) -> int:
        return len(self.variants)

    @property
    def metric_ids(self) -> tuple[str, ...]:
        return tuple(metric.metric_id for metric in self.metrics)


@dataclass(frozen=True, slots=True)
class _AxisOption:
    selection: AxisSelection
    overrides: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class _ExpandedVariant:
    overrides: dict[str, object]
    axis_selections: tuple[AxisSelection, ...]


def expand_experiment(
    spec: ExperimentSpec,
    *,
    jobs: int | None = None,
    max_variants: int | None = None,
    output_root: str | Path | None = None,
) -> ExperimentPlan:
    adapter = default_adapter_registry().get(spec.adapter)
    metrics = default_metric_registry().validate(spec.metrics)
    resolved_jobs = jobs if jobs is not None else spec.execution.jobs
    if resolved_jobs <= 0:
        raise ExperimentSpecError("jobs must be a positive integer.")
    variant_limit = max_variants if max_variants is not None else spec.execution.max_variants
    if variant_limit <= 0:
        raise ExperimentSpecError("max_variants must be a positive integer.")

    combinations = _expanded_variants(adapter, spec)
    explicitly_overrode_limit = (
        max_variants is not None or "max_variants" in spec.execution.model_fields_set
    )
    if len(combinations) > DEFAULT_MAX_VARIANTS and not explicitly_overrode_limit:
        raise ExperimentSpecError(
            "Experiment expands to "
            f"{len(combinations)} variants, exceeding the default cap of "
            f"{DEFAULT_MAX_VARIANTS}. Pass --max-variants or set execution.max_variants "
            "to make the larger sweep explicit."
        )
    if len(combinations) > variant_limit:
        raise ExperimentSpecError(
            f"Experiment expands to {len(combinations)} variants, exceeding max_variants={variant_limit}."
        )

    folds = _folds(spec)
    resolved_output_root = Path(output_root) if output_root is not None else spec.output.root
    spec_fingerprint = _fingerprint({"spec": _spec_fingerprint_payload(spec)})
    run_id = f"{spec.experiment_id}-{spec_fingerprint[:12]}"
    variants: list[VariantPlan] = []
    work_unit_index = 0
    for index, combination in enumerate(combinations, start=1):
        overrides = combination.overrides
        fingerprint = variant_fingerprint(
            adapter_id=spec.adapter,
            base_request=spec.base_request.model_dump(mode="json"),
            overrides=overrides,
            metric_ids=spec.metrics,
        )
        variant_id = f"variant-{index:03d}-{fingerprint[:8]}"
        for fold in folds:
            work_unit_index += 1
            variant_dir = (
                resolved_output_root
                / run_id
                / "variants"
                / fingerprint
                / fold.fold_id
            )
            variants.append(
                VariantPlan(
                    variant_id=variant_id,
                    fingerprint=fingerprint,
                    variant_index=index,
                    work_unit_index=work_unit_index,
                    overrides=overrides,
                    axis_selections=combination.axis_selections,
                    fold=fold,
                    output_paths=PlannedOutputPaths(
                        variant_dir=variant_dir,
                        manifest_path=variant_dir / "manifest.json",
                        comparison_csv_path=variant_dir / "comparison.csv",
                    ),
                )
            )
    return ExperimentPlan(
        spec=spec,
        adapter=adapter,
        metrics=metrics,
        folds=folds,
        variants=tuple(variants),
        output_root=resolved_output_root,
        run_id=run_id,
        spec_fingerprint=spec_fingerprint,
        jobs=resolved_jobs,
        max_variants=variant_limit,
    )


def variant_fingerprint(
    *,
    adapter_id: str,
    base_request: Mapping[str, object],
    overrides: Mapping[str, object],
    metric_ids: tuple[str, ...],
) -> str:
    payload = {
        "adapter": adapter_id,
        "base_request": base_request,
        "overrides": overrides,
        "metric_ids": sorted(metric_ids),
    }
    return _fingerprint(payload)


def _expanded_variants(
    adapter: AdapterDefinition,
    spec: ExperimentSpec,
) -> tuple[_ExpandedVariant, ...]:
    matrix_combinations = _matrix_combinations(adapter, spec)
    axis_options_by_axis = tuple(_axis_options(adapter, spec))
    combinations: list[_ExpandedVariant] = []
    for matrix_overrides in matrix_combinations:
        if axis_options_by_axis:
            selected_axis_products = itertools.product(*axis_options_by_axis)
        else:
            selected_axis_products = ((),)
        for selected_axis_options in selected_axis_products:
            overrides = dict(matrix_overrides)
            axis_selections: list[AxisSelection] = []
            for axis_option in selected_axis_options:
                _merge_overrides(overrides, axis_option.overrides)
                axis_selections.append(axis_option.selection)
            _validate_family_weights(adapter, overrides)
            _validate_backtest_portfolio_size(spec, overrides)
            combinations.append(
                _ExpandedVariant(
                    overrides=overrides,
                    axis_selections=tuple(axis_selections),
                )
            )
    return tuple(combinations)


def _matrix_combinations(
    adapter: AdapterDefinition,
    spec: ExperimentSpec,
) -> tuple[dict[str, object], ...]:
    matrix = spec.variants.matrix
    paths = tuple(sorted(matrix))
    normalized_values: list[tuple[object, ...]] = []
    for path in paths:
        normalized_values.append(
            tuple(adapter.normalize_override(path, value) for value in matrix[path])
        )
    combinations: list[dict[str, object]] = []
    for values in itertools.product(*normalized_values):
        combinations.append(dict(zip(paths, values, strict=True)))
    return tuple(combinations)


def _axis_options(
    adapter: AdapterDefinition,
    spec: ExperimentSpec,
) -> tuple[tuple[_AxisOption, ...], ...]:
    options_by_axis: list[tuple[_AxisOption, ...]] = []
    for axis in spec.variants.axes:
        axis_options: list[_AxisOption] = []
        for value in axis.values:
            axis_options.append(
                _AxisOption(
                    selection=AxisSelection(axis=axis.name, value_id=value.id),
                    overrides=_normalize_override_mapping(adapter, value.overrides),
                )
            )
        options_by_axis.append(tuple(axis_options))
    return tuple(options_by_axis)


def _normalize_override_mapping(
    adapter: AdapterDefinition,
    overrides: Mapping[str, object],
) -> dict[str, object]:
    return {
        path: adapter.normalize_override(path, overrides[path])
        for path in sorted(overrides)
    }


def _merge_overrides(
    merged: dict[str, object],
    incoming: Mapping[str, object],
) -> None:
    for path, value in incoming.items():
        existing = merged.get(path, _MISSING)
        if existing is _MISSING:
            merged[path] = value
            continue
        if existing != value:
            raise ExperimentSpecError(
                "Duplicate override path "
                f"{path!r} uses conflicting normalized values "
                f"{existing!r} and {value!r} across matrix and axes."
            )


def _validate_family_weights(
    adapter: AdapterDefinition,
    overrides: Mapping[str, object],
) -> None:
    family_weights = dict(adapter.default_family_weights)
    for path, value in overrides.items():
        if path.startswith("family_weights."):
            family = path.split(".", 1)[1]
            if not isinstance(value, Decimal):
                raise ExperimentSpecError(f"Override {path} must normalize to Decimal.")
            family_weights[family] = value
    total = sum(family_weights.values(), Decimal("0"))
    if total != Decimal("1"):
        rendered = ", ".join(
            f"{family}={value}" for family, value in sorted(family_weights.items())
        )
        raise ExperimentSpecError(
            f"family_weights must sum to 1 after defaults and overrides; got {total} ({rendered})."
        )


def _validate_backtest_portfolio_size(
    spec: ExperimentSpec,
    overrides: Mapping[str, object],
) -> None:
    portfolio_breadth = int(
        overrides.get("backtest.portfolio_breadth", spec.base_request.portfolio_breadth)
    )
    max_open_positions = int(
        overrides.get("backtest.max_open_positions", spec.base_request.max_open_positions)
    )
    if max_open_positions < portfolio_breadth:
        raise ExperimentSpecError(
            "backtest.max_open_positions must be greater than or equal to "
            "backtest.portfolio_breadth after overrides."
        )


def _folds(spec: ExperimentSpec) -> tuple[FoldPlan, ...]:
    if spec.folds.mode == "single_window":
        return (FoldPlan(fold_id="single_window", mode="single_window", index=1),)
    if spec.folds.mode == "v2a_yearly":
        return (
            FoldPlan(
                fold_id="fold_1",
                mode="v2a_yearly",
                index=1,
                evaluation_days=TRADING_DAYS_PER_YEAR,
                evaluation_end_offset_days=TRADING_DAYS_PER_YEAR * 2,
            ),
            FoldPlan(
                fold_id="fold_2",
                mode="v2a_yearly",
                index=2,
                evaluation_days=TRADING_DAYS_PER_YEAR,
                evaluation_end_offset_days=TRADING_DAYS_PER_YEAR,
            ),
            FoldPlan(
                fold_id="fold_3",
                mode="v2a_yearly",
                index=3,
                evaluation_days=TRADING_DAYS_PER_YEAR,
                evaluation_end_offset_days=0,
            ),
        )
    raise ExperimentSpecError(f"Unsupported folds.mode {spec.folds.mode!r}.")


def _spec_fingerprint_payload(spec: ExperimentSpec) -> Mapping[str, object]:
    payload = spec.model_dump(mode="json")
    variants = payload.get("variants")
    if isinstance(variants, dict) and not variants.get("axes"):
        variants.pop("axes", None)
    return payload


def _fingerprint(payload: Mapping[str, object]) -> str:
    encoded = json.dumps(
        _json_safe(payload),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value
