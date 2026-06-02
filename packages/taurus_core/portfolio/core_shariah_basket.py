from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from statistics import mean, pstdev
from typing import Any

from taurus_core.data.universe import UniverseSymbol, load_market_data_universe
from taurus_core.domain.market_data import DailyCandle
from taurus_core.intelligence.event_scoring import EVENT_SENTIMENT
from taurus_core.portfolio.money_management import MoneyManagementPolicy

CORE_STRATEGY_NAME = "core_shariah_basket_v1"
CORE_SLEEVE_ID = "core_shariah"
WEIGHT_QUANT = Decimal("0.0001")
MONEY_QUANT = Decimal("0.01")
MIN_HISTORY_DAYS = 120
VOLATILITY_WINDOW = 60
LIQUIDITY_WINDOW = 20
TREND_WINDOW = 60
MAX_STALE_CALENDAR_DAYS = 10
SEVERE_NEGATIVE_EVENT_THRESHOLD = Decimal("0.55")


@dataclass(frozen=True, slots=True)
class CoreBasketPosition:
    symbol: str
    market_value_inr: Decimal


@dataclass(frozen=True, slots=True)
class CoreBasketReviewInput:
    histories_by_symbol: dict[str, list[DailyCandle]]
    nav_inr: Decimal
    current_positions: tuple[CoreBasketPosition, ...] = ()
    as_of_date: date | None = None
    last_core_rebalance_date: date | None = None
    severe_negative_symbols: frozenset[str] = frozenset()
    sector_by_symbol: dict[str, str] | None = None
    graph_cluster_by_symbol: dict[str, str] | None = None


class CoreShariahBasketStrategy:
    """Builds a conservative long-only Shariah NSE equity basket artifact."""

    model_version = "core_shariah_basket_v1"

    def __init__(
        self,
        policy: MoneyManagementPolicy,
        *,
        min_history_days: int = MIN_HISTORY_DAYS,
        max_stale_calendar_days: int = MAX_STALE_CALENDAR_DAYS,
    ) -> None:
        self.policy = policy
        self.min_history_days = min_history_days
        self.max_stale_calendar_days = max_stale_calendar_days
        self.universe = load_market_data_universe(policy.shariah_universe_path)
        self.universe_by_symbol = {entry.symbol.upper(): entry for entry in self.universe.symbols}
        self.core_sleeve = next(
            (sleeve for sleeve in policy.sleeves if sleeve.sleeve_id == CORE_SLEEVE_ID),
            None,
        )
        if self.core_sleeve is None:
            raise ValueError("Money-management policy requires a core_shariah sleeve.")

    def review(self, review_input: CoreBasketReviewInput) -> dict[str, Any]:
        as_of_date = review_input.as_of_date or _latest_history_date(
            review_input.histories_by_symbol
        )
        candidates, rejected = self._score_candidates(review_input, as_of_date=as_of_date)
        selected = _select_diversified(candidates, preferred_max=20, preferred_min=12)
        weights = _inverse_vol_nav_weights(
            selected,
            sleeve_target_pct_nav=self.core_sleeve.target_weight_pct,
            normal_cap_pct_nav=self.policy.limits.max_stock_pct_nav,
            hard_cap_pct_nav=self.policy.limits.max_stock_hard_cap_pct_nav,
        )
        weights = _apply_group_caps(
            weights,
            group_by_symbol=review_input.sector_by_symbol or {},
            cap_pct_nav=self.policy.limits.max_sector_pct_nav,
        )
        weights = _apply_group_caps(
            weights,
            group_by_symbol=review_input.graph_cluster_by_symbol or {},
            cap_pct_nav=self.policy.limits.max_graph_cluster_pct_nav,
        )
        weights, too_small = _drop_tiny_targets(
            weights,
            nav_inr=review_input.nav_inr,
            min_notional_inr=self.policy.rebalance.min_rebalance_notional_inr,
        )
        for symbol in too_small:
            rejected[symbol] = rejected.get(symbol, []) + ["target_below_min_rebalance_notional"]
        selected = [candidate for candidate in selected if candidate.symbol in weights]

        current_weights = _current_weights(
            positions=review_input.current_positions,
            nav_inr=review_input.nav_inr,
        )
        sleeve_current_pct_nav = sum(
            (current_weights.get(symbol, Decimal("0")) for symbol in weights),
            Decimal("0"),
        ).quantize(WEIGHT_QUANT)
        sleeve_target_pct_nav = sum(weights.values(), Decimal("0")).quantize(WEIGHT_QUANT)
        sleeve_drift_pct_nav = (sleeve_target_pct_nav - sleeve_current_pct_nav).quantize(
            WEIGHT_QUANT
        )
        sleeve_drift_notional = _pct_to_notional(
            abs(sleeve_drift_pct_nav),
            review_input.nav_inr,
        )
        rebalance = _rebalance_decision(
            as_of_date=as_of_date,
            last_core_rebalance_date=review_input.last_core_rebalance_date,
            sleeve_target_pct_nav=self.core_sleeve.target_weight_pct,
            sleeve_drift_pct_nav=sleeve_drift_pct_nav,
            sleeve_drift_notional_inr=sleeve_drift_notional,
            drift_threshold_pct=self.policy.rebalance.sleeve_drift_threshold_pct,
            min_rebalance_notional_inr=self.policy.rebalance.min_rebalance_notional_inr,
        )
        decisions = _rebalance_decisions(
            weights=weights,
            current_weights=current_weights,
            nav_inr=review_input.nav_inr,
            should_rebalance=rebalance["should_rebalance"],
            min_rebalance_notional_inr=self.policy.rebalance.min_rebalance_notional_inr,
        )

        return {
            "enabled": True,
            "strategy_name": CORE_STRATEGY_NAME,
            "sleeve_id": CORE_SLEEVE_ID,
            "model_version": self.model_version,
            "review_frequency": self.policy.rebalance.review_frequency,
            "core_rebalance_frequency": self.policy.rebalance.core_rebalance_frequency,
            "as_of_date": as_of_date.isoformat(),
            "universe_name": self.universe.universe_name,
            "universe_path": str(self.universe.source_path),
            "candidate_count": len(candidates),
            "selected_symbols": [candidate.symbol for candidate in selected],
            "rejected_candidates": [
                {"symbol": symbol, "reasons": reasons}
                for symbol, reasons in sorted(rejected.items())
            ],
            "target_weights": {
                symbol: str(weight.quantize(WEIGHT_QUANT))
                for symbol, weight in sorted(weights.items())
            },
            "current_weights": {
                symbol: str(current_weights.get(symbol, Decimal("0")).quantize(WEIGHT_QUANT))
                for symbol in sorted(set(weights) | set(current_weights))
            },
            "drift": {
                "sleeve_target_pct_nav": str(sleeve_target_pct_nav),
                "sleeve_current_pct_nav": str(sleeve_current_pct_nav),
                "sleeve_drift_pct_nav": str(sleeve_drift_pct_nav),
                "sleeve_drift_notional_inr": str(sleeve_drift_notional),
            },
            "rebalance": rebalance,
            "decisions": decisions,
            "selection_scores": [
                {
                    "symbol": candidate.symbol,
                    "realized_volatility": str(candidate.realized_volatility),
                    "liquidity_inr": str(candidate.liquidity_inr),
                    "trend_quality": str(candidate.trend_quality),
                    "diversification_score": str(candidate.diversification_score),
                    "rank_score": str(candidate.rank_score),
                }
                for candidate in selected
            ],
        }

    def _score_candidates(
        self,
        review_input: CoreBasketReviewInput,
        *,
        as_of_date: date,
    ) -> tuple[list[_CandidateScore], dict[str, list[str]]]:
        rejected: dict[str, list[str]] = {}
        scores: list[_CandidateScore] = []
        supplied_symbols = {symbol.upper() for symbol in review_input.histories_by_symbol}
        for symbol in sorted(supplied_symbols - set(self.universe_by_symbol)):
            rejected[symbol] = ["shariah_universe_mismatch"]

        for symbol, universe_symbol in sorted(self.universe_by_symbol.items()):
            reasons = _unsupported_reasons(universe_symbol)
            if symbol in review_input.severe_negative_symbols:
                reasons.append("severe_negative_event")
            history = sorted(
                review_input.histories_by_symbol.get(symbol, []),
                key=lambda candle: candle.trade_date,
            )
            if len(history) < self.min_history_days:
                reasons.append("insufficient_daily_candle_history")
            elif (as_of_date - history[-1].trade_date).days > self.max_stale_calendar_days:
                reasons.append("stale_daily_candle_data")
            if reasons:
                rejected[symbol] = reasons
                continue
            score = _candidate_score(
                symbol=symbol,
                history=history,
                sector_by_symbol=review_input.sector_by_symbol or {},
                graph_cluster_by_symbol=review_input.graph_cluster_by_symbol or {},
            )
            if score is None:
                rejected[symbol] = ["insufficient_return_history"]
                continue
            scores.append(score)

        return sorted(scores, key=lambda score: score.rank_sort_key), rejected


@dataclass(frozen=True, slots=True)
class _CandidateScore:
    symbol: str
    realized_volatility: Decimal
    liquidity_inr: Decimal
    trend_quality: Decimal
    diversification_score: Decimal
    rank_score: Decimal

    @property
    def rank_sort_key(self) -> tuple[Decimal, str]:
        return (-self.rank_score, self.symbol)


def severe_negative_symbols(events_by_symbol: dict[str, list[Any]]) -> frozenset[str]:
    blocked: set[str] = set()
    for symbol, events in events_by_symbol.items():
        for event in events:
            sentiment = EVENT_SENTIMENT.get(str(event.event_type), Decimal("0"))
            if sentiment < 0 and Decimal(str(event.severity)) >= SEVERE_NEGATIVE_EVENT_THRESHOLD:
                blocked.add(symbol.upper())
                break
    return frozenset(blocked)


def _candidate_score(
    *,
    symbol: str,
    history: list[DailyCandle],
    sector_by_symbol: dict[str, str],
    graph_cluster_by_symbol: dict[str, str],
) -> _CandidateScore | None:
    closes = [_as_float(candle.close) for candle in history]
    returns = _daily_returns(closes)
    if len(returns) < VOLATILITY_WINDOW:
        return None
    vol = max(pstdev(returns[-VOLATILITY_WINDOW:]) * math.sqrt(252), 0.0001)
    liquidity = mean(
        _as_float(candle.close) * float(candle.volume)
        for candle in history[-LIQUIDITY_WINDOW:]
    )
    trend = (closes[-1] / closes[-TREND_WINDOW] - 1.0) if len(closes) >= TREND_WINDOW else 0.0
    trend_quality = max(min(trend, 0.35), -0.35)
    diversification_score = _diversification_score(
        symbol=symbol,
        sector_by_symbol=sector_by_symbol,
        graph_cluster_by_symbol=graph_cluster_by_symbol,
    )
    rank_score = (
        (Decimal("0.40") * Decimal(f"{1 / vol:.8f}"))
        + (Decimal("0.25") * Decimal(f"{math.log(max(liquidity, 1.0)):.8f}"))
        + (Decimal("0.25") * Decimal(f"{trend_quality + 0.35:.8f}"))
        + (Decimal("0.10") * diversification_score)
    )
    return _CandidateScore(
        symbol=symbol,
        realized_volatility=Decimal(f"{vol:.8f}").quantize(WEIGHT_QUANT),
        liquidity_inr=Decimal(f"{liquidity:.2f}").quantize(MONEY_QUANT),
        trend_quality=Decimal(f"{trend_quality:.8f}").quantize(WEIGHT_QUANT),
        diversification_score=diversification_score.quantize(WEIGHT_QUANT),
        rank_score=rank_score.quantize(WEIGHT_QUANT),
    )


def _select_diversified(
    candidates: list[_CandidateScore],
    *,
    preferred_min: int,
    preferred_max: int,
) -> list[_CandidateScore]:
    if not candidates:
        return []
    target_count = min(preferred_max, len(candidates))
    if len(candidates) < preferred_min:
        target_count = len(candidates)
    return candidates[:target_count]


def _inverse_vol_nav_weights(
    candidates: list[_CandidateScore],
    *,
    sleeve_target_pct_nav: Decimal,
    normal_cap_pct_nav: Decimal,
    hard_cap_pct_nav: Decimal,
) -> dict[str, Decimal]:
    if not candidates:
        return {}
    cap = min(normal_cap_pct_nav, hard_cap_pct_nav)
    inverse_vol = {
        candidate.symbol: Decimal("1") / max(candidate.realized_volatility, Decimal("0.0001"))
        for candidate in candidates
    }
    weights = {symbol: Decimal("0") for symbol in inverse_vol}
    remaining = sleeve_target_pct_nav
    uncapped = set(inverse_vol)
    while remaining > 0 and uncapped:
        total_inverse = sum((inverse_vol[symbol] for symbol in uncapped), Decimal("0"))
        if total_inverse <= 0:
            break
        allocated_this_round = Decimal("0")
        capped_this_round: set[str] = set()
        for symbol in sorted(uncapped):
            proposed = (remaining * inverse_vol[symbol] / total_inverse).quantize(WEIGHT_QUANT)
            room = cap - weights[symbol]
            allocation = min(proposed, room).quantize(WEIGHT_QUANT)
            weights[symbol] = (weights[symbol] + allocation).quantize(WEIGHT_QUANT)
            allocated_this_round += allocation
            if weights[symbol] >= cap:
                capped_this_round.add(symbol)
        remaining = (remaining - allocated_this_round).quantize(WEIGHT_QUANT)
        if not capped_this_round and allocated_this_round <= 0:
            break
        uncapped -= capped_this_round
        if allocated_this_round <= 0:
            break
    return {symbol: min(weight, hard_cap_pct_nav).quantize(WEIGHT_QUANT) for symbol, weight in weights.items()}


def _apply_group_caps(
    weights: dict[str, Decimal],
    *,
    group_by_symbol: dict[str, str],
    cap_pct_nav: Decimal,
) -> dict[str, Decimal]:
    output = dict(weights)
    groups: dict[str, list[str]] = {}
    for symbol, group in group_by_symbol.items():
        if symbol.upper() in output and str(group).strip():
            groups.setdefault(str(group).strip().lower(), []).append(symbol.upper())
    for symbols in groups.values():
        total = sum((output[symbol] for symbol in symbols), Decimal("0"))
        if total <= cap_pct_nav or total <= 0:
            continue
        scale = cap_pct_nav / total
        for symbol in symbols:
            output[symbol] = (output[symbol] * scale).quantize(WEIGHT_QUANT)
    return output


def _drop_tiny_targets(
    weights: dict[str, Decimal],
    *,
    nav_inr: Decimal,
    min_notional_inr: Decimal,
) -> tuple[dict[str, Decimal], list[str]]:
    kept: dict[str, Decimal] = {}
    dropped: list[str] = []
    for symbol, weight in sorted(weights.items()):
        if _pct_to_notional(weight, nav_inr) < min_notional_inr:
            dropped.append(symbol)
        else:
            kept[symbol] = weight
    return kept, dropped


def _rebalance_decision(
    *,
    as_of_date: date,
    last_core_rebalance_date: date | None,
    sleeve_target_pct_nav: Decimal,
    sleeve_drift_pct_nav: Decimal,
    sleeve_drift_notional_inr: Decimal,
    drift_threshold_pct: Decimal,
    min_rebalance_notional_inr: Decimal,
) -> dict[str, Any]:
    drift_threshold_nav = (sleeve_target_pct_nav * drift_threshold_pct / Decimal("100")).quantize(
        WEIGHT_QUANT
    )
    monthly_due = (
        last_core_rebalance_date is None
        or (last_core_rebalance_date.year, last_core_rebalance_date.month)
        != (as_of_date.year, as_of_date.month)
    )
    drift_due = (
        abs(sleeve_drift_pct_nav) > drift_threshold_nav
        or sleeve_drift_notional_inr > min_rebalance_notional_inr
    )
    should_rebalance = monthly_due or drift_due
    rationale = []
    if monthly_due:
        rationale.append("monthly_core_rebalance_due")
    else:
        rationale.append("monthly_gate_not_due")
    if drift_due:
        rationale.append("drift_threshold_exceeded")
    else:
        rationale.append("drift_within_threshold")
    return {
        "should_rebalance": should_rebalance,
        "monthly_due": monthly_due,
        "drift_due": drift_due,
        "last_core_rebalance_date": last_core_rebalance_date.isoformat()
        if last_core_rebalance_date is not None
        else None,
        "drift_threshold_pct_nav": str(drift_threshold_nav),
        "min_rebalance_notional_inr": str(min_rebalance_notional_inr.quantize(MONEY_QUANT)),
        "rationale": rationale,
    }


def _rebalance_decisions(
    *,
    weights: dict[str, Decimal],
    current_weights: dict[str, Decimal],
    nav_inr: Decimal,
    should_rebalance: bool,
    min_rebalance_notional_inr: Decimal,
) -> list[dict[str, Any]]:
    decisions: list[dict[str, Any]] = []
    for symbol in sorted(set(weights) | set(current_weights)):
        target = weights.get(symbol, Decimal("0")).quantize(WEIGHT_QUANT)
        current = current_weights.get(symbol, Decimal("0")).quantize(WEIGHT_QUANT)
        drift = (target - current).quantize(WEIGHT_QUANT)
        trade_notional = _pct_to_notional(abs(drift), nav_inr)
        side = "BUY" if drift > 0 else "SELL" if drift < 0 else "HOLD"
        status = "approved"
        rationale = []
        if not should_rebalance:
            status = "unchanged"
            rationale.append("core_rebalance_gate_closed")
        elif trade_notional < min_rebalance_notional_inr:
            status = "unchanged"
            rationale.append("trade_below_min_rebalance_notional")
        else:
            rationale.append("core_rebalance_trade_generated")
        decisions.append(
            {
                "symbol": symbol,
                "strategy_name": CORE_STRATEGY_NAME,
                "sleeve_id": CORE_SLEEVE_ID,
                "side": side,
                "status": status,
                "target_weight_pct_nav": str(target),
                "current_weight_pct_nav": str(current),
                "drift_pct_nav": str(drift),
                "trade_notional_inr": str(trade_notional),
                "rationale": rationale,
            }
        )
    return decisions


def _current_weights(
    *,
    positions: tuple[CoreBasketPosition, ...],
    nav_inr: Decimal,
) -> dict[str, Decimal]:
    if nav_inr <= 0:
        return {}
    return {
        position.symbol.upper(): ((position.market_value_inr / nav_inr) * Decimal("100")).quantize(
            WEIGHT_QUANT
        )
        for position in positions
        if position.market_value_inr > 0
    }


def _unsupported_reasons(symbol: UniverseSymbol) -> list[str]:
    reasons = []
    if symbol.exchange.upper() != "NSE":
        reasons.append("unsupported_exchange")
    if symbol.segment.upper() != "EQUITY":
        reasons.append("unsupported_instrument")
    return reasons


def _diversification_score(
    *,
    symbol: str,
    sector_by_symbol: dict[str, str],
    graph_cluster_by_symbol: dict[str, str],
) -> Decimal:
    score = Decimal("1")
    sector = sector_by_symbol.get(symbol)
    if sector:
        sector_count = sum(1 for value in sector_by_symbol.values() if value == sector)
        score += Decimal("1") / Decimal(max(sector_count, 1))
    cluster = graph_cluster_by_symbol.get(symbol)
    if cluster:
        cluster_count = sum(1 for value in graph_cluster_by_symbol.values() if value == cluster)
        score += Decimal("1") / Decimal(max(cluster_count, 1))
    return score


def _latest_history_date(histories_by_symbol: dict[str, list[DailyCandle]]) -> date:
    dates = [
        candle.trade_date
        for history in histories_by_symbol.values()
        for candle in history
    ]
    if not dates:
        raise ValueError("Core basket review requires at least one daily candle history.")
    return max(dates)


def _daily_returns(closes: list[float]) -> list[float]:
    return [
        (closes[index] / closes[index - 1]) - 1.0
        for index in range(1, len(closes))
        if closes[index - 1] > 0
    ]


def _pct_to_notional(weight_pct_nav: Decimal, nav_inr: Decimal) -> Decimal:
    return (nav_inr * weight_pct_nav / Decimal("100")).quantize(MONEY_QUANT)


def _as_float(value: Decimal) -> float:
    return float(value)
