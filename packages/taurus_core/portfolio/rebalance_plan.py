from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taurus_core.domain.market_data import DailyCandle
from taurus_core.execution.costs import IndiaPaperCostModel
from taurus_core.portfolio.active_allocation import (
    ACTIVE_SLEEVE_ID,
    ALLOCATABLE_SLEEVE_IDS,
    ActiveAllocationPosition,
    SleeveAllocationSnapshot,
)
from taurus_core.portfolio.core_shariah_basket import CORE_SLEEVE_ID, CORE_STRATEGY_NAME
from taurus_core.portfolio.money_management import MoneyManagementPolicy, SleevePolicy
from taurus_core.portfolio.score_semantics import calibrate_strategy_score
from taurus_core.research.schemas import TraderProposal

PORTFOLIO_REBALANCE_PLAN_MODEL_VERSION = "portfolio_rebalance_plan_v3"
MONEY_QUANT = Decimal("0.01")
PCT_QUANT = Decimal("0.0001")
DEFAULT_SAME_RUN_SELL_PROCEEDS_HAIRCUT_PCT = Decimal("80.0000")
DEFAULT_BUY_PRICE_BUFFER_PCT = Decimal("5.0000")
THRESHOLD_REBALANCE_SOURCE = "portfolio_rebalance_threshold"

PlanSide = Literal["BUY", "SELL", "HOLD"]
PlanTradeStatus = Literal["observed", "advisory_only", "missing_price", "no_trade"]
ConstraintStatus = Literal["informational", "satisfied", "blocked"]


class PortfolioPlanConstraint(BaseModel):
    model_config = ConfigDict(frozen=True)

    constraint_id: str = Field(min_length=1)
    status: ConstraintStatus
    message: str = Field(min_length=1)
    amount_inr: Decimal | None = None
    pct_nav: Decimal | None = None


class PortfolioPlanPosition(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str = Field(min_length=1)
    quantity: int = Field(ge=0)
    market_value_inr: Decimal = Field(ge=Decimal("0"))
    current_pct_nav: Decimal = Field(ge=Decimal("0"))
    sleeve_id: str = Field(min_length=1)
    sleeve_label_source: str = Field(min_length=1)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("sleeve_id")
    @classmethod
    def normalize_sleeve_id(cls, value: str) -> str:
        return value.strip().lower()


class PortfolioPlanCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    candidate_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    proposal_id: str | None = None
    action: str = Field(min_length=1)
    source: str = Field(min_length=1)
    sleeve_id: str = Field(min_length=1)
    strategy_name: str | None = None
    strategy_rank: int | None = None
    raw_strategy_score: Decimal | None = None
    calibrated_strategy_score: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    allocation_score_component: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    score_calibration_method: str = Field(min_length=1)
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    requested_position_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    current_position_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    target_position_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    requested_notional_inr: Decimal = Field(ge=Decimal("0"))
    latest_price_inr: Decimal | None = Field(default=None, ge=Decimal("0"))
    score_evidence: dict[str, Any] = Field(default_factory=dict)
    rejection_reasons: tuple[str, ...] = Field(default_factory=tuple)
    decision_status: str | None = None

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("sleeve_id")
    @classmethod
    def normalize_sleeve_id(cls, value: str) -> str:
        return value.strip().lower()


class PortfolioPlanTrade(BaseModel):
    model_config = ConfigDict(frozen=True)

    trade_id: str = Field(min_length=1)
    symbol: str = Field(min_length=1)
    proposal_id: str | None = None
    side: PlanSide
    action: str = Field(min_length=1)
    source: str = Field(min_length=1)
    sleeve_id: str = Field(min_length=1)
    rank: int | None = None
    target_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    current_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    delta_pct_nav: Decimal
    estimated_notional_inr: Decimal = Field(ge=Decimal("0"))
    estimated_quantity: int = Field(ge=0)
    latest_price_inr: Decimal | None = Field(default=None, ge=Decimal("0"))
    constraints: tuple[PortfolioPlanConstraint, ...] = Field(default_factory=tuple)
    status: PlanTradeStatus

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("sleeve_id")
    @classmethod
    def normalize_sleeve_id(cls, value: str) -> str:
        return value.strip().lower()


class PortfolioPlanSleeveBudget(BaseModel):
    model_config = ConfigDict(frozen=True)

    sleeve_id: str = Field(min_length=1)
    sleeve_name: str | None = None
    target_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    current_pct_nav: Decimal = Field(ge=Decimal("0"))
    target_exposure_inr: Decimal = Field(ge=Decimal("0"))
    current_exposure_inr: Decimal = Field(ge=Decimal("0"))
    idle_capacity_inr: Decimal = Field(ge=Decimal("0"))
    protected_capacity_inr: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    borrowable_capacity_inr: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    borrowed_capacity_inr: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
    borrowed_by_sleeve_id: str | None = None
    idle_reason: str | None = None
    projected_exposure_inr: Decimal = Field(ge=Decimal("0"))
    projected_pct_nav: Decimal = Field(ge=Decimal("0"))

    @field_validator("sleeve_id")
    @classmethod
    def normalize_sleeve_id(cls, value: str) -> str:
        return value.strip().lower()


class PortfolioPlanCashBudget(BaseModel):
    model_config = ConfigDict(frozen=True)

    row_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    amount_inr: Decimal
    spendable: bool = False
    description: str = Field(min_length=1)


class PortfolioRebalancePlan(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    portfolio_id: str = Field(min_length=1)
    model_version: str = PORTFOLIO_REBALANCE_PLAN_MODEL_VERSION
    policy_version: str = Field(min_length=1)
    as_of: datetime
    current_nav_inr: Decimal = Field(ge=Decimal("0"))
    current_cash_inr: Decimal = Field(ge=Decimal("0"))
    hard_cash_reserve_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    hard_cash_reserve_inr: Decimal = Field(ge=Decimal("0"))
    spendable_cash_before_reserve_inr: Decimal = Field(ge=Decimal("0"))
    spendable_cash_after_reserve_inr: Decimal = Field(ge=Decimal("0"))
    same_run_sell_proceeds_haircut_pct: Decimal = Field(
        ge=Decimal("0"), le=Decimal("100")
    )
    same_run_sell_proceeds_gross_inr: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0")
    )
    same_run_sell_proceeds_cost_inr: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0")
    )
    same_run_sell_proceeds_net_inr: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0")
    )
    same_run_sell_proceeds_spendable_inr: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0")
    )
    same_run_sell_proceeds_safety_reserve_inr: Decimal = Field(
        default=Decimal("0.00"), ge=Decimal("0")
    )
    buy_price_buffer_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    soft_borrowing_enabled: bool = False
    max_borrowed_capacity_pct_nav: Decimal | None = Field(
        default=None, ge=Decimal("0"), le=Decimal("100")
    )
    max_borrowed_capacity_inr: Decimal | None = Field(default=None, ge=Decimal("0"))
    positions: tuple[PortfolioPlanPosition, ...] = Field(default_factory=tuple)
    candidates: tuple[PortfolioPlanCandidate, ...] = Field(default_factory=tuple)
    core_basket_target_weights: dict[str, Decimal] = Field(default_factory=dict)
    core_basket_advisory_decisions: tuple[dict[str, Any], ...] = Field(
        default_factory=tuple
    )
    planned_trades: tuple[PortfolioPlanTrade, ...] = Field(default_factory=tuple)
    cash_budget: tuple[PortfolioPlanCashBudget, ...] = Field(default_factory=tuple)
    sleeve_budgets: tuple[PortfolioPlanSleeveBudget, ...] = Field(default_factory=tuple)
    constraints: tuple[PortfolioPlanConstraint, ...] = Field(default_factory=tuple)

    def to_artifact(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


@dataclass(frozen=True, slots=True)
class PortfolioRebalancePlanInput:
    run_id: str
    portfolio_id: str
    as_of: datetime
    strategy_name: str
    proposals: tuple[TraderProposal, ...]
    nav_inr: Decimal
    current_cash_inr: Decimal
    current_positions: tuple[ActiveAllocationPosition, ...] = ()
    sleeve_snapshots: tuple[SleeveAllocationSnapshot, ...] = ()
    histories_by_symbol: Mapping[str, tuple[DailyCandle, ...]] = field(
        default_factory=dict
    )
    core_basket_artifact: Mapping[str, Any] | None = None
    core_basket_symbols: tuple[str, ...] = ()
    strategy_rank_by_symbol: Mapping[str, int] = field(default_factory=dict)
    strategy_score_by_symbol: Mapping[str, Decimal] = field(default_factory=dict)
    money_management_policy: MoneyManagementPolicy | None = None
    fallback_policy_source: str = "settings"
    sleeve_by_symbol: Mapping[str, str] = field(default_factory=dict)
    paper_brokerage_bps: Decimal = Decimal("0")
    paper_exchange_txn_charge_bps: Decimal = Decimal("0")
    paper_tax_levy_bps: Decimal = Decimal("0")


class PortfolioRebalancePlanService:
    model_version = PORTFOLIO_REBALANCE_PLAN_MODEL_VERSION

    def build(self, plan_input: PortfolioRebalancePlanInput) -> PortfolioRebalancePlan:
        policy = plan_input.money_management_policy
        core_artifact = dict(plan_input.core_basket_artifact or {})
        target_weights = _core_target_weights(core_artifact)
        core_symbols = tuple(
            sorted(
                {
                    *[symbol.upper() for symbol in plan_input.core_basket_symbols],
                    *target_weights,
                }
            )
        )
        positions = _position_rows(plan_input, core_symbols=core_symbols)
        base_candidates = [
            *_trader_candidate_rows(plan_input),
            *_core_candidate_rows(plan_input, core_artifact),
        ]
        threshold_candidates = _threshold_position_candidate_rows(
            plan_input,
            positions=positions,
            existing_candidates=tuple(base_candidates),
        )
        candidates = tuple(
            sorted(
                [
                    *base_candidates,
                    *threshold_candidates,
                ],
                key=lambda candidate: (
                    candidate.symbol,
                    0 if candidate.source == "trader_proposal" else 1,
                    candidate.strategy_rank
                    if candidate.strategy_rank is not None
                    else 1_000_000,
                    candidate.candidate_id,
                ),
            )
        )
        planned_trades = tuple(
            sorted(
                [
                    *[
                        _trade_from_candidate(plan_input, candidate)
                        for candidate in candidates
                    ],
                ],
                key=lambda trade: (
                    trade.rank if trade.rank is not None else 1_000_000,
                    trade.source,
                    trade.symbol,
                    trade.trade_id,
                ),
            )
        )
        haircut_pct = (
            policy.rebalance_capacity.same_run_proceeds_haircut_pct
            if policy is not None
            else DEFAULT_SAME_RUN_SELL_PROCEEDS_HAIRCUT_PCT
        ).quantize(PCT_QUANT)
        buy_price_buffer_pct = (
            policy.rebalance_capacity.buy_price_buffer_pct
            if policy is not None
            else DEFAULT_BUY_PRICE_BUFFER_PCT
        ).quantize(PCT_QUANT)
        reserve_pct = (
            policy.rebalance_capacity.hard_cash_reserve_pct_nav
            if policy is not None
            else Decimal("0.0000")
        ).quantize(PCT_QUANT)
        hard_reserve = _pct_to_notional(reserve_pct, plan_input.nav_inr)
        spendable_after_reserve = max(
            Decimal("0.00"),
            _money(plan_input.current_cash_inr) - hard_reserve,
        ).quantize(MONEY_QUANT)
        cash_budget = _cash_budget_rows(
            current_cash=plan_input.current_cash_inr,
            hard_reserve=hard_reserve,
            spendable_after_reserve=spendable_after_reserve,
            planned_trades=planned_trades,
            same_run_sell_proceeds_haircut_pct=haircut_pct,
            cost_model=_cost_model(plan_input),
        )
        proceeds_summary = _same_run_proceeds_summary(cash_budget)
        return PortfolioRebalancePlan(
            plan_id=f"portfolio-plan-{plan_input.run_id}",
            run_id=plan_input.run_id,
            portfolio_id=plan_input.portfolio_id,
            policy_version=policy.policy_version
            if policy is not None
            else plan_input.fallback_policy_source,
            as_of=_aware_datetime(plan_input.as_of),
            current_nav_inr=_money(plan_input.nav_inr),
            current_cash_inr=_money(plan_input.current_cash_inr),
            hard_cash_reserve_pct_nav=reserve_pct,
            hard_cash_reserve_inr=hard_reserve,
            spendable_cash_before_reserve_inr=_money(plan_input.current_cash_inr),
            spendable_cash_after_reserve_inr=spendable_after_reserve,
            same_run_sell_proceeds_haircut_pct=haircut_pct,
            same_run_sell_proceeds_gross_inr=proceeds_summary["gross"],
            same_run_sell_proceeds_cost_inr=proceeds_summary["cost"],
            same_run_sell_proceeds_net_inr=proceeds_summary["net"],
            same_run_sell_proceeds_spendable_inr=proceeds_summary["spendable"],
            same_run_sell_proceeds_safety_reserve_inr=proceeds_summary[
                "safety_reserve"
            ],
            buy_price_buffer_pct=buy_price_buffer_pct,
            soft_borrowing_enabled=(
                bool(policy.rebalance_capacity.soft_borrowing_enabled)
                if policy is not None
                else False
            ),
            max_borrowed_capacity_pct_nav=(
                policy.rebalance_capacity.max_borrowed_capacity_pct_nav
                if policy is not None
                else None
            ),
            max_borrowed_capacity_inr=(
                policy.rebalance_capacity.max_borrowed_capacity_inr
                if policy is not None
                else None
            ),
            positions=positions,
            candidates=candidates,
            core_basket_target_weights=target_weights,
            core_basket_advisory_decisions=tuple(
                _json_safe(row) for row in _core_decisions(core_artifact)
            ),
            planned_trades=planned_trades,
            cash_budget=cash_budget,
            sleeve_budgets=_sleeve_budget_rows(
                plan_input,
                positions=positions,
                planned_trades=planned_trades,
                candidates=candidates,
            ),
            constraints=(
                PortfolioPlanConstraint(
                    constraint_id="portfolio_rebalance_execution_scope",
                    status="informational",
                    message=(
                        "Portfolio plan is the default source for executable BUY, "
                        "REDUCE, and EXIT rebalance proposals before paper-only risk, "
                        "final approval, and next-open routing."
                    ),
                ),
            ),
        )


def _position_rows(
    plan_input: PortfolioRebalancePlanInput,
    *,
    core_symbols: tuple[str, ...],
) -> tuple[PortfolioPlanPosition, ...]:
    core_symbol_set = {symbol.upper() for symbol in core_symbols}
    rows = []
    for position in sorted(
        plan_input.current_positions,
        key=lambda item: item.symbol.upper(),
    ):
        sleeve_id, source = _sleeve_label_for_position(
            position.symbol,
            core_symbols=core_symbol_set,
            sleeve_by_symbol=plan_input.sleeve_by_symbol,
            policy=plan_input.money_management_policy,
        )
        rows.append(
            PortfolioPlanPosition(
                symbol=position.symbol,
                quantity=position.quantity,
                market_value_inr=_money(position.market_value_inr),
                current_pct_nav=_pct_of_nav(
                    position.market_value_inr, plan_input.nav_inr
                ),
                sleeve_id=sleeve_id,
                sleeve_label_source=source,
            )
        )
    return tuple(rows)


def _trader_candidate_rows(
    plan_input: PortfolioRebalancePlanInput,
) -> tuple[PortfolioPlanCandidate, ...]:
    rows = []
    for proposal in sorted(
        plan_input.proposals, key=lambda item: (item.symbol, item.proposal_id)
    ):
        symbol = proposal.symbol.upper()
        rank = _strategy_rank(plan_input, symbol)
        raw_score = _strategy_score(plan_input, symbol)
        calibration = calibrate_strategy_score(raw_score, strategy_rank=rank)
        sleeve_id = _sleeve_id_for_strategy(
            policy=plan_input.money_management_policy,
            strategy_name=plan_input.strategy_name,
            fallback_policy_source=plan_input.fallback_policy_source,
        )
        action = proposal.action
        target_pct = proposal.target_position_pct_nav
        score_evidence: dict[str, Any] = {}
        threshold = _threshold_action_for_position(
            plan_input,
            symbol=symbol,
            current_pct=proposal.current_position_pct_nav,
            current_quantity=proposal.current_position_quantity,
            sleeve_id=sleeve_id,
            raw_score=raw_score,
            existing_action=proposal.action,
        )
        if threshold is not None:
            action = threshold["action"]
            target_pct = threshold["target_pct"]
            score_evidence = {
                "threshold_reason": threshold["reason"],
                "threshold_source": THRESHOLD_REBALANCE_SOURCE,
                **threshold["metadata"],
            }
        rows.append(
            PortfolioPlanCandidate(
                candidate_id=f"candidate-{proposal.proposal_id}",
                symbol=symbol,
                proposal_id=proposal.proposal_id,
                action=action,
                source="trader_proposal",
                sleeve_id=sleeve_id,
                strategy_name=plan_input.strategy_name,
                strategy_rank=rank,
                raw_strategy_score=raw_score,
                calibrated_strategy_score=calibration.calibrated_strategy_score,
                allocation_score_component=calibration.allocation_score_component,
                score_calibration_method=calibration.method,
                confidence=proposal.confidence,
                requested_position_pct_nav=proposal.requested_position_pct_nav,
                current_position_pct_nav=proposal.current_position_pct_nav,
                target_position_pct_nav=target_pct,
                requested_notional_inr=_requested_notional(
                    current_pct=proposal.current_position_pct_nav,
                    target_pct=target_pct,
                    nav_inr=plan_input.nav_inr,
                ),
                latest_price_inr=_latest_close(
                    plan_input.histories_by_symbol.get(symbol, tuple())
                ),
                score_evidence=score_evidence,
                decision_status="approved" if threshold is not None else None,
            )
        )
    return tuple(rows)


def _core_candidate_rows(
    plan_input: PortfolioRebalancePlanInput,
    core_artifact: Mapping[str, Any],
) -> tuple[PortfolioPlanCandidate, ...]:
    score_by_symbol, rank_by_symbol = _core_selection_score_maps(core_artifact)
    rejection_reasons = _core_rejection_reasons_by_symbol(core_artifact)
    rows = []
    for decision in _core_decisions(core_artifact):
        symbol = str(decision.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        target_pct = _as_decimal(decision.get("target_weight_pct_nav")).quantize(
            PCT_QUANT
        )
        current_pct = _as_decimal(decision.get("current_weight_pct_nav")).quantize(
            PCT_QUANT
        )
        action = _core_candidate_action(
            decision, target_pct=target_pct, current_pct=current_pct
        )
        score_evidence = score_by_symbol.get(symbol, {})
        raw_score = (
            _as_decimal(score_evidence.get("rank_score")).quantize(PCT_QUANT)
            if score_evidence
            else None
        )
        score_component = _core_score_component(raw_score)
        decision_status = str(decision.get("status") or "").strip().lower() or None
        rows.append(
            PortfolioPlanCandidate(
                candidate_id=f"candidate-core-{symbol.lower()}",
                symbol=symbol,
                proposal_id=None,
                action=action,
                source=CORE_STRATEGY_NAME,
                sleeve_id=CORE_SLEEVE_ID,
                strategy_name=CORE_STRATEGY_NAME,
                strategy_rank=rank_by_symbol.get(symbol),
                raw_strategy_score=raw_score,
                calibrated_strategy_score=score_component,
                allocation_score_component=score_component,
                score_calibration_method=(
                    "core_rank_score_observed_v1"
                    if raw_score is not None
                    else "core_missing_score_default_v1"
                ),
                confidence=Decimal("1.0000")
                if decision_status == "approved"
                else Decimal("0.5000"),
                requested_position_pct_nav=target_pct,
                current_position_pct_nav=current_pct,
                target_position_pct_nav=target_pct,
                requested_notional_inr=_money(
                    _as_decimal(decision.get("trade_notional_inr"))
                ),
                latest_price_inr=_latest_close(
                    plan_input.histories_by_symbol.get(symbol, tuple())
                ),
                score_evidence=_json_safe(score_evidence),
                rejection_reasons=tuple(rejection_reasons.get(symbol, tuple())),
                decision_status=decision_status,
            )
        )
    return tuple(rows)


def _threshold_position_candidate_rows(
    plan_input: PortfolioRebalancePlanInput,
    *,
    positions: tuple[PortfolioPlanPosition, ...],
    existing_candidates: tuple[PortfolioPlanCandidate, ...],
) -> tuple[PortfolioPlanCandidate, ...]:
    existing_symbols = {candidate.symbol.upper() for candidate in existing_candidates}
    rows: list[PortfolioPlanCandidate] = []
    for position in positions:
        symbol = position.symbol.upper()
        if symbol in existing_symbols:
            continue
        raw_score = _strategy_score(plan_input, symbol)
        threshold = _threshold_action_for_position(
            plan_input,
            symbol=symbol,
            current_pct=position.current_pct_nav,
            current_quantity=position.quantity,
            sleeve_id=position.sleeve_id,
            raw_score=raw_score,
            existing_action="HOLD",
        )
        if threshold is None:
            continue
        rank = _strategy_rank(plan_input, symbol)
        calibration = calibrate_strategy_score(raw_score, strategy_rank=rank)
        target_pct = threshold["target_pct"]
        rows.append(
            PortfolioPlanCandidate(
                candidate_id=f"candidate-threshold-{symbol.lower()}",
                symbol=symbol,
                proposal_id=None,
                action=threshold["action"],
                source=THRESHOLD_REBALANCE_SOURCE,
                sleeve_id=position.sleeve_id,
                strategy_name=plan_input.strategy_name,
                strategy_rank=rank,
                raw_strategy_score=raw_score,
                calibrated_strategy_score=calibration.calibrated_strategy_score,
                allocation_score_component=calibration.allocation_score_component,
                score_calibration_method=calibration.method,
                confidence=Decimal("1.0000"),
                requested_position_pct_nav=target_pct,
                current_position_pct_nav=position.current_pct_nav,
                target_position_pct_nav=target_pct,
                requested_notional_inr=_requested_notional(
                    current_pct=position.current_pct_nav,
                    target_pct=target_pct,
                    nav_inr=plan_input.nav_inr,
                ),
                latest_price_inr=_latest_close(
                    plan_input.histories_by_symbol.get(symbol, tuple())
                ),
                score_evidence={
                    "threshold_reason": threshold["reason"],
                    "threshold_source": THRESHOLD_REBALANCE_SOURCE,
                    **threshold["metadata"],
                },
                decision_status="approved",
            )
        )
    return tuple(rows)


def _threshold_action_for_position(
    plan_input: PortfolioRebalancePlanInput,
    *,
    symbol: str,
    current_pct: Decimal,
    current_quantity: int,
    sleeve_id: str,
    raw_score: Decimal | None,
    existing_action: str,
) -> dict[str, Any] | None:
    policy = plan_input.money_management_policy
    if policy is None or current_quantity <= 0 or current_pct <= 0:
        return None
    if existing_action.upper() in {"REDUCE", "EXIT", "SELL"}:
        return None

    rebalance = policy.rebalance
    normalized = symbol.upper()
    core_targets = _core_target_weights(dict(plan_input.core_basket_artifact or {}))
    core_review_available = bool(core_targets or plan_input.core_basket_symbols)

    if (
        sleeve_id == CORE_SLEEVE_ID
        and core_review_available
        and normalized not in core_targets
    ):
        return _threshold_result(
            action="EXIT",
            target_pct=Decimal("0.0000"),
            reason="core_symbol_removed_from_target_basket",
            current_pct=current_pct,
            nav_inr=plan_input.nav_inr,
            policy=policy,
            metadata={"core_target_present": False},
        )

    if (
        rebalance.stale_unmapped_exit_enabled
        and sleeve_id not in ALLOCATABLE_SLEEVE_IDS
        and sleeve_id != "cash_buffer"
    ):
        return _threshold_result(
            action="EXIT",
            target_pct=Decimal("0.0000"),
            reason="stale_unmapped_sleeve_cleanup",
            current_pct=current_pct,
            nav_inr=plan_input.nav_inr,
            policy=policy,
            metadata={"sleeve_id": sleeve_id},
        )

    if raw_score is not None and raw_score <= rebalance.score_below_exit_threshold:
        return _threshold_result(
            action="EXIT",
            target_pct=Decimal("0.0000"),
            reason="strategy_score_below_exit_threshold",
            current_pct=current_pct,
            nav_inr=plan_input.nav_inr,
            policy=policy,
            metadata={
                "raw_strategy_score": str(raw_score.quantize(PCT_QUANT)),
                "score_below_exit_threshold": str(
                    rebalance.score_below_exit_threshold.quantize(PCT_QUANT)
                ),
            },
        )

    if (
        rebalance.over_hard_cap_trim_enabled
        and current_pct > policy.limits.max_stock_hard_cap_pct_nav
    ):
        target_pct = min(
            policy.limits.max_stock_pct_nav,
            policy.limits.max_stock_hard_cap_pct_nav,
        ).quantize(PCT_QUANT)
        return _threshold_result(
            action="REDUCE",
            target_pct=target_pct,
            reason="position_over_hard_cap_trim",
            current_pct=current_pct,
            nav_inr=plan_input.nav_inr,
            policy=policy,
            metadata={
                "max_stock_pct_nav": str(policy.limits.max_stock_pct_nav),
                "max_stock_hard_cap_pct_nav": str(
                    policy.limits.max_stock_hard_cap_pct_nav
                ),
            },
        )

    if raw_score is not None and raw_score <= rebalance.score_below_trim_threshold:
        target_pct = (current_pct / Decimal("2")).quantize(PCT_QUANT)
        return _threshold_result(
            action="REDUCE",
            target_pct=target_pct,
            reason="strategy_score_below_trim_threshold",
            current_pct=current_pct,
            nav_inr=plan_input.nav_inr,
            policy=policy,
            metadata={
                "raw_strategy_score": str(raw_score.quantize(PCT_QUANT)),
                "score_below_trim_threshold": str(
                    rebalance.score_below_trim_threshold.quantize(PCT_QUANT)
                ),
            },
        )

    if sleeve_id == CORE_SLEEVE_ID and core_review_available:
        target_pct = core_targets.get(normalized)
        if target_pct is not None and target_pct < current_pct:
            action = "EXIT" if target_pct <= 0 else "REDUCE"
            return _threshold_result(
                action=action,
                target_pct=target_pct.quantize(PCT_QUANT),
                reason="core_target_weight_below_current_position",
                current_pct=current_pct,
                nav_inr=plan_input.nav_inr,
                policy=policy,
                metadata={"core_target_pct_nav": str(target_pct.quantize(PCT_QUANT))},
            )

    return None


def _threshold_result(
    *,
    action: str,
    target_pct: Decimal,
    reason: str,
    current_pct: Decimal,
    nav_inr: Decimal,
    policy: MoneyManagementPolicy,
    metadata: dict[str, Any],
) -> dict[str, Any] | None:
    target_pct = max(Decimal("0.0000"), target_pct).quantize(PCT_QUANT)
    drift_pct = max(Decimal("0.0000"), current_pct - target_pct).quantize(PCT_QUANT)
    trade_notional = _pct_to_notional(drift_pct, nav_inr)
    if drift_pct < policy.rebalance.min_trade_drift_pct_nav:
        return None
    if trade_notional < policy.rebalance.min_rebalance_notional_inr:
        return None
    return {
        "action": action,
        "target_pct": target_pct,
        "reason": reason,
        "metadata": {
            **metadata,
            "min_trade_drift_pct_nav": str(
                policy.rebalance.min_trade_drift_pct_nav.quantize(PCT_QUANT)
            ),
            "min_rebalance_notional_inr": str(
                policy.rebalance.min_rebalance_notional_inr.quantize(MONEY_QUANT)
            ),
            "planned_drift_pct_nav": str(drift_pct),
            "planned_trade_notional_inr": str(trade_notional),
        },
    }


def _trade_from_candidate(
    plan_input: PortfolioRebalancePlanInput,
    candidate: PortfolioPlanCandidate,
) -> PortfolioPlanTrade:
    delta_pct = (
        candidate.target_position_pct_nav - candidate.current_position_pct_nav
    ).quantize(PCT_QUANT)
    action = candidate.action.upper()
    side: PlanSide
    if action == "BUY" and delta_pct > 0:
        side = "BUY"
    elif action in {"SELL", "REDUCE", "EXIT"} and delta_pct < 0:
        side = "SELL"
    else:
        side = "HOLD"
        delta_pct = Decimal("0.0000")

    latest_price = candidate.latest_price_inr
    notional = _pct_to_notional(abs(delta_pct), plan_input.nav_inr)
    quantity = _estimated_quantity(
        notional=notional,
        latest_price=latest_price,
        max_quantity=_current_quantity_for(plan_input, candidate.symbol)
        if side == "SELL"
        else None,
        exit_all=action == "EXIT",
    )
    constraints = [
        PortfolioPlanConstraint(
            constraint_id="paper_risk_final_routing_scope",
            status="informational",
            message=(
                "Portfolio-plan BUY, REDUCE, and EXIT rows must pass paper-only "
                "risk review, final approval, and next-open routing."
            ),
        )
    ]
    if candidate.source == CORE_STRATEGY_NAME:
        constraints.append(
            PortfolioPlanConstraint(
                constraint_id="core_rebalance_routing_scope",
                status="informational",
                message=(
                    "Core basket BUY, REDUCE, and EXIT candidates can become "
                    "planner-generated paper proposal inputs."
                ),
            )
        )
    status: PlanTradeStatus = "observed"
    if side == "HOLD" or notional <= 0:
        status = "no_trade"
    elif latest_price is None or latest_price <= 0:
        status = "missing_price"
        constraints.append(
            PortfolioPlanConstraint(
                constraint_id="latest_price_missing",
                status="blocked",
                message="No latest close was available for planner quantity estimation.",
            )
        )
    elif side == "BUY":
        constraints.append(
            PortfolioPlanConstraint(
                constraint_id="hard_cash_reserve_observed",
                status="informational",
                message="BUY row observes the hard cash reserve before executable allocation.",
            )
        )
    else:
        constraints.append(
            PortfolioPlanConstraint(
                constraint_id="same_run_proceeds_haircut_applied",
                status="informational",
                message=(
                    "Sell proceeds are forecast net of estimated paper costs and "
                    "only the configured haircut share is spendable by same-run BUY sizing."
                ),
            )
        )
    sleeve_id = (
        _sleeve_id_for_existing_holding(plan_input, candidate.symbol)
        if side == "SELL"
        else candidate.sleeve_id
    )
    return PortfolioPlanTrade(
        trade_id=_trade_id_for_candidate(candidate),
        symbol=candidate.symbol,
        proposal_id=candidate.proposal_id,
        side=side,
        action=action,
        source=candidate.source,
        sleeve_id=sleeve_id,
        rank=candidate.strategy_rank,
        target_pct_nav=candidate.target_position_pct_nav,
        current_pct_nav=candidate.current_position_pct_nav,
        delta_pct_nav=delta_pct,
        estimated_notional_inr=notional,
        estimated_quantity=quantity,
        latest_price_inr=latest_price,
        constraints=tuple(constraints),
        status=status,
    )


def _trade_id_for_candidate(candidate: PortfolioPlanCandidate) -> str:
    if candidate.proposal_id:
        return f"trade-{candidate.proposal_id}"
    if candidate.source == CORE_STRATEGY_NAME:
        return f"trade-core-{candidate.symbol.lower()}"
    return f"trade-{candidate.candidate_id}"


def _core_candidate_action(
    decision: Mapping[str, Any],
    *,
    target_pct: Decimal,
    current_pct: Decimal,
) -> str:
    status = str(decision.get("status") or "").strip().lower()
    if status != "approved":
        return "HOLD"
    side = str(decision.get("side") or "HOLD").strip().upper()
    if side == "BUY":
        return "BUY"
    if side == "SELL":
        return "EXIT" if target_pct <= 0 and current_pct > 0 else "REDUCE"
    return "HOLD"


def _core_score_component(raw_score: Decimal | None) -> Decimal:
    if raw_score is None:
        return Decimal("50.0000")
    return max(Decimal("0"), min(Decimal("100"), raw_score)).quantize(PCT_QUANT)


def _core_selection_score_maps(
    core_artifact: Mapping[str, Any],
) -> tuple[dict[str, dict[str, Any]], dict[str, int]]:
    selection_scores = core_artifact.get("selection_scores")
    if not isinstance(selection_scores, list | tuple):
        return {}, {}
    scores: dict[str, dict[str, Any]] = {}
    ranks: dict[str, int] = {}
    for rank, row in enumerate(selection_scores, start=1):
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        scores[symbol] = _json_safe(dict(row))
        ranks[symbol] = rank
    return scores, ranks


def _core_rejection_reasons_by_symbol(
    core_artifact: Mapping[str, Any],
) -> dict[str, tuple[str, ...]]:
    rejected = core_artifact.get("rejected_candidates")
    if not isinstance(rejected, list | tuple):
        return {}
    reasons_by_symbol: dict[str, tuple[str, ...]] = {}
    for row in rejected:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol") or "").strip().upper()
        reasons = row.get("reasons")
        if not symbol or not isinstance(reasons, list | tuple):
            continue
        reasons_by_symbol[symbol] = tuple(str(reason) for reason in reasons)
    return reasons_by_symbol


def _cash_budget_rows(
    *,
    current_cash: Decimal,
    hard_reserve: Decimal,
    spendable_after_reserve: Decimal,
    planned_trades: tuple[PortfolioPlanTrade, ...],
    same_run_sell_proceeds_haircut_pct: Decimal,
    cost_model: IndiaPaperCostModel,
) -> tuple[PortfolioPlanCashBudget, ...]:
    forecast_sell_gross = sum(
        (
            trade.estimated_notional_inr
            for trade in planned_trades
            if trade.side == "SELL" and trade.status != "missing_price"
        ),
        Decimal("0.00"),
    ).quantize(MONEY_QUANT)
    forecast_sell_costs = sum(
        (
            cost_model.calculate(trade.estimated_notional_inr).total_inr
            for trade in planned_trades
            if trade.side == "SELL" and trade.status != "missing_price"
        ),
        Decimal("0.00"),
    ).quantize(MONEY_QUANT)
    forecast_sell_proceeds = max(
        Decimal("0.00"),
        forecast_sell_gross - forecast_sell_costs,
    ).quantize(MONEY_QUANT)
    spendable_same_run_proceeds = (
        forecast_sell_proceeds * same_run_sell_proceeds_haircut_pct / Decimal("100")
    ).quantize(MONEY_QUANT)
    unspendable_same_run_proceeds = (
        forecast_sell_proceeds - spendable_same_run_proceeds
    ).quantize(MONEY_QUANT)
    estimated_buy_notional = sum(
        (
            trade.estimated_notional_inr
            for trade in planned_trades
            if trade.side == "BUY" and trade.status != "missing_price"
        ),
        Decimal("0.00"),
    ).quantize(MONEY_QUANT)
    unallocated = (
        spendable_after_reserve + spendable_same_run_proceeds - estimated_buy_notional
    ).quantize(MONEY_QUANT)
    return (
        PortfolioPlanCashBudget(
            row_id="existing_cash",
            label="Existing cash",
            amount_inr=_money(current_cash),
            spendable=True,
            description="Current paper account cash before the portfolio plan.",
        ),
        PortfolioPlanCashBudget(
            row_id="reserved_cash",
            label="Reserved cash",
            amount_inr=hard_reserve,
            spendable=False,
            description="Hard cash reserve protected from portfolio-plan BUY sizing.",
        ),
        PortfolioPlanCashBudget(
            row_id="forecast_sell_proceeds_gross",
            label="Forecast sell proceeds gross",
            amount_inr=forecast_sell_gross,
            spendable=False,
            description="Gross latest-close notional from planned REDUCE/EXIT rows.",
        ),
        PortfolioPlanCashBudget(
            row_id="forecast_sell_costs",
            label="Estimated sell costs",
            amount_inr=forecast_sell_costs,
            spendable=False,
            description="Estimated paper costs deducted from forecast sell proceeds.",
        ),
        PortfolioPlanCashBudget(
            row_id="forecast_sell_proceeds",
            label="Forecast sell proceeds net",
            amount_inr=forecast_sell_proceeds,
            spendable=False,
            description="Forecast REDUCE/EXIT proceeds after estimated paper costs.",
        ),
        PortfolioPlanCashBudget(
            row_id="spendable_same_run_proceeds",
            label="Spendable same-run proceeds",
            amount_inr=spendable_same_run_proceeds,
            spendable=True,
            description=(
                "Forecast sell proceeds after the current "
                f"{same_run_sell_proceeds_haircut_pct}% spendable haircut."
            ),
        ),
        PortfolioPlanCashBudget(
            row_id="unspendable_same_run_proceeds",
            label="Same-run proceeds safety reserve",
            amount_inr=unspendable_same_run_proceeds,
            spendable=False,
            description="Unspendable haircut reserve held back from same-run BUY sizing.",
        ),
        PortfolioPlanCashBudget(
            row_id="unallocated_cash",
            label="Unallocated cash",
            amount_inr=unallocated,
            spendable=unallocated > 0,
            description="Plan residual after reserve, spendable proceeds, and observed BUY rows.",
        ),
    )


def _same_run_proceeds_summary(
    cash_budget: tuple[PortfolioPlanCashBudget, ...],
) -> dict[str, Decimal]:
    rows = {row.row_id: row.amount_inr for row in cash_budget}
    return {
        "gross": _money(rows.get("forecast_sell_proceeds_gross", Decimal("0.00"))),
        "cost": _money(rows.get("forecast_sell_costs", Decimal("0.00"))),
        "net": _money(rows.get("forecast_sell_proceeds", Decimal("0.00"))),
        "spendable": _money(rows.get("spendable_same_run_proceeds", Decimal("0.00"))),
        "safety_reserve": _money(
            rows.get("unspendable_same_run_proceeds", Decimal("0.00"))
        ),
    }


def _cost_model(plan_input: PortfolioRebalancePlanInput) -> IndiaPaperCostModel:
    return IndiaPaperCostModel(
        brokerage_bps=plan_input.paper_brokerage_bps,
        exchange_txn_charge_bps=plan_input.paper_exchange_txn_charge_bps,
        tax_levy_bps=plan_input.paper_tax_levy_bps,
    )


def _sleeve_budget_rows(
    plan_input: PortfolioRebalancePlanInput,
    *,
    positions: tuple[PortfolioPlanPosition, ...],
    planned_trades: tuple[PortfolioPlanTrade, ...],
    candidates: tuple[PortfolioPlanCandidate, ...],
) -> tuple[PortfolioPlanSleeveBudget, ...]:
    policy = plan_input.money_management_policy
    deltas = _trade_deltas_by_sleeve(planned_trades)
    if policy is None:
        current = sum(
            (position.market_value_inr for position in positions), Decimal("0.00")
        )
        target = _money(plan_input.nav_inr)
        projected = max(
            Decimal("0.00"), current + deltas.get("settings_fallback", Decimal("0.00"))
        )
        return (
            PortfolioPlanSleeveBudget(
                sleeve_id="settings_fallback",
                sleeve_name="Settings fallback",
                target_pct_nav=Decimal("100.0000"),
                current_pct_nav=_pct_of_nav(current, plan_input.nav_inr),
                target_exposure_inr=target,
                current_exposure_inr=_money(current),
                idle_capacity_inr=max(Decimal("0.00"), target - current).quantize(
                    MONEY_QUANT
                ),
                protected_capacity_inr=Decimal("0.00"),
                borrowable_capacity_inr=Decimal("0.00"),
                borrowed_capacity_inr=Decimal("0.00"),
                projected_exposure_inr=_money(projected),
                projected_pct_nav=_pct_of_nav(projected, plan_input.nav_inr),
            ),
        )

    snapshot_by_sleeve = {
        snapshot.sleeve_id: snapshot for snapshot in plan_input.sleeve_snapshots
    }
    position_exposure_by_sleeve: dict[str, Decimal] = {}
    for position in positions:
        position_exposure_by_sleeve[position.sleeve_id] = (
            position_exposure_by_sleeve.get(position.sleeve_id, Decimal("0.00"))
            + position.market_value_inr
        ).quantize(MONEY_QUANT)

    capacity = policy.rebalance_capacity
    borrower_ids = set(capacity.borrower_sleeve_ids)
    borrowable_ids = set(capacity.borrowable_sleeve_ids)
    deployed_buy_by_sleeve = _deployable_buy_notional_by_sleeve(candidates)
    row_inputs: dict[str, dict[str, Any]] = {}
    for sleeve in policy.sleeves:
        target = _pct_to_notional(sleeve.target_weight_pct, plan_input.nav_inr)
        snapshot = snapshot_by_sleeve.get(sleeve.sleeve_id)
        current = (
            snapshot.current_exposure_inr
            if snapshot is not None
            else position_exposure_by_sleeve.get(sleeve.sleeve_id, Decimal("0.00"))
        )
        current = _money(current)
        projected = max(
            Decimal("0.00"),
            current + deltas.get(sleeve.sleeve_id, Decimal("0.00")),
        ).quantize(MONEY_QUANT)
        raw_capacity = max(Decimal("0.00"), target - current).quantize(MONEY_QUANT)
        has_deployable_buy = (
            deployed_buy_by_sleeve.get(sleeve.sleeve_id, Decimal("0.00")) > 0
        )
        freeze_reason = _sleeve_freeze_reason(sleeve, snapshot)
        idle_capacity = (
            raw_capacity
            if raw_capacity > 0 and not has_deployable_buy
            else Decimal("0.00")
        )
        protected_capacity = Decimal("0.00")
        borrowable_capacity = Decimal("0.00")
        idle_reason: str | None = None

        if sleeve.sleeve_id == "cash_buffer":
            protected_capacity = _pct_to_notional(
                capacity.hard_cash_reserve_pct_nav,
                plan_input.nav_inr,
            )
            idle_capacity = Decimal("0.00")
            idle_reason = "hard_cash_reserve_non_borrowable"
        elif raw_capacity <= 0:
            idle_reason = "sleeve_at_or_above_target"
        elif has_deployable_buy:
            protected_capacity = raw_capacity
            idle_reason = "own_executable_candidate_available"
        elif freeze_reason is not None:
            protected_capacity = raw_capacity
            idle_reason = freeze_reason
        elif not capacity.soft_borrowing_enabled:
            protected_capacity = raw_capacity
            idle_reason = "soft_borrowing_disabled"
        elif sleeve.sleeve_id not in borrowable_ids:
            protected_capacity = raw_capacity
            idle_reason = "sleeve_not_borrowable_by_policy"
        elif sleeve.sleeve_id in borrower_ids:
            protected_capacity = raw_capacity
            idle_reason = "borrower_sleeve_not_lender"
        else:
            borrowable_capacity = idle_capacity
            idle_reason = "borrowable_idle_capacity"

        row_inputs[sleeve.sleeve_id] = {
            "sleeve": sleeve,
            "target": target,
            "current": current,
            "projected": projected,
            "idle_capacity": idle_capacity,
            "protected_capacity": protected_capacity,
            "borrowable_capacity": borrowable_capacity,
            "remaining_borrowable_capacity": borrowable_capacity,
            "borrowed_capacity": Decimal("0.00"),
            "borrowed_by_sleeve_id": None,
            "idle_reason": idle_reason,
        }

    _assign_soft_borrowing(
        row_inputs,
        policy=policy,
        nav_inr=plan_input.nav_inr,
    )

    rows = []
    for sleeve in policy.sleeves:
        row = row_inputs[sleeve.sleeve_id]
        rows.append(
            PortfolioPlanSleeveBudget(
                sleeve_id=sleeve.sleeve_id,
                sleeve_name=sleeve.name,
                target_pct_nav=sleeve.target_weight_pct,
                current_pct_nav=_pct_of_nav(row["current"], plan_input.nav_inr),
                target_exposure_inr=row["target"],
                current_exposure_inr=row["current"],
                idle_capacity_inr=row["idle_capacity"],
                protected_capacity_inr=row["protected_capacity"],
                borrowable_capacity_inr=row["borrowable_capacity"],
                borrowed_capacity_inr=row["borrowed_capacity"],
                borrowed_by_sleeve_id=row["borrowed_by_sleeve_id"],
                idle_reason=row["idle_reason"],
                projected_exposure_inr=row["projected"],
                projected_pct_nav=_pct_of_nav(row["projected"], plan_input.nav_inr),
            )
        )
    return tuple(rows)


def _trade_deltas_by_sleeve(
    planned_trades: tuple[PortfolioPlanTrade, ...],
) -> dict[str, Decimal]:
    deltas: dict[str, Decimal] = {}
    for trade in planned_trades:
        if trade.status in {"missing_price", "no_trade"}:
            continue
        multiplier = Decimal("1") if trade.side == "BUY" else Decimal("-1")
        deltas[trade.sleeve_id] = (
            deltas.get(trade.sleeve_id, Decimal("0.00"))
            + (trade.estimated_notional_inr * multiplier)
        ).quantize(MONEY_QUANT)
    return deltas


def _deployable_buy_notional_by_sleeve(
    candidates: tuple[PortfolioPlanCandidate, ...],
) -> dict[str, Decimal]:
    deployed: dict[str, Decimal] = {}
    for candidate in candidates:
        if candidate.action.upper() != "BUY":
            continue
        if candidate.requested_notional_inr <= 0:
            continue
        if candidate.latest_price_inr is None or candidate.latest_price_inr <= 0:
            continue
        if candidate.decision_status not in {None, "approved"}:
            continue
        deployed[candidate.sleeve_id] = (
            deployed.get(candidate.sleeve_id, Decimal("0.00"))
            + candidate.requested_notional_inr
        ).quantize(MONEY_QUANT)
    return deployed


def _sleeve_freeze_reason(
    sleeve: SleevePolicy,
    snapshot: SleeveAllocationSnapshot | None,
) -> str | None:
    if snapshot is None or sleeve.drawdown_freeze_threshold_pct is None:
        return None
    if snapshot.drawdown_pct > sleeve.drawdown_freeze_threshold_pct:
        return "sleeve_drawdown_freeze_protected"
    return None


def _assign_soft_borrowing(
    row_inputs: dict[str, dict[str, Any]],
    *,
    policy: MoneyManagementPolicy,
    nav_inr: Decimal,
) -> None:
    capacity = policy.rebalance_capacity
    if not capacity.soft_borrowing_enabled:
        return

    remaining_guard = _soft_borrow_guard(policy, nav_inr=nav_inr)
    if remaining_guard <= 0:
        return

    borrowable_order = tuple(capacity.borrowable_sleeve_ids)
    for borrower_id in capacity.borrower_sleeve_ids:
        borrower = row_inputs.get(borrower_id)
        if borrower is None:
            continue
        borrower_need = max(
            Decimal("0.00"),
            borrower["projected"] - borrower["target"],
        ).quantize(MONEY_QUANT)
        if borrower_need <= 0:
            continue
        borrower_need = min(borrower_need, remaining_guard).quantize(MONEY_QUANT)
        borrowed = Decimal("0.00")
        for lender_id in borrowable_order:
            if lender_id == borrower_id:
                continue
            lender = row_inputs.get(lender_id)
            if lender is None:
                continue
            available = lender["remaining_borrowable_capacity"]
            if available <= 0:
                continue
            amount = min(available, borrower_need - borrowed).quantize(MONEY_QUANT)
            if amount <= 0:
                continue
            lender["remaining_borrowable_capacity"] = (available - amount).quantize(
                MONEY_QUANT
            )
            lender["borrowed_by_sleeve_id"] = borrower_id
            borrower["borrowed_capacity"] = (
                borrower["borrowed_capacity"] + amount
            ).quantize(MONEY_QUANT)
            borrowed = (borrowed + amount).quantize(MONEY_QUANT)
            remaining_guard = (remaining_guard - amount).quantize(MONEY_QUANT)
            if borrowed >= borrower_need or remaining_guard <= 0:
                break
        if remaining_guard <= 0:
            break


def _soft_borrow_guard(policy: MoneyManagementPolicy, *, nav_inr: Decimal) -> Decimal:
    capacity = policy.rebalance_capacity
    guards: list[Decimal] = []
    if capacity.max_borrowed_capacity_pct_nav is not None:
        guards.append(_pct_to_notional(capacity.max_borrowed_capacity_pct_nav, nav_inr))
    if capacity.max_borrowed_capacity_inr is not None:
        guards.append(_money(capacity.max_borrowed_capacity_inr))
    if not guards:
        return Decimal("999999999999.99")
    return min(guards).quantize(MONEY_QUANT)


def _core_target_weights(core_artifact: Mapping[str, Any]) -> dict[str, Decimal]:
    target_weights = core_artifact.get("target_weights")
    if not isinstance(target_weights, Mapping):
        return {}
    weights: dict[str, Decimal] = {}
    for raw_symbol, raw_weight in target_weights.items():
        symbol = str(raw_symbol).strip().upper()
        if not symbol:
            continue
        weights[symbol] = _as_decimal(raw_weight).quantize(PCT_QUANT)
    return dict(sorted(weights.items()))


def _core_decisions(core_artifact: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    decisions = core_artifact.get("decisions")
    if not isinstance(decisions, list | tuple):
        return tuple()
    rows = [dict(row) for row in decisions if isinstance(row, Mapping)]
    return tuple(sorted(rows, key=lambda row: str(row.get("symbol") or "")))


def _sleeve_label_for_position(
    symbol: str,
    *,
    core_symbols: set[str],
    sleeve_by_symbol: Mapping[str, str],
    policy: MoneyManagementPolicy | None,
) -> tuple[str, str]:
    normalized = symbol.strip().upper()
    if normalized in core_symbols:
        return CORE_SLEEVE_ID, "core_basket_target_weights"
    mapped = str(sleeve_by_symbol.get(normalized) or "").strip().lower()
    if mapped:
        return mapped, "latest_allocation_decision"
    if policy is not None:
        sleeve_ids = {sleeve.sleeve_id for sleeve in policy.sleeves}
        if ACTIVE_SLEEVE_ID in sleeve_ids:
            return ACTIVE_SLEEVE_ID, "default_active_strategy"
    return "settings_fallback", "settings_fallback"


def _sleeve_id_for_existing_holding(
    plan_input: PortfolioRebalancePlanInput,
    symbol: str,
) -> str:
    target_weights = _core_target_weights(dict(plan_input.core_basket_artifact or {}))
    core_symbols = {
        *[item.upper() for item in plan_input.core_basket_symbols],
        *target_weights,
    }
    sleeve_id, _source = _sleeve_label_for_position(
        symbol,
        core_symbols=core_symbols,
        sleeve_by_symbol=plan_input.sleeve_by_symbol,
        policy=plan_input.money_management_policy,
    )
    return sleeve_id


def _sleeve_id_for_strategy(
    *,
    policy: MoneyManagementPolicy | None,
    strategy_name: str,
    fallback_policy_source: str,
) -> str:
    if policy is None:
        return "settings_fallback"
    for mapping in policy.strategy_mappings:
        if mapping.strategy_name == strategy_name:
            return mapping.sleeve_id
    return "unmapped"


def _strategy_rank(plan_input: PortfolioRebalancePlanInput, symbol: str) -> int | None:
    rank = plan_input.strategy_rank_by_symbol.get(symbol.upper())
    return int(rank) if rank is not None else None


def _strategy_score(
    plan_input: PortfolioRebalancePlanInput, symbol: str
) -> Decimal | None:
    score = plan_input.strategy_score_by_symbol.get(symbol.upper())
    return Decimal(str(score)) if score is not None else None


def _requested_notional(
    *,
    current_pct: Decimal,
    target_pct: Decimal,
    nav_inr: Decimal,
) -> Decimal:
    return _pct_to_notional(abs(target_pct - current_pct), nav_inr)


def _current_quantity_for(plan_input: PortfolioRebalancePlanInput, symbol: str) -> int:
    normalized = symbol.upper()
    for position in plan_input.current_positions:
        if position.symbol.upper() == normalized:
            return position.quantity
    return 0


def _estimated_quantity(
    *,
    notional: Decimal,
    latest_price: Decimal | None,
    max_quantity: int | None = None,
    exit_all: bool,
) -> int:
    if exit_all and max_quantity is not None:
        return max(max_quantity, 0)
    if latest_price is None or latest_price <= 0 or notional <= 0:
        return 0
    quantity = int((notional / latest_price).to_integral_value(rounding=ROUND_DOWN))
    if max_quantity is not None:
        return min(quantity, max(max_quantity, 0))
    return max(quantity, 0)


def _latest_close(history: tuple[DailyCandle, ...]) -> Decimal | None:
    if not history:
        return None
    return _money(sorted(history, key=lambda candle: candle.trade_date)[-1].close)


def _pct_to_notional(percent: Decimal, nav_inr: Decimal) -> Decimal:
    if percent <= 0 or nav_inr <= 0:
        return Decimal("0.00")
    return _money(nav_inr * percent / Decimal("100"))


def _pct_of_nav(amount: Decimal, nav_inr: Decimal) -> Decimal:
    if amount <= 0 or nav_inr <= 0:
        return Decimal("0.0000")
    return ((amount / nav_inr) * Decimal("100")).quantize(PCT_QUANT)


def _money(value: Decimal) -> Decimal:
    return Decimal(str(value)).quantize(MONEY_QUANT)


def _as_decimal(value: object) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal("0")


def _aware_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return _aware_datetime(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_json_safe(item) for item in value)
    return value
