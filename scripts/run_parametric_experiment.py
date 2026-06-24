from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from experiments.parametric.errors import ExperimentSpecError
from experiments.parametric.runner import (
    DryRunSummary,
    execute_experiment_plan,
    prepare_experiment_plan,
)
from taurus_core.ops.progress import create_progress_reporter, emit_progress


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate and expand declarative Taurus parametric experiment specs."
    )
    parser.add_argument(
        "--spec",
        default=os.environ.get("EXPERIMENT_SPEC", ""),
        help="YAML experiment spec path.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=_bool_env("PARAMETRIC_DRY_RUN"),
        help="Validate and print the planned matrix without creating run outputs.",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=_optional_int_env("PARAMETRIC_JOBS"),
        help="Bounded worker count. Defaults to execution.jobs from the spec.",
    )
    parser.add_argument(
        "--max-variants",
        type=int,
        default=_optional_int_env("PARAMETRIC_MAX_VARIANTS"),
        help="Explicit matrix expansion cap.",
    )
    parser.add_argument(
        "--output-root",
        default=os.environ.get("PARAMETRIC_OUTPUT_ROOT", ""),
        help="Override output root used for planned run paths.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.spec:
        print("error: --spec or EXPERIMENT_SPEC is required", file=sys.stderr)
        return 2
    output_root = Path(args.output_root) if args.output_root else None
    try:
        with create_progress_reporter("parametric-experiment") as progress:
            plan = prepare_experiment_plan(
                args.spec,
                jobs=args.jobs,
                max_variants=args.max_variants,
                output_root=output_root,
                progress=progress,
            )
            if args.dry_run:
                for variant in plan.variants:
                    emit_progress(
                        progress,
                        "parametric.work_unit_completed",
                        stage="expansion",
                        variant_id=variant.variant_id,
                        fold_id=variant.fold.fold_id,
                        current=variant.work_unit_index,
                        total=plan.total_work_units,
                        completed=variant.work_unit_index,
                    )
                emit_progress(
                    progress,
                    "parametric.stage_started",
                    stage="result_writing",
                    completed=plan.total_work_units,
                    total=plan.total_work_units,
                )
                print(DryRunSummary(plan=plan).render())
                emit_progress(
                    progress,
                    "parametric.completed",
                    stage="result_writing",
                    completed=plan.total_work_units,
                    total=plan.total_work_units,
                )
                return 0
            outcome = execute_experiment_plan(plan, progress=progress)
    except ExperimentSpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"experiment_run_id={outcome.run_id}")
    print(f"run_dir={outcome.run_dir}")
    print(f"comparison_csv={outcome.comparison_csv_path}")
    print(f"manifest={outcome.manifest_path}")
    print(f"status={outcome.status}")
    print(f"variant_count={outcome.variant_count}")
    print(f"total_work_units={plan.total_work_units}")
    return 0


def _bool_env(name: str) -> bool:
    raw = os.environ.get(name, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _optional_int_env(name: str) -> int | None:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"{name} must be an integer") from exc


if __name__ == "__main__":
    sys.exit(main())
