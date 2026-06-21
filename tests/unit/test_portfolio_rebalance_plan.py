from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from taurus_core.domain.market_data import DailyCandle
from taurus_core.portfolio import (
    ActiveAllocationPosition,
    MoneyManagementPolicy,
    PortfolioRebalancePlan,
    PortfolioRebalancePlanInput,
    PortfolioRebalancePlanService,
    SleeveAllocationSnapshot,
)
from taurus_core.research.schemas import TraderProposal


def test_portfolio_rebalance_plan_serializes_deterministically_and_preserves_inputs() -> None:
    policy = _policy()
    buy = _proposal(
        symbol="INFY",
        action="BUY",
        target_pct=Decimal("5.0000"),
        current_pct=Decimal("0.0000"),
        current_quantity=0,
    )
    exit_position = _proposal(
        symbol="TCS",
        action="EXIT",
        target_pct=Decimal("0.0000"),
        current_pct=Decimal("4.0000"),
        current_quantity=10,
    )
    original_payloads = [buy.model_dump(mode="json"), exit_position.model_dump(mode="json")]

    plan = PortfolioRebalancePlanService().build(
        PortfolioRebalancePlanInput(
            run_id="pr-plan-test",
            portfolio_id="local-paper",
            as_of=datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc),
            strategy_name="graph_aware_score_v1",
            proposals=(buy, exit_position),
            nav_inr=Decimal("100000.00"),
            current_cash_inr=Decimal("60000.00"),
            current_positions=(
                ActiveAllocationPosition(
                    symbol="TCS",
                    quantity=10,
                    market_value_inr=Decimal("4000.00"),
                ),
            ),
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="core_shariah",
                    starting_nav_estimate_inr=Decimal("40000.00"),
                    current_exposure_inr=Decimal("4000.00"),
                    open_position_count=1,
                    open_trade_risk_inr=Decimal("240.00"),
                ),
                SleeveAllocationSnapshot(
                    sleeve_id="active_strategy",
                    starting_nav_estimate_inr=Decimal("55000.00"),
                    current_exposure_inr=Decimal("0.00"),
                    open_position_count=0,
                    open_trade_risk_inr=Decimal("0.00"),
                ),
                SleeveAllocationSnapshot(
                    sleeve_id="cash_buffer",
                    starting_nav_estimate_inr=Decimal("5000.00"),
                    current_exposure_inr=Decimal("0.00"),
                    open_position_count=0,
                    open_trade_risk_inr=Decimal("0.00"),
                ),
            ),
            histories_by_symbol={
                "INFY": tuple(_candles("INFY", Decimal("100.00"))),
                "TCS": tuple(_candles("TCS", Decimal("400.00"))),
            },
            core_basket_artifact={
                "target_weights": {"INFY": "3.0000", "TCS": "0.0000"},
                "decisions": [
                    {
                        "symbol": "INFY",
                        "strategy_name": "core_shariah_basket_v1",
                        "sleeve_id": "core_shariah",
                        "side": "BUY",
                        "status": "approved",
                        "target_weight_pct_nav": "3.0000",
                        "current_weight_pct_nav": "0.0000",
                        "drift_pct_nav": "3.0000",
                        "trade_notional_inr": "3000.00",
                        "rationale": ["core_rebalance_trade_generated"],
                    }
                ],
            },
            core_basket_symbols=("INFY",),
            strategy_rank_by_symbol={"INFY": 1, "TCS": 2},
            strategy_score_by_symbol={
                "INFY": Decimal("0.2500"),
                "TCS": Decimal("-0.1000"),
            },
            money_management_policy=policy,
            sleeve_by_symbol={"TCS": "core_shariah"},
        )
    )

    artifact = plan.to_artifact()
    restored = PortfolioRebalancePlan.model_validate(artifact)

    assert restored.to_artifact() == artifact
    assert artifact["model_version"] == "portfolio_rebalance_dry_run_v1"
    assert artifact["policy_version"] == "plan_test_policy"
    assert artifact["hard_cash_reserve_inr"] == "5000.00"
    assert artifact["spendable_cash_after_reserve_inr"] == "55000.00"
    assert artifact["positions"][0]["sleeve_id"] == "core_shariah"
    assert artifact["positions"][0]["sleeve_label_source"] == "core_basket_target_weights"
    assert artifact["candidates"][0]["raw_strategy_score"] == "0.2500"
    assert artifact["candidates"][0]["calibrated_strategy_score"] == "85.0000"
    assert artifact["candidates"][0]["allocation_score_component"] == "85.0000"

    trades_by_id = {row["trade_id"]: row for row in artifact["planned_trades"]}
    assert trades_by_id["trade-tp-infy"]["side"] == "BUY"
    assert trades_by_id["trade-tp-infy"]["estimated_quantity"] == 50
    assert trades_by_id["trade-tp-tcs"]["side"] == "SELL"
    assert trades_by_id["trade-tp-tcs"]["estimated_quantity"] == 10
    assert trades_by_id["core-advisory-INFY"]["source"] == "core_shariah_basket_v1"
    assert trades_by_id["core-advisory-INFY"]["status"] == "advisory_only"

    cash_budget = {row["row_id"]: row for row in artifact["cash_budget"]}
    assert cash_budget["forecast_sell_proceeds"]["amount_inr"] == "4000.00"
    assert cash_budget["spendable_same_run_proceeds"]["amount_inr"] == "3200.00"
    assert cash_budget["unallocated_cash"]["amount_inr"] == "50200.00"

    sleeve_budgets = {row["sleeve_id"]: row for row in artifact["sleeve_budgets"]}
    assert sleeve_budgets["active_strategy"]["projected_exposure_inr"] == "5000.00"
    assert sleeve_budgets["core_shariah"]["projected_exposure_inr"] == "3000.00"
    assert [buy.model_dump(mode="json"), exit_position.model_dump(mode="json")] == original_payloads
    assert buy.allocation_decision is None
    assert exit_position.allocation_decision is None


def _policy() -> MoneyManagementPolicy:
    return MoneyManagementPolicy.model_validate(
        {
            "policy_version": "plan_test_policy",
            "shariah_universe_path": "configs/market_data/nifty_500_shariah.yaml",
            "sleeves": [
                {
                    "sleeve_id": "core_shariah",
                    "name": "Core",
                    "target_weight_pct": "40.0",
                    "role": "Core sleeve",
                },
                {
                    "sleeve_id": "active_strategy",
                    "name": "Active",
                    "target_weight_pct": "55.0",
                    "role": "Active sleeve",
                },
                {
                    "sleeve_id": "cash_buffer",
                    "name": "Cash",
                    "target_weight_pct": "5.0",
                    "role": "Cash buffer",
                },
            ],
            "strategy_mappings": [
                {
                    "strategy_name": "graph_aware_score_v1",
                    "sleeve_id": "active_strategy",
                }
            ],
            "limits": {
                "max_stock_pct_nav": "7.5",
                "max_stock_hard_cap_pct_nav": "7.5",
                "max_sector_pct_nav": "25.0",
                "max_graph_cluster_pct_nav": "35.0",
                "max_open_positions": 20,
            },
            "trade_risk": {
                "normal_trade_risk_pct_nav": "0.50",
                "strong_trade_risk_pct_nav": "0.75",
                "max_single_trade_risk_pct_nav": "1.00",
                "max_total_open_trade_risk_pct_nav": "5.00",
            },
            "allocation_scoring": {
                "weights": {
                    "strategy_score": "0.30",
                    "trader_confidence": "0.25",
                    "liquidity": "0.15",
                    "volatility": "0.15",
                    "diversification": "0.10",
                    "recent_sleeve_performance": "0.05",
                },
                "score_bands": {
                    "reject_below": "60.0",
                    "half_normal_below": "75.0",
                    "normal_below": "85.0",
                },
            },
            "rebalance": {
                "sleeve_drift_threshold_pct": "20.0",
                "min_rebalance_notional_inr": "5000",
                "review_frequency": "daily_after_close",
                "core_rebalance_frequency": "monthly",
            },
        }
    )


def _proposal(
    *,
    symbol: str,
    action: str,
    target_pct: Decimal,
    current_pct: Decimal,
    current_quantity: int,
) -> TraderProposal:
    return TraderProposal(
        proposal_id=f"tp-{symbol.lower()}",
        run_id="pr-plan-test",
        portfolio_id="local-paper",
        symbol=symbol,
        debate_id=f"deb-{symbol.lower()}",
        as_of=datetime(2026, 6, 22, 9, 0, tzinfo=timezone.utc),
        action=action,  # type: ignore[arg-type]
        confidence=Decimal("0.9000"),
        horizon="medium",
        requested_position_pct_nav=target_pct,
        current_position_quantity=current_quantity,
        current_position_pct_nav=current_pct,
        target_position_pct_nav=target_pct,
        lifecycle_trigger="new_entry" if action == "BUY" else "thesis_invalidated",
        evaluation_mode="after_close",
        order_type="MARKET" if action in {"BUY", "REDUCE", "EXIT"} else "NONE",
        entry_rule="Plan test proposal.",
        stop_loss_pct=Decimal("6.0000"),
        take_profit_pct=Decimal("12.0000"),
        reason_summary="Plan test proposal.",
        invalid_if=["Plan test invalidation."],
        position_management_summary="Plan test lifecycle summary.",
        source_report_ids=[f"ar-{symbol.lower()}"],
        is_order=False,
        requires_risk_approval=True,
        model_version="test_trader",
    )


def _candles(symbol: str, close: Decimal) -> list[DailyCandle]:
    return [
        DailyCandle(
            symbol=symbol,
            trade_date=date(2026, 6, 19),
            open=close,
            high=close,
            low=close,
            close=close,
            volume=1_000_000,
            source="test",
            data_available_time=datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc),
        )
    ]
