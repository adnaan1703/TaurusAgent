from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from experiments.parametric.errors import ExperimentSpecError
from experiments.parametric.expansion import expand_experiment
from experiments.parametric.loader import load_experiment_spec
from experiments.parametric.runner import DryRunSummary


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
        spec = load_experiment_spec(args.spec)
        plan = expand_experiment(
            spec,
            jobs=args.jobs,
            max_variants=args.max_variants,
            output_root=output_root,
        )
    except ExperimentSpecError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.dry_run:
        print(DryRunSummary(plan=plan).render())
        return 0

    print(
        "error: non-dry-run parametric execution is planned for M92; "
        "rerun with --dry-run for the M90 runner shell.",
        file=sys.stderr,
    )
    return 3


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

