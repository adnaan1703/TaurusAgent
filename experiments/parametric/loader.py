from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

import yaml
from pydantic import ValidationError

from experiments.parametric.errors import ExperimentSpecError
from experiments.parametric.spec import ExperimentSpec


def load_experiment_spec(path: str | Path) -> ExperimentSpec:
    spec_path = Path(path)
    try:
        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ExperimentSpecError(f"Invalid YAML in {spec_path}: {exc}") from exc
    except OSError as exc:
        raise ExperimentSpecError(f"Could not read experiment spec {spec_path}: {exc}") from exc
    if not isinstance(raw, Mapping):
        raise ExperimentSpecError(f"Experiment spec {spec_path} must be a YAML mapping.")
    return parse_experiment_spec(raw, source=str(spec_path))


def parse_experiment_spec(raw: Mapping[str, Any], *, source: str = "<memory>") -> ExperimentSpec:
    try:
        return ExperimentSpec.model_validate(raw)
    except ValidationError as exc:
        raise ExperimentSpecError(f"Invalid experiment spec {source}: {exc}") from exc

