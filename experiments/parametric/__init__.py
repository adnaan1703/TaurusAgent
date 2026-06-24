"""Parametric experiment harness primitives."""

from experiments.parametric.adapters import AdapterDefinition, AdapterRegistry
from experiments.parametric.expansion import ExperimentPlan, expand_experiment
from experiments.parametric.loader import load_experiment_spec
from experiments.parametric.runner import dry_run_summary, execute_experiment
from experiments.parametric.spec import DEFAULT_MAX_VARIANTS, ExperimentSpec

__all__ = [
    "AdapterDefinition",
    "AdapterRegistry",
    "DEFAULT_MAX_VARIANTS",
    "ExperimentPlan",
    "ExperimentSpec",
    "dry_run_summary",
    "execute_experiment",
    "expand_experiment",
    "load_experiment_spec",
]
