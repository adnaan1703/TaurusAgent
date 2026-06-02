from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from taurus_core.domain.market_data import DailyCandle
from taurus_core.portfolio import (
    ActiveAllocationInput,
    ActiveAllocationPosition,
    PortfolioAllocationService,
    SleeveAllocationSnapshot,
    load_money_management_policy,
)
from taurus_core.research.schemas import TraderProposal


def test_trade_risk_cap_limits_active_buy(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, max_stock_pct=Decimal("50.0"))
    allocated = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
        ),
    )

    decision = allocated.allocation_decision
    assert decision is not None
    assert allocated.action == "BUY"
    assert decision.binding_constraint == "trade_risk"
    assert decision.approved_notional_inr < decision.requested_notional_inr
    assert decision.estimated_risk_inr <= decision.allowed_risk_inr


def test_stock_exposure_cap_limits_active_buy(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, max_stock_pct=Decimal("3.0"))
    allocated = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
        ),
    )

    decision = allocated.allocation_decision
    assert decision is not None
    assert decision.binding_constraint == "stock_exposure"
    assert decision.approved_position_pct_nav <= Decimal("3.0000")


def test_sleeve_capacity_cap_limits_active_buy(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        active_target_pct=Decimal("4.0"),
        max_stock_pct=Decimal("50.0"),
    )
    allocated = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
        ),
    )

    decision = allocated.allocation_decision
    assert decision is not None
    assert decision.binding_constraint == "sleeve_capacity"
    assert decision.approved_position_pct_nav <= Decimal("4.0000")


def test_active_capacity_excludes_runtime_core_basket_holdings(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        active_target_pct=Decimal("10.0"),
        max_stock_pct=Decimal("50.0"),
    )
    core_holding = ActiveAllocationPosition(
        symbol="TCS",
        quantity=3000,
        market_value_inr=Decimal("300000.00"),
    )
    without_runtime_core = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            positions=(core_holding,),
        ),
    )
    with_runtime_core = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            positions=(core_holding,),
            core_basket_symbols=("TCS",),
        ),
    )

    assert without_runtime_core.allocation_decision is not None
    assert with_runtime_core.allocation_decision is not None
    assert without_runtime_core.action == "NO_TRADE"
    assert without_runtime_core.allocation_decision.binding_constraint == "sleeve_capacity"
    assert with_runtime_core.action == "BUY"
    assert with_runtime_core.allocation_decision.binding_constraint == "sleeve_capacity"
    assert Decimal("0") < with_runtime_core.allocation_decision.approved_notional_inr
    assert with_runtime_core.allocation_decision.approved_notional_inr <= Decimal("100000.00")


def test_cash_buffer_cap_limits_active_buy(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, max_stock_pct=Decimal("50.0"))
    allocated = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            available_cash=Decimal("70000"),
        ),
    )

    decision = allocated.allocation_decision
    assert decision is not None
    assert decision.binding_constraint == "cash_buffer"
    assert decision.approved_notional_inr <= Decimal("20000.00")


def test_total_open_trade_risk_cap_limits_active_buy(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        active_target_pct=Decimal("90.0"),
        max_stock_pct=Decimal("50.0"),
    )
    allocated = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            positions=(
                ActiveAllocationPosition(
                    symbol="TCS",
                    quantity=8000,
                    market_value_inr=Decimal("800000.00"),
                ),
            ),
        ),
    )

    decision = allocated.allocation_decision
    assert decision is not None
    assert decision.binding_constraint == "total_open_trade_risk"
    assert decision.estimated_risk_inr <= Decimal("2000.00")


def test_open_position_count_cap_rejects_new_active_buy(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        max_open_positions=1,
        max_stock_pct=Decimal("50.0"),
    )
    allocated = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            positions=(
                ActiveAllocationPosition(
                    symbol="TCS",
                    quantity=100,
                    market_value_inr=Decimal("10000.00"),
                ),
            ),
        ),
    )

    decision = allocated.allocation_decision
    assert decision is not None
    assert allocated.action == "NO_TRADE"
    assert decision.binding_constraint == "open_positions"
    assert decision.approved_quantity == 0


def test_sector_and_graph_caps_limit_active_buy(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        active_target_pct=Decimal("90.0"),
        max_stock_pct=Decimal("50.0"),
    )
    sector_limited = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            positions=(
                ActiveAllocationPosition(
                    symbol="TCS",
                    quantity=2450,
                    market_value_inr=Decimal("245000.00"),
                ),
            ),
            sector_by_symbol={"INFY": "IT", "TCS": "IT"},
        ),
    )
    graph_limited = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            positions=(
                ActiveAllocationPosition(
                    symbol="TCS",
                    quantity=3450,
                    market_value_inr=Decimal("345000.00"),
                ),
            ),
            graph_cluster_by_symbol={"INFY": "cluster_1", "TCS": "cluster_1"},
        ),
    )

    assert sector_limited.allocation_decision is not None
    assert graph_limited.allocation_decision is not None
    assert sector_limited.allocation_decision.binding_constraint == "sector_concentration"
    assert graph_limited.allocation_decision.binding_constraint == "graph_concentration"


def test_invalid_stop_loss_rejects_new_buy_but_not_reduce_or_exit(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, max_stock_pct=Decimal("50.0"))
    rejected = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            proposal=_proposal(action="BUY", stop_loss_pct=Decimal("0.0000")),
        ),
    )
    reduced = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("1.0000"),
            proposal=_proposal(
                action="REDUCE",
                target_pct=Decimal("1.0000"),
                current_quantity=10,
                current_pct=Decimal("2.0000"),
                stop_loss_pct=Decimal("0.0000"),
            ),
        ),
    )
    exited = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("0.0000"),
            proposal=_proposal(
                action="EXIT",
                target_pct=Decimal("0.0000"),
                current_quantity=10,
                current_pct=Decimal("2.0000"),
                stop_loss_pct=Decimal("0.0000"),
            ),
        ),
    )

    assert rejected.action == "NO_TRADE"
    assert rejected.allocation_decision is not None
    assert rejected.allocation_decision.binding_constraint == "invalid_stop_loss_or_price"
    assert reduced.action == "REDUCE"
    assert reduced.allocation_decision is not None
    assert reduced.allocation_decision.status == "unchanged"
    assert exited.action == "EXIT"
    assert exited.allocation_decision is not None
    assert exited.allocation_decision.status == "unchanged"


def test_volatile_stock_receives_smaller_quantity_than_lower_vol_stock(
    tmp_path: Path,
) -> None:
    policy_path = _write_policy(tmp_path, max_stock_pct=Decimal("50.0"))
    low_vol = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            history=tuple(_candles(symbol="INFY", volatility="low")),
        ),
    )
    high_vol = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            history=tuple(_candles(symbol="INFY", volatility="high")),
        ),
    )

    assert low_vol.allocation_decision is not None
    assert high_vol.allocation_decision is not None
    assert high_vol.allocation_decision.volatility_used > low_vol.allocation_decision.volatility_used
    assert high_vol.allocation_decision.approved_quantity < low_vol.allocation_decision.approved_quantity


def test_strategy_to_sleeve_mapping_is_config_driven(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        active_target_pct=Decimal("60.0"),
        diversifying_target_pct=Decimal("15.0"),
        experimental_target_pct=Decimal("5.0"),
        max_stock_pct=Decimal("50.0"),
    )
    policy = load_money_management_policy(policy_path)
    service = PortfolioAllocationService(policy)

    assert service.sleeve_id_for_strategy("graph_aware_score_v1") == "active_strategy"
    assert service.sleeve_id_for_strategy("blended_score_v1") == "diversifying_strategy"
    assert service.sleeve_id_for_strategy("experimental_score_v1") == "experimental_models"

    allocated = service.allocate(
        _input(
            target_pct=Decimal("10.0000"),
            strategy_name="blended_score_v1",
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="diversifying_strategy",
                    starting_nav_estimate_inr=Decimal("150000.00"),
                ),
            ),
        )
    )

    assert allocated.allocation_decision is not None
    assert allocated.allocation_decision.sleeve_id == "diversifying_strategy"
    assert allocated.action == "BUY"


def test_portfolio_drawdown_governors_reduce_and_freeze_new_buys(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        active_target_pct=Decimal("80.0"),
        max_stock_pct=Decimal("50.0"),
    )
    caution = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            nav=Decimal("960000"),
            portfolio_starting_nav=Decimal("1000000"),
        ),
    )
    defensive = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            nav=Decimal("940000"),
            portfolio_starting_nav=Decimal("1000000"),
        ),
    )
    frozen = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("20.0000"),
            nav=Decimal("890000"),
            portfolio_starting_nav=Decimal("1000000"),
        ),
    )

    assert caution.allocation_decision is not None
    assert defensive.allocation_decision is not None
    assert frozen.allocation_decision is not None
    assert caution.allocation_decision.governor_scale_factor == Decimal("0.7500")
    assert defensive.allocation_decision.governor_scale_factor == Decimal("0.5000")
    assert defensive.allocation_decision.approved_quantity < caution.allocation_decision.approved_quantity
    assert frozen.action == "NO_TRADE"
    assert frozen.allocation_decision.binding_constraint == "portfolio_drawdown_freeze"
    assert frozen.allocation_decision.governor_reasons


def test_sleeve_drawdown_governor_freezes_only_that_sleeve(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        active_target_pct=Decimal("60.0"),
        diversifying_target_pct=Decimal("15.0"),
        experimental_target_pct=Decimal("5.0"),
        max_stock_pct=Decimal("50.0"),
    )
    frozen = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("10.0000"),
            strategy_name="blended_score_v1",
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="diversifying_strategy",
                    starting_nav_estimate_inr=Decimal("150000.00"),
                    unrealized_pnl_inr=Decimal("-13500.00"),
                ),
            ),
        ),
    )
    active = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("10.0000"),
            strategy_name="graph_aware_score_v1",
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="diversifying_strategy",
                    starting_nav_estimate_inr=Decimal("150000.00"),
                    unrealized_pnl_inr=Decimal("-13500.00"),
                ),
            ),
        ),
    )

    assert frozen.allocation_decision is not None
    assert active.allocation_decision is not None
    assert frozen.action == "NO_TRADE"
    assert frozen.allocation_decision.binding_constraint == "sleeve_drawdown_freeze"
    assert active.action == "BUY"


def test_experimental_sleeve_risk_cap_limits_new_entry(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        active_target_pct=Decimal("60.0"),
        diversifying_target_pct=Decimal("15.0"),
        experimental_target_pct=Decimal("5.0"),
        max_stock_pct=Decimal("50.0"),
    )
    allocated = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("10.0000"),
            strategy_name="experimental_score_v1",
        ),
    )

    assert allocated.allocation_decision is not None
    assert allocated.allocation_decision.sleeve_id == "experimental_models"
    assert allocated.allocation_decision.binding_constraint == "sleeve_trade_risk_cap"
    assert allocated.allocation_decision.estimated_risk_inr <= Decimal("1000.00")


def test_exits_remain_routable_during_portfolio_freeze(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, max_stock_pct=Decimal("50.0"))
    exited = _allocate(
        policy_path,
        _input(
            target_pct=Decimal("0.0000"),
            portfolio_starting_nav=Decimal("1000000"),
            nav=Decimal("890000"),
            proposal=_proposal(
                action="EXIT",
                target_pct=Decimal("0.0000"),
                current_quantity=10,
                current_pct=Decimal("2.0000"),
            ),
        ),
    )

    assert exited.action == "EXIT"
    assert exited.allocation_decision is not None
    assert exited.allocation_decision.status == "unchanged"
    assert exited.allocation_decision.binding_constraint == "lifecycle_action_not_new_risk"


def _allocate(policy_path: Path, allocation_input: ActiveAllocationInput) -> TraderProposal:
    policy = load_money_management_policy(policy_path)
    return PortfolioAllocationService(policy).allocate(allocation_input)


def _input(
    *,
    target_pct: Decimal,
    proposal: TraderProposal | None = None,
    nav: Decimal = Decimal("1000000"),
    available_cash: Decimal = Decimal("1000000"),
    portfolio_starting_nav: Decimal | None = None,
    positions: tuple[ActiveAllocationPosition, ...] = (),
    sleeve_snapshots: tuple[SleeveAllocationSnapshot, ...] = (),
    history: tuple[DailyCandle, ...] | None = None,
    strategy_name: str = "graph_aware_score_v1",
    sector_by_symbol: dict[str, str] | None = None,
    graph_cluster_by_symbol: dict[str, str] | None = None,
    core_basket_symbols: tuple[str, ...] = (),
) -> ActiveAllocationInput:
    base = proposal or _proposal(action="BUY", target_pct=target_pct)
    if proposal is None:
        base = base.model_copy(
            update={
                "target_position_pct_nav": target_pct,
                "requested_position_pct_nav": target_pct,
            }
        )
    tagged = base.model_copy(
        update={
            "allocation_decision": None,
        }
    )
    return ActiveAllocationInput(
        proposal=tagged,
        strategy_name=strategy_name,
        nav_inr=nav,
        available_cash_inr=available_cash,
        portfolio_starting_nav_estimate_inr=portfolio_starting_nav,
        current_positions=positions,
        sleeve_snapshots=sleeve_snapshots,
        core_basket_symbols=core_basket_symbols,
        history=history or tuple(_candles(symbol=tagged.symbol, volatility="low")),
        strategy_score=Decimal("0.2000"),
        sector_by_symbol=sector_by_symbol,
        graph_cluster_by_symbol=graph_cluster_by_symbol,
    )


def _proposal(
    *,
    action: str,
    target_pct: Decimal = Decimal("20.0000"),
    current_quantity: int = 0,
    current_pct: Decimal = Decimal("0.0000"),
    stop_loss_pct: Decimal = Decimal("6.0000"),
) -> TraderProposal:
    return TraderProposal(
        proposal_id="tp-test",
        run_id="run-test",
        portfolio_id="local-paper",
        symbol="INFY",
        debate_id="deb-test",
        as_of=datetime(2024, 5, 20, tzinfo=timezone.utc),
        action=action,  # type: ignore[arg-type]
        confidence=Decimal("0.9000"),
        horizon="medium",
        requested_position_pct_nav=target_pct,
        current_position_quantity=current_quantity,
        current_position_pct_nav=current_pct,
        target_position_pct_nav=target_pct,
        lifecycle_trigger="new_entry",
        evaluation_mode="after_close",
        order_type="LIMIT" if action in {"BUY", "REDUCE", "EXIT"} else "NONE",
        entry_rule="Test proposal.",
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=Decimal("12.0000"),
        reason_summary="Test proposal.",
        invalid_if=["Test invalidation."],
        position_management_summary="Test lifecycle summary.",
        source_report_ids=["ar-test"],
        is_order=False,
        requires_risk_approval=True,
        model_version="test_trader",
    )


def _candles(*, symbol: str, volatility: str) -> list[DailyCandle]:
    price = Decimal("100.00")
    candles: list[DailyCandle] = []
    for offset in range(90):
        if volatility == "high":
            move = Decimal("0.0800") if offset % 2 == 0 else Decimal("-0.0700")
        else:
            move = Decimal("0.0010")
        price = (price * (Decimal("1") + move)).quantize(Decimal("0.01"))
        candles.append(
            DailyCandle(
                symbol=symbol,
                trade_date=date.fromordinal(date(2024, 1, 1).toordinal() + offset),
                open=price,
                high=(price * Decimal("1.01")).quantize(Decimal("0.01")),
                low=(price * Decimal("0.99")).quantize(Decimal("0.01")),
                close=price,
                volume=1_000_000,
                source="test",
            )
        )
    return candles


def _write_policy(
    tmp_path: Path,
    *,
    active_target_pct: Decimal = Decimal("80.0"),
    diversifying_target_pct: Decimal = Decimal("0.0"),
    experimental_target_pct: Decimal = Decimal("0.0"),
    max_stock_pct: Decimal = Decimal("50.0"),
    max_open_positions: int = 20,
) -> Path:
    cash_pct = Decimal("5.0")
    core_pct = (
        Decimal("100.0")
        - active_target_pct
        - diversifying_target_pct
        - experimental_target_pct
        - cash_pct
    )
    universe_path = tmp_path / "shariah.yaml"
    universe_path.write_text(
        "universe_name: active_test\n"
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
        "policy_version: active_test_policy\n"
        f"shariah_universe_path: {universe_path}\n"
        "sleeves:\n"
        "  - sleeve_id: core_shariah\n"
        "    name: Core\n"
        f"    target_weight_pct: {core_pct}\n"
        "    role: Core sleeve\n"
        "  - sleeve_id: active_strategy\n"
        "    name: Active\n"
        f"    target_weight_pct: {active_target_pct}\n"
        "    role: Active sleeve\n"
        "    drawdown_reduce_threshold_pct: 6.0\n"
        "    drawdown_freeze_threshold_pct: 10.0\n"
        "  - sleeve_id: diversifying_strategy\n"
        "    name: Diversifying\n"
        f"    target_weight_pct: {diversifying_target_pct}\n"
        "    role: Diversifying sleeve\n"
        "    drawdown_reduce_threshold_pct: 5.0\n"
        "    drawdown_freeze_threshold_pct: 8.0\n"
        "  - sleeve_id: experimental_models\n"
        "    name: Experimental\n"
        f"    target_weight_pct: {experimental_target_pct}\n"
        "    role: Experimental sleeve\n"
        "    drawdown_reduce_threshold_pct: 2.0\n"
        "    drawdown_freeze_threshold_pct: 4.0\n"
        "    new_entry_risk_cap_pct_nav: 0.10\n"
        "  - sleeve_id: cash_buffer\n"
        "    name: Cash\n"
        f"    target_weight_pct: {cash_pct}\n"
        "    role: Cash buffer\n"
        "strategy_mappings:\n"
        "  - strategy_name: graph_aware_score_v1\n"
        "    sleeve_id: active_strategy\n"
        "  - strategy_name: moving_average_crossover_v1\n"
        "    sleeve_id: active_strategy\n"
        "  - strategy_name: blended_score_v1\n"
        "    sleeve_id: diversifying_strategy\n"
        "  - strategy_name: experimental_score_v1\n"
        "    sleeve_id: experimental_models\n"
        "limits:\n"
        f"  max_stock_pct_nav: {max_stock_pct}\n"
        f"  max_stock_hard_cap_pct_nav: {max_stock_pct}\n"
        "  max_sector_pct_nav: 25.0\n"
        "  max_graph_cluster_pct_nav: 35.0\n"
        f"  max_open_positions: {max_open_positions}\n"
        "trade_risk:\n"
        "  normal_trade_risk_pct_nav: 0.50\n"
        "  strong_trade_risk_pct_nav: 0.75\n"
        "  max_single_trade_risk_pct_nav: 1.00\n"
        "  max_total_open_trade_risk_pct_nav: 5.00\n"
        "drawdown_governors:\n"
        "  - name: portfolio_caution\n"
        "    drawdown_pct: 3.0\n"
        "    action: reduce_new_position_sizes_25_pct\n"
        "  - name: portfolio_defensive\n"
        "    drawdown_pct: 5.0\n"
        "    action: reduce_new_position_sizes_50_pct\n"
        "  - name: experimental_freeze\n"
        "    drawdown_pct: 8.0\n"
        "    action: stop_experimental_new_entries\n"
        "  - name: portfolio_freeze\n"
        "    drawdown_pct: 10.0\n"
        "    action: freeze_new_buys_allow_exits\n"
        "rebalance:\n"
        "  sleeve_drift_threshold_pct: 20.0\n"
        "  min_rebalance_notional_inr: 5000\n"
        "  review_frequency: daily_after_close\n"
        "  core_rebalance_frequency: monthly\n",
        encoding="utf-8",
    )
    return policy_path
