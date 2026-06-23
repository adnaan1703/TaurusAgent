from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from taurus_core.domain.market_data import DailyCandle
from taurus_core.portfolio import (
    ActiveAllocationPosition,
    FallbackAllocationPolicy,
    PortfolioPlanAllocationService,
    PortfolioRebalancePlanInput,
    PortfolioRebalancePlanService,
    RunAllocationInput,
    RunLevelAllocationService,
    SleeveAllocationSnapshot,
    load_money_management_policy,
)
from taurus_core.research.schemas import TraderProposal


def test_money_management_batch_allocation_consumes_pending_sleeve_capacity(
    tmp_path: Path,
) -> None:
    policy = load_money_management_policy(
        _write_policy(tmp_path, active_target_pct="10.0")
    )
    proposals = tuple(
        _proposal(symbol=symbol, target_pct=Decimal("5.0000"))
        for symbol in ("AAA", "BBB", "CCC")
    )

    result = RunLevelAllocationService().allocate(
        RunAllocationInput(
            run_id="run-batch",
            strategy_name="graph_aware_score_v1",
            proposals=proposals,
            nav_inr=Decimal("1000000"),
            available_cash_inr=Decimal("1000000"),
            current_positions=tuple(),
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="active_strategy",
                    starting_nav_estimate_inr=Decimal("100000.00"),
                    current_exposure_inr=Decimal("0.00"),
                ),
            ),
            histories_by_symbol={
                proposal.symbol: tuple(_candles(proposal.symbol))
                for proposal in proposals
            },
            strategy_rank_by_symbol={"AAA": 1, "BBB": 2, "CCC": 3},
            strategy_score_by_symbol={
                "AAA": Decimal("0.20"),
                "BBB": Decimal("0.19"),
                "CCC": Decimal("0.18"),
            },
            money_management_policy=policy,
        )
    )

    by_symbol = {entry.symbol: entry for entry in result.ledger}
    assert result.summary["selected_count"] == 2
    assert by_symbol["AAA"].status == "selected"
    assert by_symbol["BBB"].status == "selected"
    assert by_symbol["CCC"].status == "not_selected"
    assert by_symbol["CCC"].binding_constraint == "sleeve_capacity"


def test_fallback_allocation_orders_scores_above_old_saturation_before_rank() -> None:
    high_score = _proposal(symbol="HIGH", target_pct=Decimal("5.0000"))
    saturated_score = _proposal(symbol="SAT", target_pct=Decimal("5.0000"))

    result = RunLevelAllocationService().allocate(
        RunAllocationInput(
            run_id="run-fallback-score-precision",
            strategy_name="graph_aware_score_v1",
            proposals=(high_score, saturated_score),
            nav_inr=Decimal("1000000"),
            available_cash_inr=Decimal("1000000"),
            histories_by_symbol={
                high_score.symbol: tuple(_candles(high_score.symbol)),
                saturated_score.symbol: tuple(_candles(saturated_score.symbol)),
            },
            strategy_rank_by_symbol={"SAT": 1, "HIGH": 2},
            strategy_score_by_symbol={
                "SAT": Decimal("0.1000"),
                "HIGH": Decimal("0.2000"),
            },
            fallback_policy=FallbackAllocationPolicy(
                max_open_positions=1,
                max_position_pct_nav=Decimal("5.0"),
            ),
        )
    )

    by_symbol = {entry.symbol: entry for entry in result.ledger}
    assert by_symbol["HIGH"].status == "selected"
    assert by_symbol["SAT"].status == "not_selected"
    assert by_symbol["HIGH"].candidate_score is not None
    assert by_symbol["SAT"].candidate_score is not None
    assert by_symbol["HIGH"].candidate_score > by_symbol["SAT"].candidate_score


def test_fallback_allocation_derives_selected_count_from_cash_and_settings() -> None:
    proposals = tuple(
        _proposal(symbol=symbol, target_pct=Decimal("5.0000"))
        for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE")
    )

    result = RunLevelAllocationService().allocate(
        RunAllocationInput(
            run_id="run-fallback",
            strategy_name="graph_aware_score_v1",
            proposals=proposals,
            nav_inr=Decimal("1000000"),
            available_cash_inr=Decimal("120000"),
            histories_by_symbol={
                proposal.symbol: tuple(_candles(proposal.symbol))
                for proposal in proposals
            },
            strategy_rank_by_symbol={
                proposal.symbol: index
                for index, proposal in enumerate(proposals, start=1)
            },
            strategy_score_by_symbol={
                proposal.symbol: Decimal("0.20") for proposal in proposals
            },
            fallback_policy=FallbackAllocationPolicy(
                max_open_positions=8,
                max_position_pct_nav=Decimal("5.0"),
            ),
        )
    )

    assert result.summary["selected_count"] == 3
    assert result.summary["allocation_reduced_count"] == 1
    assert result.summary["not_selected_count"] == 2
    assert result.binding_constraints["available_cash"] == 3


def test_fallback_allocation_stops_without_fixed_candidate_count() -> None:
    proposals = tuple(
        _proposal(symbol=symbol, target_pct=Decimal("5.0000"))
        for symbol in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF")
    )

    result = RunLevelAllocationService().allocate(
        RunAllocationInput(
            run_id="run-open-limit",
            strategy_name="graph_aware_score_v1",
            proposals=proposals,
            nav_inr=Decimal("1000000"),
            available_cash_inr=Decimal("1000000"),
            histories_by_symbol={
                proposal.symbol: tuple(_candles(proposal.symbol))
                for proposal in proposals
            },
            strategy_rank_by_symbol={
                proposal.symbol: index
                for index, proposal in enumerate(proposals, start=1)
            },
            strategy_score_by_symbol={
                proposal.symbol: Decimal("0.20") for proposal in proposals
            },
            fallback_policy=FallbackAllocationPolicy(
                max_open_positions=4,
                max_position_pct_nav=Decimal("5.0"),
            ),
        )
    )

    assert result.summary["selected_count"] == 4
    assert result.summary["not_selected_count"] == 2
    assert result.binding_constraints["open_positions"] == 2


def test_open_position_lifecycle_proposal_remains_in_ledger() -> None:
    proposal = _proposal(
        symbol="AAA",
        action="HOLD",
        target_pct=Decimal("3.0000"),
        current_quantity=10,
        current_pct=Decimal("3.0000"),
    )

    result = RunLevelAllocationService().allocate(
        RunAllocationInput(
            run_id="run-lifecycle",
            strategy_name="graph_aware_score_v1",
            proposals=(proposal,),
            nav_inr=Decimal("1000000"),
            available_cash_inr=Decimal("1000000"),
            current_positions=(
                ActiveAllocationPosition(
                    symbol="AAA",
                    quantity=10,
                    market_value_inr=Decimal("30000.00"),
                ),
            ),
            histories_by_symbol={"AAA": tuple(_candles("AAA"))},
            fallback_policy=FallbackAllocationPolicy(
                max_open_positions=1,
                max_position_pct_nav=Decimal("5.0"),
            ),
        )
    )

    assert result.ledger[0].symbol == "AAA"
    assert result.ledger[0].status == "open_position_management"
    assert result.proposals[0].action == "HOLD"


def test_portfolio_plan_allocation_ranks_active_and_core_buys_together(
    tmp_path: Path,
) -> None:
    policy = load_money_management_policy(
        _write_policy(tmp_path, active_target_pct="50.0")
    )
    active = _proposal(symbol="AAA", target_pct=Decimal("5.0000"))
    plan = _portfolio_plan(
        policy=policy,
        proposals=(active,),
        nav_inr=Decimal("100000.00"),
        cash_inr=Decimal("5200.00"),
        core_symbol="BBB",
        core_target_pct=Decimal("5.0000"),
        core_rank_score=Decimal("95.0000"),
    )

    result = PortfolioPlanAllocationService().allocate(
        RunAllocationInput(
            run_id=plan.run_id,
            strategy_name="graph_aware_score_v1",
            proposals=(active,),
            nav_inr=plan.current_nav_inr,
            available_cash_inr=plan.current_cash_inr,
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="active_strategy",
                    starting_nav_estimate_inr=Decimal("50000.00"),
                ),
                SleeveAllocationSnapshot(
                    sleeve_id="core_shariah",
                    starting_nav_estimate_inr=Decimal("45000.00"),
                ),
                SleeveAllocationSnapshot(
                    sleeve_id="cash_buffer",
                    starting_nav_estimate_inr=Decimal("5000.00"),
                ),
            ),
            histories_by_symbol={
                "AAA": tuple(_candles("AAA")),
                "BBB": tuple(_candles("BBB")),
            },
            core_basket_symbols=("BBB",),
            strategy_rank_by_symbol={"AAA": 1},
            strategy_score_by_symbol={"AAA": Decimal("0.0000")},
            money_management_policy=policy,
        ),
        portfolio_plan=plan,
    )

    by_symbol = {entry.symbol: entry for entry in result.ledger}
    core = by_symbol["BBB"]
    active_entry = by_symbol["AAA"]

    assert result.model_version == "portfolio_plan_rebalance_allocation_v2"
    assert result.policy_source == "portfolio_plan"
    assert core.status in {"selected", "allocation_reduced"}
    assert core.proposal_source == "portfolio_plan_core"
    assert core.portfolio_plan_trade_id == "trade-core-bbb"
    assert core.planner_source == "core_shariah_basket_v1"
    assert active_entry.status == "not_selected"
    assert active_entry.binding_constraint == "cash_buffer"


def test_portfolio_plan_allocation_nets_same_run_sell_proceeds_for_buys(
    tmp_path: Path,
) -> None:
    policy = load_money_management_policy(
        _write_policy(tmp_path, active_target_pct="50.0")
    )
    sell = _proposal(
        symbol="TCS",
        action="EXIT",
        target_pct=Decimal("0.0000"),
        current_quantity=100,
        current_pct=Decimal("10.0000"),
    )
    buy = _proposal(symbol="AAA", target_pct=Decimal("5.0000"))
    position = ActiveAllocationPosition(
        symbol="TCS",
        quantity=100,
        market_value_inr=Decimal("10000.00"),
    )
    plan = _portfolio_plan(
        policy=policy,
        proposals=(sell, buy),
        nav_inr=Decimal("100000.00"),
        cash_inr=Decimal("5000.00"),
        positions=(position,),
    )

    result = PortfolioPlanAllocationService().allocate(
        RunAllocationInput(
            run_id=plan.run_id,
            strategy_name="graph_aware_score_v1",
            proposals=(sell, buy),
            nav_inr=plan.current_nav_inr,
            available_cash_inr=plan.current_cash_inr,
            current_positions=(position,),
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="active_strategy",
                    starting_nav_estimate_inr=Decimal("50000.00"),
                    current_exposure_inr=Decimal("10000.00"),
                    open_position_count=1,
                ),
                SleeveAllocationSnapshot(
                    sleeve_id="cash_buffer",
                    starting_nav_estimate_inr=Decimal("5000.00"),
                ),
            ),
            histories_by_symbol={
                "AAA": tuple(_candles("AAA")),
                "TCS": tuple(_candles("TCS")),
            },
            strategy_rank_by_symbol={"AAA": 1, "TCS": 2},
            strategy_score_by_symbol={
                "AAA": Decimal("0.3000"),
                "TCS": Decimal("-0.3000"),
            },
            money_management_policy=policy,
        ),
        portfolio_plan=plan,
    )

    by_symbol = {entry.symbol: entry for entry in result.ledger}

    assert plan.same_run_sell_proceeds_spendable_inr > Decimal("0.00")
    assert by_symbol["TCS"].status == "open_position_management"
    assert by_symbol["TCS"].action == "EXIT"
    assert by_symbol["AAA"].status in {"selected", "allocation_reduced"}
    assert by_symbol["AAA"].funding_source == "same_run_sell_proceeds"
    assert by_symbol["AAA"].existing_cash_used_inr == Decimal("0.00")
    assert by_symbol["AAA"].same_run_proceeds_used_inr > Decimal("0.00")
    assert by_symbol["AAA"].same_run_proceeds_available_inr == (
        plan.same_run_sell_proceeds_spendable_inr
    )
    assert by_symbol["AAA"].hard_cash_reserve_inr == Decimal("5000.00")
    assert by_symbol["AAA"].buy_price_buffer_pct == Decimal("5.0000")


def test_portfolio_plan_allocation_allows_observable_active_soft_borrowing(
    tmp_path: Path,
) -> None:
    policy = load_money_management_policy(
        _write_policy(
            tmp_path,
            active_target_pct="35.0",
            rebalance_capacity=(
                "rebalance_capacity:\n"
                "  hard_cash_reserve_pct_nav: 5.0\n"
                "  same_run_proceeds_haircut_pct: 80.0\n"
                "  buy_price_buffer_pct: 5.0\n"
                "  soft_borrowing_enabled: true\n"
                "  borrowable_sleeve_ids:\n"
                "    - core_shariah\n"
                "  borrower_sleeve_ids:\n"
                "    - active_strategy\n"
                "  max_borrowed_capacity_pct_nav: 20.0\n"
            ),
        )
    )
    active = _proposal(
        symbol="AAA",
        target_pct=Decimal("50.0000"),
        current_quantity=340,
        current_pct=Decimal("34.0000"),
    )
    plan = _portfolio_plan(
        policy=policy,
        proposals=(active,),
        nav_inr=Decimal("100000.00"),
        cash_inr=Decimal("30000.00"),
        positions=(
            ActiveAllocationPosition(
                symbol="AAA",
                quantity=340,
                market_value_inr=Decimal("34000.00"),
            ),
        ),
    )

    result = PortfolioPlanAllocationService().allocate(
        RunAllocationInput(
            run_id=plan.run_id,
            strategy_name="graph_aware_score_v1",
            proposals=(active,),
            nav_inr=plan.current_nav_inr,
            available_cash_inr=plan.current_cash_inr,
            current_positions=(
                ActiveAllocationPosition(
                    symbol="AAA",
                    quantity=340,
                    market_value_inr=Decimal("34000.00"),
                ),
            ),
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="active_strategy",
                    starting_nav_estimate_inr=Decimal("35000.00"),
                    current_exposure_inr=Decimal("34000.00"),
                    open_position_count=1,
                ),
                SleeveAllocationSnapshot(
                    sleeve_id="core_shariah",
                    starting_nav_estimate_inr=Decimal("60000.00"),
                    current_exposure_inr=Decimal("0.00"),
                ),
                SleeveAllocationSnapshot(
                    sleeve_id="cash_buffer",
                    starting_nav_estimate_inr=Decimal("5000.00"),
                ),
            ),
            histories_by_symbol={"AAA": tuple(_candles("AAA"))},
            strategy_rank_by_symbol={"AAA": 1},
            strategy_score_by_symbol={"AAA": Decimal("0.3000")},
            money_management_policy=policy,
        ),
        portfolio_plan=plan,
    )

    entry = result.ledger[0]

    assert entry.status in {"selected", "allocation_reduced"}
    assert entry.capacity_source == "borrowed_sleeve_capacity"
    assert entry.borrowed_from_sleeve_ids == ("core_shariah",)
    assert entry.approved_notional_inr > Decimal("1000.00")


def test_portfolio_plan_allocation_rejects_tiny_core_buy_after_rounding(
    tmp_path: Path,
) -> None:
    policy = load_money_management_policy(
        _write_policy(tmp_path, active_target_pct="50.0")
    )
    plan = _portfolio_plan(
        policy=policy,
        proposals=tuple(),
        nav_inr=Decimal("100000.00"),
        cash_inr=Decimal("100000.00"),
        core_symbol="BBB",
        core_target_pct=Decimal("0.0100"),
        core_trade_notional=Decimal("10.00"),
        core_rank_score=Decimal("95.0000"),
    )

    result = PortfolioPlanAllocationService().allocate(
        RunAllocationInput(
            run_id=plan.run_id,
            strategy_name="graph_aware_score_v1",
            proposals=tuple(),
            nav_inr=plan.current_nav_inr,
            available_cash_inr=plan.current_cash_inr,
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="core_shariah",
                    starting_nav_estimate_inr=Decimal("45000.00"),
                ),
            ),
            histories_by_symbol={"BBB": tuple(_candles("BBB"))},
            core_basket_symbols=("BBB",),
            money_management_policy=policy,
        ),
        portfolio_plan=plan,
    )

    entry = result.ledger[0]
    proposal = result.proposals[0]

    assert entry.symbol == "BBB"
    assert entry.status == "allocation_rejected"
    assert entry.approved_quantity == 0
    assert entry.binding_constraint == "requested_notional"
    assert proposal.action == "NO_TRADE"
    assert proposal.allocation_decision is not None
    assert proposal.allocation_decision.portfolio_plan_trade_id == "trade-core-bbb"


def test_legacy_run_level_allocation_still_available_without_portfolio_plan(
    tmp_path: Path,
) -> None:
    policy = load_money_management_policy(
        _write_policy(tmp_path, active_target_pct="10.0")
    )
    proposal = _proposal(symbol="AAA", target_pct=Decimal("5.0000"))

    result = RunLevelAllocationService().allocate(
        RunAllocationInput(
            run_id="run-legacy",
            strategy_name="graph_aware_score_v1",
            proposals=(proposal,),
            nav_inr=Decimal("100000.00"),
            available_cash_inr=Decimal("100000.00"),
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="active_strategy",
                    starting_nav_estimate_inr=Decimal("10000.00"),
                ),
            ),
            histories_by_symbol={"AAA": tuple(_candles("AAA"))},
            strategy_rank_by_symbol={"AAA": 1},
            strategy_score_by_symbol={"AAA": Decimal("0.2000")},
            money_management_policy=policy,
        )
    )

    assert result.model_version == "run_level_dynamic_allocation_v1"
    assert result.policy_source == "money_management_policy"
    assert result.ledger[0].portfolio_plan_id is None


@pytest.mark.parametrize(
    ("allocation_scoring", "message"),
    [
        (
            "allocation_scoring:\n"
            "  weights:\n"
            "    strategy_score: 0.31\n"
            "    trader_confidence: 0.25\n"
            "    liquidity: 0.15\n"
            "    volatility: 0.15\n"
            "    diversification: 0.10\n"
            "    recent_sleeve_performance: 0.05\n"
            "  score_bands:\n"
            "    reject_below: 60.0\n"
            "    half_normal_below: 75.0\n"
            "    normal_below: 85.0\n",
            "weights must sum to 1.00",
        ),
        (
            "allocation_scoring:\n"
            "  weights:\n"
            "    strategy_score: 0.30\n"
            "    trader_confidence: 0.25\n"
            "    liquidity: 0.15\n"
            "    volatility: 0.15\n"
            "    diversification: 0.10\n"
            "    recent_sleeve_performance: 0.05\n"
            "  score_bands:\n"
            "    reject_below: 80.0\n"
            "    half_normal_below: 75.0\n"
            "    normal_below: 85.0\n",
            "score bands must satisfy",
        ),
    ],
)
def test_score_weight_and_band_config_validation(
    tmp_path: Path,
    allocation_scoring: str,
    message: str,
) -> None:
    policy_path = _write_policy(
        tmp_path,
        active_target_pct="10.0",
        allocation_scoring=allocation_scoring,
    )

    with pytest.raises(ValueError, match=message):
        load_money_management_policy(policy_path)


def _proposal(
    *,
    symbol: str,
    action: str = "BUY",
    target_pct: Decimal = Decimal("5.0000"),
    current_quantity: int = 0,
    current_pct: Decimal = Decimal("0.0000"),
) -> TraderProposal:
    return TraderProposal(
        proposal_id=f"tp-{symbol.lower()}",
        run_id="run-test",
        portfolio_id="local-paper",
        symbol=symbol,
        debate_id=f"deb-{symbol.lower()}",
        as_of=datetime(2024, 5, 20, tzinfo=timezone.utc),
        action=action,  # type: ignore[arg-type]
        confidence=Decimal("0.9000"),
        horizon="medium",
        requested_position_pct_nav=target_pct,
        current_position_quantity=current_quantity,
        current_position_pct_nav=current_pct,
        target_position_pct_nav=target_pct,
        lifecycle_trigger="new_entry" if current_quantity == 0 else "hold_review",
        evaluation_mode="after_close",
        order_type="LIMIT" if action in {"BUY", "REDUCE", "EXIT"} else "NONE",
        entry_rule="Test proposal.",
        stop_loss_pct=Decimal("6.0000"),
        take_profit_pct=Decimal("12.0000"),
        reason_summary="Test proposal.",
        invalid_if=["Test invalidation."],
        position_management_summary="Test lifecycle summary.",
        source_report_ids=[f"ar-{symbol.lower()}"],
        is_order=False,
        requires_risk_approval=True,
        model_version="test_trader",
    )


def _candles(symbol: str) -> list[DailyCandle]:
    price = Decimal("100.00")
    candles: list[DailyCandle] = []
    for offset in range(90):
        price = (price * Decimal("1.0010")).quantize(Decimal("0.01"))
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


def _portfolio_plan(
    *,
    policy,
    proposals: tuple[TraderProposal, ...],
    nav_inr: Decimal,
    cash_inr: Decimal,
    core_symbol: str = "AAA",
    core_target_pct: Decimal | None = None,
    core_trade_notional: Decimal | None = None,
    core_rank_score: Decimal = Decimal("90.0000"),
    positions: tuple[ActiveAllocationPosition, ...] = (),
):
    core_target_pct = (
        core_target_pct if core_target_pct is not None else Decimal("0.0000")
    )
    core_trade_notional = (
        core_trade_notional
        if core_trade_notional is not None
        else (nav_inr * core_target_pct / Decimal("100")).quantize(Decimal("0.01"))
    )
    core_artifact = {"target_weights": {}, "decisions": [], "selection_scores": []}
    if core_target_pct > 0:
        core_artifact = {
            "target_weights": {core_symbol: str(core_target_pct)},
            "decisions": [
                {
                    "symbol": core_symbol,
                    "side": "BUY",
                    "status": "approved",
                    "target_weight_pct_nav": str(core_target_pct),
                    "current_weight_pct_nav": "0.0000",
                    "drift_pct_nav": str(core_target_pct),
                    "trade_notional_inr": str(core_trade_notional),
                }
            ],
            "selection_scores": [
                {"symbol": core_symbol, "rank_score": str(core_rank_score)}
            ],
        }
    histories = {
        proposal.symbol: tuple(_candles(proposal.symbol)) for proposal in proposals
    }
    if core_target_pct > 0:
        histories[core_symbol.upper()] = tuple(_candles(core_symbol))
    return PortfolioRebalancePlanService().build(
        PortfolioRebalancePlanInput(
            run_id="run-plan-allocation",
            portfolio_id="local-paper",
            as_of=datetime(2026, 6, 22, tzinfo=timezone.utc),
            strategy_name="graph_aware_score_v1",
            proposals=proposals,
            nav_inr=nav_inr,
            current_cash_inr=cash_inr,
            current_positions=positions,
            sleeve_snapshots=(
                SleeveAllocationSnapshot(
                    sleeve_id="active_strategy",
                    starting_nav_estimate_inr=Decimal("35000.00"),
                    current_exposure_inr=sum(
                        (
                            position.market_value_inr
                            for position in positions
                            if core_target_pct <= 0
                            or position.symbol.upper() != core_symbol.upper()
                        ),
                        Decimal("0.00"),
                    ),
                    open_position_count=len(positions),
                ),
                SleeveAllocationSnapshot(
                    sleeve_id="core_shariah",
                    starting_nav_estimate_inr=Decimal("60000.00"),
                    current_exposure_inr=Decimal("0.00"),
                ),
                SleeveAllocationSnapshot(
                    sleeve_id="cash_buffer",
                    starting_nav_estimate_inr=Decimal("5000.00"),
                ),
            ),
            histories_by_symbol=histories,
            core_basket_artifact=core_artifact,
            core_basket_symbols=(core_symbol,) if core_target_pct > 0 else tuple(),
            strategy_rank_by_symbol={
                proposal.symbol: index
                for index, proposal in enumerate(proposals, start=1)
            },
            strategy_score_by_symbol={
                proposal.symbol: Decimal("0.3000") for proposal in proposals
            },
            money_management_policy=policy,
        )
    )


def _write_policy(
    tmp_path: Path,
    *,
    active_target_pct: str,
    allocation_scoring: str | None = None,
    rebalance_capacity: str | None = None,
) -> Path:
    universe_path = tmp_path / "shariah.yaml"
    universe_path.write_text(
        "universe_name: run_allocation_test\n"
        "default_exchange: NSE\n"
        "default_segment: EQUITY\n"
        "symbols:\n"
        "  - symbol: AAA\n"
        "    name: AAA Ltd.\n"
        "    enabled: true\n"
        "    providers:\n"
        "      kite:\n"
        "        exchange: NSE\n"
        "        tradingsymbol: AAA\n",
        encoding="utf-8",
    )
    scoring = allocation_scoring or (
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
    )
    core_pct = Decimal("95.0") - Decimal(active_target_pct)
    policy_path = tmp_path / "money_management.yaml"
    policy_path.write_text(
        "policy_version: run_allocation_test_policy\n"
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
        "  max_stock_pct_nav: 50.0\n"
        "  max_stock_hard_cap_pct_nav: 50.0\n"
        "  max_sector_pct_nav: 25.0\n"
        "  max_graph_cluster_pct_nav: 35.0\n"
        "  max_open_positions: 20\n"
        "trade_risk:\n"
        "  normal_trade_risk_pct_nav: 0.50\n"
        "  strong_trade_risk_pct_nav: 0.75\n"
        "  max_single_trade_risk_pct_nav: 1.00\n"
        "  max_total_open_trade_risk_pct_nav: 5.00\n"
        f"{scoring}"
        "rebalance:\n"
        "  sleeve_drift_threshold_pct: 20.0\n"
        "  min_rebalance_notional_inr: 5000\n"
        "  review_frequency: daily_after_close\n"
        "  core_rebalance_frequency: monthly\n"
        f"{rebalance_capacity or ''}",
        encoding="utf-8",
    )
    return policy_path
