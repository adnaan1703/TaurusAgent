from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import subprocess
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from scripts.migrate import run_migrations
from taurus_core.backtesting import BacktestConfig, BacktestEngine
from taurus_core.config import Settings, get_settings
from taurus_core.data.universe import load_market_data_universe
from taurus_core.db.models import (
    BacktestEquityPointModel,
    BacktestFillModel,
    BacktestRunModel,
    BacktestSignalModel,
)
from taurus_core.db.repositories import (
    BacktestRepository,
    CandleRepository,
    InstrumentRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.official_context import (
    build_official_technical_context,
    official_context_with_snapshot_returns,
)
from taurus_core.features.store import FeatureSnapshot, TechnicalFeatureService
from taurus_core.features.technical_context import build_universe_technical_context
from taurus_core.features.technical_signal import (
    ANALYST_FEATURE_NAMES,
    ANALYST_RULE_PROFILE,
    OFFICIAL_V2B_PROFILE,
    OHLCV_V2_PROFILE,
    TechnicalSignalService,
)
from taurus_core.ops.progress import (
    ProgressEventCallback,
    create_progress_reporter,
    emit_progress,
)
from taurus_core.portfolio.score_semantics import calibrate_strategy_score
from taurus_core.strategies import load_strategy_config

ARTIFACT_VERSION = "technical_validation_v2"
TRADING_DAYS_PER_YEAR = 252
DEFAULT_WARMUP_DAYS = 252
STANDARD_VALIDATION_YEARS = 3
STRONG_VALIDATION_YEARS = 5
V1_STRATEGY_PATH = Path("configs/strategies/graph_aware_score_v1.yaml")
V2_STRATEGY_PATH = Path("configs/strategies/graph_aware_score_v2.yaml")
V2B_STRATEGY_PATH = Path("configs/strategies/graph_aware_score_v2b.yaml")
COMPARISON_METRICS = (
    "total_return",
    "cagr",
    "sharpe",
    "sortino",
    "max_drawdown",
    "win_rate",
    "profit_factor",
    "portfolio_breadth",
    "ranked_candidate_count",
    "eligible_candidate_count",
    "rebalance_count",
    "graph_trade_count",
    "graph_hit_rate",
    "graph_average_return",
    "graph_signal_count",
)
PREDICTION_HORIZONS = (5, 21, 63)
BASELINE_PROFILE_NAME = "graph_aware_score_v1"
CANDIDATE_PROFILE_NAME = "graph_aware_score_v2"
OFFICIAL_CANDIDATE_PROFILE_NAME = "graph_aware_score_v2b"
TECHNICAL_PROFILE_FOR_STRATEGY = {
    "graph_aware_score_v1": ANALYST_RULE_PROFILE,
    "graph_aware_score_v1_technical_only": ANALYST_RULE_PROFILE,
    "graph_aware_score_v2": OHLCV_V2_PROFILE,
    "graph_aware_score_v2_technical_only": OHLCV_V2_PROFILE,
    "graph_aware_score_v2b": OFFICIAL_V2B_PROFILE,
    "graph_aware_score_v2b_technical_only": OFFICIAL_V2B_PROFILE,
}
PROMOTION_DRAWDOWN_TOLERANCE = 0.02
PROMOTION_TURNOVER_MULTIPLE = 1.25
PROMOTION_TURNOVER_ABSOLUTE_BUFFER = 0.20


@dataclass(frozen=True, slots=True)
class ValidationRequest:
    symbols: tuple[str, ...]
    universe_source: str
    universe_path: str | None
    mode: str
    validation_years: int
    evaluation_days: int
    warmup_days: int
    timeframe: str
    artifact_root: Path
    initial_capital_inr: Decimal
    max_open_positions: int
    portfolio_breadth: int
    rebalance_every_days: int
    cost_bps: Decimal
    slippage_bps: Decimal
    strict_insufficient_data: bool = False
    include_v2b: bool = False
    report_root: Path = Path("docs/reports/technical_validation")

    @property
    def required_candle_count(self) -> int:
        return self.warmup_days + self.evaluation_days + 1


@dataclass(frozen=True, slots=True)
class DataReadiness:
    status: str
    common_dates: tuple[date, ...]
    selected_dates: tuple[date, ...]
    coverage_rows: tuple[dict[str, object], ...]
    artifact: dict[str, object]

    @property
    def sufficient(self) -> bool:
        return self.status == "sufficient"

    @property
    def warmup_start_date(self) -> date:
        return self.selected_dates[0]

    @property
    def evaluation_end_date(self) -> date:
        return self.selected_dates[-1]


@dataclass(frozen=True, slots=True)
class ValidationProfile:
    profile_name: str
    strategy_name: str
    strategy_type: str
    strategy_config_path: str
    strategy_parameters: Mapping[str, object]
    graph_contribution_enabled: bool
    notes: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ValidationOutcome:
    run_id: str
    artifact_dir: Path
    status: str
    manifest: dict[str, object]
    report_path: Path | None = None
    promotion_decision: str | None = None


@dataclass(frozen=True, slots=True)
class _TechnicalEvaluationProfile:
    report_profile_name: str
    technical_profile: str
    ohlcv_scoring_params: Mapping[str, object] | None


def run_validation(
    *,
    settings: Settings,
    request: ValidationRequest,
    profiles: Sequence[ValidationProfile] | None = None,
    progress: ProgressEventCallback | None = None,
) -> ValidationOutcome:
    if not request.symbols:
        raise ValueError("Validation requires at least one symbol.")

    emit_progress(progress, "technical_validation.setup_started", stage="migrations")
    run_migrations(settings)
    emit_progress(progress, "technical_validation.setup_completed", stage="migrations")
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        readiness = build_data_readiness(session, request, progress=progress)

    profiles = tuple(profiles) if profiles is not None else validation_profiles(
        include_v2b=request.include_v2b
    )
    if not profiles:
        raise ValueError("Validation requires at least one profile.")
    run_id = _stable_validation_run_id(
        request=request,
        readiness=readiness,
        profiles=profiles,
    )
    artifact_dir = request.artifact_root / run_id
    artifact_dir.mkdir(parents=True, exist_ok=True)
    _write_json(artifact_dir / "data_readiness.json", readiness.artifact)

    profile_runs: list[dict[str, object]] = []
    if readiness.sufficient:
        emit_progress(
            progress,
            "technical_validation.backtests_started",
            total=len(profiles),
        )
        for index, profile in enumerate(profiles, start=1):
            emit_progress(
                progress,
                "technical_validation.backtest_profile_started",
                current=index,
                total=len(profiles),
                profile_name=profile.profile_name,
            )
            config = _backtest_config(
                request=request,
                readiness=readiness,
                profile=profile,
            )
            with session_factory() as session:
                result = BacktestEngine(session, config).run()
                counts = BacktestRepository(session).count_artifacts(result.run_id)
            profile_runs.append(
                _profile_run_artifact(
                    profile=profile,
                    result=result,
                    artifact_counts=counts,
                )
            )
            emit_progress(
                progress,
                "technical_validation.backtest_profile_completed",
                current=index,
                total=len(profiles),
                profile_name=profile.profile_name,
            )
        _write_json(artifact_dir / "profile_runs.json", profile_runs)
        status = "complete"
    else:
        status = "insufficient_data"

    emit_progress(progress, "technical_validation.reports_started", status=status)
    with session_factory() as session:
        technical_report = _technical_agent_predictive_report(
            session=session,
            request=request,
            readiness=readiness,
            profiles=profiles,
        )
        system_report = _system_backtest_report(
            session=session,
            request=request,
            readiness=readiness,
            profile_runs=profile_runs,
        )
    promotion_gate = _promotion_gate(
        readiness=readiness,
        technical_report=technical_report,
        system_report=system_report,
        profile_runs=profile_runs,
        include_v2b=request.include_v2b,
    )
    _write_json(
        artifact_dir / "technical_agent_predictive_report.json",
        technical_report,
    )
    _write_technical_prediction_checks_csv(
        artifact_dir / "technical_agent_prediction_checks.csv",
        technical_report,
    )
    (artifact_dir / "technical_agent_predictive_report.md").write_text(
        _technical_report_markdown(technical_report),
        encoding="utf-8",
    )
    _write_json(artifact_dir / "system_backtest_report.json", system_report)
    _write_system_profile_summary_csv(
        artifact_dir / "system_backtest_profile_summary.csv",
        system_report,
    )
    (artifact_dir / "system_backtest_report.md").write_text(
        _system_report_markdown(system_report),
        encoding="utf-8",
    )
    _write_json(artifact_dir / "promotion_gate.json", promotion_gate)
    _write_comparison_matrix(
        artifact_dir / "profile_comparison_matrix.csv",
        profiles=profiles,
        profile_runs=profile_runs,
        technical_report=technical_report,
        system_report=system_report,
        readiness=readiness,
    )
    report_path = request.report_root / f"{run_id}.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        _operator_report_markdown(
            run_id=run_id,
            artifact_dir=artifact_dir,
            manifest_status=status,
            technical_report=technical_report,
            system_report=system_report,
            promotion_gate=promotion_gate,
        ),
        encoding="utf-8",
    )

    manifest = _manifest(
        request=request,
        readiness=readiness,
        profiles=profiles,
        profile_runs=profile_runs,
        run_id=run_id,
        status=status,
        report_path=report_path,
        promotion_gate=promotion_gate,
    )
    _write_json(artifact_dir / "validation_manifest.json", manifest)
    emit_progress(progress, "technical_validation.completed", status=status)
    return ValidationOutcome(
        run_id=run_id,
        artifact_dir=artifact_dir,
        status=status,
        manifest=manifest,
        report_path=report_path,
        promotion_decision=str(promotion_gate["decision"]),
    )


def build_data_readiness(
    session: Session,
    request: ValidationRequest,
    *,
    progress: ProgressEventCallback | None = None,
) -> DataReadiness:
    instrument_repo = InstrumentRepository(session)
    candle_repo = CandleRepository(session)
    date_sets: list[set[date]] = []
    coverage_rows: list[dict[str, object]] = []

    emit_progress(
        progress,
        "technical_validation.readiness_started",
        total=len(request.symbols),
    )
    for index, symbol in enumerate(request.symbols, start=1):
        emit_progress(
            progress,
            "technical_validation.readiness_symbol_started",
            symbol=symbol,
            current=index,
            total=len(request.symbols),
        )
        instrument = instrument_repo.get(symbol)
        active_instrument = bool(instrument is not None and instrument.active)
        candles = candle_repo.get_by_symbol_and_date_range(
            symbol=symbol,
            timeframe=request.timeframe,
        )
        candle_dates = tuple(candle.trade_date for candle in candles)
        if active_instrument and candle_dates:
            date_sets.append(set(candle_dates))
        coverage_rows.append(
            {
                "symbol": symbol,
                "active_instrument": active_instrument,
                "candle_count": len(candle_dates),
                "first_date": candle_dates[0].isoformat()
                if candle_dates
                else None,
                "last_date": candle_dates[-1].isoformat() if candle_dates else None,
                "missing_candle_count_vs_required": max(
                    0,
                    request.required_candle_count - len(candle_dates),
                ),
            }
        )
        emit_progress(
            progress,
            "technical_validation.readiness_symbol_completed",
            symbol=symbol,
            current=index,
            total=len(request.symbols),
        )

    common_dates: tuple[date, ...] = ()
    if len(date_sets) == len(request.symbols):
        common_dates = tuple(sorted(set.intersection(*date_sets)))

    selected_dates: tuple[date, ...] = ()
    status = "insufficient_data"
    if len(common_dates) >= request.required_candle_count:
        selected_dates = tuple(common_dates[-request.required_candle_count :])
        status = "sufficient"

    missing_symbols = [
        row["symbol"]
        for row in coverage_rows
        if not row["active_instrument"] or row["candle_count"] == 0
    ]
    common_missing_count = max(0, request.required_candle_count - len(common_dates))
    artifact: dict[str, object] = {
        "artifact_version": ARTIFACT_VERSION,
        "status": status,
        "universe": {
            "source": request.universe_source,
            "path": request.universe_path,
            "symbol_count": len(request.symbols),
            "symbols": list(request.symbols),
        },
        "window": {
            "mode": request.mode,
            "validation_years": request.validation_years,
            "evaluation_trading_days": request.evaluation_days,
            "warmup_trading_days": request.warmup_days,
            "required_common_candle_count": request.required_candle_count,
            "common_candle_count": len(common_dates),
            "common_start_date": common_dates[0].isoformat()
            if common_dates
            else None,
            "common_end_date": common_dates[-1].isoformat()
            if common_dates
            else None,
            "selected_warmup_start_date": selected_dates[0].isoformat()
            if selected_dates
            else None,
            "selected_scoring_start_date": selected_dates[
                request.warmup_days + 1
            ].isoformat()
            if selected_dates
            else None,
            "selected_evaluation_end_date": selected_dates[-1].isoformat()
            if selected_dates
            else None,
            "missing_common_candle_count": common_missing_count,
        },
        "coverage_by_symbol": coverage_rows,
        "missing_symbols": missing_symbols,
        "next_actions": []
        if status == "sufficient"
        else _insufficient_data_actions(request, common_missing_count),
    }
    emit_progress(
        progress,
        "technical_validation.readiness_completed",
        status=status,
        total=len(request.symbols),
        common_candle_count=len(common_dates),
        required_common_candle_count=request.required_candle_count,
    )
    return DataReadiness(
        status=status,
        common_dates=common_dates,
        selected_dates=selected_dates,
        coverage_rows=tuple(coverage_rows),
        artifact=artifact,
    )


def validation_profiles(*, include_v2b: bool = False) -> tuple[ValidationProfile, ...]:
    v1 = load_strategy_config(V1_STRATEGY_PATH)
    v2 = load_strategy_config(V2_STRATEGY_PATH)
    profiles = [
        ValidationProfile(
            profile_name="graph_aware_score_v1",
            strategy_name=v1.strategy_name,
            strategy_type=v1.strategy_type,
            strategy_config_path=str(V1_STRATEGY_PATH),
            strategy_parameters=dict(v1.parameters),
            graph_contribution_enabled=True,
            notes=("Existing v1 graph-aware score profile.",),
        ),
        ValidationProfile(
            profile_name="graph_aware_score_v1_technical_only",
            strategy_name="graph_aware_score_v1_technical_only",
            strategy_type=v1.strategy_type,
            strategy_config_path=str(V1_STRATEGY_PATH),
            strategy_parameters=_without_graph_contribution(v1.parameters),
            graph_contribution_enabled=False,
            notes=(
                "V1 graph-aware strategy with graph contribution weight set to zero.",
                "Backtest graph loading remains available, but ranking ignores graph score.",
            ),
        ),
        ValidationProfile(
            profile_name="graph_aware_score_v2",
            strategy_name=v2.strategy_name,
            strategy_type=v2.strategy_type,
            strategy_config_path=str(V2_STRATEGY_PATH),
            strategy_parameters=dict(v2.parameters),
            graph_contribution_enabled=True,
            notes=("Opt-in v2A OHLCV graph-aware score profile.",),
        ),
        ValidationProfile(
            profile_name="graph_aware_score_v2_technical_only",
            strategy_name="graph_aware_score_v2_technical_only",
            strategy_type=v2.strategy_type,
            strategy_config_path=str(V2_STRATEGY_PATH),
            strategy_parameters=_without_graph_contribution(v2.parameters),
            graph_contribution_enabled=False,
            notes=(
                "V2A OHLCV graph-aware strategy with graph contribution weight set to zero.",
                "Backtest graph loading remains available, but ranking ignores graph score.",
            ),
        ),
    ]
    if include_v2b:
        v2b = load_strategy_config(V2B_STRATEGY_PATH)
        profiles.extend(
            [
                ValidationProfile(
                    profile_name="graph_aware_score_v2b",
                    strategy_name=v2b.strategy_name,
                    strategy_type=v2b.strategy_type,
                    strategy_config_path=str(V2B_STRATEGY_PATH),
                    strategy_parameters=dict(v2b.parameters),
                    graph_contribution_enabled=True,
                    notes=("Opt-in v2B official-data graph-aware score profile.",),
                ),
                ValidationProfile(
                    profile_name="graph_aware_score_v2b_technical_only",
                    strategy_name="graph_aware_score_v2b_technical_only",
                    strategy_type=v2b.strategy_type,
                    strategy_config_path=str(V2B_STRATEGY_PATH),
                    strategy_parameters=_without_graph_contribution(v2b.parameters),
                    graph_contribution_enabled=False,
                    notes=(
                        "V2B official-data graph-aware strategy with graph contribution weight set to zero.",
                        "Backtest graph loading remains available, but ranking ignores graph score.",
                    ),
                ),
            ]
        )
    return tuple(profiles)


def request_from_args(
    args: argparse.Namespace,
    *,
    settings: Settings,
) -> ValidationRequest:
    symbols, universe_source, universe_path = _resolve_validation_universe(
        args,
        settings=settings,
    )
    validation_years = (
        STRONG_VALIDATION_YEARS
        if args.mode == "strong"
        else STANDARD_VALIDATION_YEARS
    )
    portfolio_breadth = (
        int(args.portfolio_breadth)
        if args.portfolio_breadth is not None
        else settings.taurus_backtest_target_positions
        or settings.taurus_max_open_positions
    )
    initial_capital = Decimal(
        str(args.initial_capital_inr or settings.taurus_initial_capital_inr)
    )
    cost_bps = Decimal(str(args.cost_bps or "10"))
    slippage_bps = Decimal(str(args.slippage_bps or settings.taurus_paper_slippage_bps))
    return ValidationRequest(
        symbols=symbols,
        universe_source=universe_source,
        universe_path=universe_path,
        mode=args.mode,
        validation_years=validation_years,
        evaluation_days=validation_years * TRADING_DAYS_PER_YEAR,
        warmup_days=DEFAULT_WARMUP_DAYS,
        timeframe=settings.taurus_timeframe,
        artifact_root=Path(args.artifact_root),
        initial_capital_inr=initial_capital,
        max_open_positions=int(
            args.max_open_positions or settings.taurus_max_open_positions
        ),
        portfolio_breadth=portfolio_breadth,
        rebalance_every_days=int(args.rebalance_every_days),
        cost_bps=cost_bps,
        slippage_bps=slippage_bps,
        strict_insufficient_data=bool(args.strict_insufficient_data),
        include_v2b=bool(args.include_v2b),
        report_root=Path(args.report_root),
    )


def _resolve_validation_universe(
    args: argparse.Namespace,
    *,
    settings: Settings,
) -> tuple[tuple[str, ...], str, str | None]:
    if args.symbols:
        symbols = _normalize_symbols(args.symbols.split(","))
        if not symbols:
            raise ValueError("--symbols did not contain any symbols.")
        return symbols, "manual_symbols", None

    universe_path = (
        args.universe
        or settings.taurus_target_market_universe_path.strip()
        or settings.taurus_market_data_universe_path.strip()
    )
    universe = load_market_data_universe(universe_path)
    symbols = tuple(universe.enabled_symbols())
    return symbols, "market_data_universe", str(universe.source_path)


def _backtest_config(
    *,
    request: ValidationRequest,
    readiness: DataReadiness,
    profile: ValidationProfile,
) -> BacktestConfig:
    return BacktestConfig(
        strategy_name=profile.strategy_name,
        strategy_type=profile.strategy_type,
        strategy_config_path=profile.strategy_config_path,
        strategy_parameters=dict(profile.strategy_parameters),
        seed=42,
        initial_capital_inr=request.initial_capital_inr,
        max_open_positions=request.max_open_positions,
        portfolio_breadth=request.portfolio_breadth,
        portfolio_breadth_source="technical_validation",
        lookback_days=request.warmup_days,
        rebalance_every_days=request.rebalance_every_days,
        cost_bps=request.cost_bps,
        slippage_bps=request.slippage_bps,
        timeframe=request.timeframe,
        graph_enabled=True,
        symbols=request.symbols,
        start_date=readiness.warmup_start_date,
        end_date=readiness.evaluation_end_date,
    )


def _profile_run_artifact(
    *,
    profile: ValidationProfile,
    result: Any,
    artifact_counts: Mapping[str, int],
) -> dict[str, object]:
    return {
        "profile_name": profile.profile_name,
        "strategy_name": profile.strategy_name,
        "strategy_type": profile.strategy_type,
        "strategy_config_path": profile.strategy_config_path,
        "graph_contribution_enabled": profile.graph_contribution_enabled,
        "notes": list(profile.notes),
        "backtest_run_id": result.run_id,
        "start_date": result.start_date.isoformat(),
        "end_date": result.end_date.isoformat(),
        "metrics": result.metrics,
        "artifact_counts": dict(artifact_counts),
        "feature_value_count": result.feature_value_count,
        "signal_count": result.signal_count,
        "order_count": result.order_count,
        "fill_count": result.fill_count,
        "position_count": result.position_count,
        "equity_point_count": result.equity_point_count,
        "audit_row_count": result.audit_row_count,
    }


def _technical_evaluation_profiles(
    profiles: Sequence[ValidationProfile],
) -> tuple[_TechnicalEvaluationProfile, ...]:
    evaluations: list[_TechnicalEvaluationProfile] = []
    seen: set[tuple[str, str, str]] = set()
    for profile in profiles:
        technical_profile = _technical_scoring_profile(profile)
        report_profile_name = _technical_report_profile_name(profile)
        ohlcv_scoring_params = (
            _ohlcv_scoring_params(profile)
            if technical_profile == OHLCV_V2_PROFILE
            else None
        )
        fingerprint = json.dumps(
            _json_safe(ohlcv_scoring_params or {}),
            sort_keys=True,
            separators=(",", ":"),
        )
        key = (report_profile_name, technical_profile, fingerprint)
        if key in seen:
            continue
        seen.add(key)
        evaluations.append(
            _TechnicalEvaluationProfile(
                report_profile_name=report_profile_name,
                technical_profile=technical_profile,
                ohlcv_scoring_params=ohlcv_scoring_params,
            )
        )
    return tuple(evaluations)


def _technical_report_profile_name(profile: ValidationProfile) -> str:
    return TECHNICAL_PROFILE_FOR_STRATEGY.get(profile.profile_name, profile.profile_name)


def _technical_scoring_profile(profile: ValidationProfile) -> str:
    known_profile = TECHNICAL_PROFILE_FOR_STRATEGY.get(profile.profile_name)
    if known_profile is not None:
        return known_profile
    raw_profile = profile.strategy_parameters.get(
        "technical_profile",
        profile.strategy_parameters.get("technical_analyst_profile", ""),
    )
    technical_profile = str(raw_profile or "").strip()
    if technical_profile in {OHLCV_V2_PROFILE, OFFICIAL_V2B_PROFILE}:
        return technical_profile
    return ANALYST_RULE_PROFILE


def _ohlcv_scoring_params(
    profile: ValidationProfile,
) -> Mapping[str, object] | None:
    raw_params = profile.strategy_parameters.get("technical_ohlcv_v2_params")
    if raw_params is None:
        return None
    if not isinstance(raw_params, Mapping):
        raise ValueError("technical_ohlcv_v2_params must be a mapping.")
    return raw_params


def _technical_agent_predictive_report(
    *,
    session: Session,
    request: ValidationRequest,
    readiness: DataReadiness,
    profiles: Sequence[ValidationProfile],
) -> dict[str, object]:
    base_report: dict[str, object] = {
        "artifact_version": ARTIFACT_VERSION,
        "status": "not_run",
        "prediction_label": {
            "label_type": "forward_return",
            "horizons_trading_days": list(PREDICTION_HORIZONS),
            "definition": (
                "Close-to-close forward return from scoring date to "
                "scoring date plus horizon trading days."
            ),
        },
        "universe": readiness.artifact["universe"],
        "window": readiness.artifact["window"],
        "profiles": [],
        "checks": [],
        "coverage_diagnostics": {
            "status": readiness.status,
            "coverage_by_symbol": readiness.artifact["coverage_by_symbol"],
            "missing_symbols": readiness.artifact["missing_symbols"],
        },
        "notes": [],
    }
    if not readiness.sufficient:
        base_report["notes"] = [
            "Predictive checks were not run because common candle coverage is insufficient.",
            *list(readiness.artifact["next_actions"]),
        ]
        return base_report

    evaluations = _technical_evaluation_profiles(profiles)
    candles_by_symbol = _load_validation_candles(session, request, readiness)
    observations_by_profile: dict[str, list[dict[str, object]]] = defaultdict(list)
    signal_service = TechnicalSignalService()
    feature_services = {
        evaluation.report_profile_name: TechnicalFeatureService.ohlcv_v2()
        if evaluation.technical_profile in {OHLCV_V2_PROFILE, OFFICIAL_V2B_PROFILE}
        else TechnicalFeatureService()
        for evaluation in evaluations
    }
    v2b_config = (
        load_strategy_config(V2B_STRATEGY_PATH)
        if any(
            evaluation.technical_profile == OFFICIAL_V2B_PROFILE
            for evaluation in evaluations
        )
        else None
    )
    evaluation_by_report_name = {
        evaluation.report_profile_name: evaluation for evaluation in evaluations
    }
    scoring_start_index = request.warmup_days + 1
    for date_index, scoring_date in enumerate(readiness.selected_dates):
        if date_index < scoring_start_index:
            continue
        if (date_index - scoring_start_index) % request.rebalance_every_days != 0:
            continue

        snapshots_by_profile = {
            profile_name: _snapshots_for_scoring_date(
                candles_by_symbol=candles_by_symbol,
                scoring_date=scoring_date,
                feature_service=feature_service,
            )
            for profile_name, feature_service in feature_services.items()
        }
        v2_context_snapshots = next(
            (
                snapshots_by_profile[evaluation.report_profile_name]
                for evaluation in evaluations
                if evaluation.technical_profile
                in {OHLCV_V2_PROFILE, OFFICIAL_V2B_PROFILE}
            ),
            {},
        )
        v2_context = (
            build_universe_technical_context(
                v2_context_snapshots,
                as_of_date=scoring_date,
            )
            if v2_context_snapshots
            else None
        )
        v2b_official_context = None
        official_evaluation = next(
            (
                evaluation
                for evaluation in evaluations
                if evaluation.technical_profile == OFFICIAL_V2B_PROFILE
            ),
            None,
        )
        if official_evaluation is not None and v2b_config is not None:
            official_snapshots = snapshots_by_profile[
                official_evaluation.report_profile_name
            ]
            v2b_official_context = official_context_with_snapshot_returns(
                build_official_technical_context(
                    session,
                    symbols=tuple(official_snapshots),
                    as_of=scoring_date,
                    benchmark_index_symbol=_official_benchmark_index_symbol(
                        v2b_config.parameters
                    ),
                    volatility_index_symbol=_official_volatility_index_symbol(
                        v2b_config.parameters
                    ),
                    sector_index_by_symbol=_official_sector_index_by_symbol(
                        v2b_config.parameters
                    ),
                    index_timeframe=_official_index_timeframe(v2b_config.parameters),
                    microstructure_timeframe=_official_microstructure_timeframe(
                        v2b_config.parameters
                    ),
                ),
                {
                    symbol: snapshot.get("return_20d")
                    for symbol, snapshot in official_snapshots.items()
                },
            )
        for profile_name, snapshots in snapshots_by_profile.items():
            evaluation = evaluation_by_report_name[profile_name]
            for symbol, snapshot in snapshots.items():
                if evaluation.technical_profile == OFFICIAL_V2B_PROFILE:
                    result = signal_service.score_official_v2b(
                        snapshot,
                        universe_context=v2_context,
                        official_context=v2b_official_context,
                        symbol=symbol,
                    )
                    score = result.score if result.available else None
                    confidence = result.confidence
                    coverage = result.coverage
                    top_contributor_count = len(result.top_contributors)
                    vector_present = bool(result.top_contributors)
                    missing_features = tuple(result.missing_features)
                    components = dict(result.components)
                elif evaluation.technical_profile == OHLCV_V2_PROFILE:
                    result = signal_service.score_ohlcv_v2(
                        snapshot,
                        universe_context=v2_context,
                        symbol=symbol,
                        scoring_params=evaluation.ohlcv_scoring_params,
                    )
                    score = result.score if result.available else None
                    confidence = result.confidence
                    coverage = result.coverage
                    top_contributor_count = len(result.top_contributors)
                    vector_present = bool(result.top_contributors)
                    missing_features = tuple(result.missing_features)
                    components = dict(result.components)
                else:
                    result = signal_service.score_analyst_rule(
                        snapshot,
                        latest_signal=None,
                        symbol=symbol,
                    )
                    score = result.score if result.available else None
                    confidence = result.confidence or Decimal("0")
                    missing_features = tuple(result.missing_features)
                    coverage = _coverage_decimal(
                        available_count=len(ANALYST_FEATURE_NAMES)
                        - len(missing_features),
                        total_count=len(ANALYST_FEATURE_NAMES),
                    )
                    top_contributor_count = len(result.key_points)
                    vector_present = bool(result.components)
                    components = dict(result.components)

                for horizon in PREDICTION_HORIZONS:
                    outcome = _future_return(
                        candles_by_symbol=candles_by_symbol,
                        symbol=symbol,
                        scoring_date=scoring_date,
                        date_index=date_index,
                        horizon=horizon,
                        selected_dates=readiness.selected_dates,
                    )
                    if outcome is None:
                        continue
                    outcome_date, forward_return = outcome
                    observations_by_profile[profile_name].append(
                        {
                            "profile_name": profile_name,
                            "symbol": symbol,
                            "scoring_date": scoring_date.isoformat(),
                            "outcome_date": outcome_date.isoformat(),
                            "horizon_days": horizon,
                            "score": score,
                            "confidence": confidence,
                            "forward_return": forward_return,
                            "coverage": coverage,
                            "missing_features": list(missing_features),
                            "component_count": len(components),
                            "top_contributor_count": top_contributor_count,
                            "vector_present": vector_present,
                        }
                    )

    checks: list[dict[str, object]] = []
    profiles: list[dict[str, object]] = []
    for evaluation in evaluations:
        observations = observations_by_profile.get(evaluation.report_profile_name, [])
        checks.extend(_prediction_checks(evaluation.report_profile_name, observations))
        profiles.append(
            _technical_profile_summary(
                evaluation.report_profile_name,
                observations,
                technical_profile=evaluation.technical_profile,
            )
        )

    return {
        **base_report,
        "status": "complete",
        "profiles": profiles,
        "checks": checks,
        "coverage_diagnostics": {
            **base_report["coverage_diagnostics"],
            "scoring_date_count": len(
                {
                    row["scoring_date"]
                    for rows in observations_by_profile.values()
                    for row in rows
                }
            ),
            "observation_count": sum(
                len(rows) for rows in observations_by_profile.values()
            ),
        },
        "notes": [
            "Technical-agent evidence is computed DB-free from validation candles and the shared TechnicalSignalService profiles.",
            "Scores use information available before the scoring date; labels use future close-to-close returns.",
        ],
    }


def _system_backtest_report(
    *,
    session: Session,
    request: ValidationRequest,
    readiness: DataReadiness,
    profile_runs: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    if not readiness.sufficient or not profile_runs:
        return {
            "artifact_version": ARTIFACT_VERSION,
            "status": "not_run",
            "universe": readiness.artifact["universe"],
            "window": readiness.artifact["window"],
            "profiles": [],
            "notes": [
                "Full-system report was not run because comparable backtests were not available.",
                *list(readiness.artifact["next_actions"]),
            ],
        }

    profiles: list[dict[str, object]] = []
    for profile_run in profile_runs:
        run_id = str(profile_run["backtest_run_id"])
        run = session.get(BacktestRunModel, run_id)
        if run is None:
            continue
        equity_points = list(
            session.scalars(
                select(BacktestEquityPointModel)
                .where(BacktestEquityPointModel.run_id == run_id)
                .order_by(BacktestEquityPointModel.trade_date)
            )
        )
        fills = list(
            session.scalars(
                select(BacktestFillModel)
                .where(BacktestFillModel.run_id == run_id)
                .order_by(BacktestFillModel.trade_date, BacktestFillModel.symbol)
            )
        )
        signals = list(
            session.scalars(
                select(BacktestSignalModel)
                .where(BacktestSignalModel.run_id == run_id)
                .order_by(BacktestSignalModel.trade_date, BacktestSignalModel.symbol)
            )
        )
        profiles.append(
            _system_profile_summary(
                request=request,
                profile_run=profile_run,
                run=run,
                equity_points=equity_points,
                fills=fills,
                signals=signals,
            )
        )

    return {
        "artifact_version": ARTIFACT_VERSION,
        "status": "complete",
        "universe": readiness.artifact["universe"],
        "window": readiness.artifact["window"],
        "profiles": profiles,
        "notes": [
            "Full-system evidence is produced from the comparable BacktestEngine profile runs.",
            "Backtests do not run the live planner allocation ledger; allocation-score behavior is reported as a deterministic backtest proxy.",
        ],
    }


def _promotion_gate(
    *,
    readiness: DataReadiness,
    technical_report: Mapping[str, object],
    system_report: Mapping[str, object],
    profile_runs: Sequence[Mapping[str, object]],
    include_v2b: bool,
) -> dict[str, object]:
    checks: list[dict[str, object]] = []
    blockers: list[str] = []

    if not readiness.sufficient:
        blockers.append("Data readiness is insufficient for comparable validation.")
        checks.append(
            _gate_check(
                "data_readiness",
                "fail",
                "Common local candle coverage is insufficient.",
            )
        )
    else:
        checks.append(
            _gate_check("data_readiness", "pass", "Common candle coverage is sufficient.")
        )

    system_profiles = {
        str(row["profile_name"]): row
        for row in system_report.get("profiles", [])
        if isinstance(row, Mapping)
    }
    baseline = system_profiles.get(BASELINE_PROFILE_NAME)
    candidate = system_profiles.get(CANDIDATE_PROFILE_NAME)
    if baseline is None or candidate is None:
        blockers.append("Missing v1 or v2A full-system backtest comparison.")
        checks.append(
            _gate_check(
                "full_system_comparison",
                "fail",
                "Baseline and candidate profile reports are both required.",
            )
        )
    else:
        checks.extend(_system_gate_checks(baseline, candidate, blockers))

    v2_rank_check = _technical_gate_check(technical_report)
    checks.append(v2_rank_check)
    if v2_rank_check["status"] != "pass":
        blockers.append(str(v2_rank_check["detail"]))

    safety_status = "pass" if profile_runs else "fail"
    if safety_status != "pass":
        blockers.append("Operational safety cannot be checked without profile runs.")
    checks.append(
        _gate_check(
            "operational_safety",
            safety_status,
            (
                "Validation only writes reports and leaves graph_aware_score_v1 and technical_rule_v1 defaults unchanged."
                if safety_status == "pass"
                else "Profile runs were unavailable, so safety evidence is incomplete."
            ),
        )
    )

    if blockers and readiness.sufficient:
        decision = "keep_opt_in"
    elif blockers:
        decision = "defer"
    else:
        decision = "promote"

    return {
        "artifact_version": ARTIFACT_VERSION,
        "decision": decision,
        "baseline_profile": BASELINE_PROFILE_NAME,
        "candidate_profile": CANDIDATE_PROFILE_NAME,
        "official_candidate_profile": OFFICIAL_CANDIDATE_PROFILE_NAME
        if include_v2b
        else None,
        "official_candidate_validation_enabled": include_v2b,
        "checks": checks,
        "blocking_reasons": blockers,
        "promotion_policy": {
            "after_costs_rule": "v2A total return must beat or tie v1 after configured costs and slippage.",
            "drawdown_rule": f"v2A max drawdown cannot worsen by more than {PROMOTION_DRAWDOWN_TOLERANCE:.2%}.",
            "turnover_rule": (
                "v2A turnover must be no more than "
                f"{PROMOTION_TURNOVER_MULTIPLE:.2f}x v1 plus "
                f"{PROMOTION_TURNOVER_ABSOLUTE_BUFFER:.2f} absolute turnover."
            ),
            "rank_rule": "v2A 21d rank correlation and top-vs-bottom spread must be non-negative.",
            "utilization_rule": "v2A must avoid lower allocation utilization or inferred sizing failures versus v1.",
        },
        "note": (
            "This gate reports a recommendation only; v2B validation was explicitly enabled for this run."
            if include_v2b
            else "This gate reports a recommendation only; v2B validation is disabled by default until official-data readiness is available."
        ),
    }


def _manifest(
    *,
    request: ValidationRequest,
    readiness: DataReadiness,
    profiles: Sequence[ValidationProfile],
    profile_runs: Sequence[Mapping[str, object]],
    run_id: str,
    status: str,
    report_path: Path,
    promotion_gate: Mapping[str, object],
) -> dict[str, object]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "status": status,
        "code_commit": _git_commit(),
        "data_readiness_path": "data_readiness.json",
        "profile_runs_path": "profile_runs.json" if profile_runs else None,
        "profile_comparison_matrix_path": "profile_comparison_matrix.csv",
        "technical_agent_predictive_report_path": "technical_agent_predictive_report.json",
        "system_backtest_report_path": "system_backtest_report.json",
        "promotion_gate_path": "promotion_gate.json",
        "operator_markdown_report_path": str(report_path),
        "promotion_decision": promotion_gate["decision"],
        "request": {
            "mode": request.mode,
            "validation_years": request.validation_years,
            "evaluation_trading_days": request.evaluation_days,
            "warmup_trading_days": request.warmup_days,
            "timeframe": request.timeframe,
            "initial_capital_inr": str(request.initial_capital_inr),
            "max_open_positions": request.max_open_positions,
            "portfolio_breadth": request.portfolio_breadth,
            "rebalance_every_days": request.rebalance_every_days,
            "cost_bps": str(request.cost_bps),
            "slippage_bps": str(request.slippage_bps),
            "include_v2b": request.include_v2b,
            "report_root": str(request.report_root),
        },
        "universe": readiness.artifact["universe"],
        "window": readiness.artifact["window"],
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
        "profile_run_count": len(profile_runs),
        "profile_runs": [
            {
                "profile_name": row["profile_name"],
                "backtest_run_id": row["backtest_run_id"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
            }
            for row in profile_runs
        ],
        "next_actions": readiness.artifact["next_actions"],
    }


def _load_validation_candles(
    session: Session,
    request: ValidationRequest,
    readiness: DataReadiness,
) -> dict[str, list[DailyCandle]]:
    candle_repo = CandleRepository(session)
    candles_by_symbol: dict[str, list[DailyCandle]] = {}
    for symbol in request.symbols:
        models = candle_repo.get_by_symbol_and_date_range(
            symbol=symbol,
            start_date=readiness.warmup_start_date,
            end_date=readiness.evaluation_end_date,
            timeframe=request.timeframe,
        )
        candles_by_symbol[symbol] = [
            DailyCandle(
                symbol=model.symbol,
                trade_date=model.trade_date,
                open=model.open,
                high=model.high,
                low=model.low,
                close=model.close,
                volume=model.volume,
                timeframe=model.timeframe,
                source=model.source,
                data_available_time=model.data_available_time,
            )
            for model in models
        ]
    return candles_by_symbol


def _snapshots_for_scoring_date(
    *,
    candles_by_symbol: Mapping[str, Sequence[DailyCandle]],
    scoring_date: date,
    feature_service: TechnicalFeatureService,
) -> dict[str, FeatureSnapshot]:
    snapshots: dict[str, FeatureSnapshot] = {}
    for symbol, candles in candles_by_symbol.items():
        history = [candle for candle in candles if candle.trade_date < scoring_date]
        snapshot = feature_service.build_snapshot(
            symbol=symbol,
            as_of_date=scoring_date,
            history=history,
        )
        if snapshot is not None:
            snapshots[symbol] = snapshot
    return snapshots


def _future_return(
    *,
    candles_by_symbol: Mapping[str, Sequence[DailyCandle]],
    symbol: str,
    scoring_date: date,
    date_index: int,
    horizon: int,
    selected_dates: Sequence[date],
) -> tuple[date, Decimal] | None:
    outcome_index = date_index + horizon
    if outcome_index >= len(selected_dates):
        return None
    outcome_date = selected_dates[outcome_index]
    candle_by_date = {candle.trade_date: candle for candle in candles_by_symbol[symbol]}
    scoring_candle = candle_by_date.get(scoring_date)
    outcome_candle = candle_by_date.get(outcome_date)
    if scoring_candle is None or outcome_candle is None or scoring_candle.close <= 0:
        return None
    forward_return = (outcome_candle.close / scoring_candle.close) - Decimal("1")
    return outcome_date, forward_return.quantize(Decimal("0.00000001"))


def _prediction_checks(
    profile_name: str,
    observations: Sequence[Mapping[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for horizon in PREDICTION_HORIZONS:
        horizon_observations = [
            row for row in observations if row["horizon_days"] == horizon
        ]
        scored = [
            row
            for row in horizon_observations
            if row.get("score") is not None and row.get("forward_return") is not None
        ]
        rank_correlation = _spearman_rank_correlation(
            [
                (
                    _float(row["score"]),
                    _float(row["forward_return"]),
                )
                for row in scored
            ]
        )
        decile = _top_bottom_spread(scored)
        confidence = _confidence_hit_rates(scored)
        coverage_values = [_float(row["coverage"]) for row in scored]
        missing_feature_counts = [
            len(row.get("missing_features", []))
            for row in scored
            if isinstance(row.get("missing_features"), list)
        ]
        monotonicity_status = (
            "pass"
            if rank_correlation is not None
            and rank_correlation >= 0
            and decile["top_bottom_spread"] is not None
            and decile["top_bottom_spread"] >= 0
            else "fail"
            if scored
            else "not_applicable"
        )
        rows.append(
            {
                "profile_name": profile_name,
                "horizon_days": horizon,
                "observation_count": len(scored),
                "rank_correlation": rank_correlation,
                "top_decile_mean_return": decile["top_mean"],
                "bottom_decile_mean_return": decile["bottom_mean"],
                "top_bottom_decile_spread": decile["top_bottom_spread"],
                "hit_rate": confidence["hit_rate"],
                "high_confidence_hit_rate": confidence["high_confidence_hit_rate"],
                "low_confidence_hit_rate": confidence["low_confidence_hit_rate"],
                "high_confidence_count": confidence["high_confidence_count"],
                "low_confidence_count": confidence["low_confidence_count"],
                "coverage_pct": _mean_float(coverage_values),
                "average_missing_feature_count": _mean_float(missing_feature_counts),
                "monotonicity_status": monotonicity_status,
            }
        )
    return rows


def _technical_profile_summary(
    profile_name: str,
    observations: Sequence[Mapping[str, object]],
    *,
    technical_profile: str | None = None,
) -> dict[str, object]:
    scored = [row for row in observations if row.get("score") is not None]
    coverage_values = [_float(row["coverage"]) for row in scored]
    missing_feature_counts = [
        len(row.get("missing_features", []))
        for row in scored
        if isinstance(row.get("missing_features"), list)
    ]
    vector_presence_values = [bool(row.get("vector_present")) for row in scored]
    contributor_counts = [
        int(row.get("top_contributor_count", 0) or 0) for row in scored
    ]
    return {
        "profile_name": profile_name,
        "observation_count": len(scored),
        "score_distribution": _distribution([_float(row["score"]) for row in scored]),
        "confidence_distribution": _distribution(
            [_float(row["confidence"]) for row in scored]
        ),
        "coverage_pct": _mean_float(coverage_values),
        "average_missing_feature_count": _mean_float(missing_feature_counts),
        "missing_feature_names": sorted(
            {
                feature
                for row in scored
                for feature in row.get("missing_features", [])
                if isinstance(row.get("missing_features"), list)
            }
        ),
        "explanation_quality": {
            "vector_presence_pct": _mean_float(
                [1.0 if present else 0.0 for present in vector_presence_values]
            ),
            "average_contributor_count": _mean_float(contributor_counts),
            "summary": (
                "v2 vector/contributor evidence present"
                if (technical_profile or profile_name)
                in {OHLCV_V2_PROFILE, OFFICIAL_V2B_PROFILE}
                else "v1 scalar score with deterministic components/key points"
            ),
        },
    }


def _system_profile_summary(
    *,
    request: ValidationRequest,
    profile_run: Mapping[str, object],
    run: BacktestRunModel,
    equity_points: Sequence[BacktestEquityPointModel],
    fills: Sequence[BacktestFillModel],
    signals: Sequence[BacktestSignalModel],
) -> dict[str, object]:
    metrics = dict(run.metrics or {})
    buy_signals = [signal for signal in signals if signal.action == "BUY"]
    buy_fills = [fill for fill in fills if fill.side == "BUY"]
    sell_fills = [fill for fill in fills if fill.side == "SELL"]
    signal_scores = [Decimal(signal.score) for signal in signals]
    calibrated_scores = [
        calibrate_strategy_score(score).allocation_score_component
        for score in signal_scores
    ]
    ranked_candidate_count = int(metrics.get("ranked_candidate_count") or 0)
    eligible_candidate_count = int(metrics.get("eligible_candidate_count") or 0)
    portfolio_breadth = int(metrics.get("portfolio_breadth") or request.portfolio_breadth)
    trimmed_count = max(0, eligible_candidate_count - portfolio_breadth)
    rejected_count = max(0, ranked_candidate_count - eligible_candidate_count)
    sizing_failure_count = max(0, len(buy_signals) - len(buy_fills))
    cash_utilization = _cash_utilization_summary(equity_points)
    equity_curve = _equity_curve_summary(equity_points)
    turnover = _turnover(fills=fills, equity_points=equity_points)
    selected_symbols = sorted({fill.symbol for fill in buy_fills})
    return {
        "profile_name": str(profile_run["profile_name"]),
        "strategy_name": str(profile_run["strategy_name"]),
        "strategy_config_path": str(profile_run["strategy_config_path"]),
        "backtest_run_id": run.run_id,
        "start_date": run.start_date.isoformat(),
        "end_date": run.end_date.isoformat(),
        "money_management_config": "backtest_equal_weight_rebalance",
        "graph_enabled": bool(profile_run["graph_contribution_enabled"]),
        "paper_only_execution": True,
        "initial_capital_inr": str(run.initial_capital_inr),
        "final_equity_inr": str(run.final_equity_inr),
        "metrics": {
            "total_return": metrics.get("total_return"),
            "cagr": metrics.get("cagr"),
            "sharpe": metrics.get("sharpe"),
            "sortino": metrics.get("sortino"),
            "max_drawdown": metrics.get("max_drawdown"),
            "turnover": turnover,
            "win_rate": metrics.get("win_rate"),
            "profit_factor": metrics.get("profit_factor"),
            "trade_count": len(fills),
            "fill_count": len(fills),
            "buy_fill_count": len(buy_fills),
            "sell_fill_count": len(sell_fills),
            "open_position_count": int(profile_run.get("position_count") or 0),
        },
        "selected_symbol_counts": {
            "selected_symbol_count": len(selected_symbols),
            "selected_symbols": selected_symbols,
            "buy_signal_count": len(buy_signals),
            "signal_count": len(signals),
        },
        "cash_utilization": cash_utilization,
        "allocation_candidate_score_behavior": {
            "source": "backtest_strategy_signal_proxy",
            "raw_strategy_score_distribution": _distribution(
                [_float(score) for score in signal_scores]
            ),
            "calibrated_allocation_component_distribution": _distribution(
                [_float(score) for score in calibrated_scores]
            ),
            "ranked_candidate_count": ranked_candidate_count,
            "eligible_candidate_count": eligible_candidate_count,
            "portfolio_breadth": portfolio_breadth,
        },
        "rejected_or_trimmed_candidate_counts": {
            "rejected_candidate_count": rejected_count,
            "trimmed_candidate_count": trimmed_count,
            "sizing_failure_count": sizing_failure_count,
        },
        "equity_curve_summary": equity_curve,
        "artifact_counts": dict(profile_run.get("artifact_counts", {})),
    }


def _system_gate_checks(
    baseline: Mapping[str, object],
    candidate: Mapping[str, object],
    blockers: list[str],
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []
    baseline_metrics = _metrics(baseline)
    candidate_metrics = _metrics(candidate)
    baseline_return = _metric_float(baseline_metrics, "total_return")
    candidate_return = _metric_float(candidate_metrics, "total_return")
    if baseline_return is None or candidate_return is None:
        status = "fail"
        detail = "Total-return comparison is missing."
    elif candidate_return + 1e-12 >= baseline_return:
        status = "pass"
        detail = f"v2A total_return={candidate_return:.6f} beats/ties v1={baseline_return:.6f}."
    else:
        status = "fail"
        detail = f"v2A total_return={candidate_return:.6f} trails v1={baseline_return:.6f}."
    if status != "pass":
        blockers.append(detail)
    checks.append(_gate_check("after_costs_return", status, detail))

    baseline_drawdown = _metric_float(baseline_metrics, "max_drawdown")
    candidate_drawdown = _metric_float(candidate_metrics, "max_drawdown")
    if baseline_drawdown is None or candidate_drawdown is None:
        status = "fail"
        detail = "Max-drawdown comparison is missing."
    elif candidate_drawdown + PROMOTION_DRAWDOWN_TOLERANCE >= baseline_drawdown:
        status = "pass"
        detail = f"v2A max_drawdown={candidate_drawdown:.6f} is within tolerance of v1={baseline_drawdown:.6f}."
    else:
        status = "fail"
        detail = f"v2A max_drawdown={candidate_drawdown:.6f} materially worsens v1={baseline_drawdown:.6f}."
    if status != "pass":
        blockers.append(detail)
    checks.append(_gate_check("max_drawdown", status, detail))

    baseline_turnover = _metric_float(baseline_metrics, "turnover")
    candidate_turnover = _metric_float(candidate_metrics, "turnover")
    if baseline_turnover is None or candidate_turnover is None:
        status = "fail"
        detail = "Turnover comparison is missing."
    else:
        allowed_turnover = (
            baseline_turnover * PROMOTION_TURNOVER_MULTIPLE
        ) + PROMOTION_TURNOVER_ABSOLUTE_BUFFER
        status = "pass" if candidate_turnover <= allowed_turnover else "fail"
        detail = (
            f"v2A turnover={candidate_turnover:.6f}; allowed={allowed_turnover:.6f} "
            f"from v1={baseline_turnover:.6f}."
        )
    if status != "pass":
        blockers.append(detail)
    checks.append(_gate_check("turnover_control", status, detail))

    baseline_utilization = _nested_metric(
        baseline, "cash_utilization", "average_cash_utilization_pct"
    )
    candidate_utilization = _nested_metric(
        candidate, "cash_utilization", "average_cash_utilization_pct"
    )
    candidate_failures = _nested_metric(
        candidate, "rejected_or_trimmed_candidate_counts", "sizing_failure_count"
    )
    if baseline_utilization is None or candidate_utilization is None:
        status = "fail"
        detail = "Cash utilization comparison is missing."
    elif candidate_failures and candidate_failures > 0:
        status = "fail"
        detail = f"v2A has {candidate_failures:.0f} inferred sizing failures."
    elif candidate_utilization + 0.10 >= baseline_utilization:
        status = "pass"
        detail = (
            f"v2A average cash utilization={candidate_utilization:.6f} is not materially below "
            f"v1={baseline_utilization:.6f}."
        )
    else:
        status = "fail"
        detail = (
            f"v2A average cash utilization={candidate_utilization:.6f} is materially below "
            f"v1={baseline_utilization:.6f}."
        )
    if status != "pass":
        blockers.append(detail)
    checks.append(_gate_check("allocation_utilization", status, detail))
    return checks


def _technical_gate_check(technical_report: Mapping[str, object]) -> dict[str, object]:
    checks = [
        row
        for row in technical_report.get("checks", [])
        if isinstance(row, Mapping)
        and row.get("profile_name") == OHLCV_V2_PROFILE
        and row.get("horizon_days") == 21
    ]
    if not checks:
        return _gate_check(
            "rank_monotonicity",
            "fail",
            "Missing v2A 21d rank evidence.",
        )
    check = checks[0]
    rank_correlation = check.get("rank_correlation")
    spread = check.get("top_bottom_decile_spread")
    if rank_correlation is None or spread is None:
        return _gate_check(
            "rank_monotonicity",
            "fail",
            "v2A 21d rank evidence is not available.",
        )
    if _float(rank_correlation) >= 0 and _float(spread) >= 0:
        return _gate_check(
            "rank_monotonicity",
            "pass",
            f"v2A 21d rank_correlation={_float(rank_correlation):.6f}, top_bottom_spread={_float(spread):.6f}.",
        )
    return _gate_check(
        "rank_monotonicity",
        "fail",
        f"v2A 21d rank_correlation={_float(rank_correlation):.6f}, top_bottom_spread={_float(spread):.6f}.",
    )


def _gate_check(name: str, status: str, detail: str) -> dict[str, object]:
    return {"name": name, "status": status, "detail": detail}


def _metrics(profile: Mapping[str, object]) -> Mapping[str, object]:
    metrics = profile.get("metrics")
    return metrics if isinstance(metrics, Mapping) else {}


def _metric_float(metrics: Mapping[str, object], name: str) -> float | None:
    value = metrics.get(name)
    if value is None:
        return None
    return _float(value)


def _nested_metric(
    mapping: Mapping[str, object],
    group_name: str,
    metric_name: str,
) -> float | None:
    group = mapping.get(group_name)
    if not isinstance(group, Mapping):
        return None
    value = group.get(metric_name)
    if value is None:
        return None
    return _float(value)


def _coverage_decimal(*, available_count: int, total_count: int) -> Decimal:
    if total_count <= 0:
        return Decimal("0")
    return (Decimal(available_count) / Decimal(total_count)).quantize(
        Decimal("0.0001")
    )


def _spearman_rank_correlation(pairs: Sequence[tuple[float, float]]) -> float | None:
    if len(pairs) < 2:
        return None
    x_ranks = _average_ranks([pair[0] for pair in pairs])
    y_ranks = _average_ranks([pair[1] for pair in pairs])
    return _pearson_correlation(x_ranks, y_ranks)


def _average_ranks(values: Sequence[float]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: (item[1], item[0]))
    ranks = [0.0 for _ in values]
    index = 0
    while index < len(ordered):
        end = index + 1
        while end < len(ordered) and ordered[end][1] == ordered[index][1]:
            end += 1
        average_rank = (index + 1 + end) / 2
        for original_index, _value in ordered[index:end]:
            ranks[original_index] = average_rank
        index = end
    return ranks


def _pearson_correlation(x_values: Sequence[float], y_values: Sequence[float]) -> float | None:
    if len(x_values) != len(y_values) or len(x_values) < 2:
        return None
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    numerator = sum(
        (x_value - x_mean) * (y_value - y_mean)
        for x_value, y_value in zip(x_values, y_values, strict=True)
    )
    x_denom = math.sqrt(sum((x_value - x_mean) ** 2 for x_value in x_values))
    y_denom = math.sqrt(sum((y_value - y_mean) ** 2 for y_value in y_values))
    if x_denom == 0 or y_denom == 0:
        return None
    return round(numerator / (x_denom * y_denom), 8)


def _top_bottom_spread(
    observations: Sequence[Mapping[str, object]],
) -> dict[str, float | None]:
    if len(observations) < 2:
        return {"top_mean": None, "bottom_mean": None, "top_bottom_spread": None}
    ordered = sorted(observations, key=lambda row: (_float(row["score"]), str(row["symbol"])))
    bucket_size = max(1, len(ordered) // 10)
    bottom = ordered[:bucket_size]
    top = ordered[-bucket_size:]
    bottom_mean = _mean_float([_float(row["forward_return"]) for row in bottom])
    top_mean = _mean_float([_float(row["forward_return"]) for row in top])
    spread = None
    if bottom_mean is not None and top_mean is not None:
        spread = round(top_mean - bottom_mean, 8)
    return {
        "top_mean": top_mean,
        "bottom_mean": bottom_mean,
        "top_bottom_spread": spread,
    }


def _confidence_hit_rates(
    observations: Sequence[Mapping[str, object]],
) -> dict[str, object]:
    directional = [
        row
        for row in observations
        if row.get("score") is not None
        and _float(row["score"]) != 0
        and row.get("forward_return") is not None
    ]
    if not directional:
        return {
            "hit_rate": None,
            "high_confidence_hit_rate": None,
            "low_confidence_hit_rate": None,
            "high_confidence_count": 0,
            "low_confidence_count": 0,
        }
    ordered = sorted(directional, key=lambda row: (_float(row["confidence"]), str(row["symbol"])))
    split = max(1, len(ordered) // 2)
    low = ordered[:split]
    high = ordered[split:] or ordered[split - 1 :]
    return {
        "hit_rate": _hit_rate(directional),
        "high_confidence_hit_rate": _hit_rate(high),
        "low_confidence_hit_rate": _hit_rate(low),
        "high_confidence_count": len(high),
        "low_confidence_count": len(low),
    }


def _hit_rate(observations: Sequence[Mapping[str, object]]) -> float | None:
    if not observations:
        return None
    hits = 0
    for row in observations:
        score = _float(row["score"])
        forward_return = _float(row["forward_return"])
        if (score > 0 and forward_return > 0) or (score < 0 and forward_return < 0):
            hits += 1
    return round(hits / len(observations), 8)


def _cash_utilization_summary(
    equity_points: Sequence[BacktestEquityPointModel],
) -> dict[str, object]:
    values = []
    for point in equity_points:
        total = Decimal(point.total_equity_inr)
        if total <= 0:
            continue
        values.append(_float(Decimal("1") - (Decimal(point.cash_inr) / total)))
    return {
        "average_cash_utilization_pct": _mean_float(values),
        "min_cash_utilization_pct": min(values) if values else None,
        "max_cash_utilization_pct": max(values) if values else None,
        "point_count": len(values),
    }


def _equity_curve_summary(
    equity_points: Sequence[BacktestEquityPointModel],
) -> dict[str, object]:
    if not equity_points:
        return {
            "point_count": 0,
            "first_equity_inr": None,
            "last_equity_inr": None,
            "min_equity_inr": None,
            "max_equity_inr": None,
            "worst_drawdown": None,
            "tail": [],
        }
    equities = [Decimal(point.total_equity_inr) for point in equity_points]
    return {
        "point_count": len(equity_points),
        "first_equity_inr": str(equities[0]),
        "last_equity_inr": str(equities[-1]),
        "min_equity_inr": str(min(equities)),
        "max_equity_inr": str(max(equities)),
        "worst_drawdown": min(_float(point.drawdown_pct) for point in equity_points),
        "tail": [
            {
                "trade_date": point.trade_date.isoformat(),
                "cash_inr": str(point.cash_inr),
                "holdings_value_inr": str(point.holdings_value_inr),
                "total_equity_inr": str(point.total_equity_inr),
                "drawdown_pct": str(point.drawdown_pct),
            }
            for point in equity_points[-5:]
        ],
    }


def _turnover(
    *,
    fills: Sequence[BacktestFillModel],
    equity_points: Sequence[BacktestEquityPointModel],
) -> float:
    traded_value = sum((Decimal(fill.gross_value_inr) for fill in fills), Decimal("0"))
    equity_values = [Decimal(point.total_equity_inr) for point in equity_points]
    average_equity = (
        sum(equity_values, Decimal("0")) / Decimal(len(equity_values))
        if equity_values
        else Decimal("0")
    )
    if average_equity <= 0:
        return 0.0
    return round(float(traded_value / average_equity), 8)


def _distribution(values: Sequence[float]) -> dict[str, float | int | None]:
    ordered = sorted(value for value in values if value is not None)
    if not ordered:
        return {
            "count": 0,
            "min": None,
            "p25": None,
            "median": None,
            "p75": None,
            "max": None,
            "mean": None,
        }
    return {
        "count": len(ordered),
        "min": ordered[0],
        "p25": _percentile(ordered, 0.25),
        "median": _percentile(ordered, 0.50),
        "p75": _percentile(ordered, 0.75),
        "max": ordered[-1],
        "mean": _mean_float(ordered),
    }


def _percentile(ordered_values: Sequence[float], percentile: float) -> float:
    if len(ordered_values) == 1:
        return ordered_values[0]
    position = percentile * (len(ordered_values) - 1)
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered_values[lower]
    weight = position - lower
    return round(
        ordered_values[lower] * (1 - weight) + ordered_values[upper] * weight,
        8,
    )


def _mean_float(values: Sequence[float | int]) -> float | None:
    if not values:
        return None
    return round(float(sum(values) / len(values)), 8)


def _float(value: object) -> float:
    if isinstance(value, Decimal):
        return float(value)
    return float(str(value))


def _write_comparison_matrix(
    path: Path,
    *,
    profiles: Sequence[ValidationProfile],
    profile_runs: Sequence[Mapping[str, object]],
    technical_report: Mapping[str, object],
    system_report: Mapping[str, object],
    readiness: DataReadiness,
) -> None:
    fieldnames = [
        "profile_name",
        "strategy_name",
        "slice_name",
        "start_date",
        "end_date",
        "symbol_count",
        "trade_count",
        "coverage_pct",
        "rank_ic",
        "top_bottom_spread",
        "hit_rate",
        "total_return",
        "cagr",
        "sharpe",
        "sortino",
        "max_drawdown",
        "turnover",
        "status",
        "notes",
    ]
    runs_by_profile = {
        str(row["profile_name"]): row
        for row in profile_runs
        if isinstance(row, Mapping)
    }
    system_by_profile = {
        str(row["profile_name"]): row
        for row in system_report.get("profiles", [])
        if isinstance(row, Mapping)
    }
    technical_checks = {
        (
            str(row["profile_name"]),
            int(row["horizon_days"]),
        ): row
        for row in technical_report.get("checks", [])
        if isinstance(row, Mapping)
    }
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for profile in profiles:
            run = runs_by_profile.get(profile.profile_name, {})
            system = system_by_profile.get(profile.profile_name, {})
            metrics = _metrics(system)
            technical_profile = _technical_report_profile_name(profile)
            technical_check = technical_checks.get((technical_profile, 21), {})
            status = "pass" if readiness.sufficient and run else "not_applicable"
            writer.writerow(
                {
                    "profile_name": profile.profile_name,
                    "strategy_name": profile.strategy_name,
                    "slice_name": "overall_21d_rank_proxy",
                    "start_date": run.get("start_date", ""),
                    "end_date": run.get("end_date", ""),
                    "symbol_count": len(readiness.artifact["universe"]["symbols"]),
                    "trade_count": _csv_value(metrics.get("trade_count")),
                    "coverage_pct": _csv_value(technical_check.get("coverage_pct")),
                    "rank_ic": _csv_value(technical_check.get("rank_correlation")),
                    "top_bottom_spread": _csv_value(
                        technical_check.get("top_bottom_decile_spread")
                    ),
                    "hit_rate": _csv_value(technical_check.get("hit_rate")),
                    "total_return": _csv_value(metrics.get("total_return")),
                    "cagr": _csv_value(metrics.get("cagr")),
                    "sharpe": _csv_value(metrics.get("sharpe")),
                    "sortino": _csv_value(metrics.get("sortino")),
                    "max_drawdown": _csv_value(metrics.get("max_drawdown")),
                    "turnover": _csv_value(metrics.get("turnover")),
                    "status": status,
                    "notes": ""
                    if status == "pass"
                    else "Backtest profile not run because validation data was insufficient.",
                }
            )


def _write_technical_prediction_checks_csv(
    path: Path,
    technical_report: Mapping[str, object],
) -> None:
    fieldnames = [
        "profile_name",
        "horizon_days",
        "observation_count",
        "rank_correlation",
        "top_decile_mean_return",
        "bottom_decile_mean_return",
        "top_bottom_decile_spread",
        "hit_rate",
        "high_confidence_hit_rate",
        "low_confidence_hit_rate",
        "high_confidence_count",
        "low_confidence_count",
        "coverage_pct",
        "average_missing_feature_count",
        "monotonicity_status",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in technical_report.get("checks", []):
            if isinstance(row, Mapping):
                writer.writerow({name: _csv_value(row.get(name)) for name in fieldnames})


def _write_system_profile_summary_csv(
    path: Path,
    system_report: Mapping[str, object],
) -> None:
    fieldnames = [
        "profile_name",
        "backtest_run_id",
        "start_date",
        "end_date",
        "total_return",
        "cagr",
        "sharpe",
        "sortino",
        "max_drawdown",
        "turnover",
        "win_rate",
        "profit_factor",
        "selected_symbol_count",
        "average_cash_utilization_pct",
        "ranked_candidate_count",
        "eligible_candidate_count",
        "rejected_candidate_count",
        "trimmed_candidate_count",
        "sizing_failure_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in system_report.get("profiles", []):
            if not isinstance(row, Mapping):
                continue
            metrics = _metrics(row)
            selected = row.get("selected_symbol_counts", {})
            cash = row.get("cash_utilization", {})
            scores = row.get("allocation_candidate_score_behavior", {})
            counts = row.get("rejected_or_trimmed_candidate_counts", {})
            writer.writerow(
                {
                    "profile_name": row.get("profile_name"),
                    "backtest_run_id": row.get("backtest_run_id"),
                    "start_date": row.get("start_date"),
                    "end_date": row.get("end_date"),
                    "total_return": _csv_value(metrics.get("total_return")),
                    "cagr": _csv_value(metrics.get("cagr")),
                    "sharpe": _csv_value(metrics.get("sharpe")),
                    "sortino": _csv_value(metrics.get("sortino")),
                    "max_drawdown": _csv_value(metrics.get("max_drawdown")),
                    "turnover": _csv_value(metrics.get("turnover")),
                    "win_rate": _csv_value(metrics.get("win_rate")),
                    "profit_factor": _csv_value(metrics.get("profit_factor")),
                    "selected_symbol_count": _csv_value(
                        selected.get("selected_symbol_count")
                        if isinstance(selected, Mapping)
                        else None
                    ),
                    "average_cash_utilization_pct": _csv_value(
                        cash.get("average_cash_utilization_pct")
                        if isinstance(cash, Mapping)
                        else None
                    ),
                    "ranked_candidate_count": _csv_value(
                        scores.get("ranked_candidate_count")
                        if isinstance(scores, Mapping)
                        else None
                    ),
                    "eligible_candidate_count": _csv_value(
                        scores.get("eligible_candidate_count")
                        if isinstance(scores, Mapping)
                        else None
                    ),
                    "rejected_candidate_count": _csv_value(
                        counts.get("rejected_candidate_count")
                        if isinstance(counts, Mapping)
                        else None
                    ),
                    "trimmed_candidate_count": _csv_value(
                        counts.get("trimmed_candidate_count")
                        if isinstance(counts, Mapping)
                        else None
                    ),
                    "sizing_failure_count": _csv_value(
                        counts.get("sizing_failure_count")
                        if isinstance(counts, Mapping)
                        else None
                    ),
                }
            )


def _operator_report_markdown(
    *,
    run_id: str,
    artifact_dir: Path,
    manifest_status: str,
    technical_report: Mapping[str, object],
    system_report: Mapping[str, object],
    promotion_gate: Mapping[str, object],
) -> str:
    blocking_reason_lines = [
        f"- {reason}" for reason in promotion_gate.get("blocking_reasons", [])
    ] or ["- None"]
    lines = [
        f"# Technical Validation Report - {run_id}",
        "",
        "## Summary",
        "",
        f"- Validation status: `{manifest_status}`",
        f"- Recommendation: `{promotion_gate['decision']}`",
        f"- Artifact directory: `{artifact_dir}`",
        f"- Technical evidence status: `{technical_report['status']}`",
        f"- Full-system evidence status: `{system_report['status']}`",
        "",
        "## Promotion Gate",
        "",
        _markdown_table(
            ["Check", "Status", "Detail"],
            [
                [str(row["name"]), str(row["status"]), str(row["detail"])]
                for row in promotion_gate.get("checks", [])
                if isinstance(row, Mapping)
            ],
        ),
        "",
        "Blocking reasons:",
        "",
        *blocking_reason_lines,
        "",
        "## Technical-Agent Evidence",
        "",
        _technical_report_markdown(technical_report, include_title=False),
        "",
        "## Full-System Evidence",
        "",
        _system_report_markdown(system_report, include_title=False),
        "",
        "## Machine-Readable Artifacts",
        "",
        "- `validation_manifest.json`",
        "- `data_readiness.json`",
        "- `technical_agent_predictive_report.json`",
        "- `technical_agent_prediction_checks.csv`",
        "- `system_backtest_report.json`",
        "- `system_backtest_profile_summary.csv`",
        "- `profile_comparison_matrix.csv`",
        "- `promotion_gate.json`",
        "",
        "Validation report only: this command does not promote v2B or change canonical v1 defaults.",
        "",
    ]
    return "\n".join(lines)


def _technical_report_markdown(
    technical_report: Mapping[str, object],
    *,
    include_title: bool = True,
) -> str:
    lines: list[str] = []
    if include_title:
        lines.extend(["# Technical-Agent Predictive Report", ""])
    lines.extend(
        [
            f"Status: `{technical_report['status']}`",
            "",
            "Prediction label: close-to-close forward return at 5d, 21d, and 63d horizons.",
            "",
            "### Horizon Checks",
            "",
            _markdown_table(
                [
                    "Profile",
                    "Horizon",
                    "Obs",
                    "Rank IC",
                    "Top-Bottom",
                    "Hit Rate",
                    "High Conf Hit",
                    "Coverage",
                    "Status",
                ],
                [
                    [
                        str(row["profile_name"]),
                        str(row["horizon_days"]),
                        str(row["observation_count"]),
                        _fmt(row.get("rank_correlation")),
                        _fmt(row.get("top_bottom_decile_spread")),
                        _fmt(row.get("hit_rate")),
                        _fmt(row.get("high_confidence_hit_rate")),
                        _fmt(row.get("coverage_pct")),
                        str(row["monotonicity_status"]),
                    ]
                    for row in technical_report.get("checks", [])
                    if isinstance(row, Mapping)
                ],
            ),
            "",
            "### Explanation Quality",
            "",
            _markdown_table(
                [
                    "Profile",
                    "Obs",
                    "Score Median",
                    "Confidence Median",
                    "Coverage",
                    "Avg Missing",
                    "Vector Presence",
                    "Avg Contributors",
                ],
                [
                    [
                        str(row["profile_name"]),
                        str(row["observation_count"]),
                        _fmt(_distribution_value(row, "score_distribution", "median")),
                        _fmt(
                            _distribution_value(
                                row,
                                "confidence_distribution",
                                "median",
                            )
                        ),
                        _fmt(row.get("coverage_pct")),
                        _fmt(row.get("average_missing_feature_count")),
                        _fmt(
                            _nested_metric(
                                row,
                                "explanation_quality",
                                "vector_presence_pct",
                            )
                        ),
                        _fmt(
                            _nested_metric(
                                row,
                                "explanation_quality",
                                "average_contributor_count",
                            )
                        ),
                    ]
                    for row in technical_report.get("profiles", [])
                    if isinstance(row, Mapping)
                ],
            ),
        ]
    )
    notes = technical_report.get("notes", [])
    if notes:
        lines.extend(["", "Notes:", ""])
        lines.extend(f"- {note}" for note in notes)
    lines.append("")
    return "\n".join(lines)


def _system_report_markdown(
    system_report: Mapping[str, object],
    *,
    include_title: bool = True,
) -> str:
    lines: list[str] = []
    if include_title:
        lines.extend(["# Full-System Backtest Report", ""])
    lines.extend(
        [
            f"Status: `{system_report['status']}`",
            "",
            "### Profile Metrics",
            "",
            _markdown_table(
                [
                    "Profile",
                    "Return",
                    "CAGR",
                    "Sharpe",
                    "Sortino",
                    "Max DD",
                    "Turnover",
                    "Win Rate",
                    "Profit Factor",
                    "Selected",
                    "Cash Util",
                    "Rejected",
                    "Trimmed",
                    "Sizing Fail",
                ],
                [
                    _system_markdown_row(row)
                    for row in system_report.get("profiles", [])
                    if isinstance(row, Mapping)
                ],
            ),
            "",
            "### Equity Curve Summary",
            "",
            _markdown_table(
                ["Profile", "Points", "First", "Last", "Min", "Max", "Worst DD"],
                [
                    [
                        str(row["profile_name"]),
                        str(
                            _nested_raw(
                                row,
                                "equity_curve_summary",
                                "point_count",
                            )
                        ),
                        str(
                            _nested_raw(
                                row,
                                "equity_curve_summary",
                                "first_equity_inr",
                            )
                        ),
                        str(
                            _nested_raw(
                                row,
                                "equity_curve_summary",
                                "last_equity_inr",
                            )
                        ),
                        str(
                            _nested_raw(
                                row,
                                "equity_curve_summary",
                                "min_equity_inr",
                            )
                        ),
                        str(
                            _nested_raw(
                                row,
                                "equity_curve_summary",
                                "max_equity_inr",
                            )
                        ),
                        _fmt(
                            _nested_metric(
                                row,
                                "equity_curve_summary",
                                "worst_drawdown",
                            )
                        ),
                    ]
                    for row in system_report.get("profiles", [])
                    if isinstance(row, Mapping)
                ],
            ),
        ]
    )
    notes = system_report.get("notes", [])
    if notes:
        lines.extend(["", "Notes:", ""])
        lines.extend(f"- {note}" for note in notes)
    lines.append("")
    return "\n".join(lines)


def _system_markdown_row(row: Mapping[str, object]) -> list[str]:
    metrics = _metrics(row)
    return [
        str(row["profile_name"]),
        _fmt(metrics.get("total_return")),
        _fmt(metrics.get("cagr")),
        _fmt(metrics.get("sharpe")),
        _fmt(metrics.get("sortino")),
        _fmt(metrics.get("max_drawdown")),
        _fmt(metrics.get("turnover")),
        _fmt(metrics.get("win_rate")),
        _fmt(metrics.get("profit_factor")),
        str(_nested_raw(row, "selected_symbol_counts", "selected_symbol_count")),
        _fmt(_nested_metric(row, "cash_utilization", "average_cash_utilization_pct")),
        str(
            _nested_raw(
                row,
                "rejected_or_trimmed_candidate_counts",
                "rejected_candidate_count",
            )
        ),
        str(
            _nested_raw(
                row,
                "rejected_or_trimmed_candidate_counts",
                "trimmed_candidate_count",
            )
        ),
        str(
            _nested_raw(
                row,
                "rejected_or_trimmed_candidate_counts",
                "sizing_failure_count",
            )
        ),
    ]


def _markdown_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    if not rows:
        rows = [["n/a" for _header in headers]]
    header = "| " + " | ".join(headers) + " |"
    separator = "| " + " | ".join("---" for _header in headers) + " |"
    body = [
        "| " + " | ".join(_escape_table_cell(value) for value in row) + " |"
        for row in rows
    ]
    return "\n".join([header, separator, *body])


def _escape_table_cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _fmt(value: object) -> str:
    if value is None:
        return "n/a"
    try:
        return f"{_float(value):.6f}"
    except (TypeError, ValueError):
        return str(value)


def _distribution_value(
    row: Mapping[str, object],
    group_name: str,
    metric_name: str,
) -> object | None:
    group = row.get(group_name)
    if not isinstance(group, Mapping):
        return None
    return group.get(metric_name)


def _nested_raw(
    mapping: Mapping[str, object],
    group_name: str,
    metric_name: str,
) -> object | None:
    group = mapping.get(group_name)
    if not isinstance(group, Mapping):
        return None
    return group.get(metric_name)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(_json_safe(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _stable_validation_run_id(
    *,
    request: ValidationRequest,
    readiness: DataReadiness,
    profiles: Sequence[ValidationProfile],
) -> str:
    payload = {
        "artifact_version": ARTIFACT_VERSION,
        "symbols": request.symbols,
        "universe_source": request.universe_source,
        "universe_path": request.universe_path,
        "mode": request.mode,
        "validation_years": request.validation_years,
        "evaluation_days": request.evaluation_days,
        "warmup_days": request.warmup_days,
        "timeframe": request.timeframe,
        "initial_capital_inr": str(request.initial_capital_inr),
        "max_open_positions": request.max_open_positions,
        "portfolio_breadth": request.portfolio_breadth,
        "rebalance_every_days": request.rebalance_every_days,
        "cost_bps": str(request.cost_bps),
        "slippage_bps": str(request.slippage_bps),
        "include_v2b": request.include_v2b,
        "readiness_status": readiness.status,
        "common_start_date": readiness.common_dates[0].isoformat()
        if readiness.common_dates
        else None,
        "common_end_date": readiness.common_dates[-1].isoformat()
        if readiness.common_dates
        else None,
        "common_date_count": len(readiness.common_dates),
        "selected_start_date": readiness.selected_dates[0].isoformat()
        if readiness.selected_dates
        else None,
        "selected_end_date": readiness.selected_dates[-1].isoformat()
        if readiness.selected_dates
        else None,
        "profiles": [
            {
                "profile_name": profile.profile_name,
                "strategy_name": profile.strategy_name,
                "strategy_config_path": profile.strategy_config_path,
                "strategy_parameters": dict(profile.strategy_parameters),
            }
            for profile in profiles
        ],
    }
    digest = hashlib.sha256(
        json.dumps(_json_safe(payload), sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"techval-{digest[:16]}"


def _without_graph_contribution(
    parameters: Mapping[str, object],
) -> dict[str, object]:
    updated = dict(parameters)
    updated["graph_weight"] = "0"
    updated["require_graph_signal"] = False
    return updated


def _official_benchmark_index_symbol(parameters: Mapping[str, object]) -> str:
    return _official_string_parameter(
        parameters,
        "official_benchmark_index_symbol",
        default="NIFTY_50",
    )


def _official_volatility_index_symbol(parameters: Mapping[str, object]) -> str:
    return _official_string_parameter(
        parameters,
        "official_volatility_index_symbol",
        default="INDIA_VIX",
    )


def _official_index_timeframe(parameters: Mapping[str, object]) -> str:
    return _official_string_parameter(
        parameters,
        "official_index_timeframe",
        default="1d",
        uppercase=False,
    )


def _official_microstructure_timeframe(parameters: Mapping[str, object]) -> str:
    return _official_string_parameter(
        parameters,
        "official_microstructure_timeframe",
        default="1d",
        uppercase=False,
    )


def _official_sector_index_by_symbol(parameters: Mapping[str, object]) -> dict[str, str]:
    nested = parameters.get("official_data")
    value: object | None = None
    if isinstance(nested, Mapping):
        value = nested.get("sector_index_by_symbol")
    if value is None:
        value = parameters.get("official_sector_index_by_symbol")
    if not isinstance(value, Mapping):
        return {}
    return {
        str(symbol).upper(): str(index_symbol).upper()
        for symbol, index_symbol in value.items()
        if str(symbol).strip() and str(index_symbol).strip()
    }


def _official_string_parameter(
    parameters: Mapping[str, object],
    key: str,
    *,
    default: str,
    uppercase: bool = True,
) -> str:
    nested = parameters.get("official_data")
    value = nested.get(key.replace("official_", "")) if isinstance(nested, Mapping) else None
    if not value:
        value = parameters.get(key)
    if isinstance(value, str) and value.strip():
        cleaned = value.strip()
        return cleaned.upper() if uppercase else cleaned
    return default


def _insufficient_data_actions(
    request: ValidationRequest,
    missing_common_candle_count: int,
) -> list[str]:
    import_days = _calendar_days_for_trading_days(request.required_candle_count)
    return [
        (
            "Import deeper local Kite history, then rerun validation: "
            f"TAURUS_MARKET_DATA_LOOKBACK_DAYS={import_days} make import-kite-candles"
        ),
        (
            "For a smaller readiness slice, rerun with "
            "TECHNICAL_VALIDATION_SYMBOLS=INFY,TCS make validate-technical-v2"
        ),
        (
            "Missing common candles across the requested universe: "
            f"{missing_common_candle_count}"
        ),
    ]


def _calendar_days_for_trading_days(trading_days: int) -> int:
    return (
        int(
            (
                Decimal(trading_days) * Decimal("7") / Decimal("5")
            ).to_integral_value()
        )
        + 21
    )


def _normalize_symbols(raw_symbols: Sequence[str]) -> tuple[str, ...]:
    normalized = sorted(
        {symbol.strip().upper() for symbol in raw_symbols if symbol.strip()}
    )
    return tuple(normalized)


def _json_safe(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


def _csv_value(value: object) -> object:
    if isinstance(value, Decimal):
        return str(value)
    if value is None:
        return ""
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(_json_safe(value), sort_keys=True)
    return value


def _git_commit() -> str:
    repo_root = Path(__file__).resolve().parents[1]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return result.stdout.strip() or "unknown"


def _bool_env(name: str) -> bool:
    raw = os.environ.get(name, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate local daily_candles readiness and run comparable "
            "technical v1/v2 backtest profiles when coverage is sufficient."
        )
    )
    parser.add_argument(
        "--mode",
        choices=("standard", "strong"),
        default=os.environ.get("TECHNICAL_VALIDATION_MODE", "standard"),
        help="standard uses a 3-year evaluation window; strong uses 5 years.",
    )
    parser.add_argument(
        "--symbols",
        default=os.environ.get("TECHNICAL_VALIDATION_SYMBOLS", ""),
        help="Comma-separated validation symbols. Overrides --universe.",
    )
    parser.add_argument(
        "--universe",
        default=os.environ.get("TECHNICAL_VALIDATION_UNIVERSE", ""),
        help="Market-data universe YAML path. Defaults to Taurus target/market universe settings.",
    )
    parser.add_argument(
        "--artifact-root",
        default=os.environ.get(
            "TECHNICAL_VALIDATION_ARTIFACT_ROOT",
            "artifacts/technical_validation",
        ),
        help="Root directory for validation artifacts.",
    )
    parser.add_argument(
        "--report-root",
        default=os.environ.get(
            "TECHNICAL_VALIDATION_REPORT_ROOT",
            "docs/reports/technical_validation",
        ),
        help="Root directory for operator-readable Markdown validation reports.",
    )
    parser.add_argument(
        "--initial-capital-inr",
        default=os.environ.get("TECHNICAL_VALIDATION_INITIAL_CAPITAL_INR", ""),
        help="Initial NAV for every compared profile.",
    )
    parser.add_argument(
        "--max-open-positions",
        type=int,
        default=int(os.environ["TECHNICAL_VALIDATION_MAX_OPEN_POSITIONS"])
        if os.environ.get("TECHNICAL_VALIDATION_MAX_OPEN_POSITIONS")
        else None,
        help="Shared max open positions for every compared profile.",
    )
    parser.add_argument(
        "--portfolio-breadth",
        type=int,
        default=int(os.environ["TECHNICAL_VALIDATION_PORTFOLIO_BREADTH"])
        if os.environ.get("TECHNICAL_VALIDATION_PORTFOLIO_BREADTH")
        else None,
        help="Shared target portfolio breadth for every compared profile.",
    )
    parser.add_argument(
        "--rebalance-every-days",
        type=int,
        default=int(os.environ.get("TECHNICAL_VALIDATION_REBALANCE_EVERY_DAYS", "21")),
        help="Shared rebalance cadence for every compared profile.",
    )
    parser.add_argument(
        "--cost-bps",
        default=os.environ.get("TECHNICAL_VALIDATION_COST_BPS", ""),
        help="Shared transaction cost in basis points.",
    )
    parser.add_argument(
        "--slippage-bps",
        default=os.environ.get("TECHNICAL_VALIDATION_SLIPPAGE_BPS", ""),
        help="Shared slippage in basis points.",
    )
    parser.add_argument(
        "--strict-insufficient-data",
        action="store_true",
        default=_bool_env("TECHNICAL_VALIDATION_STRICT_INSUFFICIENT"),
        help="Exit non-zero when coverage is insufficient.",
    )
    parser.add_argument(
        "--include-v2b",
        action="store_true",
        default=_bool_env("TECHNICAL_VALIDATION_INCLUDE_V2B"),
        help=(
            "Include graph_aware_score_v2b and v2B technical-only profiles. "
            "Defaults off until official index and microstructure data are ready."
        ),
    )
    return parser.parse_args(argv)


def _print_outcome(outcome: ValidationOutcome) -> None:
    manifest = outcome.manifest
    print(f"validation_run_id={outcome.run_id}")
    print(f"artifact_dir={outcome.artifact_dir}")
    if outcome.report_path is not None:
        print(f"report_path={outcome.report_path}")
    print(f"status={outcome.status}")
    if outcome.promotion_decision is not None:
        print(f"promotion_decision={outcome.promotion_decision}")
    window = manifest.get("window")
    if isinstance(window, Mapping):
        print(
            "window="
            f"{window.get('selected_scoring_start_date') or 'n/a'}.."
            f"{window.get('selected_evaluation_end_date') or 'n/a'} "
            f"common_candles={window.get('common_candle_count')}"
        )
    for profile_run in manifest.get("profile_runs", []):
        if isinstance(profile_run, Mapping):
            print(
                "profile="
                f"{profile_run.get('profile_name')} "
                f"backtest_run_id={profile_run.get('backtest_run_id')}"
            )
    print("artifacts:")
    for path_name in (
        "technical_agent_predictive_report_path",
        "system_backtest_report_path",
        "profile_comparison_matrix_path",
        "promotion_gate_path",
    ):
        print(f"- {path_name}={manifest.get(path_name)}")
    next_actions = manifest.get("next_actions")
    if isinstance(next_actions, list) and next_actions:
        print("next_actions:")
        for action in next_actions:
            print(f"- {action}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    request = request_from_args(args, settings=settings)
    with create_progress_reporter("validate-technical-v2") as progress:
        outcome = run_validation(settings=settings, request=request, progress=progress)
    _print_outcome(outcome)
    if outcome.status != "complete" and request.strict_insufficient_data:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
