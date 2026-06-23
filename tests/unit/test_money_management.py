from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from taurus_core.portfolio import load_money_management_policy


def test_rebalance_capacity_loads_from_default_policy() -> None:
    policy = load_money_management_policy("configs/portfolio/money_management_v1.yaml")

    capacity = policy.rebalance_capacity

    assert capacity.hard_cash_reserve_pct_nav == Decimal("5.0")
    assert capacity.same_run_proceeds_haircut_pct == Decimal("80.0")
    assert capacity.buy_price_buffer_pct == Decimal("5.0")
    assert capacity.soft_borrowing_enabled is True
    assert capacity.borrower_sleeve_ids == ("active_strategy",)
    assert capacity.borrowable_sleeve_ids == (
        "diversifying_strategy",
        "experimental_models",
        "core_shariah",
    )
    assert "cash_buffer" not in capacity.borrowable_sleeve_ids
    assert capacity.max_borrowed_capacity_pct_nav == Decimal("20.0")
    assert capacity.max_borrowed_capacity_inr is None
    assert capacity.repay_priority_sleeve_ids == (
        "core_shariah",
        "diversifying_strategy",
        "experimental_models",
    )


def test_graph_aware_v2_maps_to_active_strategy_in_default_policy() -> None:
    policy = load_money_management_policy("configs/portfolio/money_management_v1.yaml")

    mappings = {mapping.strategy_name: mapping.sleeve_id for mapping in policy.strategy_mappings}

    assert mappings["graph_aware_score_v1"] == "active_strategy"
    assert mappings["graph_aware_score_v2"] == "active_strategy"


def test_legacy_policy_without_rebalance_capacity_uses_safe_defaults(tmp_path: Path) -> None:
    policy = load_money_management_policy(_write_policy(tmp_path))

    capacity = policy.rebalance_capacity

    assert capacity.hard_cash_reserve_pct_nav == Decimal("5.0")
    assert capacity.same_run_proceeds_haircut_pct == Decimal("80.0")
    assert capacity.buy_price_buffer_pct == Decimal("5.0")
    assert capacity.soft_borrowing_enabled is True
    assert capacity.borrower_sleeve_ids == ("active_strategy",)
    assert capacity.borrowable_sleeve_ids == ("core_shariah",)
    assert "cash_buffer" not in capacity.borrowable_sleeve_ids


def test_cash_buffer_cannot_be_borrowable_capacity(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        extra=(
            "rebalance_capacity:\n"
            "  borrowable_sleeve_ids:\n"
            "    - cash_buffer\n"
            "  borrower_sleeve_ids:\n"
            "    - active_strategy\n"
        ),
    )

    with pytest.raises(ValueError, match="cash_buffer cannot be a borrowable sleeve"):
        load_money_management_policy(policy_path)


def _write_policy(tmp_path: Path, *, extra: str = "") -> Path:
    universe_path = tmp_path / "universe.yaml"
    universe_path.write_text(
        "universe_name: test_shariah\n"
        "default_exchange: NSE\n"
        "default_segment: EQUITY\n"
        "symbols:\n"
        "  - symbol: INFY\n"
        "    name: Infosys Ltd.\n"
        "    enabled: true\n"
        "    providers:\n"
        "      kite:\n"
        "        exchange: NSE\n"
        "        tradingsymbol: INFY\n",
        encoding="utf-8",
    )
    policy_path = tmp_path / "money_management.yaml"
    policy_path.write_text(
        "policy_version: legacy_test_policy\n"
        f"shariah_universe_path: {universe_path}\n"
        "sleeves:\n"
        "  - sleeve_id: core_shariah\n"
        "    name: Core\n"
        "    target_weight_pct: 60.0\n"
        "    role: Core sleeve\n"
        "  - sleeve_id: active_strategy\n"
        "    name: Active\n"
        "    target_weight_pct: 35.0\n"
        "    role: Active sleeve\n"
        "  - sleeve_id: cash_buffer\n"
        "    name: Cash\n"
        "    target_weight_pct: 5.0\n"
        "    role: Cash buffer\n"
        "strategy_mappings:\n"
        "  - strategy_name: core_shariah_basket_v1\n"
        "    sleeve_id: core_shariah\n"
        "  - strategy_name: graph_aware_score_v1\n"
        "    sleeve_id: active_strategy\n"
        "limits:\n"
        "  max_stock_pct_nav: 5.0\n"
        "  max_stock_hard_cap_pct_nav: 7.5\n"
        "  max_sector_pct_nav: 25.0\n"
        "  max_graph_cluster_pct_nav: 35.0\n"
        "  max_open_positions: 20\n"
        "trade_risk:\n"
        "  normal_trade_risk_pct_nav: 0.50\n"
        "  strong_trade_risk_pct_nav: 0.75\n"
        "  max_single_trade_risk_pct_nav: 1.00\n"
        "  max_total_open_trade_risk_pct_nav: 5.00\n"
        "allocation_scoring:\n"
        "  weights:\n"
        "    strategy_score: 0.30\n"
        "    trader_confidence: 0.25\n"
        "    liquidity: 0.15\n"
        "    volatility: 0.15\n"
        "    diversification: 0.10\n"
        "    recent_sleeve_performance: 0.05\n"
        "  score_bands:\n"
        "    reject_below: 60.0\n"
        "    half_normal_below: 75.0\n"
        "    normal_below: 85.0\n"
        "rebalance:\n"
        "  sleeve_drift_threshold_pct: 20.0\n"
        "  min_rebalance_notional_inr: 5000\n"
        "  review_frequency: daily_after_close\n"
        "  core_rebalance_frequency: monthly\n"
        f"{extra}",
        encoding="utf-8",
    )
    return policy_path
