from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from scripts.migrate import run_migrations
from taurus_core.backtesting import BacktestConfig, BacktestEngine
from taurus_core.config import Settings, get_settings
from taurus_core.data.universe import load_market_data_universe
from taurus_core.db.repositories import (
    BacktestRepository,
    CandleRepository,
    InstrumentRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.strategies import load_strategy_config

ARTIFACT_VERSION = "technical_validation_v1"
TRADING_DAYS_PER_YEAR = 252
DEFAULT_WARMUP_DAYS = 252
STANDARD_VALIDATION_YEARS = 3
STRONG_VALIDATION_YEARS = 5
V1_STRATEGY_PATH = Path("configs/strategies/graph_aware_score_v1.yaml")
V2_STRATEGY_PATH = Path("configs/strategies/graph_aware_score_v2.yaml")
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


def run_validation(
    *,
    settings: Settings,
    request: ValidationRequest,
) -> ValidationOutcome:
    if not request.symbols:
        raise ValueError("Validation requires at least one symbol.")

    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        readiness = build_data_readiness(session, request)

    profiles = validation_profiles()
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
        for profile in profiles:
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
        _write_json(artifact_dir / "profile_runs.json", profile_runs)
        _write_comparison_matrix(
            artifact_dir / "profile_comparison_matrix.csv",
            profile_runs,
        )
        status = "complete"
    else:
        status = "insufficient_data"

    manifest = _manifest(
        request=request,
        readiness=readiness,
        profiles=profiles,
        profile_runs=profile_runs,
        run_id=run_id,
        status=status,
    )
    _write_json(artifact_dir / "validation_manifest.json", manifest)
    return ValidationOutcome(
        run_id=run_id,
        artifact_dir=artifact_dir,
        status=status,
        manifest=manifest,
    )


def build_data_readiness(
    session: Session,
    request: ValidationRequest,
) -> DataReadiness:
    instrument_repo = InstrumentRepository(session)
    candle_repo = CandleRepository(session)
    date_sets: list[set[date]] = []
    coverage_rows: list[dict[str, object]] = []

    for symbol in request.symbols:
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
    return DataReadiness(
        status=status,
        common_dates=common_dates,
        selected_dates=selected_dates,
        coverage_rows=tuple(coverage_rows),
        artifact=artifact,
    )


def validation_profiles() -> tuple[ValidationProfile, ...]:
    v1 = load_strategy_config(V1_STRATEGY_PATH)
    v2 = load_strategy_config(V2_STRATEGY_PATH)
    return (
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
    )


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


def _manifest(
    *,
    request: ValidationRequest,
    readiness: DataReadiness,
    profiles: Sequence[ValidationProfile],
    profile_runs: Sequence[Mapping[str, object]],
    run_id: str,
    status: str,
) -> dict[str, object]:
    return {
        "artifact_version": ARTIFACT_VERSION,
        "run_id": run_id,
        "status": status,
        "code_commit": _git_commit(),
        "data_readiness_path": "data_readiness.json",
        "profile_runs_path": "profile_runs.json" if profile_runs else None,
        "profile_comparison_matrix_path": "profile_comparison_matrix.csv"
        if profile_runs
        else None,
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


def _write_comparison_matrix(
    path: Path,
    profile_runs: Sequence[Mapping[str, object]],
) -> None:
    fieldnames = [
        "profile_name",
        "backtest_run_id",
        "start_date",
        "end_date",
        "graph_contribution_enabled",
        *COMPARISON_METRICS,
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in profile_runs:
            metrics = row.get("metrics")
            if not isinstance(metrics, Mapping):
                metrics = {}
            writer.writerow(
                {
                    "profile_name": row["profile_name"],
                    "backtest_run_id": row["backtest_run_id"],
                    "start_date": row["start_date"],
                    "end_date": row["end_date"],
                    "graph_contribution_enabled": row[
                        "graph_contribution_enabled"
                    ],
                    **{
                        name: _csv_value(metrics.get(name))
                        for name in COMPARISON_METRICS
                    },
                }
            )


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
    return parser.parse_args(argv)


def _print_outcome(outcome: ValidationOutcome) -> None:
    manifest = outcome.manifest
    print(f"validation_run_id={outcome.run_id}")
    print(f"artifact_dir={outcome.artifact_dir}")
    print(f"status={outcome.status}")
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
    next_actions = manifest.get("next_actions")
    if isinstance(next_actions, list) and next_actions:
        print("next_actions:")
        for action in next_actions:
            print(f"- {action}")


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    settings = get_settings()
    request = request_from_args(args, settings=settings)
    outcome = run_validation(settings=settings, request=request)
    _print_outcome(outcome)
    if outcome.status != "complete" and request.strict_insufficient_data:
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
