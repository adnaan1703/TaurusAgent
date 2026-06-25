from __future__ import annotations

import csv
import json
from concurrent.futures import Future
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

from experiments.parametric.errors import ExperimentSpecError
from experiments.parametric.expansion import expand_experiment
from experiments.parametric.loader import load_experiment_spec, parse_experiment_spec
from experiments.parametric.runner import dry_run_summary
from experiments.parametric.technical_validation_v2a import (
    run_technical_validation_v2a,
)
from scripts.validate_technical_v2 import ValidationOutcome
from taurus_core.config import Settings


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


def test_default_v2a_yearly_folds_expand_to_fold_work_units(tmp_path: Path) -> None:
    raw = _base_spec()
    raw.pop("folds")
    plan = expand_experiment(
        parse_experiment_spec(raw),
        output_root=tmp_path / "runs",
    )

    assert plan.variant_count == 1
    assert plan.fold_count == 3
    assert plan.total_work_units == 3
    assert [fold.fold_id for fold in plan.folds] == ["fold_1", "fold_2", "fold_3"]
    assert [fold.evaluation_days for fold in plan.folds] == [252, 252, 252]
    assert [fold.evaluation_end_offset_days for fold in plan.folds] == [504, 252, 0]
    assert len({variant.variant_id for variant in plan.variants}) == 1


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


def test_v2a_adapter_writes_manifest_csv_and_metric_deltas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _base_spec()
    raw["variants"] = {
        "matrix": {
            "backtest.cost_bps": ["12"],
            "family_weights.alpha": ["0.65"],
            "family_weights.risk": ["0.20"],
            "family_weights.tradability": ["0.15"],
        }
    }
    plan = expand_experiment(
        parse_experiment_spec(raw),
        output_root=tmp_path / "runs",
    )
    calls = []

    def fake_run_validation(*, settings, request, profiles, progress=None, run_schema_migrations=True):
        assert run_schema_migrations is False
        calls.append((request, profiles))
        artifact_dir = request.artifact_root / "techval-fake"
        artifact_dir.mkdir(parents=True)
        request.report_root.mkdir(parents=True)
        variant_profile = next(
            profile
            for profile in profiles
            if profile.profile_name.startswith("graph_aware_score_v2a_")
        )
        system_profiles = [
            _system_profile("graph_aware_score_v1", total_return=0.10, drawdown=-0.10),
            _system_profile("graph_aware_score_v2", total_return=0.12, drawdown=-0.09),
            _system_profile(variant_profile.profile_name, total_return=0.15, drawdown=-0.08),
        ]
        technical_report = {
            "checks": [
                _rank_check("technical_rule_v1", 0.01),
                _rank_check("technical_ohlcv_v2", 0.02),
                _rank_check(variant_profile.profile_name, 0.05),
            ],
            "profiles": [],
        }
        system_report = {"profiles": system_profiles}
        promotion_gate = {"decision": "keep_opt_in", "checks": []}
        _write_json(artifact_dir / "technical_agent_predictive_report.json", technical_report)
        _write_json(artifact_dir / "system_backtest_report.json", system_report)
        _write_json(artifact_dir / "promotion_gate.json", promotion_gate)
        _write_json(artifact_dir / "validation_manifest.json", {"run_id": "techval-fake"})
        return ValidationOutcome(
            run_id="techval-fake",
            artifact_dir=artifact_dir,
            status="complete",
            manifest={"run_id": "techval-fake"},
            report_path=request.report_root / "techval-fake.md",
            promotion_decision="keep_opt_in",
        )

    monkeypatch.setattr(
        "experiments.parametric.technical_validation_v2a.run_validation",
        fake_run_validation,
    )

    outcome = run_technical_validation_v2a(plan, settings=Settings())

    assert outcome.status == "complete"
    assert calls
    request, profiles = calls[0]
    assert request.cost_bps == Decimal("12")
    assert [profile.profile_name for profile in profiles[:2]] == [
        "graph_aware_score_v1",
        "graph_aware_score_v2",
    ]
    variant_profile = profiles[2]
    assert "technical_ohlcv_v2_params" in variant_profile.strategy_parameters

    rows = list(csv.DictReader(outcome.comparison_csv_path.open(encoding="utf-8")))
    assert len(rows) == 3
    variant_row = next(row for row in rows if row["profile_role"] == "variant")
    assert variant_row["system.total_return"] == "0.15"
    assert variant_row["system.total_return.delta_vs_v1"] == "0.05"
    assert variant_row["system.total_return.delta_vs_current_v2a"] == "0.03"
    assert variant_row["rank.21d.rank_correlation"] == "0.05"
    assert variant_row["rank.21d.rank_correlation.delta_vs_current_v2a"] == "0.03"

    manifest = json.loads(outcome.manifest_path.read_text(encoding="utf-8"))
    assert manifest["run_id"] == plan.run_id
    assert manifest["output_paths"]["comparison_csv"] == str(outcome.comparison_csv_path)
    assert manifest["variants"][0]["validation"]["promotion_gate_report_only"] is True
    assert manifest["variants"][0]["output_paths"]["manifest"].endswith("manifest.json")


def test_v2a_adapter_deduplicates_run_level_baselines(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _base_spec()
    raw["variants"] = {
        "matrix": {
            "backtest.cost_bps": ["10", "12"],
            "family_weights.alpha": ["0.65"],
            "family_weights.risk": ["0.20"],
            "family_weights.tradability": ["0.15"],
        }
    }
    plan = expand_experiment(
        parse_experiment_spec(raw),
        output_root=tmp_path / "runs",
    )

    class ImmediateProcessPoolExecutor:
        def __init__(self, *, max_workers: int) -> None:
            self.max_workers = max_workers

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> bool:
            return False

        def submit(self, fn, *args):
            future = Future()
            try:
                future.set_result(fn(*args))
            except BaseException as exc:
                future.set_exception(exc)
            return future

    def fake_run_validation(
        *,
        settings,
        request,
        profiles,
        progress=None,
        run_schema_migrations=True,
    ):
        assert run_schema_migrations is False
        artifact_dir = request.artifact_root / f"techval-fake-{request.cost_bps}"
        artifact_dir.mkdir(parents=True, exist_ok=True)
        request.report_root.mkdir(parents=True, exist_ok=True)
        variant_profile = next(
            profile
            for profile in profiles
            if profile.profile_name.startswith("graph_aware_score_v2a_")
        )
        variant_return = Decimal("0.15") if request.cost_bps == 10 else Decimal("0.16")
        system_profiles = [
            _system_profile("graph_aware_score_v1", total_return=0.10, drawdown=-0.10),
            _system_profile("graph_aware_score_v2", total_return=0.12, drawdown=-0.09),
            _system_profile(
                variant_profile.profile_name,
                total_return=float(variant_return),
                drawdown=-0.08,
            ),
        ]
        technical_report = {
            "checks": [
                _rank_check("technical_rule_v1", 0.01),
                _rank_check("technical_ohlcv_v2", 0.02),
                _rank_check(variant_profile.profile_name, 0.05),
            ],
            "profiles": [],
        }
        system_report = {"profiles": system_profiles}
        promotion_gate = {"decision": "keep_opt_in", "checks": []}
        _write_json(artifact_dir / "technical_agent_predictive_report.json", technical_report)
        _write_json(artifact_dir / "system_backtest_report.json", system_report)
        _write_json(artifact_dir / "promotion_gate.json", promotion_gate)
        _write_json(artifact_dir / "validation_manifest.json", {"run_id": artifact_dir.name})
        return ValidationOutcome(
            run_id=artifact_dir.name,
            artifact_dir=artifact_dir,
            status="complete",
            manifest={"run_id": artifact_dir.name},
            report_path=request.report_root / f"{artifact_dir.name}.md",
            promotion_decision="keep_opt_in",
        )

    monkeypatch.setattr(
        "experiments.parametric.technical_validation_v2a.run_validation",
        fake_run_validation,
    )
    monkeypatch.setattr(
        "experiments.parametric.technical_validation_v2a.ProcessPoolExecutor",
        ImmediateProcessPoolExecutor,
    )

    outcome = run_technical_validation_v2a(plan, settings=Settings())

    rows = list(csv.DictReader(outcome.comparison_csv_path.open(encoding="utf-8")))
    assert [row["profile_role"] for row in rows] == [
        "baseline_v1",
        "baseline_current_v2a",
        "variant",
        "variant",
    ]
    assert rows[0]["variant_id"] == ""
    assert rows[1]["variant_id"] == ""
    assert [row["profile_role"] for row in rows].count("baseline_v1") == 1
    assert [row["profile_role"] for row in rows].count("baseline_current_v2a") == 1


def test_v2a_adapter_writes_fold_aggregate_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _base_spec()
    raw.pop("folds")
    plan = expand_experiment(
        parse_experiment_spec(raw),
        output_root=tmp_path / "runs",
    )

    def fake_run_validation(*, settings, request, profiles, progress=None, run_schema_migrations=True):
        assert run_schema_migrations is False
        artifact_dir = request.artifact_root / f"techval-fake-{request.evaluation_end_offset_days}"
        artifact_dir.mkdir(parents=True)
        request.report_root.mkdir(parents=True)
        variant_profile = next(
            profile
            for profile in profiles
            if profile.profile_name.startswith("graph_aware_score_v2a_")
        )
        variant_return_by_offset = {
            504: 0.11,
            252: 0.15,
            0: 0.19,
        }
        variant_total_return = variant_return_by_offset[
            request.evaluation_end_offset_days
        ]
        system_profiles = [
            _system_profile("graph_aware_score_v1", total_return=0.10, drawdown=-0.10),
            _system_profile("graph_aware_score_v2", total_return=0.12, drawdown=-0.09),
            _system_profile(
                variant_profile.profile_name,
                total_return=variant_total_return,
                drawdown=-0.08,
            ),
        ]
        technical_report = {
            "checks": [
                _rank_check("technical_rule_v1", 0.01),
                _rank_check("technical_ohlcv_v2", 0.02),
                _rank_check(variant_profile.profile_name, 0.05),
            ],
            "profiles": [],
        }
        system_report = {"profiles": system_profiles}
        promotion_gate = {"decision": "keep_opt_in", "checks": []}
        _write_json(artifact_dir / "technical_agent_predictive_report.json", technical_report)
        _write_json(artifact_dir / "system_backtest_report.json", system_report)
        _write_json(artifact_dir / "promotion_gate.json", promotion_gate)
        _write_json(artifact_dir / "validation_manifest.json", {"run_id": artifact_dir.name})
        return ValidationOutcome(
            run_id=artifact_dir.name,
            artifact_dir=artifact_dir,
            status="complete",
            manifest={"run_id": artifact_dir.name},
            report_path=request.report_root / f"{artifact_dir.name}.md",
            promotion_decision="keep_opt_in",
        )

    monkeypatch.setattr(
        "experiments.parametric.technical_validation_v2a.run_validation",
        fake_run_validation,
    )

    outcome = run_technical_validation_v2a(plan, settings=Settings())

    rows = list(csv.DictReader(outcome.comparison_csv_path.open(encoding="utf-8")))
    aggregate_row = next(row for row in rows if row["profile_role"] == "variant_aggregate")
    assert aggregate_row["fold_id"] == "aggregate"
    assert aggregate_row["fold_count"] == "3"
    assert aggregate_row["system.total_return"] == "0.15"
    assert aggregate_row["system.total_return.fold_min"] == "0.11"
    assert aggregate_row["system.total_return.fold_max"] == "0.19"
    assert aggregate_row["system.total_return.fold_mean"] == "0.15"
    assert aggregate_row["system.total_return.fold_stddev"] == "0.03265986"

    manifest = json.loads(outcome.manifest_path.read_text(encoding="utf-8"))
    assert manifest["variant_count"] == 1
    assert manifest["fold_count"] == 3
    assert manifest["total_work_units"] == 3
    assert [fold["fold_id"] for fold in manifest["folds"]] == [
        "fold_1",
        "fold_2",
        "fold_3",
    ]


def test_v2a_adapter_uses_bounded_process_pool_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = expand_experiment(
        parse_experiment_spec(_base_spec()),
        jobs=2,
        output_root=tmp_path / "runs",
    )
    calls = []
    max_workers_seen = []

    class ImmediateProcessPoolExecutor:
        def __init__(self, *, max_workers: int) -> None:
            max_workers_seen.append(max_workers)

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, traceback) -> bool:
            return False

        def submit(self, fn, *args):
            future = Future()
            try:
                future.set_result(fn(*args))
            except BaseException as exc:
                future.set_exception(exc)
            return future

    def fake_run_validation(*, settings, request, profiles, progress=None, run_schema_migrations=True):
        assert run_schema_migrations is False
        calls.append(request.cost_bps)
        artifact_dir = request.artifact_root / f"techval-fake-{request.cost_bps}"
        artifact_dir.mkdir(parents=True)
        request.report_root.mkdir(parents=True)
        variant_profile = next(
            profile
            for profile in profiles
            if profile.profile_name.startswith("graph_aware_score_v2a_")
        )
        system_profiles = [
            _system_profile("graph_aware_score_v1", total_return=0.10, drawdown=-0.10),
            _system_profile("graph_aware_score_v2", total_return=0.12, drawdown=-0.09),
            _system_profile(variant_profile.profile_name, total_return=0.15, drawdown=-0.08),
        ]
        technical_report = {
            "checks": [
                _rank_check("technical_rule_v1", 0.01),
                _rank_check("technical_ohlcv_v2", 0.02),
                _rank_check(variant_profile.profile_name, 0.05),
            ],
            "profiles": [],
        }
        _write_json(
            artifact_dir / "technical_agent_predictive_report.json",
            technical_report,
        )
        _write_json(artifact_dir / "system_backtest_report.json", {"profiles": system_profiles})
        _write_json(
            artifact_dir / "promotion_gate.json",
            {"decision": "keep_opt_in", "checks": []},
        )
        _write_json(artifact_dir / "validation_manifest.json", {"run_id": artifact_dir.name})
        return ValidationOutcome(
            run_id=artifact_dir.name,
            artifact_dir=artifact_dir,
            status="complete",
            manifest={"run_id": artifact_dir.name},
            report_path=request.report_root / f"{artifact_dir.name}.md",
            promotion_decision="keep_opt_in",
        )

    monkeypatch.setattr(
        "experiments.parametric.technical_validation_v2a.run_validation",
        fake_run_validation,
    )
    monkeypatch.setattr(
        "experiments.parametric.technical_validation_v2a.ProcessPoolExecutor",
        ImmediateProcessPoolExecutor,
    )

    outcome = run_technical_validation_v2a(plan, settings=Settings())

    assert outcome.status == "complete"
    assert max_workers_seen == [2]
    assert sorted(calls) == [Decimal("10")]
    assert outcome.variant_count == 1


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


def _system_profile(
    profile_name: str,
    *,
    total_return: float,
    drawdown: float,
) -> dict[str, object]:
    return {
        "profile_name": profile_name,
        "metrics": {
            "total_return": total_return,
            "max_drawdown": drawdown,
        },
        "cash_utilization": {},
        "allocation_candidate_score_behavior": {},
        "rejected_or_trimmed_candidate_counts": {},
    }


def _rank_check(profile_name: str, rank_correlation: float) -> dict[str, object]:
    return {
        "profile_name": profile_name,
        "horizon_days": 21,
        "rank_correlation": rank_correlation,
        "top_bottom_decile_spread": None,
        "hit_rate": None,
    }


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")
