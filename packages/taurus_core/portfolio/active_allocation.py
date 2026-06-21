from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN
from statistics import mean, pstdev

from taurus_core.allocation_schemas import AllocationDecision
from taurus_core.domain.market_data import DailyCandle
from taurus_core.portfolio.money_management import (
    AllocationScoreBandsPolicy,
    AllocationScoreWeightsPolicy,
    MoneyManagementPolicy,
    SleevePolicy,
)
from taurus_core.portfolio.score_semantics import calibrate_strategy_score
from taurus_core.research.schemas import TraderProposal

ACTIVE_SLEEVE_ID = "active_strategy"
DIVERSIFYING_SLEEVE_ID = "diversifying_strategy"
EXPERIMENTAL_SLEEVE_ID = "experimental_models"
ALLOCATABLE_SLEEVE_IDS = frozenset(
    {ACTIVE_SLEEVE_ID, DIVERSIFYING_SLEEVE_ID, EXPERIMENTAL_SLEEVE_ID}
)
SCORE_QUANT = Decimal("0.0001")
MONEY_QUANT = Decimal("0.01")
VOLATILITY_QUANT = Decimal("0.0001")
DEFAULT_OPEN_POSITION_STOP_RISK_PCT = Decimal("6.0000")
VOLATILITY_WINDOW = 60
LIQUIDITY_WINDOW = 20


@dataclass(frozen=True, slots=True)
class ActiveAllocationPosition:
    symbol: str
    quantity: int
    market_value_inr: Decimal


@dataclass(frozen=True, slots=True)
class SleeveAllocationSnapshot:
    sleeve_id: str
    starting_nav_estimate_inr: Decimal
    current_exposure_inr: Decimal = Decimal("0")
    realized_pnl_inr: Decimal = Decimal("0")
    unrealized_pnl_inr: Decimal = Decimal("0")
    open_position_count: int = 0
    open_trade_risk_inr: Decimal = Decimal("0")
    turnover_inr: Decimal = Decimal("0")

    @property
    def drawdown_pct(self) -> Decimal:
        if self.starting_nav_estimate_inr <= 0:
            return Decimal("0.0000")
        current_nav = (
            self.starting_nav_estimate_inr
            + self.realized_pnl_inr
            + self.unrealized_pnl_inr
        )
        drawdown = (
            (self.starting_nav_estimate_inr - current_nav)
            / self.starting_nav_estimate_inr
            * Decimal("100")
        )
        return max(Decimal("0"), drawdown).quantize(SCORE_QUANT)


@dataclass(frozen=True, slots=True)
class ActiveAllocationInput:
    proposal: TraderProposal
    strategy_name: str
    nav_inr: Decimal
    available_cash_inr: Decimal
    portfolio_starting_nav_estimate_inr: Decimal | None = None
    current_positions: tuple[ActiveAllocationPosition, ...] = ()
    sleeve_snapshots: tuple[SleeveAllocationSnapshot, ...] = ()
    core_basket_symbols: tuple[str, ...] = ()
    history: tuple[DailyCandle, ...] = ()
    strategy_score: Decimal | None = None
    strategy_rank: int | None = None
    sector_by_symbol: dict[str, str] | None = None
    graph_cluster_by_symbol: dict[str, str] | None = None
    recent_sleeve_performance_score: Decimal | None = None


@dataclass(frozen=True, slots=True)
class GovernorEvaluation:
    scale_factor: Decimal = Decimal("1.0000")
    portfolio_drawdown_pct: Decimal = Decimal("0.0000")
    sleeve_drawdown_pct: Decimal = Decimal("0.0000")
    governor_reasons: tuple[str, ...] = ()
    frozen: bool = False
    binding_constraint: str | None = None


class PortfolioAllocationService:
    """Risk-budgeted strategy-sleeve sizing for paper BUY/increase proposals."""

    model_version = "strategy_sleeve_allocation_v1"

    def __init__(self, policy: MoneyManagementPolicy) -> None:
        self.policy = policy
        self.sleeves_by_id = {sleeve.sleeve_id: sleeve for sleeve in policy.sleeves}
        self.strategy_to_sleeve = {
            mapping.strategy_name: mapping.sleeve_id
            for mapping in policy.strategy_mappings
        }

    def sleeve_id_for_strategy(self, strategy_name: str) -> str | None:
        return self.strategy_to_sleeve.get(strategy_name)

    def candidate_score(
        self,
        allocation_input: ActiveAllocationInput,
    ) -> tuple[Decimal, dict[str, Decimal]]:
        return _candidate_score(allocation_input, weights=self.policy.allocation_scoring.weights)

    def score_band_for(self, score: Decimal) -> tuple[str, Decimal]:
        return _score_band(
            score,
            bands=self.policy.allocation_scoring.score_bands,
            trade_risk_normal=self.policy.trade_risk.normal_trade_risk_pct_nav,
            trade_risk_strong=self.policy.trade_risk.strong_trade_risk_pct_nav,
            max_single_trade_risk=self.policy.trade_risk.max_single_trade_risk_pct_nav,
        )

    def allocate(self, allocation_input: ActiveAllocationInput) -> TraderProposal:
        proposal = allocation_input.proposal
        strategy_name = allocation_input.strategy_name
        mapped_sleeve = self.strategy_to_sleeve.get(strategy_name)
        sleeve = self.sleeves_by_id.get(mapped_sleeve or "")
        if sleeve is None or mapped_sleeve not in ALLOCATABLE_SLEEVE_IDS:
            return self._with_decision(
                proposal,
                AllocationDecision(
                    symbol=proposal.symbol,
                    action=proposal.action,
                    strategy_name=strategy_name,
                    sleeve_id=mapped_sleeve or "unmapped",
                    sleeve_name=None,
                    status="unchanged",
                    requested_position_pct_nav=proposal.requested_position_pct_nav,
                    approved_position_pct_nav=proposal.target_position_pct_nav,
                    requested_notional_inr=_requested_increase_notional(
                        proposal=proposal,
                        nav_inr=allocation_input.nav_inr,
                    ),
                    approved_notional_inr=Decimal("0"),
                    approved_quantity=0,
                    binding_constraint=(
                        "strategy_unmapped"
                        if mapped_sleeve is None
                        else "strategy_not_allocatable_sleeve"
                    ),
                    rationale=("Strategy is outside M34 strategy-sleeve allocation scope.",),
                ),
            )

        if proposal.action not in {"BUY"}:
            return self._with_decision(
                proposal,
                AllocationDecision(
                    symbol=proposal.symbol,
                    action=proposal.action,
                    strategy_name=strategy_name,
                    sleeve_id=sleeve.sleeve_id,
                    sleeve_name=sleeve.name,
                    status="unchanged",
                    requested_position_pct_nav=proposal.requested_position_pct_nav,
                    approved_position_pct_nav=proposal.target_position_pct_nav,
                    requested_notional_inr=_requested_increase_notional(
                        proposal=proposal,
                        nav_inr=allocation_input.nav_inr,
                    ),
                    approved_notional_inr=Decimal("0"),
                    approved_quantity=0,
                    binding_constraint="lifecycle_action_not_new_risk",
                    rationale=(
                        f"Lifecycle action {proposal.action} does not require new sleeve risk.",
                    ),
                ),
            )

        governor = _evaluate_governors(allocation_input, sleeve=sleeve, policy=self.policy)
        if governor.frozen:
            return self._rejected_buy(
                allocation_input,
                sleeve=sleeve,
                governor=governor,
                requested_notional=_requested_increase_notional(
                    proposal=proposal,
                    nav_inr=allocation_input.nav_inr,
                ),
                candidate_score=None,
                score_band="governor_freeze",
                volatility=None,
                binding_constraint=governor.binding_constraint or "governor_freeze",
                rationale=governor.governor_reasons,
            )

        latest_price = _latest_close(allocation_input.history)
        requested_notional = _requested_increase_notional(
            proposal=proposal,
            nav_inr=allocation_input.nav_inr,
        )
        current_notional = _pct_to_notional(
            proposal.current_position_pct_nav,
            allocation_input.nav_inr,
        )
        risk_per_share = _risk_per_share(
            latest_price=latest_price,
            stop_loss_pct=proposal.stop_loss_pct,
        )
        if latest_price <= 0 or risk_per_share <= 0:
            return self._rejected_buy(
                allocation_input,
                sleeve=sleeve,
                governor=governor,
                requested_notional=requested_notional,
                candidate_score=None,
                score_band="invalid_stop_loss",
                volatility=None,
                binding_constraint="invalid_stop_loss_or_price",
                rationale=(
                    "Strategy-sleeve BUY requires a positive latest price and stop-loss distance.",
                ),
            )

        candidate_score, score_parts = self.candidate_score(allocation_input)
        score_band, base_risk_pct = self.score_band_for(candidate_score)
        volatility = _realized_volatility(allocation_input.history)
        volatility_factor = _volatility_factor(volatility)
        allowed_risk = _pct_to_notional(base_risk_pct, allocation_input.nav_inr)
        dampened_allowed_risk = (
            allowed_risk * volatility_factor * governor.scale_factor
        ).quantize(MONEY_QUANT)

        if score_band == "reject":
            return self._rejected_buy(
                allocation_input,
                sleeve=sleeve,
                governor=governor,
                requested_notional=requested_notional,
                candidate_score=candidate_score,
                score_band=score_band,
                volatility=volatility,
                binding_constraint="candidate_score_below_entry_floor",
                rationale=(
                    "Candidate score "
                    f"{candidate_score} is below the configured "
                    f"{self.policy.allocation_scoring.score_bands.reject_below} "
                    "strategy-sleeve entry floor.",
                    _score_parts_text(score_parts),
                ),
            )

        trade_risk_notional = _risk_to_notional(
            allowed_risk_inr=dampened_allowed_risk,
            latest_price=latest_price,
            risk_per_share=risk_per_share,
        )
        sleeve_snapshot = _sleeve_snapshot_for(allocation_input, sleeve.sleeve_id)
        caps = {
            "requested_notional": requested_notional,
            "trade_risk": trade_risk_notional,
            "sleeve_trade_risk_cap": _sleeve_trade_risk_cap_room(
                sleeve=sleeve,
                nav_inr=allocation_input.nav_inr,
                latest_price=latest_price,
                risk_per_share=risk_per_share,
            ),
            "stock_exposure": _stock_exposure_room(
                proposal=proposal,
                nav_inr=allocation_input.nav_inr,
                current_notional=current_notional,
                policy=self.policy,
            ),
            "sleeve_capacity": _sleeve_capacity_room(
                proposal=proposal,
                nav_inr=allocation_input.nav_inr,
                positions=allocation_input.current_positions,
                sleeve_id=sleeve.sleeve_id,
                sleeve_target_pct=sleeve.target_weight_pct,
                sleeve_snapshot=sleeve_snapshot,
                core_basket_symbols=allocation_input.core_basket_symbols,
            ),
            "cash_buffer": _cash_buffer_room(allocation_input, self.policy),
            "total_open_trade_risk": _total_trade_risk_room(
                allocation_input,
                policy=self.policy,
                risk_per_share=risk_per_share,
                latest_price=latest_price,
            ),
            "open_positions": _open_position_room(allocation_input, policy=self.policy),
            "sector_concentration": _group_room(
                allocation_input,
                group_by_symbol=allocation_input.sector_by_symbol or {},
                cap_pct_nav=self.policy.limits.max_sector_pct_nav,
            ),
            "graph_concentration": _group_room(
                allocation_input,
                group_by_symbol=allocation_input.graph_cluster_by_symbol or {},
                cap_pct_nav=self.policy.limits.max_graph_cluster_pct_nav,
            ),
        }
        binding_constraint, approved_notional = min(
            caps.items(),
            key=lambda item: (item[1], item[0]),
        )
        approved_quantity = int((approved_notional / latest_price).to_integral_value(rounding=ROUND_DOWN))
        approved_notional = _money(latest_price * Decimal(approved_quantity))
        estimated_risk = _money(risk_per_share * Decimal(approved_quantity))
        target_position = (
            ((current_notional + approved_notional) / allocation_input.nav_inr) * Decimal("100")
            if allocation_input.nav_inr > 0
            else Decimal("0")
        ).quantize(SCORE_QUANT)
        status = "approved" if approved_quantity > 0 else "rejected"
        decision = AllocationDecision(
            symbol=proposal.symbol,
            action=proposal.action,
            strategy_name=strategy_name,
            sleeve_id=sleeve.sleeve_id,
            sleeve_name=sleeve.name,
            status=status,
            candidate_score=candidate_score,
            score_band=score_band,
            requested_position_pct_nav=proposal.requested_position_pct_nav,
            approved_position_pct_nav=target_position,
            requested_notional_inr=requested_notional,
            approved_notional_inr=approved_notional,
            approved_quantity=approved_quantity,
            allowed_risk_inr=dampened_allowed_risk,
            estimated_risk_inr=estimated_risk,
            volatility_used=volatility,
            governor_scale_factor=governor.scale_factor,
            portfolio_drawdown_pct=governor.portfolio_drawdown_pct,
            sleeve_drawdown_pct=governor.sleeve_drawdown_pct,
            governor_reasons=governor.governor_reasons,
            binding_constraint=binding_constraint,
            rationale=(
                f"Strategy-sleeve score band {score_band} allowed {dampened_allowed_risk} INR risk.",
                f"Volatility factor {volatility_factor} applied to realized volatility {volatility}.",
                f"Governor scale factor {governor.scale_factor} applied.",
                _score_parts_text(score_parts),
            ),
        )
        if approved_quantity <= 0:
            return self._zero_buy_target(
                proposal,
                decision=decision,
                current_position_pct_nav=proposal.current_position_pct_nav,
            )
        return self._with_decision(
            proposal.model_copy(
                update={
                    "target_position_pct_nav": target_position,
                    "model_version": f"{proposal.model_version}+{self.model_version}",
                    "position_management_summary": (
                        f"{proposal.position_management_summary} Strategy-sleeve allocation approved "
                        f"{approved_quantity} shares; binding constraint {binding_constraint}."
                    ),
                }
            ),
            decision,
        )

    def _rejected_buy(
        self,
        allocation_input: ActiveAllocationInput,
        *,
        sleeve: SleevePolicy,
        governor: GovernorEvaluation,
        requested_notional: Decimal,
        candidate_score: Decimal | None,
        score_band: str,
        volatility: Decimal | None,
        binding_constraint: str,
        rationale: tuple[str, ...],
    ) -> TraderProposal:
        proposal = allocation_input.proposal
        decision = AllocationDecision(
            symbol=proposal.symbol,
            action=proposal.action,
            strategy_name=allocation_input.strategy_name,
            sleeve_id=sleeve.sleeve_id,
            sleeve_name=sleeve.name,
            status="rejected",
            candidate_score=candidate_score,
            score_band=score_band,
            requested_position_pct_nav=proposal.requested_position_pct_nav,
            approved_position_pct_nav=proposal.current_position_pct_nav,
            requested_notional_inr=requested_notional,
            approved_notional_inr=Decimal("0"),
            approved_quantity=0,
            allowed_risk_inr=Decimal("0"),
            estimated_risk_inr=Decimal("0"),
            volatility_used=volatility,
            governor_scale_factor=governor.scale_factor,
            portfolio_drawdown_pct=governor.portfolio_drawdown_pct,
            sleeve_drawdown_pct=governor.sleeve_drawdown_pct,
            governor_reasons=governor.governor_reasons,
            binding_constraint=binding_constraint,
            rationale=rationale,
        )
        return self._zero_buy_target(
            proposal,
            decision=decision,
            current_position_pct_nav=proposal.current_position_pct_nav,
        )

    def _zero_buy_target(
        self,
        proposal: TraderProposal,
        *,
        decision: AllocationDecision,
        current_position_pct_nav: Decimal,
    ) -> TraderProposal:
        if proposal.current_position_quantity > 0:
            updated = proposal.model_copy(
                update={
                    "action": "HOLD",
                    "target_position_pct_nav": current_position_pct_nav.quantize(SCORE_QUANT),
                    "order_type": "NONE",
                    "entry_rule": "Strategy-sleeve allocation produced no incremental paper BUY quantity.",
                    "model_version": f"{proposal.model_version}+{self.model_version}",
                    "position_management_summary": (
                        f"{proposal.position_management_summary} Strategy-sleeve allocation produced no "
                        "incremental BUY quantity; existing paper position remains under HOLD."
                    ),
                }
            )
            return self._with_decision(updated, decision)
        updated = proposal.model_copy(
            update={
                "action": "NO_TRADE",
                "target_position_pct_nav": Decimal("0.0000"),
                "order_type": "NONE",
                "entry_rule": "Strategy-sleeve allocation rejected the new BUY before risk review.",
                "model_version": f"{proposal.model_version}+{self.model_version}",
                "position_management_summary": (
                    f"{proposal.position_management_summary} Strategy-sleeve allocation rejected the "
                    f"new BUY; binding constraint {decision.binding_constraint}."
                ),
            }
        )
        return self._with_decision(updated, decision)

    def _with_decision(
        self,
        proposal: TraderProposal,
        decision: AllocationDecision,
    ) -> TraderProposal:
        return proposal.model_copy(update={"allocation_decision": decision})


def _evaluate_governors(
    allocation_input: ActiveAllocationInput,
    *,
    sleeve: SleevePolicy,
    policy: MoneyManagementPolicy,
) -> GovernorEvaluation:
    portfolio_drawdown = _portfolio_drawdown_pct(allocation_input)
    sleeve_snapshot = _sleeve_snapshot_for(allocation_input, sleeve.sleeve_id)
    sleeve_drawdown = (
        sleeve_snapshot.drawdown_pct if sleeve_snapshot is not None else Decimal("0.0000")
    )
    scale_factor = Decimal("1.0000")
    frozen = False
    binding_constraint: str | None = None
    reasons: list[str] = []

    for governor in sorted(policy.drawdown_governors, key=lambda item: item.drawdown_pct):
        if portfolio_drawdown <= governor.drawdown_pct:
            continue
        action = governor.action.strip().lower()
        reasons.append(
            f"Portfolio drawdown {portfolio_drawdown}% exceeded {governor.name} "
            f"threshold {governor.drawdown_pct}%."
        )
        if action == "reduce_new_position_sizes_25_pct":
            scale_factor = min(scale_factor, Decimal("0.7500"))
        elif action == "reduce_new_position_sizes_50_pct":
            scale_factor = min(scale_factor, Decimal("0.5000"))
        elif action == "stop_experimental_new_entries" and sleeve.sleeve_id == EXPERIMENTAL_SLEEVE_ID:
            frozen = True
            binding_constraint = "experimental_portfolio_drawdown_freeze"
        elif action == "freeze_new_buys_allow_exits":
            frozen = True
            binding_constraint = "portfolio_drawdown_freeze"

    if (
        sleeve.drawdown_reduce_threshold_pct is not None
        and sleeve_drawdown > sleeve.drawdown_reduce_threshold_pct
    ):
        reduction_factor = (
            (Decimal("100") - sleeve.drawdown_reduce_size_pct) / Decimal("100")
        ).quantize(SCORE_QUANT)
        scale_factor = min(scale_factor, reduction_factor)
        reasons.append(
            f"Sleeve {sleeve.sleeve_id} drawdown {sleeve_drawdown}% exceeded reduce "
            f"threshold {sleeve.drawdown_reduce_threshold_pct}%."
        )

    if (
        sleeve.drawdown_freeze_threshold_pct is not None
        and sleeve_drawdown > sleeve.drawdown_freeze_threshold_pct
    ):
        frozen = True
        binding_constraint = "sleeve_drawdown_freeze"
        reasons.append(
            f"Sleeve {sleeve.sleeve_id} drawdown {sleeve_drawdown}% exceeded freeze "
            f"threshold {sleeve.drawdown_freeze_threshold_pct}%."
        )

    return GovernorEvaluation(
        scale_factor=scale_factor,
        portfolio_drawdown_pct=portfolio_drawdown,
        sleeve_drawdown_pct=sleeve_drawdown,
        governor_reasons=tuple(reasons),
        frozen=frozen,
        binding_constraint=binding_constraint,
    )


def _portfolio_drawdown_pct(allocation_input: ActiveAllocationInput) -> Decimal:
    starting_nav = allocation_input.portfolio_starting_nav_estimate_inr
    if starting_nav is None:
        starting_nav = sum(
            (
                snapshot.starting_nav_estimate_inr
                for snapshot in allocation_input.sleeve_snapshots
            ),
            Decimal("0"),
        )
    if starting_nav <= 0:
        return Decimal("0.0000")
    drawdown = (
        (starting_nav - allocation_input.nav_inr)
        / starting_nav
        * Decimal("100")
    )
    return max(Decimal("0"), drawdown).quantize(SCORE_QUANT)


def _sleeve_snapshot_for(
    allocation_input: ActiveAllocationInput,
    sleeve_id: str,
) -> SleeveAllocationSnapshot | None:
    normalized = sleeve_id.strip().lower()
    return next(
        (
            snapshot
            for snapshot in allocation_input.sleeve_snapshots
            if snapshot.sleeve_id.strip().lower() == normalized
        ),
        None,
    )


def _requested_increase_notional(*, proposal: TraderProposal, nav_inr: Decimal) -> Decimal:
    requested_pct = max(
        Decimal("0"),
        proposal.target_position_pct_nav - proposal.current_position_pct_nav,
    )
    return _pct_to_notional(requested_pct, nav_inr)


def _pct_to_notional(percent: Decimal, nav_inr: Decimal) -> Decimal:
    if percent <= 0 or nav_inr <= 0:
        return Decimal("0")
    return (nav_inr * percent / Decimal("100")).quantize(MONEY_QUANT)


def _latest_close(history: tuple[DailyCandle, ...]) -> Decimal:
    if not history:
        return Decimal("0")
    return sorted(history, key=lambda candle: candle.trade_date)[-1].close.quantize(MONEY_QUANT)


def _risk_per_share(*, latest_price: Decimal, stop_loss_pct: Decimal) -> Decimal:
    if latest_price <= 0 or stop_loss_pct <= 0:
        return Decimal("0")
    return (latest_price * stop_loss_pct / Decimal("100")).quantize(MONEY_QUANT)


def _candidate_score(
    allocation_input: ActiveAllocationInput,
    *,
    weights: AllocationScoreWeightsPolicy,
) -> tuple[Decimal, dict[str, Decimal]]:
    history = allocation_input.history
    strategy_calibration = calibrate_strategy_score(
        allocation_input.strategy_score,
        strategy_rank=allocation_input.strategy_rank,
    )
    strategy_component = strategy_calibration.allocation_score_component
    confidence_component = (allocation_input.proposal.confidence * Decimal("100")).quantize(
        SCORE_QUANT
    )
    liquidity_component = _liquidity_score(history)
    volatility = _realized_volatility(history)
    volatility_component = _volatility_score(volatility)
    diversification_component = _diversification_score(allocation_input)
    performance_component = allocation_input.recent_sleeve_performance_score or Decimal("75")
    parts = {
        **strategy_calibration.score_parts(),
        "trader_confidence": confidence_component,
        "liquidity": liquidity_component,
        "volatility": volatility_component,
        "diversification": diversification_component,
        "recent_sleeve_performance": _clamp(performance_component, Decimal("0"), Decimal("100")),
    }
    score = (
        (parts["strategy_score"] * weights.strategy_score)
        + (parts["trader_confidence"] * weights.trader_confidence)
        + (parts["liquidity"] * weights.liquidity)
        + (parts["volatility"] * weights.volatility)
        + (parts["diversification"] * weights.diversification)
        + (
            parts["recent_sleeve_performance"]
            * weights.recent_sleeve_performance
        )
    ).quantize(SCORE_QUANT)
    return _clamp(score, Decimal("0"), Decimal("100")), parts


def _strategy_score_component(score: Decimal | None) -> Decimal:
    return calibrate_strategy_score(score).allocation_score_component


def _liquidity_score(history: tuple[DailyCandle, ...]) -> Decimal:
    if not history:
        return Decimal("0")
    window = sorted(history, key=lambda candle: candle.trade_date)[-LIQUIDITY_WINDOW:]
    liquidity = mean(float(candle.close) * float(candle.volume) for candle in window)
    if liquidity >= 50_000_000:
        return Decimal("100")
    if liquidity <= 1_000_000:
        return Decimal("20")
    return Decimal(str(20 + ((liquidity - 1_000_000) / 49_000_000 * 80))).quantize(SCORE_QUANT)


def _realized_volatility(history: tuple[DailyCandle, ...]) -> Decimal:
    ordered = sorted(history, key=lambda candle: candle.trade_date)
    closes = [float(candle.close) for candle in ordered]
    if len(closes) < VOLATILITY_WINDOW + 1:
        return Decimal("0.2500")
    returns = [
        (closes[index] / closes[index - 1]) - 1.0
        for index in range(1, len(closes))
        if closes[index - 1] > 0
    ]
    if len(returns) < VOLATILITY_WINDOW:
        return Decimal("0.2500")
    volatility = pstdev(returns[-VOLATILITY_WINDOW:]) * math.sqrt(252)
    return Decimal(f"{max(volatility, 0.0001):.8f}").quantize(VOLATILITY_QUANT)


def _volatility_score(volatility: Decimal) -> Decimal:
    if volatility <= Decimal("0.1200"):
        return Decimal("100")
    if volatility >= Decimal("0.6000"):
        return Decimal("25")
    score = Decimal("100") - ((volatility - Decimal("0.1200")) / Decimal("0.4800") * Decimal("75"))
    return _clamp(score, Decimal("25"), Decimal("100")).quantize(SCORE_QUANT)


def _volatility_factor(volatility: Decimal) -> Decimal:
    if volatility <= Decimal("0.1800"):
        return Decimal("1.0000")
    factor = Decimal("0.1800") / volatility
    return _clamp(factor, Decimal("0.3500"), Decimal("1.0000")).quantize(SCORE_QUANT)


def _diversification_score(allocation_input: ActiveAllocationInput) -> Decimal:
    score = Decimal("100")
    symbol = allocation_input.proposal.symbol.upper()
    for group_by_symbol, penalty in (
        (allocation_input.sector_by_symbol or {}, Decimal("12")),
        (allocation_input.graph_cluster_by_symbol or {}, Decimal("8")),
    ):
        group = group_by_symbol.get(symbol)
        if not group:
            continue
        matching_positions = [
            position
            for position in allocation_input.current_positions
            if position.symbol.upper() != symbol
            and group_by_symbol.get(position.symbol.upper()) == group
        ]
        score -= penalty * Decimal(len(matching_positions))
    return _clamp(score, Decimal("40"), Decimal("100")).quantize(SCORE_QUANT)


def _score_band(
    score: Decimal,
    *,
    bands: AllocationScoreBandsPolicy,
    trade_risk_normal: Decimal,
    trade_risk_strong: Decimal,
    max_single_trade_risk: Decimal,
) -> tuple[str, Decimal]:
    if score < bands.reject_below:
        return "reject", Decimal("0")
    if score < bands.half_normal_below:
        return "half_normal", min(
            trade_risk_normal / Decimal("2"),
            max_single_trade_risk,
        )
    if score < bands.normal_below:
        return "normal", min(trade_risk_normal, max_single_trade_risk)
    return "strong", min(trade_risk_strong, max_single_trade_risk, Decimal("0.75"))


def _risk_to_notional(
    *,
    allowed_risk_inr: Decimal,
    latest_price: Decimal,
    risk_per_share: Decimal,
) -> Decimal:
    if allowed_risk_inr <= 0 or latest_price <= 0 or risk_per_share <= 0:
        return Decimal("0")
    quantity = int((allowed_risk_inr / risk_per_share).to_integral_value(rounding=ROUND_DOWN))
    return _money(latest_price * Decimal(quantity))


def _stock_exposure_room(
    *,
    proposal: TraderProposal,
    nav_inr: Decimal,
    current_notional: Decimal,
    policy: MoneyManagementPolicy,
) -> Decimal:
    target_cap = _pct_to_notional(policy.limits.max_stock_pct_nav, nav_inr)
    return max(Decimal("0"), target_cap - current_notional).quantize(MONEY_QUANT)


def _sleeve_capacity_room(
    *,
    proposal: TraderProposal,
    nav_inr: Decimal,
    positions: tuple[ActiveAllocationPosition, ...],
    sleeve_id: str,
    sleeve_target_pct: Decimal,
    sleeve_snapshot: SleeveAllocationSnapshot | None,
    core_basket_symbols: tuple[str, ...],
) -> Decimal:
    if sleeve_snapshot is not None:
        capacity = _pct_to_notional(sleeve_target_pct, nav_inr)
        return max(Decimal("0"), capacity - sleeve_snapshot.current_exposure_inr).quantize(
            MONEY_QUANT
        )

    core_symbols = {symbol.upper() for symbol in core_basket_symbols}
    current_active_notional = sum(
        (
            position.market_value_inr
            for position in positions
            if position.symbol.upper() not in core_symbols
            and position.symbol.upper() != proposal.symbol.upper()
        ),
        Decimal("0"),
    )
    capacity = _pct_to_notional(sleeve_target_pct, nav_inr)
    if sleeve_id != ACTIVE_SLEEVE_ID:
        current_active_notional = Decimal("0")
    return max(Decimal("0"), capacity - current_active_notional).quantize(MONEY_QUANT)


def _sleeve_trade_risk_cap_room(
    *,
    sleeve: SleevePolicy,
    nav_inr: Decimal,
    latest_price: Decimal,
    risk_per_share: Decimal,
) -> Decimal:
    if sleeve.new_entry_risk_cap_pct_nav is None:
        return Decimal("999999999999.99")
    allowed_risk = _pct_to_notional(sleeve.new_entry_risk_cap_pct_nav, nav_inr)
    return _risk_to_notional(
        allowed_risk_inr=allowed_risk,
        latest_price=latest_price,
        risk_per_share=risk_per_share,
    )


def _cash_buffer_room(
    allocation_input: ActiveAllocationInput,
    policy: MoneyManagementPolicy,
) -> Decimal:
    protected_cash = _pct_to_notional(policy.cash_buffer_target_pct, allocation_input.nav_inr)
    return max(Decimal("0"), allocation_input.available_cash_inr - protected_cash).quantize(
        MONEY_QUANT
    )


def _total_trade_risk_room(
    allocation_input: ActiveAllocationInput,
    *,
    policy: MoneyManagementPolicy,
    risk_per_share: Decimal,
    latest_price: Decimal,
) -> Decimal:
    max_total_risk = _pct_to_notional(
        policy.trade_risk.max_total_open_trade_risk_pct_nav,
        allocation_input.nav_inr,
    )
    symbol = allocation_input.proposal.symbol.upper()
    existing_risk = sum(
        (
            position.market_value_inr
            * DEFAULT_OPEN_POSITION_STOP_RISK_PCT
            / Decimal("100")
            for position in allocation_input.current_positions
            if position.symbol.upper() != symbol
        ),
        Decimal("0"),
    ).quantize(MONEY_QUANT)
    remaining_risk = max(Decimal("0"), max_total_risk - existing_risk)
    return _risk_to_notional(
        allowed_risk_inr=remaining_risk,
        latest_price=latest_price,
        risk_per_share=risk_per_share,
    )


def _open_position_room(
    allocation_input: ActiveAllocationInput,
    *,
    policy: MoneyManagementPolicy,
) -> Decimal:
    proposal = allocation_input.proposal
    if proposal.current_position_quantity > 0:
        return Decimal("999999999999.99")
    open_count = sum(1 for position in allocation_input.current_positions if position.quantity > 0)
    if open_count >= policy.limits.max_open_positions:
        return Decimal("0")
    return Decimal("999999999999.99")


def _group_room(
    allocation_input: ActiveAllocationInput,
    *,
    group_by_symbol: dict[str, str],
    cap_pct_nav: Decimal,
) -> Decimal:
    symbol = allocation_input.proposal.symbol.upper()
    group = group_by_symbol.get(symbol)
    if not group:
        return Decimal("999999999999.99")
    cap = _pct_to_notional(cap_pct_nav, allocation_input.nav_inr)
    current_group_notional = sum(
        (
            position.market_value_inr
            for position in allocation_input.current_positions
            if position.symbol.upper() != symbol
            and group_by_symbol.get(position.symbol.upper()) == group
        ),
        Decimal("0"),
    ).quantize(MONEY_QUANT)
    return max(Decimal("0"), cap - current_group_notional).quantize(MONEY_QUANT)


def _score_parts_text(parts: dict[str, Decimal]) -> str:
    return "Score parts: " + ", ".join(
        f"{name}={value}" for name, value in sorted(parts.items())
    )


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT)


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(upper, value))
