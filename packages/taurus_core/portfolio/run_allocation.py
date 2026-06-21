from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN
from typing import Any

from taurus_core.allocation_schemas import AllocationDecision
from taurus_core.domain.market_data import DailyCandle
from taurus_core.portfolio.active_allocation import (
    ActiveAllocationInput,
    ActiveAllocationPosition,
    PortfolioAllocationService,
    SleeveAllocationSnapshot,
)
from taurus_core.portfolio.core_shariah_basket import CORE_SLEEVE_ID, CORE_STRATEGY_NAME
from taurus_core.portfolio.money_management import MoneyManagementPolicy
from taurus_core.portfolio.rebalance_plan import (
    PortfolioPlanCandidate,
    PortfolioPlanTrade,
    PortfolioRebalancePlan,
    THRESHOLD_REBALANCE_SOURCE,
)
from taurus_core.portfolio.score_semantics import calibrate_strategy_score
from taurus_core.research.schemas import TraderProposal

RUN_ALLOCATION_MODEL_VERSION = "run_level_dynamic_allocation_v1"
PORTFOLIO_PLAN_ALLOCATION_MODEL_VERSION = "portfolio_plan_rebalance_allocation_v2"
MONEY_QUANT = Decimal("0.01")
SCORE_QUANT = Decimal("0.0001")
UNLIMITED_ROOM = Decimal("999999999999.99")
SELECTED_LEDGER_STATUSES = frozenset({"selected", "allocation_reduced"})
RUN_LEVEL_RESOURCE_CONSTRAINTS = frozenset(
    {
        "cash_buffer",
        "open_positions",
        "sector_concentration",
        "graph_concentration",
        "sleeve_capacity",
        "sleeve_trade_risk_cap",
        "stock_exposure",
        "total_open_trade_risk",
        "trade_risk",
    }
)


@dataclass(frozen=True, slots=True)
class FallbackAllocationPolicy:
    max_open_positions: int
    max_position_pct_nav: Decimal
    source: str = "settings"

    @classmethod
    def from_settings(cls, settings: Any) -> FallbackAllocationPolicy:
        return cls(
            max_open_positions=int(settings.taurus_max_open_positions),
            max_position_pct_nav=Decimal(str(settings.taurus_max_position_pct)),
            source="settings",
        )


@dataclass(frozen=True, slots=True)
class RunAllocationInput:
    run_id: str
    strategy_name: str
    proposals: tuple[TraderProposal, ...]
    nav_inr: Decimal
    available_cash_inr: Decimal
    portfolio_starting_nav_estimate_inr: Decimal | None = None
    current_positions: tuple[ActiveAllocationPosition, ...] = ()
    sleeve_snapshots: tuple[SleeveAllocationSnapshot, ...] = ()
    histories_by_symbol: Mapping[str, tuple[DailyCandle, ...]] = field(default_factory=dict)
    core_basket_symbols: tuple[str, ...] = ()
    strategy_rank_by_symbol: Mapping[str, int] = field(default_factory=dict)
    strategy_score_by_symbol: Mapping[str, Decimal] = field(default_factory=dict)
    sector_by_symbol: Mapping[str, str] = field(default_factory=dict)
    graph_cluster_by_symbol: Mapping[str, str] = field(default_factory=dict)
    money_management_policy: MoneyManagementPolicy | None = None
    fallback_policy: FallbackAllocationPolicy | None = None


@dataclass(frozen=True, slots=True)
class AllocationLedgerEntry:
    symbol: str
    proposal_id: str
    action: str
    status: str
    selected: bool
    strategy_rank: int | None
    strategy_score: Decimal | None
    trader_confidence: Decimal
    candidate_score: Decimal | None
    score_band: str | None
    requested_position_pct_nav: Decimal
    approved_position_pct_nav: Decimal
    requested_notional_inr: Decimal
    approved_notional_inr: Decimal
    approved_quantity: int
    binding_constraint: str | None
    portfolio_plan_id: str | None = None
    portfolio_plan_trade_id: str | None = None
    planner_candidate_id: str | None = None
    planner_source: str | None = None
    planner_rank: int | None = None
    capacity_source: str | None = None
    borrowed_from_sleeve_ids: tuple[str, ...] = ()
    funding_source: str | None = None
    existing_cash_used_inr: Decimal = Decimal("0")
    same_run_proceeds_used_inr: Decimal = Decimal("0")
    same_run_proceeds_available_inr: Decimal = Decimal("0")
    same_run_proceeds_haircut_pct: Decimal | None = None
    hard_cash_reserve_inr: Decimal | None = None
    buy_price_buffer_pct: Decimal | None = None
    proposal_source: str | None = None
    rationale: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return _json_safe(
            {
                "symbol": self.symbol,
                "proposal_id": self.proposal_id,
                "action": self.action,
                "status": self.status,
                "selected": self.selected,
                "strategy_rank": self.strategy_rank,
                "strategy_score": self.strategy_score,
                "trader_confidence": self.trader_confidence,
                "candidate_score": self.candidate_score,
                "score_band": self.score_band,
                "requested_position_pct_nav": self.requested_position_pct_nav,
                "approved_position_pct_nav": self.approved_position_pct_nav,
                "requested_notional_inr": self.requested_notional_inr,
                "approved_notional_inr": self.approved_notional_inr,
                "approved_quantity": self.approved_quantity,
                "binding_constraint": self.binding_constraint,
                "portfolio_plan_id": self.portfolio_plan_id,
                "portfolio_plan_trade_id": self.portfolio_plan_trade_id,
                "planner_candidate_id": self.planner_candidate_id,
                "planner_source": self.planner_source,
                "planner_rank": self.planner_rank,
                "capacity_source": self.capacity_source,
                "borrowed_from_sleeve_ids": self.borrowed_from_sleeve_ids,
                "funding_source": self.funding_source,
                "existing_cash_used_inr": self.existing_cash_used_inr,
                "same_run_proceeds_used_inr": self.same_run_proceeds_used_inr,
                "same_run_proceeds_available_inr": self.same_run_proceeds_available_inr,
                "same_run_proceeds_haircut_pct": self.same_run_proceeds_haircut_pct,
                "hard_cash_reserve_inr": self.hard_cash_reserve_inr,
                "buy_price_buffer_pct": self.buy_price_buffer_pct,
                "proposal_source": self.proposal_source,
                "rationale": list(self.rationale),
            }
        )


@dataclass(frozen=True, slots=True)
class RunAllocationResult:
    proposals: tuple[TraderProposal, ...]
    ledger: tuple[AllocationLedgerEntry, ...]
    summary: dict[str, int]
    binding_constraints: dict[str, int]
    policy_source: str
    model_version: str = RUN_ALLOCATION_MODEL_VERSION

    def proposal_by_symbol(self) -> dict[str, TraderProposal]:
        return {proposal.symbol.upper(): proposal for proposal in self.proposals}

    def to_artifact(self) -> dict[str, object]:
        return {
            "model_version": self.model_version,
            "policy_source": self.policy_source,
            "summary": dict(self.summary),
            "binding_constraints": dict(self.binding_constraints),
            "ledger": [entry.to_dict() for entry in self.ledger],
        }


@dataclass(frozen=True, slots=True)
class _PlannerBuyCandidate:
    proposal: TraderProposal
    candidate: PortfolioPlanCandidate
    trade: PortfolioPlanTrade


@dataclass(frozen=True, slots=True)
class _PlannerSellCandidate:
    proposal: TraderProposal
    candidate: PortfolioPlanCandidate
    trade: PortfolioPlanTrade
    generated: bool = False


@dataclass(slots=True)
class _FundingTracker:
    existing_cash_remaining_inr: Decimal
    same_run_proceeds_remaining_inr: Decimal
    same_run_proceeds_available_inr: Decimal


class RunLevelAllocationService:
    """Batch allocator that compares all trader proposals before sizing buys."""

    model_version = RUN_ALLOCATION_MODEL_VERSION

    def allocate(self, allocation_input: RunAllocationInput) -> RunAllocationResult:
        if allocation_input.money_management_policy is not None:
            return self._allocate_with_money_management(allocation_input)
        if allocation_input.fallback_policy is None:
            raise ValueError(
                "Run-level allocation requires a money-management policy or fallback policy."
            )
        return self._allocate_with_fallback(allocation_input)

    def _allocate_with_money_management(
        self,
        allocation_input: RunAllocationInput,
    ) -> RunAllocationResult:
        assert allocation_input.money_management_policy is not None
        service = PortfolioAllocationService(allocation_input.money_management_policy)
        simulated_positions = tuple(allocation_input.current_positions)
        simulated_sleeves = tuple(allocation_input.sleeve_snapshots)
        available_cash = allocation_input.available_cash_inr
        proposals: list[TraderProposal] = []
        ledger: list[AllocationLedgerEntry] = []
        candidates: list[tuple[tuple[Decimal, int, Decimal, str, str], TraderProposal]] = []

        for proposal in sorted(allocation_input.proposals, key=_proposal_sort_key):
            if proposal.action == "BUY":
                score_input = _active_input_for(
                    allocation_input,
                    proposal=proposal,
                    available_cash=allocation_input.available_cash_inr,
                    current_positions=allocation_input.current_positions,
                    sleeve_snapshots=allocation_input.sleeve_snapshots,
                )
                candidate_score, _score_parts = service.candidate_score(score_input)
                strategy_rank = _strategy_rank(allocation_input, proposal.symbol)
                sort_key = (
                    -candidate_score,
                    strategy_rank if strategy_rank is not None else 1_000_000,
                    -proposal.confidence,
                    proposal.symbol.upper(),
                    proposal.proposal_id,
                )
                candidates.append((sort_key, proposal))
                continue

            allocated = service.allocate(
                _active_input_for(
                    allocation_input,
                    proposal=proposal,
                    available_cash=available_cash,
                    current_positions=simulated_positions,
                    sleeve_snapshots=simulated_sleeves,
                )
            )
            status = _lifecycle_status(proposal)
            updated = _with_run_status(
                allocated,
                status=status,
                summary_suffix="Run-level allocation preserved lifecycle handling.",
            )
            proposals.append(updated)
            ledger.append(_ledger_entry(allocation_input, updated, status=status))

        for _sort_key, proposal in sorted(candidates, key=lambda item: item[0]):
            allocated = service.allocate(
                _active_input_for(
                    allocation_input,
                    proposal=proposal,
                    available_cash=available_cash,
                    current_positions=simulated_positions,
                    sleeve_snapshots=simulated_sleeves,
                )
            )
            decision = _require_decision(allocated)
            status = _money_management_buy_status(decision)
            updated = _with_run_status(
                allocated,
                status=status,
                summary_suffix=_summary_suffix_for_status(status, decision),
            )
            proposals.append(updated)
            ledger.append(_ledger_entry(allocation_input, updated, status=status))

            if status in SELECTED_LEDGER_STATUSES and decision.approved_quantity > 0:
                available_cash = max(
                    Decimal("0"),
                    available_cash - decision.approved_notional_inr,
                ).quantize(MONEY_QUANT)
                opened_new_position = proposal.current_position_quantity <= 0
                simulated_positions = _positions_with_pending_allocation(
                    simulated_positions,
                    symbol=proposal.symbol,
                    quantity=decision.approved_quantity,
                    notional=decision.approved_notional_inr,
                )
                simulated_sleeves = _sleeves_with_pending_allocation(
                    simulated_sleeves,
                    sleeve_id=decision.sleeve_id,
                    notional=decision.approved_notional_inr,
                    risk=decision.estimated_risk_inr,
                    opened_new_position=opened_new_position,
                )

        return _result(
            proposals=tuple(sorted(proposals, key=_proposal_sort_key)),
            ledger=tuple(sorted(ledger, key=lambda entry: entry.symbol)),
            policy_source="money_management_policy",
        )

    def _allocate_with_fallback(
        self,
        allocation_input: RunAllocationInput,
    ) -> RunAllocationResult:
        assert allocation_input.fallback_policy is not None
        policy = allocation_input.fallback_policy
        simulated_positions = tuple(allocation_input.current_positions)
        available_cash = allocation_input.available_cash_inr
        proposals: list[TraderProposal] = []
        ledger: list[AllocationLedgerEntry] = []
        candidates: list[tuple[tuple[Decimal, int, Decimal, str, str], TraderProposal]] = []

        for proposal in sorted(allocation_input.proposals, key=_proposal_sort_key):
            if proposal.action != "BUY":
                status = _lifecycle_status(proposal)
                decision = _fallback_lifecycle_decision(
                    allocation_input,
                    proposal=proposal,
                    status=status,
                    policy=policy,
                )
                updated = _fallback_updated_proposal(proposal, decision, status=status)
                proposals.append(updated)
                ledger.append(_ledger_entry(allocation_input, updated, status=status))
                continue

            candidate_score = _fallback_candidate_score(allocation_input, proposal)
            strategy_rank = _strategy_rank(allocation_input, proposal.symbol)
            candidates.append(
                (
                    (
                        -candidate_score,
                        strategy_rank if strategy_rank is not None else 1_000_000,
                        -proposal.confidence,
                        proposal.symbol.upper(),
                        proposal.proposal_id,
                    ),
                    proposal,
                )
            )

        for _sort_key, proposal in sorted(candidates, key=lambda item: item[0]):
            decision = _fallback_buy_decision(
                allocation_input,
                proposal=proposal,
                policy=policy,
                available_cash=available_cash,
                current_positions=simulated_positions,
            )
            status = _fallback_buy_status(decision)
            updated = _fallback_updated_proposal(proposal, decision, status=status)
            proposals.append(updated)
            ledger.append(_ledger_entry(allocation_input, updated, status=status))
            if status in SELECTED_LEDGER_STATUSES and decision.approved_quantity > 0:
                available_cash = max(
                    Decimal("0"),
                    available_cash - decision.approved_notional_inr,
                ).quantize(MONEY_QUANT)
                simulated_positions = _positions_with_pending_allocation(
                    simulated_positions,
                    symbol=proposal.symbol,
                    quantity=decision.approved_quantity,
                    notional=decision.approved_notional_inr,
                )

        return _result(
            proposals=tuple(sorted(proposals, key=_proposal_sort_key)),
            ledger=tuple(sorted(ledger, key=lambda entry: entry.symbol)),
            policy_source=policy.source,
        )


class PortfolioPlanAllocationService:
    """Executable rebalance allocator driven by the persisted portfolio plan."""

    model_version = PORTFOLIO_PLAN_ALLOCATION_MODEL_VERSION

    def allocate(
        self,
        allocation_input: RunAllocationInput,
        *,
        portfolio_plan: PortfolioRebalancePlan,
    ) -> RunAllocationResult:
        if allocation_input.money_management_policy is None:
            return RunLevelAllocationService().allocate(allocation_input)

        policy = allocation_input.money_management_policy
        service = PortfolioAllocationService(policy)
        simulated_positions = tuple(allocation_input.current_positions)
        simulated_sleeves = tuple(allocation_input.sleeve_snapshots)
        available_cash = (
            allocation_input.available_cash_inr
            + portfolio_plan.same_run_sell_proceeds_spendable_inr
        ).quantize(MONEY_QUANT)
        funding_tracker = _funding_tracker_for_plan(
            allocation_input,
            portfolio_plan=portfolio_plan,
        )
        proposals: list[TraderProposal] = []
        ledger: list[AllocationLedgerEntry] = []
        processed_proposal_ids: set[str] = set()

        for item in _planner_sell_candidates(
            allocation_input,
            portfolio_plan=portfolio_plan,
        ):
            updated = _with_plan_sell_linkage(
                item.proposal,
                portfolio_plan=portfolio_plan,
                candidate=item.candidate,
                trade=item.trade,
                proposal_source=_proposal_source_for_plan_candidate(item.candidate),
            )
            status = _lifecycle_status(updated)
            updated = _with_run_status(
                updated,
                status=status,
                summary_suffix="Portfolio-plan allocation selected this sell-side lifecycle proposal.",
                allocation_model_version=self.model_version,
            )
            proposals.append(updated)
            ledger.append(_ledger_entry(allocation_input, updated, status=status))
            processed_proposal_ids.add(updated.proposal_id)

        for proposal in sorted(allocation_input.proposals, key=_proposal_sort_key):
            if proposal.action == "BUY" or proposal.proposal_id in processed_proposal_ids:
                continue
            allocated = service.allocate(
                _active_input_for(
                    allocation_input,
                    proposal=proposal,
                    available_cash=available_cash,
                    current_positions=simulated_positions,
                    sleeve_snapshots=simulated_sleeves,
                )
            )
            status = _lifecycle_status(proposal)
            updated = _with_run_status(
                allocated,
                status=status,
                summary_suffix="Portfolio-plan allocation preserved lifecycle handling.",
                allocation_model_version=self.model_version,
            )
            proposals.append(updated)
            ledger.append(_ledger_entry(allocation_input, updated, status=status))

        buy_candidates = _planner_buy_candidates(
            allocation_input,
            portfolio_plan=portfolio_plan,
        )
        sortable: list[tuple[tuple[Decimal, int, int, Decimal, str, str], _PlannerBuyCandidate]] = []
        for item in buy_candidates:
            score_input = _active_input_for_plan_candidate(
                allocation_input,
                item=item,
                portfolio_plan=portfolio_plan,
                available_cash=available_cash,
                current_positions=simulated_positions,
                sleeve_snapshots=simulated_sleeves,
            )
            candidate_score, _score_parts = service.candidate_score(score_input)
            sortable.append((_planner_sort_key(item, candidate_score), item))

        for _sort_key, item in sorted(sortable, key=lambda row: row[0]):
            allocated = service.allocate(
                _active_input_for_plan_candidate(
                    allocation_input,
                    item=item,
                    portfolio_plan=portfolio_plan,
                    available_cash=available_cash,
                    current_positions=simulated_positions,
                    sleeve_snapshots=simulated_sleeves,
                )
            )
            allocated = _with_plan_linkage(
                allocated,
                portfolio_plan=portfolio_plan,
                candidate=item.candidate,
                trade=item.trade,
            )
            decision = _require_decision(allocated)
            status = _money_management_buy_status(decision)
            allocated = _with_funding_metadata(
                allocated,
                portfolio_plan=portfolio_plan,
                funding_tracker=funding_tracker,
                decision=decision,
                status=status,
            )
            decision = _require_decision(allocated)
            updated = _with_run_status(
                allocated,
                status=status,
                summary_suffix=_portfolio_plan_summary_suffix(status, decision),
                allocation_model_version=self.model_version,
            )
            proposals.append(updated)
            ledger.append(_ledger_entry(allocation_input, updated, status=status))

            if status in SELECTED_LEDGER_STATUSES and decision.approved_quantity > 0:
                available_cash = max(
                    Decimal("0"),
                    available_cash - decision.approved_notional_inr,
                ).quantize(MONEY_QUANT)
                opened_new_position = item.proposal.current_position_quantity <= 0
                simulated_positions = _positions_with_pending_allocation(
                    simulated_positions,
                    symbol=item.proposal.symbol,
                    quantity=decision.approved_quantity,
                    notional=decision.approved_notional_inr,
                )
                simulated_sleeves = _sleeves_with_pending_allocation(
                    simulated_sleeves,
                    sleeve_id=decision.sleeve_id,
                    notional=decision.approved_notional_inr,
                    risk=decision.estimated_risk_inr,
                    opened_new_position=opened_new_position,
                )

        return _result(
            proposals=tuple(sorted(proposals, key=_proposal_sort_key)),
            ledger=tuple(sorted(ledger, key=lambda entry: entry.symbol)),
            policy_source="portfolio_plan",
            model_version=self.model_version,
        )


def _active_input_for(
    allocation_input: RunAllocationInput,
    *,
    proposal: TraderProposal,
    available_cash: Decimal,
    current_positions: tuple[ActiveAllocationPosition, ...],
    sleeve_snapshots: tuple[SleeveAllocationSnapshot, ...],
) -> ActiveAllocationInput:
    return ActiveAllocationInput(
        proposal=proposal.model_copy(update={"allocation_decision": None}),
        strategy_name=allocation_input.strategy_name,
        nav_inr=allocation_input.nav_inr,
        available_cash_inr=available_cash,
        portfolio_starting_nav_estimate_inr=(
            allocation_input.portfolio_starting_nav_estimate_inr
        ),
        current_positions=current_positions,
        sleeve_snapshots=sleeve_snapshots,
        core_basket_symbols=allocation_input.core_basket_symbols,
        history=tuple(
            allocation_input.histories_by_symbol.get(proposal.symbol.upper(), tuple())
        ),
        strategy_score=_strategy_score(allocation_input, proposal.symbol),
        strategy_rank=_strategy_rank(allocation_input, proposal.symbol),
        sector_by_symbol=dict(allocation_input.sector_by_symbol),
        graph_cluster_by_symbol=dict(allocation_input.graph_cluster_by_symbol),
    )


def _active_input_for_plan_candidate(
    allocation_input: RunAllocationInput,
    *,
    item: _PlannerBuyCandidate,
    portfolio_plan: PortfolioRebalancePlan,
    available_cash: Decimal,
    current_positions: tuple[ActiveAllocationPosition, ...],
    sleeve_snapshots: tuple[SleeveAllocationSnapshot, ...],
) -> ActiveAllocationInput:
    candidate = item.candidate
    return ActiveAllocationInput(
        proposal=item.proposal.model_copy(update={"allocation_decision": None}),
        strategy_name=candidate.strategy_name or allocation_input.strategy_name,
        nav_inr=allocation_input.nav_inr,
        available_cash_inr=available_cash,
        portfolio_starting_nav_estimate_inr=(
            allocation_input.portfolio_starting_nav_estimate_inr
        ),
        current_positions=current_positions,
        sleeve_snapshots=sleeve_snapshots,
        core_basket_symbols=allocation_input.core_basket_symbols,
        history=tuple(
            allocation_input.histories_by_symbol.get(candidate.symbol.upper(), tuple())
        ),
        strategy_score=(
            candidate.raw_strategy_score
            if candidate.source == CORE_STRATEGY_NAME
            else _strategy_score(allocation_input, candidate.symbol)
        ),
        strategy_rank=candidate.strategy_rank,
        strategy_score_component_override=(
            candidate.allocation_score_component
            if candidate.source == CORE_STRATEGY_NAME
            else None
        ),
        buy_price_buffer_pct=portfolio_plan.buy_price_buffer_pct,
        sleeve_capacity_overrides_inr=_sleeve_capacity_overrides(portfolio_plan),
        sector_by_symbol=dict(allocation_input.sector_by_symbol),
        graph_cluster_by_symbol=dict(allocation_input.graph_cluster_by_symbol),
    )


def _planner_buy_candidates(
    allocation_input: RunAllocationInput,
    *,
    portfolio_plan: PortfolioRebalancePlan,
) -> tuple[_PlannerBuyCandidate, ...]:
    proposals_by_symbol = {
        proposal.symbol.upper(): proposal
        for proposal in allocation_input.proposals
    }
    candidates_by_proposal_id = {
        candidate.proposal_id: candidate
        for candidate in portfolio_plan.candidates
        if candidate.proposal_id
    }
    core_candidates_by_symbol = {
        candidate.symbol.upper(): candidate
        for candidate in portfolio_plan.candidates
        if candidate.source == CORE_STRATEGY_NAME
    }
    rows: list[_PlannerBuyCandidate] = []
    routed_symbols: set[str] = set()
    for trade in sorted(
        portfolio_plan.planned_trades,
        key=lambda row: (
            row.rank if row.rank is not None else 1_000_000,
            row.source,
            row.symbol,
            row.trade_id,
        ),
    ):
        symbol = trade.symbol.upper()
        if symbol in routed_symbols:
            continue
        if trade.side != "BUY" or trade.status in {"missing_price", "no_trade"}:
            continue
        candidate = (
            candidates_by_proposal_id.get(trade.proposal_id)
            if trade.proposal_id
            else core_candidates_by_symbol.get(symbol)
        )
        if candidate is None or candidate.action != "BUY":
            continue
        existing = proposals_by_symbol.get(symbol)
        if existing is not None:
            if candidate.source == CORE_STRATEGY_NAME and candidate.proposal_id is None:
                if existing.action != "BUY":
                    routed_symbols.add(symbol)
                continue
            if existing.action != "BUY":
                routed_symbols.add(symbol)
                continue
            rows.append(
                _PlannerBuyCandidate(
                    proposal=existing,
                    candidate=candidate,
                    trade=trade,
                )
            )
            routed_symbols.add(symbol)
            continue
        if candidate.source != CORE_STRATEGY_NAME:
            continue
        rows.append(
            _PlannerBuyCandidate(
                proposal=_core_generated_proposal(
                    allocation_input,
                    portfolio_plan=portfolio_plan,
                    candidate=candidate,
                    trade=trade,
                ),
                candidate=candidate,
                trade=trade,
            )
        )
        routed_symbols.add(symbol)
    return tuple(rows)


def _planner_sell_candidates(
    allocation_input: RunAllocationInput,
    *,
    portfolio_plan: PortfolioRebalancePlan,
) -> tuple[_PlannerSellCandidate, ...]:
    proposals_by_symbol = {
        proposal.symbol.upper(): proposal
        for proposal in allocation_input.proposals
    }
    candidates_by_proposal_id = {
        candidate.proposal_id: candidate
        for candidate in portfolio_plan.candidates
        if candidate.proposal_id
    }
    generated_candidates_by_symbol = {
        candidate.symbol.upper(): candidate
        for candidate in portfolio_plan.candidates
        if candidate.proposal_id is None
        and candidate.source in {CORE_STRATEGY_NAME, THRESHOLD_REBALANCE_SOURCE}
    }
    rows: list[_PlannerSellCandidate] = []
    routed_symbols: set[str] = set()
    for trade in sorted(
        portfolio_plan.planned_trades,
        key=lambda row: (
            row.rank if row.rank is not None else 1_000_000,
            row.source,
            row.symbol,
            row.trade_id,
        ),
    ):
        symbol = trade.symbol.upper()
        if symbol in routed_symbols:
            continue
        if trade.side != "SELL" or trade.status in {"missing_price", "no_trade"}:
            continue
        if trade.estimated_quantity <= 0:
            continue
        candidate = (
            candidates_by_proposal_id.get(trade.proposal_id)
            if trade.proposal_id
            else generated_candidates_by_symbol.get(symbol)
        )
        if candidate is None or candidate.action not in {"REDUCE", "EXIT", "SELL"}:
            continue
        existing = proposals_by_symbol.get(symbol)
        if existing is not None:
            rows.append(
                _PlannerSellCandidate(
                    proposal=_proposal_for_plan_sell(
                        existing,
                        portfolio_plan=portfolio_plan,
                        candidate=candidate,
                        trade=trade,
                    ),
                    candidate=candidate,
                    trade=trade,
                    generated=False,
                )
            )
            routed_symbols.add(symbol)
            continue
        rows.append(
            _PlannerSellCandidate(
                proposal=_generated_sell_proposal(
                    allocation_input,
                    portfolio_plan=portfolio_plan,
                    candidate=candidate,
                    trade=trade,
                ),
                candidate=candidate,
                trade=trade,
                generated=True,
            )
        )
        routed_symbols.add(symbol)
    return tuple(rows)


def _core_generated_proposal(
    allocation_input: RunAllocationInput,
    *,
    portfolio_plan: PortfolioRebalancePlan,
    candidate: PortfolioPlanCandidate,
    trade: PortfolioPlanTrade,
) -> TraderProposal:
    symbol = candidate.symbol.upper()
    source_ids = [portfolio_plan.plan_id, trade.trade_id]
    return TraderProposal(
        proposal_id=f"tp-core-{portfolio_plan.run_id}-{symbol.lower()}",
        run_id=portfolio_plan.run_id,
        portfolio_id=portfolio_plan.portfolio_id,
        symbol=symbol,
        debate_id=f"deb-core-{portfolio_plan.run_id}-{symbol.lower()}",
        as_of=portfolio_plan.as_of,
        action="BUY",
        confidence=candidate.confidence,
        horizon="medium",
        requested_position_pct_nav=candidate.target_position_pct_nav,
        current_position_quantity=_current_position_quantity(allocation_input, symbol),
        current_position_pct_nav=candidate.current_position_pct_nav,
        target_position_pct_nav=candidate.target_position_pct_nav,
        lifecycle_trigger="portfolio_rebalance",
        evaluation_mode="after_close",
        latest_price_inr=candidate.latest_price_inr,
        order_type="MARKET",
        entry_rule=(
            "portfolio_rebalance: core Shariah basket BUY generated by the "
            "portfolio plan."
        ),
        stop_loss_pct=Decimal("6.0000"),
        take_profit_pct=Decimal("12.0000"),
        reason_summary=(
            "Portfolio rebalance planner generated an executable core Shariah BUY "
            f"candidate from {trade.trade_id}."
        ),
        invalid_if=[
            "Portfolio plan is superseded before risk review.",
            "Risk review or final approval rejects the core BUY.",
        ],
        position_management_summary=(
            "Portfolio-plan core candidate generated for paper-only risk, final, "
            "and next-open routing."
        ),
        source_report_ids=source_ids,
        is_order=False,
        requires_risk_approval=True,
        target_sizing_metadata={
            "proposal_source": "portfolio_plan_core",
            "portfolio_plan_id": portfolio_plan.plan_id,
            "portfolio_plan_trade_id": trade.trade_id,
            "planner_candidate_id": candidate.candidate_id,
            "planner_source": candidate.source,
            "planner_rank": trade.rank,
            "sleeve_id": candidate.sleeve_id,
            "score_evidence": candidate.score_evidence,
        },
        model_version="portfolio_rebalance_core_proposal_v1",
    )


def _generated_sell_proposal(
    allocation_input: RunAllocationInput,
    *,
    portfolio_plan: PortfolioRebalancePlan,
    candidate: PortfolioPlanCandidate,
    trade: PortfolioPlanTrade,
) -> TraderProposal:
    symbol = candidate.symbol.upper()
    action = "EXIT" if trade.action == "SELL" else trade.action
    source_ids = [portfolio_plan.plan_id, trade.trade_id]
    current_quantity = _current_position_quantity(allocation_input, symbol)
    return TraderProposal(
        proposal_id=f"tp-rebalance-{portfolio_plan.run_id}-{symbol.lower()}",
        run_id=portfolio_plan.run_id,
        portfolio_id=portfolio_plan.portfolio_id,
        symbol=symbol,
        debate_id=f"deb-rebalance-{portfolio_plan.run_id}-{symbol.lower()}",
        as_of=portfolio_plan.as_of,
        action=action,  # type: ignore[arg-type]
        confidence=candidate.confidence,
        horizon="medium",
        requested_position_pct_nav=trade.target_pct_nav,
        current_position_quantity=current_quantity,
        current_position_pct_nav=trade.current_pct_nav,
        target_position_pct_nav=trade.target_pct_nav,
        lifecycle_trigger="portfolio_rebalance",
        evaluation_mode="after_close",
        latest_price_inr=trade.latest_price_inr,
        order_type="MARKET",
        entry_rule=(
            "portfolio_rebalance: planner-generated paper sell candidate "
            "requires risk and final approval."
        ),
        stop_loss_pct=Decimal("6.0000"),
        take_profit_pct=Decimal("12.0000"),
        reason_summary=(
            "Portfolio rebalance planner generated an executable "
            f"{action} candidate from {trade.trade_id}."
        ),
        invalid_if=[
            "Portfolio plan is superseded before risk review.",
            "Risk review or final approval rejects the sell-side rebalance.",
        ],
        position_management_summary=(
            "Portfolio-plan sell candidate generated for paper-only risk, "
            "final approval, and sell-first next-open routing."
        ),
        source_report_ids=source_ids,
        is_order=False,
        requires_risk_approval=True,
        target_sizing_metadata={
            "proposal_source": _planner_generated_proposal_source(candidate),
            "portfolio_plan_id": portfolio_plan.plan_id,
            "portfolio_plan_trade_id": trade.trade_id,
            "planner_candidate_id": candidate.candidate_id,
            "planner_source": candidate.source,
            "planner_rank": trade.rank,
            "sleeve_id": trade.sleeve_id,
            "score_evidence": candidate.score_evidence,
        },
        model_version="portfolio_rebalance_sell_proposal_v1",
    )


def _proposal_for_plan_sell(
    proposal: TraderProposal,
    *,
    portfolio_plan: PortfolioRebalancePlan,
    candidate: PortfolioPlanCandidate,
    trade: PortfolioPlanTrade,
) -> TraderProposal:
    action = "EXIT" if trade.action == "SELL" else trade.action
    metadata = dict(proposal.target_sizing_metadata)
    metadata.update(
        {
            "proposal_source": _proposal_source_for_plan_candidate(candidate),
            "portfolio_plan_id": portfolio_plan.plan_id,
            "portfolio_plan_trade_id": trade.trade_id,
            "planner_candidate_id": candidate.candidate_id,
            "planner_source": candidate.source,
            "planner_rank": trade.rank,
            "sleeve_id": trade.sleeve_id,
            "score_evidence": candidate.score_evidence,
        }
    )
    return proposal.model_copy(
        update={
            "action": action,
            "requested_position_pct_nav": trade.target_pct_nav,
            "target_position_pct_nav": trade.target_pct_nav,
            "lifecycle_trigger": "portfolio_rebalance",
            "order_type": "MARKET",
            "entry_rule": (
                "portfolio_rebalance: plan-selected sell-side lifecycle proposal "
                "requires risk and final approval."
            ),
            "reason_summary": (
                f"Portfolio rebalance planner selected {action} from {trade.trade_id}."
            ),
            "position_management_summary": _append_sentence(
                proposal.position_management_summary,
                (
                    "Portfolio-plan threshold selected sell-side lifecycle handling "
                    f"for {trade.trade_id}."
                ),
            ),
            "target_sizing_metadata": metadata,
        }
    )


def _with_plan_linkage(
    proposal: TraderProposal,
    *,
    portfolio_plan: PortfolioRebalancePlan,
    candidate: PortfolioPlanCandidate,
    trade: PortfolioPlanTrade,
) -> TraderProposal:
    decision = _require_decision(proposal)
    capacity_source, borrowed_from = _capacity_metadata_for_trade(
        portfolio_plan,
        trade=trade,
    )
    proposal_source = (
        "portfolio_plan_core"
        if candidate.source == CORE_STRATEGY_NAME and candidate.proposal_id is None
        else "trader_proposal"
    )
    linked_decision = decision.model_copy(
        update={
            "portfolio_plan_id": portfolio_plan.plan_id,
            "portfolio_plan_trade_id": trade.trade_id,
            "planner_candidate_id": candidate.candidate_id,
            "planner_source": candidate.source,
            "planner_rank": trade.rank,
            "capacity_source": capacity_source,
            "borrowed_from_sleeve_ids": borrowed_from,
            "proposal_source": proposal_source,
            "rationale": (
                *decision.rationale,
                f"Portfolio plan {portfolio_plan.plan_id} selected trade {trade.trade_id}.",
                f"Planner source {candidate.source}; planner rank {trade.rank}.",
                f"Capacity source {capacity_source}.",
            ),
        }
    )
    metadata = dict(proposal.target_sizing_metadata)
    metadata.update(
        {
            "proposal_source": proposal_source,
            "portfolio_plan_id": portfolio_plan.plan_id,
            "portfolio_plan_trade_id": trade.trade_id,
            "planner_candidate_id": candidate.candidate_id,
            "planner_source": candidate.source,
            "planner_rank": trade.rank,
            "capacity_source": capacity_source,
            "borrowed_from_sleeve_ids": list(borrowed_from),
        }
    )
    return proposal.model_copy(
        update={
            "allocation_decision": linked_decision,
            "target_sizing_metadata": metadata,
        }
    )


def _with_plan_sell_linkage(
    proposal: TraderProposal,
    *,
    portfolio_plan: PortfolioRebalancePlan,
    candidate: PortfolioPlanCandidate,
    trade: PortfolioPlanTrade,
    proposal_source: str,
) -> TraderProposal:
    action = "EXIT" if trade.action == "SELL" else trade.action
    decision = AllocationDecision(
        symbol=proposal.symbol,
        action=action,
        strategy_name=candidate.strategy_name or "portfolio_rebalance",
        sleeve_id=trade.sleeve_id,
        sleeve_name=None,
        status="unchanged",
        candidate_score=candidate.allocation_score_component,
        score_band="portfolio_rebalance_sell",
        requested_position_pct_nav=proposal.requested_position_pct_nav,
        approved_position_pct_nav=trade.target_pct_nav,
        requested_notional_inr=trade.estimated_notional_inr,
        approved_notional_inr=trade.estimated_notional_inr,
        approved_quantity=trade.estimated_quantity,
        binding_constraint="portfolio_rebalance_sell_lifecycle",
        portfolio_plan_id=portfolio_plan.plan_id,
        portfolio_plan_trade_id=trade.trade_id,
        planner_candidate_id=candidate.candidate_id,
        planner_source=candidate.source,
        planner_rank=trade.rank,
        capacity_source="sell_proceeds_source",
        proposal_source=proposal_source,
        same_run_proceeds_available_inr=portfolio_plan.same_run_sell_proceeds_spendable_inr,
        same_run_proceeds_haircut_pct=portfolio_plan.same_run_sell_proceeds_haircut_pct,
        hard_cash_reserve_inr=portfolio_plan.hard_cash_reserve_inr,
        buy_price_buffer_pct=portfolio_plan.buy_price_buffer_pct,
        rationale=(
            f"Portfolio plan {portfolio_plan.plan_id} selected sell trade {trade.trade_id}.",
            "Long-only sell quantity is capped by the current holding.",
            (
                "Only the configured haircut share of accepted same-run sell "
                "proceeds may fund BUY sizing."
            ),
        ),
    )
    metadata = dict(proposal.target_sizing_metadata)
    metadata.update(
        {
            "proposal_source": proposal_source,
            "portfolio_plan_id": portfolio_plan.plan_id,
            "portfolio_plan_trade_id": trade.trade_id,
            "planner_candidate_id": candidate.candidate_id,
            "planner_source": candidate.source,
            "planner_rank": trade.rank,
            "capacity_source": "sell_proceeds_source",
        }
    )
    return proposal.model_copy(
        update={
            "allocation_decision": decision,
            "target_sizing_metadata": metadata,
        }
    )


def _with_funding_metadata(
    proposal: TraderProposal,
    *,
    portfolio_plan: PortfolioRebalancePlan,
    funding_tracker: _FundingTracker,
    decision: AllocationDecision,
    status: str,
) -> TraderProposal:
    if status not in SELECTED_LEDGER_STATUSES or decision.approved_notional_inr <= 0:
        updated_decision = decision.model_copy(
            update={
                "same_run_proceeds_available_inr": funding_tracker.same_run_proceeds_available_inr,
                "same_run_proceeds_haircut_pct": portfolio_plan.same_run_sell_proceeds_haircut_pct,
                "hard_cash_reserve_inr": portfolio_plan.hard_cash_reserve_inr,
                "buy_price_buffer_pct": portfolio_plan.buy_price_buffer_pct,
            }
        )
        return proposal.model_copy(update={"allocation_decision": updated_decision})

    approved_notional = decision.approved_notional_inr
    existing_used = min(
        funding_tracker.existing_cash_remaining_inr,
        approved_notional,
    ).quantize(MONEY_QUANT)
    remaining = (approved_notional - existing_used).quantize(MONEY_QUANT)
    proceeds_used = min(
        funding_tracker.same_run_proceeds_remaining_inr,
        remaining,
    ).quantize(MONEY_QUANT)
    funding_tracker.existing_cash_remaining_inr = max(
        Decimal("0.00"),
        funding_tracker.existing_cash_remaining_inr - existing_used,
    ).quantize(MONEY_QUANT)
    funding_tracker.same_run_proceeds_remaining_inr = max(
        Decimal("0.00"),
        funding_tracker.same_run_proceeds_remaining_inr - proceeds_used,
    ).quantize(MONEY_QUANT)
    funding_source = _funding_source_label(
        existing_cash_used=existing_used,
        same_run_proceeds_used=proceeds_used,
        capacity_source=decision.capacity_source,
    )
    updated_decision = decision.model_copy(
        update={
            "funding_source": funding_source,
            "existing_cash_used_inr": existing_used,
            "same_run_proceeds_used_inr": proceeds_used,
            "same_run_proceeds_available_inr": funding_tracker.same_run_proceeds_available_inr,
            "same_run_proceeds_haircut_pct": portfolio_plan.same_run_sell_proceeds_haircut_pct,
            "hard_cash_reserve_inr": portfolio_plan.hard_cash_reserve_inr,
            "buy_price_buffer_pct": portfolio_plan.buy_price_buffer_pct,
            "rationale": (
                *decision.rationale,
                (
                    f"BUY funding source {funding_source}; existing cash used "
                    f"{existing_used}, same-run proceeds used {proceeds_used}."
                ),
            ),
        }
    )
    metadata = dict(proposal.target_sizing_metadata)
    metadata.update(
        {
            "funding_source": funding_source,
            "existing_cash_used_inr": str(existing_used),
            "same_run_proceeds_used_inr": str(proceeds_used),
            "same_run_proceeds_available_inr": str(
                funding_tracker.same_run_proceeds_available_inr
            ),
        }
    )
    return proposal.model_copy(
        update={
            "allocation_decision": updated_decision,
            "target_sizing_metadata": metadata,
        }
    )


def _funding_tracker_for_plan(
    allocation_input: RunAllocationInput,
    *,
    portfolio_plan: PortfolioRebalancePlan,
) -> _FundingTracker:
    existing_cash = max(
        Decimal("0.00"),
        allocation_input.available_cash_inr - portfolio_plan.hard_cash_reserve_inr,
    ).quantize(MONEY_QUANT)
    same_run_proceeds = portfolio_plan.same_run_sell_proceeds_spendable_inr.quantize(
        MONEY_QUANT
    )
    return _FundingTracker(
        existing_cash_remaining_inr=existing_cash,
        same_run_proceeds_remaining_inr=same_run_proceeds,
        same_run_proceeds_available_inr=same_run_proceeds,
    )


def _funding_source_label(
    *,
    existing_cash_used: Decimal,
    same_run_proceeds_used: Decimal,
    capacity_source: str | None,
) -> str:
    sources: list[str] = []
    if existing_cash_used > 0:
        sources.append("existing_cash")
    if same_run_proceeds_used > 0:
        sources.append("same_run_sell_proceeds")
    if capacity_source == "borrowed_sleeve_capacity":
        sources.append("borrowed_sleeve_capacity")
    if not sources:
        return "none"
    return "+".join(sources)


def _proposal_source_for_plan_candidate(candidate: PortfolioPlanCandidate) -> str:
    if candidate.source == CORE_STRATEGY_NAME:
        return "portfolio_plan_core"
    if candidate.source == THRESHOLD_REBALANCE_SOURCE:
        return "portfolio_plan_threshold"
    return "trader_proposal"


def _planner_generated_proposal_source(candidate: PortfolioPlanCandidate) -> str:
    return _proposal_source_for_plan_candidate(candidate)


def _planner_sort_key(
    item: _PlannerBuyCandidate,
    candidate_score: Decimal,
) -> tuple[Decimal, int, int, Decimal, str, str]:
    source_order = 0 if item.candidate.source == "trader_proposal" else 1
    rank = item.trade.rank if item.trade.rank is not None else 1_000_000
    return (
        -candidate_score,
        rank,
        source_order,
        -item.proposal.confidence,
        item.proposal.symbol.upper(),
        item.trade.trade_id,
    )


def _sleeve_capacity_overrides(
    portfolio_plan: PortfolioRebalancePlan,
) -> dict[str, Decimal]:
    overrides: dict[str, Decimal] = {}
    for row in portfolio_plan.sleeve_budgets:
        target = row.target_exposure_inr
        if row.borrowed_capacity_inr > 0:
            target = (target + row.borrowed_capacity_inr).quantize(MONEY_QUANT)
        overrides[row.sleeve_id] = target
    return overrides


def _capacity_metadata_for_trade(
    portfolio_plan: PortfolioRebalancePlan,
    *,
    trade: PortfolioPlanTrade,
) -> tuple[str, tuple[str, ...]]:
    sleeve = next(
        (
            row
            for row in portfolio_plan.sleeve_budgets
            if row.sleeve_id == trade.sleeve_id
        ),
        None,
    )
    if sleeve is None or sleeve.borrowed_capacity_inr <= 0:
        return "own_sleeve", tuple()
    borrowed_from = tuple(
        row.sleeve_id
        for row in portfolio_plan.sleeve_budgets
        if row.borrowed_by_sleeve_id == sleeve.sleeve_id
    )
    return "borrowed_sleeve_capacity", borrowed_from


def _current_position_quantity(allocation_input: RunAllocationInput, symbol: str) -> int:
    normalized = symbol.upper()
    for position in allocation_input.current_positions:
        if position.symbol.upper() == normalized:
            return position.quantity
    return 0


def _money_management_buy_status(decision: AllocationDecision) -> str:
    if decision.status == "approved" and decision.approved_quantity > 0:
        if decision.binding_constraint != "requested_notional":
            return "allocation_reduced"
        return "selected"
    if decision.binding_constraint in RUN_LEVEL_RESOURCE_CONSTRAINTS:
        return "not_selected"
    return "allocation_rejected"


def _fallback_buy_status(decision: AllocationDecision) -> str:
    if decision.approved_quantity > 0:
        if decision.binding_constraint != "requested_notional":
            return "allocation_reduced"
        return "selected"
    if decision.binding_constraint in {
        "available_cash",
        "open_positions",
        "stock_exposure",
    }:
        return "not_selected"
    return "allocation_rejected"


def _lifecycle_status(proposal: TraderProposal) -> str:
    if proposal.current_position_quantity > 0:
        return "open_position_management"
    return "unchanged_lifecycle"


def _with_run_status(
    proposal: TraderProposal,
    *,
    status: str,
    summary_suffix: str,
    allocation_model_version: str = RUN_ALLOCATION_MODEL_VERSION,
) -> TraderProposal:
    decision = _require_decision(proposal).model_copy(update={"status": status})
    updates: dict[str, object] = {
        "allocation_decision": decision,
        "model_version": _append_model_version(
            proposal.model_version,
            allocation_model_version=allocation_model_version,
        ),
        "position_management_summary": _append_sentence(
            proposal.position_management_summary,
            summary_suffix,
        ),
    }
    if decision.action == "BUY" and status in SELECTED_LEDGER_STATUSES:
        updates["target_position_pct_nav"] = decision.approved_position_pct_nav
    if decision.action == "BUY" and status not in SELECTED_LEDGER_STATUSES:
        updates.update(
            {
                "action": "HOLD" if proposal.current_position_quantity > 0 else "NO_TRADE",
                "target_position_pct_nav": proposal.current_position_pct_nav,
                "order_type": "NONE",
                "entry_rule": (
                    "not_selected_by_run_allocation: Run-level allocation did not "
                    "select this BUY proposal."
                ),
            }
        )
    return proposal.model_copy(update=updates)


def _fallback_updated_proposal(
    proposal: TraderProposal,
    decision: AllocationDecision,
    *,
    status: str,
) -> TraderProposal:
    decision = decision.model_copy(update={"status": status})
    updates: dict[str, object] = {
        "allocation_decision": decision,
        "model_version": _append_model_version(proposal.model_version),
    }
    if status in SELECTED_LEDGER_STATUSES:
        updates["target_position_pct_nav"] = decision.approved_position_pct_nav
        updates["position_management_summary"] = _append_sentence(
            proposal.position_management_summary,
            _summary_suffix_for_status(status, decision),
        )
    elif proposal.action == "BUY":
        updates.update(
            {
                "action": "HOLD" if proposal.current_position_quantity > 0 else "NO_TRADE",
                "target_position_pct_nav": proposal.current_position_pct_nav,
                "order_type": "NONE",
                "entry_rule": (
                    "not_selected_by_run_allocation: Run-level allocation did not "
                    "select this BUY proposal."
                ),
                "position_management_summary": _append_sentence(
                    proposal.position_management_summary,
                    _summary_suffix_for_status(status, decision),
                ),
            }
        )
    return proposal.model_copy(update=updates)


def _fallback_buy_decision(
    allocation_input: RunAllocationInput,
    *,
    proposal: TraderProposal,
    policy: FallbackAllocationPolicy,
    available_cash: Decimal,
    current_positions: tuple[ActiveAllocationPosition, ...],
) -> AllocationDecision:
    latest_price = _latest_close(
        allocation_input.histories_by_symbol.get(proposal.symbol.upper(), tuple())
    )
    current_notional = _pct_to_notional(
        proposal.current_position_pct_nav,
        allocation_input.nav_inr,
    )
    requested_notional = _requested_increase_notional(
        proposal=proposal,
        nav_inr=allocation_input.nav_inr,
    )
    candidate_score = _fallback_candidate_score(allocation_input, proposal)
    requested_position = proposal.requested_position_pct_nav
    binding_constraint: str | None = None
    allowed_notional = Decimal("0")

    if latest_price <= 0:
        binding_constraint = "invalid_latest_price"
    elif candidate_score < Decimal("50"):
        binding_constraint = "candidate_score_below_fallback_floor"
    else:
        caps = {
            "requested_notional": requested_notional,
            "stock_exposure": max(
                Decimal("0"),
                _pct_to_notional(policy.max_position_pct_nav, allocation_input.nav_inr)
                - current_notional,
            ).quantize(MONEY_QUANT),
            "available_cash": max(Decimal("0"), available_cash).quantize(MONEY_QUANT),
            "open_positions": _fallback_open_position_room(
                proposal=proposal,
                current_positions=current_positions,
                max_open_positions=policy.max_open_positions,
            ),
        }
        binding_constraint, allowed_notional = min(caps.items(), key=lambda item: (item[1], item[0]))

    quantity = (
        int((allowed_notional / latest_price).to_integral_value(rounding=ROUND_DOWN))
        if latest_price > 0
        else 0
    )
    approved_notional = _money(latest_price * Decimal(quantity)) if quantity > 0 else Decimal("0")
    approved_position = (
        ((current_notional + approved_notional) / allocation_input.nav_inr) * Decimal("100")
        if allocation_input.nav_inr > 0
        else Decimal("0")
    ).quantize(SCORE_QUANT)
    status = _fallback_buy_status_from_quantity(quantity, binding_constraint)
    return AllocationDecision(
        symbol=proposal.symbol,
        action=proposal.action,
        strategy_name=allocation_input.strategy_name,
        sleeve_id="settings_fallback",
        sleeve_name="Settings fallback",
        status=status,
        candidate_score=candidate_score,
        score_band="fallback_dynamic",
        requested_position_pct_nav=requested_position,
        approved_position_pct_nav=approved_position,
        requested_notional_inr=requested_notional,
        approved_notional_inr=approved_notional,
        approved_quantity=quantity,
        binding_constraint=binding_constraint,
        rationale=(
            "Settings fallback used TAURUS_MAX_OPEN_POSITIONS, "
            "TAURUS_MAX_POSITION_PCT, available cash, trader confidence, and "
            "strategy score.",
        ),
    )


def _fallback_lifecycle_decision(
    allocation_input: RunAllocationInput,
    *,
    proposal: TraderProposal,
    status: str,
    policy: FallbackAllocationPolicy,
) -> AllocationDecision:
    return AllocationDecision(
        symbol=proposal.symbol,
        action=proposal.action,
        strategy_name=allocation_input.strategy_name,
        sleeve_id="settings_fallback",
        sleeve_name="Settings fallback",
        status=status,
        candidate_score=_fallback_candidate_score(allocation_input, proposal),
        score_band="fallback_lifecycle",
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
            f"Settings fallback preserved lifecycle action under {policy.source} caps.",
        ),
    )


def _fallback_buy_status_from_quantity(
    quantity: int,
    binding_constraint: str | None,
) -> str:
    if quantity > 0:
        return "selected"
    if binding_constraint in {"available_cash", "open_positions", "stock_exposure"}:
        return "not_selected"
    return "allocation_rejected"


def _fallback_candidate_score(
    allocation_input: RunAllocationInput,
    proposal: TraderProposal,
) -> Decimal:
    strategy_component = _strategy_score_component(
        _strategy_score(allocation_input, proposal.symbol),
        strategy_rank=_strategy_rank(allocation_input, proposal.symbol),
    )
    confidence_component = (proposal.confidence * Decimal("100")).quantize(SCORE_QUANT)
    score = (
        (strategy_component * Decimal("0.60"))
        + (confidence_component * Decimal("0.40"))
    ).quantize(SCORE_QUANT)
    return _clamp(score, Decimal("0"), Decimal("100"))


def _strategy_score_component(
    score: Decimal | None,
    *,
    strategy_rank: int | None = None,
) -> Decimal:
    return calibrate_strategy_score(score, strategy_rank=strategy_rank).allocation_score_component


def _fallback_open_position_room(
    *,
    proposal: TraderProposal,
    current_positions: tuple[ActiveAllocationPosition, ...],
    max_open_positions: int,
) -> Decimal:
    if proposal.current_position_quantity > 0:
        return UNLIMITED_ROOM
    open_count = sum(1 for position in current_positions if position.quantity > 0)
    if open_count >= max_open_positions:
        return Decimal("0")
    return UNLIMITED_ROOM


def _positions_with_pending_allocation(
    positions: tuple[ActiveAllocationPosition, ...],
    *,
    symbol: str,
    quantity: int,
    notional: Decimal,
) -> tuple[ActiveAllocationPosition, ...]:
    normalized = symbol.upper()
    updated: list[ActiveAllocationPosition] = []
    matched = False
    for position in positions:
        if position.symbol.upper() != normalized:
            updated.append(position)
            continue
        matched = True
        updated.append(
            ActiveAllocationPosition(
                symbol=position.symbol,
                quantity=position.quantity + quantity,
                market_value_inr=(position.market_value_inr + notional).quantize(MONEY_QUANT),
            )
        )
    if not matched:
        updated.append(
            ActiveAllocationPosition(
                symbol=normalized,
                quantity=quantity,
                market_value_inr=notional.quantize(MONEY_QUANT),
            )
        )
    return tuple(sorted(updated, key=lambda position: position.symbol.upper()))


def _sleeves_with_pending_allocation(
    snapshots: tuple[SleeveAllocationSnapshot, ...],
    *,
    sleeve_id: str,
    notional: Decimal,
    risk: Decimal,
    opened_new_position: bool,
) -> tuple[SleeveAllocationSnapshot, ...]:
    normalized = sleeve_id.strip().lower()
    updated = []
    matched = False
    for snapshot in snapshots:
        if snapshot.sleeve_id != normalized:
            updated.append(snapshot)
            continue
        matched = True
        updated.append(
            replace(
                snapshot,
                current_exposure_inr=(
                    snapshot.current_exposure_inr + notional
                ).quantize(MONEY_QUANT),
                open_position_count=(
                    snapshot.open_position_count + (1 if opened_new_position else 0)
                ),
                open_trade_risk_inr=(snapshot.open_trade_risk_inr + risk).quantize(
                    MONEY_QUANT
                ),
            )
        )
    if not matched:
        updated.append(
            SleeveAllocationSnapshot(
                sleeve_id=normalized,
                starting_nav_estimate_inr=Decimal("0"),
                current_exposure_inr=notional.quantize(MONEY_QUANT),
                open_position_count=1 if opened_new_position else 0,
                open_trade_risk_inr=risk.quantize(MONEY_QUANT),
            )
        )
    return tuple(updated)


def _ledger_entry(
    allocation_input: RunAllocationInput,
    proposal: TraderProposal,
    *,
    status: str,
) -> AllocationLedgerEntry:
    decision = _require_decision(proposal)
    return AllocationLedgerEntry(
        symbol=proposal.symbol,
        proposal_id=proposal.proposal_id,
        action=decision.action,
        status=status,
        selected=status in SELECTED_LEDGER_STATUSES,
        strategy_rank=_strategy_rank(allocation_input, proposal.symbol),
        strategy_score=_strategy_score(allocation_input, proposal.symbol),
        trader_confidence=proposal.confidence,
        candidate_score=decision.candidate_score,
        score_band=decision.score_band,
        requested_position_pct_nav=decision.requested_position_pct_nav,
        approved_position_pct_nav=decision.approved_position_pct_nav,
        requested_notional_inr=decision.requested_notional_inr,
        approved_notional_inr=decision.approved_notional_inr,
        approved_quantity=decision.approved_quantity,
        binding_constraint=decision.binding_constraint,
        portfolio_plan_id=decision.portfolio_plan_id,
        portfolio_plan_trade_id=decision.portfolio_plan_trade_id,
        planner_candidate_id=decision.planner_candidate_id,
        planner_source=decision.planner_source,
        planner_rank=decision.planner_rank,
        capacity_source=decision.capacity_source,
        borrowed_from_sleeve_ids=decision.borrowed_from_sleeve_ids,
        funding_source=decision.funding_source,
        existing_cash_used_inr=decision.existing_cash_used_inr,
        same_run_proceeds_used_inr=decision.same_run_proceeds_used_inr,
        same_run_proceeds_available_inr=decision.same_run_proceeds_available_inr,
        same_run_proceeds_haircut_pct=decision.same_run_proceeds_haircut_pct,
        hard_cash_reserve_inr=decision.hard_cash_reserve_inr,
        buy_price_buffer_pct=decision.buy_price_buffer_pct,
        proposal_source=decision.proposal_source,
        rationale=decision.rationale,
    )


def _result(
    *,
    proposals: tuple[TraderProposal, ...],
    ledger: tuple[AllocationLedgerEntry, ...],
    policy_source: str,
    model_version: str = RUN_ALLOCATION_MODEL_VERSION,
) -> RunAllocationResult:
    status_counts = Counter(entry.status for entry in ledger)
    binding_counts = Counter(
        entry.binding_constraint for entry in ledger if entry.binding_constraint
    )
    summary = {
        "proposal_count": len(ledger),
        "selected_count": sum(
            status_counts[status] for status in SELECTED_LEDGER_STATUSES
        ),
        "not_selected_count": status_counts["not_selected"],
        "allocation_reduced_count": status_counts["allocation_reduced"],
        "allocation_rejected_count": status_counts["allocation_rejected"],
        "unchanged_lifecycle_count": status_counts["unchanged_lifecycle"],
        "open_position_management_count": status_counts["open_position_management"],
    }
    return RunAllocationResult(
        proposals=proposals,
        ledger=ledger,
        summary=summary,
        binding_constraints=dict(sorted(binding_counts.items())),
        policy_source=policy_source,
        model_version=model_version,
    )


def _strategy_rank(allocation_input: RunAllocationInput, symbol: str) -> int | None:
    rank = allocation_input.strategy_rank_by_symbol.get(symbol.upper())
    return int(rank) if rank is not None else None


def _strategy_score(allocation_input: RunAllocationInput, symbol: str) -> Decimal | None:
    score = allocation_input.strategy_score_by_symbol.get(symbol.upper())
    return Decimal(str(score)) if score is not None else None


def _latest_close(history: tuple[DailyCandle, ...]) -> Decimal:
    if not history:
        return Decimal("0")
    return sorted(history, key=lambda candle: candle.trade_date)[-1].close.quantize(
        MONEY_QUANT
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


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT)


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(upper, value))


def _summary_suffix_for_status(status: str, decision: AllocationDecision) -> str:
    if status == "selected":
        return (
            "Run-level allocation selected this proposal before paper finalization."
        )
    if status == "allocation_reduced":
        return (
            "Run-level allocation selected and reduced this proposal because "
            f"{decision.binding_constraint} was binding."
        )
    if status == "not_selected":
        return (
            "Run-level allocation did not select this proposal because "
            f"{decision.binding_constraint} was binding."
        )
    return (
        "Run-level allocation rejected this proposal because "
        f"{decision.binding_constraint} was binding."
    )


def _portfolio_plan_summary_suffix(status: str, decision: AllocationDecision) -> str:
    if status == "selected":
        return "Portfolio-plan allocation selected this BUY before paper finalization."
    if status == "allocation_reduced":
        return (
            "Portfolio-plan allocation selected and reduced this BUY because "
            f"{decision.binding_constraint} was binding."
        )
    if status == "not_selected":
        return (
            "Portfolio-plan allocation did not select this BUY because "
            f"{decision.binding_constraint} was binding."
        )
    return (
        "Portfolio-plan allocation rejected this BUY because "
        f"{decision.binding_constraint} was binding."
    )


def _append_model_version(
    model_version: str,
    *,
    allocation_model_version: str = RUN_ALLOCATION_MODEL_VERSION,
) -> str:
    if allocation_model_version in model_version.split("+"):
        return model_version
    return f"{model_version}+{allocation_model_version}"


def _append_sentence(base: str, sentence: str) -> str:
    cleaned = base.strip()
    suffix = sentence.strip()
    if not cleaned:
        return suffix
    if suffix in cleaned:
        return cleaned
    return f"{cleaned} {suffix}"


def _require_decision(proposal: TraderProposal) -> AllocationDecision:
    if proposal.allocation_decision is None:
        raise ValueError(f"Allocation proposal {proposal.symbol} is missing a decision.")
    return proposal.allocation_decision


def _proposal_sort_key(proposal: TraderProposal) -> tuple[str, str]:
    return proposal.symbol.upper(), proposal.proposal_id


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value
