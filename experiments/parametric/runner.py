from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from experiments.parametric.errors import ExperimentSpecError
from experiments.parametric.expansion import ExperimentPlan, expand_experiment
from experiments.parametric.loader import load_experiment_spec

TECHNICAL_VALIDATION_V2A_ADAPTER_ID = "technical_validation_v2a"


@dataclass(frozen=True, slots=True)
class DryRunSummary:
    plan: ExperimentPlan

    def render(self) -> str:
        lines = [
            f"experiment_id={self.plan.spec.experiment_id}",
            f"adapter={self.plan.spec.adapter}",
            "dry_run=true",
            f"run_id={self.plan.run_id}",
            f"expanded_variants={self.plan.variant_count}",
            f"fold_count={self.plan.fold_count}",
            f"total_work_units={self.plan.total_work_units}",
            f"jobs={self.plan.jobs}",
            f"max_variants={self.plan.max_variants}",
            f"metric_ids={','.join(self.plan.metric_ids)}",
            f"output_root={self.plan.output_root}",
            "expanded_variants:",
        ]
        for variant in self.plan.variants:
            overrides = ",".join(
                f"{path}={value}" for path, value in sorted(variant.overrides.items())
            )
            lines.append(
                "- "
                f"variant_id={variant.variant_id} "
                f"fingerprint={variant.fingerprint} "
                f"fold={variant.fold.fold_id} "
                f"overrides={overrides}"
            )
        lines.append("planned_output_paths:")
        for variant in self.plan.variants:
            lines.append(
                "- "
                f"variant_id={variant.variant_id} "
                f"fold={variant.fold.fold_id} "
                f"variant_dir={variant.output_paths.variant_dir} "
                f"manifest={variant.output_paths.manifest_path} "
                f"comparison_csv={variant.output_paths.comparison_csv_path}"
            )
        return "\n".join(lines)


def dry_run_summary(
    spec_path: str | Path,
    *,
    jobs: int | None = None,
    max_variants: int | None = None,
    output_root: str | Path | None = None,
) -> DryRunSummary:
    spec = load_experiment_spec(spec_path)
    plan = expand_experiment(
        spec,
        jobs=jobs,
        max_variants=max_variants,
        output_root=output_root,
    )
    return DryRunSummary(plan=plan)


def execute_experiment(
    spec_path: str | Path,
    *,
    jobs: int | None = None,
    max_variants: int | None = None,
    output_root: str | Path | None = None,
) -> Any:
    spec = load_experiment_spec(spec_path)
    plan = expand_experiment(
        spec,
        jobs=jobs,
        max_variants=max_variants,
        output_root=output_root,
    )
    if plan.adapter.adapter_id == TECHNICAL_VALIDATION_V2A_ADAPTER_ID:
        from experiments.parametric.technical_validation_v2a import (
            run_technical_validation_v2a,
        )

        return run_technical_validation_v2a(plan)
    raise ExperimentSpecError(
        f"Adapter {plan.adapter.adapter_id!r} does not support non-dry-run execution."
    )
