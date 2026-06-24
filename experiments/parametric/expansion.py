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


@dataclass(frozen=True, slots=True)
class FoldPlan:
    fold_id: str
    mode: str


@dataclass(frozen=True, slots=True)
class PlannedOutputPaths:
    variant_dir: Path
    manifest_path: Path
    comparison_csv_path: Path


@dataclass(frozen=True, slots=True)
class VariantPlan:
    variant_id: str
    fingerprint: str
    overrides: Mapping[str, object]
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
    spec_fingerprint: str
    jobs: int
    max_variants: int

    @property
    def variant_count(self) -> int:
        return len(self.variants)

    @property
    def fold_count(self) -> int:
        return len(self.folds)

    @property
    def total_work_units(self) -> int:
        return self.variant_count

    @property
    def metric_ids(self) -> tuple[str, ...]:
        return tuple(metric.metric_id for metric in self.metrics)


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

    combinations = _expanded_overrides(adapter, spec)
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
    spec_fingerprint = _fingerprint({"spec": spec.model_dump(mode="json")})
    variants: list[VariantPlan] = []
    for index, overrides in enumerate(combinations, start=1):
        for fold in folds:
            fingerprint = variant_fingerprint(
                adapter_id=spec.adapter,
                base_request=spec.base_request.model_dump(mode="json"),
                overrides=overrides,
                fold=fold,
                metric_ids=spec.metrics,
            )
            variant_id = f"variant-{index:03d}-{fingerprint[:8]}"
            variant_dir = (
                resolved_output_root
                / spec.experiment_id
                / spec_fingerprint[:12]
                / "variants"
                / fingerprint
                / fold.fold_id
            )
            variants.append(
                VariantPlan(
                    variant_id=variant_id,
                    fingerprint=fingerprint,
                    overrides=overrides,
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
        spec_fingerprint=spec_fingerprint,
        jobs=resolved_jobs,
        max_variants=variant_limit,
    )


def variant_fingerprint(
    *,
    adapter_id: str,
    base_request: Mapping[str, object],
    overrides: Mapping[str, object],
    fold: FoldPlan,
    metric_ids: tuple[str, ...],
) -> str:
    payload = {
        "adapter": adapter_id,
        "base_request": base_request,
        "overrides": overrides,
        "fold": {"fold_id": fold.fold_id, "mode": fold.mode},
        "metric_ids": sorted(metric_ids),
    }
    return _fingerprint(payload)


def _expanded_overrides(
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
        overrides = dict(zip(paths, values, strict=True))
        _validate_family_weights(adapter, overrides)
        combinations.append(overrides)
    return tuple(combinations)


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


def _folds(spec: ExperimentSpec) -> tuple[FoldPlan, ...]:
    if spec.folds.mode != "single_window":
        raise ExperimentSpecError(f"Unsupported folds.mode {spec.folds.mode!r}.")
    return (FoldPlan(fold_id="single_window", mode="single_window"),)


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

