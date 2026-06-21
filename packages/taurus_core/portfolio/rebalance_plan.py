from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taurus_core.domain.market_data import DailyCandle
from taurus_core.portfolio.active_allocation import (
    ACTIVE_SLEEVE_ID,
    ActiveAllocationPosition,
    SleeveAllocationSnapshot,
)
from taurus_core.portfolio.core_shariah_basket import CORE_SLEEVE_ID, CORE_STRATEGY_NAME
from taurus_core.portfolio.money_management import MoneyManagementPolicy
from taurus_core.portfolio.score_semantics import calibrate_strategy_score
from taurus_core.research.schemas import TraderProposal

PORTFOLIO_REBALANCE_PLAN_MODEL_VERSION = "portfolio_rebalance_dry_run_v1"
MONEY_QUANT = Decimal("0.01")
PCT_QUANT = Decimal("0.0001")
SAME_RUN_SELL_PROCEEDS_HAIRCUT_PCT = Decimal("80.0000")

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
    borrowed_capacity_inr: Decimal = Field(default=Decimal("0.00"), ge=Decimal("0"))
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
    same_run_sell_proceeds_haircut_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    positions: tuple[PortfolioPlanPosition, ...] = Field(default_factory=tuple)
    candidates: tuple[PortfolioPlanCandidate, ...] = Field(default_factory=tuple)
    core_basket_target_weights: dict[str, Decimal] = Field(default_factory=dict)
    core_basket_advisory_decisions: tuple[dict[str, Any], ...] = Field(default_factory=tuple)
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
    histories_by_symbol: Mapping[str, tuple[DailyCandle, ...]] = field(default_factory=dict)
    core_basket_artifact: Mapping[str, Any] | None = None
    core_basket_symbols: tuple[str, ...] = ()
    strategy_rank_by_symbol: Mapping[str, int] = field(default_factory=dict)
    strategy_score_by_symbol: Mapping[str, Decimal] = field(default_factory=dict)
    money_management_policy: MoneyManagementPolicy | None = None
    fallback_policy_source: str = "settings"
    sleeve_by_symbol: Mapping[str, str] = field(default_factory=dict)


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
        candidates = _candidate_rows(plan_input)
        planned_trades = tuple(
            sorted(
                [
                    *[
                        _trade_from_candidate(plan_input, candidate)
                        for candidate in candidates
                    ],
                    *[
                        _trade_from_core_decision(plan_input, row, rank=rank)
                        for rank, row in enumerate(_core_decisions(core_artifact), start=1)
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
        reserve_pct = (
            policy.cash_buffer_target_pct
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
        )
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
            same_run_sell_proceeds_haircut_pct=SAME_RUN_SELL_PROCEEDS_HAIRCUT_PCT,
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
            ),
            constraints=(
                PortfolioPlanConstraint(
                    constraint_id="dry_run_only",
                    status="informational",
                    message=(
                        "Portfolio plan is persisted for observability only; "
                        "run-level allocation remains the source of executable sizing."
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
                current_pct_nav=_pct_of_nav(position.market_value_inr, plan_input.nav_inr),
                sleeve_id=sleeve_id,
                sleeve_label_source=source,
            )
        )
    return tuple(rows)


def _candidate_rows(
    plan_input: PortfolioRebalancePlanInput,
) -> tuple[PortfolioPlanCandidate, ...]:
    rows = []
    for proposal in sorted(plan_input.proposals, key=lambda item: (item.symbol, item.proposal_id)):
        symbol = proposal.symbol.upper()
        rank = _strategy_rank(plan_input, symbol)
        raw_score = _strategy_score(plan_input, symbol)
        calibration = calibrate_strategy_score(raw_score, strategy_rank=rank)
        sleeve_id = _sleeve_id_for_strategy(
            policy=plan_input.money_management_policy,
            strategy_name=plan_input.strategy_name,
            fallback_policy_source=plan_input.fallback_policy_source,
        )
        rows.append(
            PortfolioPlanCandidate(
                candidate_id=f"candidate-{proposal.proposal_id}",
                symbol=symbol,
                proposal_id=proposal.proposal_id,
                action=proposal.action,
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
                target_position_pct_nav=proposal.target_position_pct_nav,
                requested_notional_inr=_requested_notional(
                    current_pct=proposal.current_position_pct_nav,
                    target_pct=proposal.target_position_pct_nav,
                    nav_inr=plan_input.nav_inr,
                ),
                latest_price_inr=_latest_close(
                    plan_input.histories_by_symbol.get(symbol, tuple())
                ),
            )
        )
    return tuple(rows)


def _trade_from_candidate(
    plan_input: PortfolioRebalancePlanInput,
    candidate: PortfolioPlanCandidate,
) -> PortfolioPlanTrade:
    delta_pct = (candidate.target_position_pct_nav - candidate.current_position_pct_nav).quantize(
        PCT_QUANT
    )
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
            constraint_id="dry_run_not_routed",
            status="informational",
            message="M57 portfolio-plan rows are not routed to risk, final approval, or broker execution.",
        )
    ]
    status: PlanTradeStatus = "observed"
    if side == "HOLD" or notional <= 0:
        status = "no_trade"
    elif latest_price is None or latest_price <= 0:
        status = "missing_price"
        constraints.append(
            PortfolioPlanConstraint(
                constraint_id="latest_price_missing",
                status="blocked",
                message="No latest close was available for dry-run quantity estimation.",
            )
        )
    elif side == "BUY":
        constraints.append(
            PortfolioPlanConstraint(
                constraint_id="hard_cash_reserve_observed",
                status="informational",
                message="Dry-run row observes the hard cash reserve but does not allocate cash.",
            )
        )
    else:
        constraints.append(
            PortfolioPlanConstraint(
                constraint_id="same_run_proceeds_haircut_observed",
                status="informational",
                message="Dry-run sell proceeds are tracked with the current 80% spendable haircut.",
            )
        )
    sleeve_id = (
        _sleeve_id_for_existing_holding(plan_input, candidate.symbol)
        if side == "SELL"
        else candidate.sleeve_id
    )
    return PortfolioPlanTrade(
        trade_id=f"trade-{candidate.proposal_id or candidate.symbol}",
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


def _trade_from_core_decision(
    plan_input: PortfolioRebalancePlanInput,
    decision: Mapping[str, Any],
    *,
    rank: int,
) -> PortfolioPlanTrade:
    symbol = str(decision.get("symbol") or "").strip().upper()
    side_text = str(decision.get("side") or "HOLD").strip().upper()
    side: PlanSide = "BUY" if side_text == "BUY" else "SELL" if side_text == "SELL" else "HOLD"
    target_pct = _as_decimal(decision.get("target_weight_pct_nav")).quantize(PCT_QUANT)
    current_pct = _as_decimal(decision.get("current_weight_pct_nav")).quantize(PCT_QUANT)
    delta_pct = _as_decimal(decision.get("drift_pct_nav")).quantize(PCT_QUANT)
    notional = _money(_as_decimal(decision.get("trade_notional_inr")))
    latest_price = _latest_close(plan_input.histories_by_symbol.get(symbol, tuple()))
    quantity = _estimated_quantity(
        notional=notional,
        latest_price=latest_price,
        max_quantity=_current_quantity_for(plan_input, symbol) if side == "SELL" else None,
        exit_all=False,
    )
    status: PlanTradeStatus = "advisory_only" if side != "HOLD" and notional > 0 else "no_trade"
    constraints = [
        PortfolioPlanConstraint(
            constraint_id="core_advisory_only",
            status="informational",
            message="Core basket decisions remain advisory in M57 and are not executable plan candidates.",
        )
    ]
    if side != "HOLD" and (latest_price is None or latest_price <= 0):
        status = "missing_price"
        constraints.append(
            PortfolioPlanConstraint(
                constraint_id="latest_price_missing",
                status="blocked",
                message="No latest close was available for core advisory quantity estimation.",
            )
        )
    return PortfolioPlanTrade(
        trade_id=f"core-advisory-{symbol}",
        symbol=symbol,
        proposal_id=None,
        side=side,
        action="BUY" if side == "BUY" else "REDUCE" if side == "SELL" else "HOLD",
        source=CORE_STRATEGY_NAME,
        sleeve_id=CORE_SLEEVE_ID,
        rank=rank,
        target_pct_nav=target_pct,
        current_pct_nav=current_pct,
        delta_pct_nav=delta_pct,
        estimated_notional_inr=notional,
        estimated_quantity=quantity,
        latest_price_inr=latest_price,
        constraints=tuple(constraints),
        status=status,
    )


def _cash_budget_rows(
    *,
    current_cash: Decimal,
    hard_reserve: Decimal,
    spendable_after_reserve: Decimal,
    planned_trades: tuple[PortfolioPlanTrade, ...],
) -> tuple[PortfolioPlanCashBudget, ...]:
    forecast_sell_proceeds = sum(
        (
            trade.estimated_notional_inr
            for trade in planned_trades
            if trade.side == "SELL" and trade.status != "missing_price"
        ),
        Decimal("0.00"),
    ).quantize(MONEY_QUANT)
    spendable_same_run_proceeds = (
        forecast_sell_proceeds
        * SAME_RUN_SELL_PROCEEDS_HAIRCUT_PCT
        / Decimal("100")
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
            description="Current paper account cash before the dry-run portfolio plan.",
        ),
        PortfolioPlanCashBudget(
            row_id="reserved_cash",
            label="Reserved cash",
            amount_inr=hard_reserve,
            spendable=False,
            description="Hard cash reserve protected from dry-run BUY sizing.",
        ),
        PortfolioPlanCashBudget(
            row_id="forecast_sell_proceeds",
            label="Forecast sell proceeds",
            amount_inr=forecast_sell_proceeds,
            spendable=False,
            description="Gross notional from observed REDUCE/EXIT advisory rows.",
        ),
        PortfolioPlanCashBudget(
            row_id="spendable_same_run_proceeds",
            label="Spendable same-run proceeds",
            amount_inr=spendable_same_run_proceeds,
            spendable=True,
            description="Forecast sell proceeds after the current 80% spendable haircut.",
        ),
        PortfolioPlanCashBudget(
            row_id="unallocated_cash",
            label="Unallocated cash",
            amount_inr=unallocated,
            spendable=unallocated > 0,
            description="Dry-run residual after reserve, spendable proceeds, and observed BUY rows.",
        ),
    )


def _sleeve_budget_rows(
    plan_input: PortfolioRebalancePlanInput,
    *,
    positions: tuple[PortfolioPlanPosition, ...],
    planned_trades: tuple[PortfolioPlanTrade, ...],
) -> tuple[PortfolioPlanSleeveBudget, ...]:
    policy = plan_input.money_management_policy
    deltas = _trade_deltas_by_sleeve(planned_trades)
    if policy is None:
        current = sum((position.market_value_inr for position in positions), Decimal("0.00"))
        target = _money(plan_input.nav_inr)
        projected = max(Decimal("0.00"), current + deltas.get("settings_fallback", Decimal("0.00")))
        return (
            PortfolioPlanSleeveBudget(
                sleeve_id="settings_fallback",
                sleeve_name="Settings fallback",
                target_pct_nav=Decimal("100.0000"),
                current_pct_nav=_pct_of_nav(current, plan_input.nav_inr),
                target_exposure_inr=target,
                current_exposure_inr=_money(current),
                idle_capacity_inr=max(Decimal("0.00"), target - current).quantize(MONEY_QUANT),
                borrowed_capacity_inr=Decimal("0.00"),
                projected_exposure_inr=_money(projected),
                projected_pct_nav=_pct_of_nav(projected, plan_input.nav_inr),
            ),
        )

    snapshot_by_sleeve = {
        snapshot.sleeve_id: snapshot
        for snapshot in plan_input.sleeve_snapshots
    }
    position_exposure_by_sleeve: dict[str, Decimal] = {}
    for position in positions:
        position_exposure_by_sleeve[position.sleeve_id] = (
            position_exposure_by_sleeve.get(position.sleeve_id, Decimal("0.00"))
            + position.market_value_inr
        ).quantize(MONEY_QUANT)

    rows = []
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
        rows.append(
            PortfolioPlanSleeveBudget(
                sleeve_id=sleeve.sleeve_id,
                sleeve_name=sleeve.name,
                target_pct_nav=sleeve.target_weight_pct,
                current_pct_nav=_pct_of_nav(current, plan_input.nav_inr),
                target_exposure_inr=target,
                current_exposure_inr=current,
                idle_capacity_inr=max(Decimal("0.00"), target - current).quantize(
                    MONEY_QUANT
                ),
                borrowed_capacity_inr=Decimal("0.00"),
                projected_exposure_inr=projected,
                projected_pct_nav=_pct_of_nav(projected, plan_input.nav_inr),
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


def _strategy_score(plan_input: PortfolioRebalancePlanInput, symbol: str) -> Decimal | None:
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
