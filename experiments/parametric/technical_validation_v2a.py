from __future__ import annotations

import csv
import json
import subprocess
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from experiments.parametric.errors import ExperimentSpecError
from experiments.parametric.expansion import ExperimentPlan, VariantPlan
from experiments.parametric.spec import BaseRequestSpec
from scripts.validate_technical_v2 import (
    BASELINE_PROFILE_NAME,
    CANDIDATE_PROFILE_NAME,
    TRADING_DAYS_PER_YEAR,
    ValidationOutcome,
    ValidationProfile,
    ValidationRequest,
    run_validation,
    validation_profiles,
)
from taurus_core.config import Settings, get_settings
from taurus_core.data.universe import load_market_data_universe
from taurus_core.features.technical_params import DEFAULT_OHLCV_V2_SCORING_PARAMS
from taurus_core.strategies.graph_aware import OHLCV_V2_SCORING_PARAMS_KEY

ARTIFACT_VERSION = "parametric_experiment_v1"
ADAPTER_ID = "technical_validation_v2a"
TECHNICAL_RULE_PROFILE = "technical_rule_v1"
TECHNICAL_OHLCV_V2_PROFILE = "technical_ohlcv_v2"
BACKTEST_PREFIX = "backtest."

SYSTEM_METRIC_PATHS = {
    "system.total_return": ("metrics", "total_return"),
    "system.cagr": ("metrics", "cagr"),
    "system.sharpe": ("metrics", "sharpe"),
    "system.sortino": ("metrics", "sortino"),
    "system.max_drawdown": ("metrics", "max_drawdown"),
    "system.turnover": ("metrics", "turnover"),
    "system.win_rate": ("metrics", "win_rate"),
    "system.profit_factor": ("metrics", "profit_factor"),
    "system.average_cash_utilization_pct": (
        "cash_utilization",
        "average_cash_utilization_pct",
    ),
    "system.ranked_candidate_count": (
        "allocation_candidate_score_behavior",
        "ranked_candidate_count",
    ),
    "system.eligible_candidate_count": (
        "allocation_candidate_score_behavior",
        "eligible_candidate_count",
    ),
    "system.rejected_candidate_count": (
        "rejected_or_trimmed_candidate_counts",
        "rejected_candidate_count",
    ),
    "system.trimmed_candidate_count": (
        "rejected_or_trimmed_candidate_counts",
        "trimmed_candidate_count",
    ),
    "system.sizing_failure_count": (
        "rejected_or_trimmed_candidate_counts",
        "sizing_failure_count",
    ),
}
RANK_METRIC_FIELDS = {
    "rank_correlation": "rank_correlation",
    "top_bottom_decile_spread": "top_bottom_decile_spread",
    "hit_rate": "hit_rate",
}


@dataclass(frozen=True, slots=True)
class ParametricExecutionOutcome:
    run_id: str
    run_dir: Path
    manifest_path: Path
    comparison_csv_path: Path
    status: str
    variant_count: int


def run_technical_validation_v2a(
    plan: ExperimentPlan,
    *,
    settings: Settings | None = None,
) -> ParametricExecutionOutcome:
    if plan.adapter.adapter_id != ADAPTER_ID:
        raise ExperimentSpecError(
            f"Adapter runner {ADAPTER_ID!r} cannot execute {plan.adapter.adapter_id!r}."
        )
    if plan.jobs != 1:
        raise ExperimentSpecError(
            "Non-dry-run technical_validation_v2a execution supports jobs=1 until M93."
        )

    resolved_settings = settings or get_settings()
    run_dir = plan.output_root / plan.run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    all_rows: list[dict[str, object]] = []
    variant_manifests: list[dict[str, object]] = []

    for variant in plan.variants:
        variant.output_paths.variant_dir.mkdir(parents=True, exist_ok=True)
        request = _validation_request_for_variant(
            base_request=plan.spec.base_request,
            variant=variant,
            settings=resolved_settings,
        )
        profiles = _validation_profiles_for_variant(plan, variant)
        outcome = run_validation(
            settings=resolved_settings,
            request=request,
            profiles=profiles,
        )
        technical_report = _read_json(
            outcome.artifact_dir / "technical_agent_predictive_report.json"
        )
        system_report = _read_json(outcome.artifact_dir / "system_backtest_report.json")
        promotion_gate = _read_json(outcome.artifact_dir / "promotion_gate.json")
        rows = _comparison_rows(
            plan=plan,
            variant=variant,
            profiles=profiles,
            outcome=outcome,
            technical_report=technical_report,
            system_report=system_report,
        )
        _write_comparison_csv(
            variant.output_paths.comparison_csv_path,
            rows,
            metric_ids=plan.metric_ids,
        )
        variant_manifest = _variant_manifest(
            plan=plan,
            variant=variant,
            request=request,
            profiles=profiles,
            outcome=outcome,
            rows=rows,
            promotion_gate=promotion_gate,
        )
        _write_json(variant.output_paths.manifest_path, variant_manifest)
        all_rows.extend(rows)
        variant_manifests.append(variant_manifest)

    comparison_csv_path = run_dir / "comparison.csv"
    manifest_path = run_dir / "manifest.json"
    _write_comparison_csv(comparison_csv_path, all_rows, metric_ids=plan.metric_ids)
    status = (
        "complete"
        if all(
            variant_manifest["validation"]["status"] == "complete"
            for variant_manifest in variant_manifests
        )
        else "completed_with_validation_gaps"
    )
    _write_json(
        manifest_path,
        _run_manifest(
            plan=plan,
            run_dir=run_dir,
            comparison_csv_path=comparison_csv_path,
            variant_manifests=variant_manifests,
            status=status,
        ),
    )
    return ParametricExecutionOutcome(
        run_id=plan.run_id,
        run_dir=run_dir,
        manifest_path=manifest_path,
        comparison_csv_path=comparison_csv_path,
        status=status,
        variant_count=plan.variant_count,
    )


def _validation_request_for_variant(
    *,
    base_request: BaseRequestSpec,
    variant: VariantPlan,
    settings: Settings,
) -> ValidationRequest:
    backtest_overrides = _backtest_overrides(variant.overrides)
    mode = str(backtest_overrides.get("validation_mode", base_request.mode))
    validation_years = (
        5 if mode == "strong" else base_request.validation_years
    )
    if "validation_years" in backtest_overrides:
        validation_years = int(backtest_overrides["validation_years"])
    evaluation_days = (
        base_request.evaluation_days
        if base_request.evaluation_days is not None
        else validation_years * TRADING_DAYS_PER_YEAR
    )
    warmup_days = int(backtest_overrides.get("warmup_days", base_request.warmup_days))
    symbols, universe_source, universe_path = _resolve_symbols(
        base_request=base_request,
        backtest_overrides=backtest_overrides,
    )
    portfolio_breadth = int(
        backtest_overrides.get("portfolio_breadth", base_request.portfolio_breadth)
    )
    max_open_positions = int(
        backtest_overrides.get("max_open_positions", base_request.max_open_positions)
    )
    if max_open_positions < portfolio_breadth:
        raise ExperimentSpecError(
            "backtest.max_open_positions must be greater than or equal to "
            "backtest.portfolio_breadth after overrides."
        )
    initial_capital = (
        base_request.initial_capital_inr
        if base_request.initial_capital_inr is not None
        else Decimal(str(settings.taurus_initial_capital_inr))
    )
    return ValidationRequest(
        symbols=symbols,
        universe_source=universe_source,
        universe_path=universe_path,
        mode=mode,
        validation_years=validation_years,
        evaluation_days=evaluation_days,
        warmup_days=warmup_days,
        timeframe=base_request.timeframe,
        artifact_root=base_request.artifact_root
        or (variant.output_paths.variant_dir / "technical_validation"),
        initial_capital_inr=initial_capital,
        max_open_positions=max_open_positions,
        portfolio_breadth=portfolio_breadth,
        rebalance_every_days=int(
            backtest_overrides.get(
                "rebalance_every_days",
                base_request.rebalance_every_days,
            )
        ),
        cost_bps=Decimal(str(backtest_overrides.get("cost_bps", base_request.cost_bps))),
        slippage_bps=Decimal(
            str(backtest_overrides.get("slippage_bps", base_request.slippage_bps))
        ),
        strict_insufficient_data=base_request.strict_insufficient_data,
        include_v2b=False,
        report_root=base_request.report_root
        or (variant.output_paths.variant_dir / "reports"),
    )


def _resolve_symbols(
    *,
    base_request: BaseRequestSpec,
    backtest_overrides: Mapping[str, object],
) -> tuple[tuple[str, ...], str, str | None]:
    override_symbols = backtest_overrides.get("symbols")
    if override_symbols is not None:
        if not isinstance(override_symbols, tuple):
            raise ExperimentSpecError("backtest.symbols must normalize to symbols.")
        return override_symbols, "variant_symbols", None

    override_universe = backtest_overrides.get("universe")
    if override_universe is not None:
        universe_path = str(override_universe)
        universe = load_market_data_universe(universe_path)
        return (
            tuple(universe.enabled_symbols()),
            "variant_universe",
            str(universe.source_path),
        )

    if base_request.symbols:
        return base_request.symbols, "manual_symbols", None

    universe_path = base_request.universe_path or base_request.universe
    if not universe_path:
        raise ExperimentSpecError("base_request requires symbols or universe.")
    universe = load_market_data_universe(universe_path)
    return tuple(universe.enabled_symbols()), "market_data_universe", str(
        universe.source_path
    )


def _validation_profiles_for_variant(
    plan: ExperimentPlan,
    variant: VariantPlan,
) -> tuple[ValidationProfile, ...]:
    defaults_by_name = {
        profile.profile_name: profile for profile in validation_profiles(include_v2b=False)
    }
    profiles: list[ValidationProfile] = []
    if plan.spec.baselines.include_v1:
        profiles.append(defaults_by_name[BASELINE_PROFILE_NAME])
    if plan.spec.baselines.include_current_v2a:
        profiles.append(defaults_by_name[CANDIDATE_PROFILE_NAME])
    profiles.append(_variant_profile(defaults_by_name[CANDIDATE_PROFILE_NAME], variant))
    return tuple(profiles)


def _variant_profile(
    current_v2a: ValidationProfile,
    variant: VariantPlan,
) -> ValidationProfile:
    strategy_parameters = dict(current_v2a.strategy_parameters)
    scoring_overrides = _scoring_overrides(variant.overrides)
    if scoring_overrides:
        try:
            scoring_params = DEFAULT_OHLCV_V2_SCORING_PARAMS.with_overrides(
                scoring_overrides
            )
        except ValueError as exc:
            raise ExperimentSpecError(str(exc)) from exc
        strategy_parameters[OHLCV_V2_SCORING_PARAMS_KEY] = scoring_params.to_dict()
    safe_variant_id = variant.variant_id.replace("-", "_")
    profile_name = f"graph_aware_score_v2a_{safe_variant_id}"
    return ValidationProfile(
        profile_name=profile_name,
        strategy_name=profile_name,
        strategy_type=current_v2a.strategy_type,
        strategy_config_path=current_v2a.strategy_config_path,
        strategy_parameters=strategy_parameters,
        graph_contribution_enabled=True,
        notes=(
            "Generated v2A parametric experiment profile.",
            f"variant_id={variant.variant_id}",
            f"variant_fingerprint={variant.fingerprint}",
        ),
    )


def _comparison_rows(
    *,
    plan: ExperimentPlan,
    variant: VariantPlan,
    profiles: Sequence[ValidationProfile],
    outcome: ValidationOutcome,
    technical_report: Mapping[str, object],
    system_report: Mapping[str, object],
) -> list[dict[str, object]]:
    metric_values_by_profile = {
        profile.profile_name: _extract_metric_values(
            metric_ids=plan.metric_ids,
            profile=profile,
            technical_report=technical_report,
            system_report=system_report,
        )
        for profile in profiles
    }
    v1_metrics = metric_values_by_profile.get(BASELINE_PROFILE_NAME, {})
    v2a_metrics = metric_values_by_profile.get(CANDIDATE_PROFILE_NAME, {})
    rows: list[dict[str, object]] = []
    for profile in profiles:
        values = metric_values_by_profile[profile.profile_name]
        row: dict[str, object] = {
            "experiment_id": plan.spec.experiment_id,
            "run_id": plan.run_id,
            "variant_id": variant.variant_id,
            "variant_fingerprint": variant.fingerprint,
            "fold_id": variant.fold.fold_id,
            "profile_name": profile.profile_name,
            "profile_role": _profile_role(profile.profile_name, variant),
            "validation_run_id": outcome.run_id,
            "validation_status": outcome.status,
            "promotion_decision": outcome.promotion_decision,
            "overrides": json.dumps(
                _json_safe(dict(variant.overrides)),
                sort_keys=True,
                separators=(",", ":"),
            ),
        }
        for metric_id in plan.metric_ids:
            value = values.get(metric_id)
            row[metric_id] = _csv_value(value)
            row[f"{metric_id}.delta_vs_v1"] = _csv_value(
                _delta(value, v1_metrics.get(metric_id))
            )
            row[f"{metric_id}.delta_vs_current_v2a"] = _csv_value(
                _delta(value, v2a_metrics.get(metric_id))
            )
        rows.append(row)
    return rows


def _extract_metric_values(
    *,
    metric_ids: Sequence[str],
    profile: ValidationProfile,
    technical_report: Mapping[str, object],
    system_report: Mapping[str, object],
) -> dict[str, object | None]:
    system_profile = _profile_report_row(system_report, profile.profile_name)
    technical_profile_name = _technical_report_profile_name(profile)
    values: dict[str, object | None] = {}
    for metric_id in metric_ids:
        if metric_id.startswith("system."):
            values[metric_id] = _nested_value(
                system_profile,
                SYSTEM_METRIC_PATHS.get(metric_id, ()),
            )
            continue
        values[metric_id] = _rank_metric_value(
            technical_report,
            profile_name=technical_profile_name,
            metric_id=metric_id,
        )
    return values


def _profile_report_row(
    report: Mapping[str, object],
    profile_name: str,
) -> Mapping[str, object]:
    for row in report.get("profiles", []):
        if isinstance(row, Mapping) and row.get("profile_name") == profile_name:
            return row
    return {}


def _rank_metric_value(
    technical_report: Mapping[str, object],
    *,
    profile_name: str,
    metric_id: str,
) -> object | None:
    parts = metric_id.split(".")
    if len(parts) != 3 or parts[0] != "rank" or not parts[1].endswith("d"):
        return None
    try:
        horizon = int(parts[1][:-1])
    except ValueError:
        return None
    field_name = RANK_METRIC_FIELDS.get(parts[2])
    if field_name is None:
        return None
    for row in technical_report.get("checks", []):
        if (
            isinstance(row, Mapping)
            and row.get("profile_name") == profile_name
            and row.get("horizon_days") == horizon
        ):
            return row.get(field_name)
    return None


def _technical_report_profile_name(profile: ValidationProfile) -> str:
    if profile.profile_name in {
        "graph_aware_score_v1",
        "graph_aware_score_v1_technical_only",
    }:
        return TECHNICAL_RULE_PROFILE
    if profile.profile_name in {
        "graph_aware_score_v2",
        "graph_aware_score_v2_technical_only",
    }:
        return TECHNICAL_OHLCV_V2_PROFILE
    return profile.profile_name


def _nested_value(
    row: Mapping[str, object],
    path: Sequence[str],
) -> object | None:
    current: object = row
    for part in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(part)
        if current is None:
            return None
    return current


def _profile_role(profile_name: str, variant: VariantPlan) -> str:
    if profile_name == BASELINE_PROFILE_NAME:
        return "baseline_v1"
    if profile_name == CANDIDATE_PROFILE_NAME:
        return "baseline_current_v2a"
    if variant.variant_id.replace("-", "_") in profile_name:
        return "variant"
    return "comparison"


def _variant_manifest(
    *,
    plan: ExperimentPlan,
    variant: VariantPlan,
    request: ValidationRequest,
    profiles: Sequence[ValidationProfile],
    outcome: ValidationOutcome,
    rows: Sequence[Mapping[str, object]],
    promotion_gate: Mapping[str, object],
) -> dict[str, object]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": plan.run_id,
        "variant_id": variant.variant_id,
        "variant_fingerprint": variant.fingerprint,
        "adapter": plan.adapter.adapter_id,
        "spec_fingerprint": plan.spec_fingerprint,
        "git_commit": _git_commit(),
        "fold": {"fold_id": variant.fold.fold_id, "mode": variant.fold.mode},
        "metric_ids": list(plan.metric_ids),
        "baseline_profile_names": [
            profile.profile_name
            for profile in profiles
            if profile.profile_name in {BASELINE_PROFILE_NAME, CANDIDATE_PROFILE_NAME}
        ],
        "variant_params": dict(variant.overrides),
        "request": {
            "mode": request.mode,
            "validation_years": request.validation_years,
            "evaluation_days": request.evaluation_days,
            "warmup_days": request.warmup_days,
            "symbols": list(request.symbols),
            "portfolio_breadth": request.portfolio_breadth,
            "max_open_positions": request.max_open_positions,
            "rebalance_every_days": request.rebalance_every_days,
            "cost_bps": str(request.cost_bps),
            "slippage_bps": str(request.slippage_bps),
            "include_v2b": request.include_v2b,
        },
        "profiles": [
            {
                "profile_name": profile.profile_name,
                "strategy_name": profile.strategy_name,
                "strategy_config_path": profile.strategy_config_path,
                "graph_contribution_enabled": profile.graph_contribution_enabled,
                "strategy_parameters": dict(profile.strategy_parameters),
                "notes": list(profile.notes),
            }
            for profile in profiles
        ],
        "validation": {
            "run_id": outcome.run_id,
            "status": outcome.status,
            "artifact_dir": str(outcome.artifact_dir),
            "validation_manifest_path": str(outcome.artifact_dir / "validation_manifest.json"),
            "technical_agent_predictive_report_path": str(
                outcome.artifact_dir / "technical_agent_predictive_report.json"
            ),
            "system_backtest_report_path": str(
                outcome.artifact_dir / "system_backtest_report.json"
            ),
            "profile_comparison_matrix_path": str(
                outcome.artifact_dir / "profile_comparison_matrix.csv"
            ),
            "promotion_gate_path": str(outcome.artifact_dir / "promotion_gate.json"),
            "operator_report_path": str(outcome.report_path)
            if outcome.report_path is not None
            else None,
            "promotion_decision": outcome.promotion_decision,
            "promotion_gate_report_only": True,
            "promotion_gate": promotion_gate,
        },
        "output_paths": {
            "variant_dir": str(variant.output_paths.variant_dir),
            "manifest": str(variant.output_paths.manifest_path),
            "comparison_csv": str(variant.output_paths.comparison_csv_path),
        },
        "comparison_rows": list(rows),
        "status": outcome.status,
    }


def _run_manifest(
    *,
    plan: ExperimentPlan,
    run_dir: Path,
    comparison_csv_path: Path,
    variant_manifests: Sequence[Mapping[str, object]],
    status: str,
) -> dict[str, object]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": plan.run_id,
        "status": status,
        "adapter": plan.adapter.adapter_id,
        "experiment_id": plan.spec.experiment_id,
        "description": plan.spec.description,
        "spec_fingerprint": plan.spec_fingerprint,
        "git_commit": _git_commit(),
        "metric_ids": list(plan.metric_ids),
        "output_paths": {
            "run_dir": str(run_dir),
            "comparison_csv": str(comparison_csv_path),
            "manifest": str(run_dir / "manifest.json"),
        },
        "baseline_profile_names": [
            BASELINE_PROFILE_NAME,
            CANDIDATE_PROFILE_NAME,
        ],
        "variant_count": plan.variant_count,
        "fold_count": plan.fold_count,
        "jobs": plan.jobs,
        "max_variants": plan.max_variants,
        "variants": list(variant_manifests),
    }


def _backtest_overrides(overrides: Mapping[str, object]) -> dict[str, object]:
    return {
        path.removeprefix(BACKTEST_PREFIX): value
        for path, value in overrides.items()
        if path.startswith(BACKTEST_PREFIX)
    }


def _scoring_overrides(overrides: Mapping[str, object]) -> dict[str, object]:
    return {
        path: value for path, value in overrides.items() if not path.startswith(BACKTEST_PREFIX)
    }


def _delta(value: object | None, baseline: object | None) -> float | None:
    numeric_value = _numeric(value)
    numeric_baseline = _numeric(baseline)
    if numeric_value is None or numeric_baseline is None:
        return None
    return round(numeric_value - numeric_baseline, 8)


def _numeric(value: object | None) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(Decimal(str(value)))
    except (InvalidOperation, ValueError):
        return None


def _write_comparison_csv(
    path: Path,
    rows: Sequence[Mapping[str, object]],
    *,
    metric_ids: Sequence[str],
) -> None:
    fieldnames = [
        "experiment_id",
        "run_id",
        "variant_id",
        "variant_fingerprint",
        "fold_id",
        "profile_name",
        "profile_role",
        "validation_run_id",
        "validation_status",
        "promotion_decision",
        "overrides",
    ]
    for metric_id in metric_ids:
        fieldnames.extend(
            [
                metric_id,
                f"{metric_id}.delta_vs_v1",
                f"{metric_id}.delta_vs_current_v2a",
            ]
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: _csv_value(row.get(field)) for field in fieldnames})


def _read_json(path: Path) -> dict[str, object]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ExperimentSpecError(f"Expected validation artifact was not written: {path}") from exc
    if not isinstance(payload, dict):
        raise ExperimentSpecError(f"Expected validation artifact to be a JSON object: {path}")
    return payload


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _csv_value(value: object) -> object:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(_json_safe(value), sort_keys=True)
    return value


def _git_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"
