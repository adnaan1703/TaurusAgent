from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from taurus_core.domain.market_data import DailyCandle
from taurus_core.strategies.base import StrategyRanking, ranked_symbols


@dataclass(frozen=True, slots=True)
class MomentumSignal:
    trade_date: date
    symbol: str
    action: str
    score: Decimal
    reason: str


class MockMomentumStrategy:
    def __init__(
        self, *, lookback_days: int, target_positions: int | None = None
    ) -> None:
        self.lookback_days = lookback_days
        self.target_positions = target_positions

    def rank_universe(
        self,
        *,
        trade_date: date,
        history_by_symbol: dict[str, list[DailyCandle]],
        current_positions: set[str],
    ) -> list[StrategyRanking]:
        scored: list[tuple[str, Decimal]] = []
        ineligible: list[StrategyRanking] = []
        for symbol, history in history_by_symbol.items():
            if len(history) <= self.lookback_days:
                ineligible.append(
                    self._ranking(
                        trade_date=trade_date,
                        symbol=symbol,
                        action_intent="SELL"
                        if symbol in current_positions
                        else "NO_TRADE",
                        score=None,
                        rank=None,
                        eligibility_status="ineligible",
                        reasons=["Not enough history for momentum lookback"],
                    )
                )
                continue
            current_close = history[-1].close
            lookback_close = history[-self.lookback_days - 1].close
            if lookback_close <= 0:
                ineligible.append(
                    self._ranking(
                        trade_date=trade_date,
                        symbol=symbol,
                        action_intent="SELL"
                        if symbol in current_positions
                        else "NO_TRADE",
                        score=None,
                        rank=None,
                        eligibility_status="ineligible",
                        reasons=["Lookback close was not positive"],
                    )
                )
                continue
            score = (current_close / lookback_close) - Decimal("1")
            if score > Decimal("0"):
                scored.append((symbol, score))
            else:
                ineligible.append(
                    self._ranking(
                        trade_date=trade_date,
                        symbol=symbol,
                        action_intent="SELL"
                        if symbol in current_positions
                        else "NO_TRADE",
                        score=score,
                        rank=None,
                        eligibility_status="ineligible",
                        reasons=["Momentum score was not positive"],
                    )
                )

        ranked = sorted(scored, key=lambda item: (-item[1], item[0]))
        rankings = [
            self._ranking(
                trade_date=trade_date,
                symbol=symbol,
                action_intent="HOLD" if symbol in current_positions else "BUY",
                score=score,
                rank=index,
                eligibility_status="eligible",
                reasons=[f"{self.lookback_days}d momentum score={score}"],
            )
            for index, (symbol, score) in enumerate(ranked, start=1)
        ]
        for symbol in sorted(current_positions - set(history_by_symbol)):
            rankings.append(
                self._ranking(
                    trade_date=trade_date,
                    symbol=symbol,
                    action_intent="SELL",
                    score=None,
                    rank=None,
                    eligibility_status="ineligible",
                    reasons=["Missing history for current position"],
                )
            )
        return [*rankings, *sorted(ineligible, key=lambda ranking: ranking.symbol)]

    def select_targets(
        self,
        *,
        trade_date: date,
        history_by_symbol: dict[str, list[DailyCandle]],
        current_positions: set[str],
        target_limit: int | None = None,
    ) -> tuple[set[str], list[MomentumSignal]]:
        rankings = self.rank_universe(
            trade_date=trade_date,
            history_by_symbol=history_by_symbol,
            current_positions=current_positions,
        )
        targets = ranked_symbols(rankings, target_limit=target_limit)

        signals: list[MomentumSignal] = []
        for ranking in rankings:
            if ranking.raw_strategy_score is None:
                continue
            symbol = ranking.symbol
            score = ranking.raw_strategy_score
            if symbol in targets and symbol not in current_positions:
                signals.append(
                    MomentumSignal(
                        trade_date=trade_date,
                        symbol=symbol,
                        action="BUY",
                        score=score,
                        reason=f"{self.lookback_days}d momentum rank selected",
                    )
                )
            elif symbol in current_positions and symbol not in targets:
                signals.append(
                    MomentumSignal(
                        trade_date=trade_date,
                        symbol=symbol,
                        action="SELL",
                        score=score,
                        reason="Momentum candidate no longer selected by legacy target cap",
                    )
                )
        return targets, signals

    def _ranking(
        self,
        *,
        trade_date: date,
        symbol: str,
        action_intent: str,
        score: Decimal | None,
        rank: int | None,
        eligibility_status: str,
        reasons: list[str],
    ) -> StrategyRanking:
        return StrategyRanking(
            trade_date=trade_date,
            symbol=symbol,
            action_intent=action_intent,
            raw_strategy_score=score,
            normalized_score=None,
            rank=rank,
            eligibility_status=eligibility_status,
            reasons=reasons,
            invalidation_rules=[
                f"history length <= {self.lookback_days}",
                "lookback close <= 0",
                "momentum score <= 0",
            ],
            feature_snapshot_id="",
            metadata={
                "strategy_type": "mock_momentum",
                "lookback_days": self.lookback_days,
            },
        )
