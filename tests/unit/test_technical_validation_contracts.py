from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from scripts.validate_technical_v2 import (
    DataReadiness,
    _closed_trade_economics_summary,
    _write_comparison_matrix,
    _write_system_profile_summary_csv,
    _write_technical_prediction_checks_csv,
    validation_profiles,
)
from taurus_core.db.models import BacktestFillModel, BacktestPositionModel


def test_validation_profiles_pin_current_v1_and_v2a_contract() -> None:
    profiles = validation_profiles()
    profile_by_name = {profile.profile_name: profile for profile in profiles}

    assert tuple(profile_by_name) == (
        "graph_aware_score_v1",
        "graph_aware_score_v1_technical_only",
        "graph_aware_score_v2",
        "graph_aware_score_v2_technical_only",
    )
    assert all("v2b" not in profile.profile_name for profile in profiles)
    assert profile_by_name["graph_aware_score_v1"].graph_contribution_enabled is True
    assert (
        profile_by_name["graph_aware_score_v1"].strategy_config_path
        == "configs/strategies/graph_aware_score_v1.yaml"
    )
    assert (
        profile_by_name[
            "graph_aware_score_v1_technical_only"
        ].graph_contribution_enabled
        is False
    )
    assert (
        profile_by_name[
            "graph_aware_score_v1_technical_only"
        ].strategy_parameters["graph_weight"]
        == "0"
    )
    assert profile_by_name["graph_aware_score_v2"].graph_contribution_enabled is True
    assert (
        profile_by_name["graph_aware_score_v2"].strategy_config_path
        == "configs/strategies/graph_aware_score_v2.yaml"
    )
    assert profile_by_name["graph_aware_score_v2"].strategy_parameters[
        "technical_profile"
    ] == "technical_ohlcv_v2"
    assert profile_by_name["graph_aware_score_v2"].strategy_parameters[
        "technical_feature_version"
    ] == "technical_ohlcv_v2"
    assert (
        profile_by_name[
            "graph_aware_score_v2_technical_only"
        ].graph_contribution_enabled
        is False
    )
    assert (
        profile_by_name[
            "graph_aware_score_v2_technical_only"
        ].strategy_parameters["graph_weight"]
        == "0"
    )


def test_validation_summary_csv_headers_are_stable(tmp_path: Path) -> None:
    readiness = DataReadiness(
        status="insufficient_data",
        common_dates=(),
        selected_dates=(),
        coverage_rows=(),
        artifact={"universe": {"symbols": ["INFY", "TCS"]}},
    )
    comparison_path = tmp_path / "profile_comparison_matrix.csv"
    prediction_path = tmp_path / "technical_agent_prediction_checks.csv"
    system_path = tmp_path / "system_backtest_profile_summary.csv"

    _write_comparison_matrix(
        comparison_path,
        profiles=validation_profiles(),
        profile_runs=(),
        technical_report={"checks": []},
        system_report={"profiles": []},
        readiness=readiness,
    )
    _write_technical_prediction_checks_csv(prediction_path, {"checks": []})
    _write_system_profile_summary_csv(system_path, {"profiles": []})

    assert _csv_header(comparison_path) == [
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
    assert _csv_header(prediction_path) == [
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
    assert _csv_header(system_path) == [
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
        "realized_pnl_inr",
        "unrealized_pnl_inr",
        "closed_trade_count",
        "closed_win_count",
        "closed_loss_count",
        "gross_profit_inr",
        "gross_loss_inr",
        "average_closed_win_inr",
        "average_closed_loss_inr",
        "selected_symbol_count",
        "average_cash_utilization_pct",
        "ranked_candidate_count",
        "eligible_candidate_count",
        "rejected_candidate_count",
        "trimmed_candidate_count",
        "sizing_failure_count",
    ]


def test_closed_trade_economics_summary_reconstructs_fill_pnl() -> None:
    fills = [
        _fill("INFY", "BUY", 10, "1000.0000", "10.0000"),
        _fill("INFY", "SELL", 10, "1200.0000", "12.0000"),
        _fill("TCS", "BUY", 10, "1000.0000", "10.0000"),
        _fill("TCS", "SELL", 10, "900.0000", "9.0000"),
    ]
    positions = [
        BacktestPositionModel(
            run_id="run-1",
            symbol="INFY",
            quantity=0,
            average_cost_inr=Decimal("0"),
            market_value_inr=Decimal("0"),
            realized_pnl_inr=Decimal("178.0000"),
            unrealized_pnl_inr=Decimal("0.0000"),
        ),
        BacktestPositionModel(
            run_id="run-1",
            symbol="OPEN",
            quantity=1,
            average_cost_inr=Decimal("100.0000"),
            market_value_inr=Decimal("125.2500"),
            realized_pnl_inr=Decimal("0.0000"),
            unrealized_pnl_inr=Decimal("25.2500"),
        ),
    ]

    summary = _closed_trade_economics_summary(fills=fills, positions=positions)

    assert summary == {
        "realized_pnl_inr": "59.0000",
        "unrealized_pnl_inr": "25.2500",
        "closed_trade_count": 2,
        "closed_win_count": 1,
        "closed_loss_count": 1,
        "gross_profit_inr": "178.0000",
        "gross_loss_inr": "119.0000",
        "average_closed_win_inr": "178.0000",
        "average_closed_loss_inr": "119.0000",
    }


def _csv_header(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8").splitlines()[0].split(",")


def _fill(
    symbol: str,
    side: str,
    quantity: int,
    gross_value: str,
    cost: str,
) -> BacktestFillModel:
    return BacktestFillModel(
        order_id=1,
        run_id="run-1",
        trade_date=date(2026, 1, 1),
        symbol=symbol,
        side=side,
        quantity=quantity,
        fill_price_inr=Decimal(gross_value) / Decimal(quantity),
        gross_value_inr=Decimal(gross_value),
        cost_inr=Decimal(cost),
        slippage_bps=Decimal("5"),
    )
