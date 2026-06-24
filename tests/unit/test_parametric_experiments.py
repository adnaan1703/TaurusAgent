from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from experiments.parametric.errors import ExperimentSpecError
from experiments.parametric.expansion import expand_experiment
from experiments.parametric.loader import load_experiment_spec, parse_experiment_spec
from experiments.parametric.runner import dry_run_summary


def test_v2a_smoke_spec_expands_without_creating_outputs(tmp_path: Path) -> None:
    output_root = tmp_path / "runs"
    summary = dry_run_summary(
        "experiments/specs/v2a_smoke.yaml",
        output_root=output_root,
    )

    assert summary.plan.variant_count == 2
    assert summary.plan.fold_count == 1
    assert summary.plan.total_work_units == 2
    assert summary.plan.metric_ids == (
        "system.total_return",
        "system.max_drawdown",
        "rank.21d.rank_correlation",
    )
    assert not output_root.exists()
    rendered = summary.render()
    assert "expanded_variants=2" in rendered
    assert "fold_count=1" in rendered
    assert "total_work_units=2" in rendered
    assert "planned_output_paths:" in rendered
    assert str(output_root) in rendered


def test_invalid_yaml_fails_before_expansion(tmp_path: Path) -> None:
    spec_path = tmp_path / "bad.yaml"
    spec_path.write_text("schema_version: [\n", encoding="utf-8")

    with pytest.raises(ExperimentSpecError, match="Invalid YAML"):
        load_experiment_spec(spec_path)


def test_unknown_adapter_fails_before_execution() -> None:
    spec = parse_experiment_spec({**_base_spec(), "adapter": "unknown_adapter"})

    with pytest.raises(ExperimentSpecError, match="Unknown adapter"):
        expand_experiment(spec)


def test_unknown_metric_id_fails_before_execution() -> None:
    spec = parse_experiment_spec({**_base_spec(), "metrics": ["system.not_real"]})

    with pytest.raises(ExperimentSpecError, match="Unknown metric"):
        expand_experiment(spec)


def test_unknown_override_key_fails_before_execution() -> None:
    raw = _base_spec()
    raw["variants"] = {"matrix": {"private_helper_name": ["1"]}}
    spec = parse_experiment_spec(raw)

    with pytest.raises(ExperimentSpecError, match="Unknown override path"):
        expand_experiment(spec)


def test_oversized_matrix_requires_explicit_override() -> None:
    raw = _base_spec()
    raw["variants"] = {
        "matrix": {
            "backtest.portfolio_breadth": [str(value) for value in range(1, 24)],
            "backtest.max_open_positions": [str(value) for value in range(24, 47)],
        }
    }
    spec = parse_experiment_spec(raw)

    with pytest.raises(ExperimentSpecError, match="exceeding the default cap"):
        expand_experiment(spec)

    plan = expand_experiment(spec, max_variants=600)
    assert plan.variant_count == 529


def test_family_weight_overrides_must_sum_to_one() -> None:
    raw = _base_spec()
    raw["variants"] = {"matrix": {"family_weights.alpha": ["0.70"]}}
    spec = parse_experiment_spec(raw)

    with pytest.raises(ExperimentSpecError, match="family_weights must sum to 1"):
        expand_experiment(spec)


def test_variant_fingerprint_is_stable_for_same_semantics(tmp_path: Path) -> None:
    first = tmp_path / "first.yaml"
    second = tmp_path / "second.yaml"
    first.write_text(yaml.safe_dump(_base_spec(sort_matrix=False)), encoding="utf-8")
    second.write_text(yaml.safe_dump(_base_spec(sort_matrix=True)), encoding="utf-8")

    first_plan = expand_experiment(load_experiment_spec(first))
    second_plan = expand_experiment(load_experiment_spec(second))

    assert first_plan.variants[0].fingerprint == second_plan.variants[0].fingerprint


def _base_spec(*, sort_matrix: bool = False) -> dict[str, object]:
    matrix = {
        "family_weights.alpha": ["0.65"],
        "family_weights.risk": ["0.20"],
        "family_weights.tradability": ["0.15"],
    }
    if sort_matrix:
        matrix = {
            "family_weights.tradability": ["0.15"],
            "family_weights.risk": ["0.20"],
            "family_weights.alpha": ["0.65"],
        }
    return {
        "schema_version": 1,
        "experiment_id": "unit_smoke",
        "adapter": "technical_validation_v2a",
        "base_request": {
            "mode": "standard",
            "symbols": ["INFY", "TCS"],
            "validation_years": 3,
            "warmup_days": 252,
            "portfolio_breadth": 2,
            "max_open_positions": 2,
            "rebalance_every_days": 21,
            "cost_bps": "10",
            "slippage_bps": "5",
        },
        "variants": {"matrix": matrix},
        "folds": {"mode": "single_window"},
        "metrics": [
            "system.total_return",
            "system.max_drawdown",
            "rank.21d.rank_correlation",
        ],
    }

