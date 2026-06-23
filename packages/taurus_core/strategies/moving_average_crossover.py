from __future__ import annotations

from datetime import date
from decimal import Decimal

from taurus_core.features.store import FeatureSnapshot
from taurus_core.strategies.base import (
    SignalExplanation,
    StrategyRanking,
    StrategySignal,
    decimal_param,
    int_param,
    ranked_symbols,
)

SCORE_VALUE = Decimal("0.00000001")


class MovingAverageCrossoverStrategy:
    def __init__(
        self,
        *,
        name: str,
        parameters: dict[str, object],
    ) -> None:
        self._name = name
        self.fast_window = int_param(parameters, "fast_window", 10)
        self.slow_window = int_param(parameters, "slow_window", 30)
        self.min_spread = decimal_param(parameters, "min_spread", "0")
        self.min_return_20d = decimal_param(parameters, "min_return_20d", "-1")
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be smaller than slow_window")

    @property
    def name(self) -> str:
        return self._name

    def rank_universe(
        self,
        *,
        trade_date: date,
        features_by_symbol: dict[str, FeatureSnapshot],
        current_positions: set[str],
        graph_signals_by_symbol: object | None = None,
    ) -> list[StrategyRanking]:
        eligible: list[tuple[str, Decimal, FeatureSnapshot, list[str]]] = []
        ineligible: list[StrategyRanking] = []
        for symbol, snapshot in features_by_symbol.items():
            score = self._score(snapshot)
            if score is None:
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
                        snapshot=snapshot,
                        reasons=["Missing moving-average features"],
                    )
                )
                continue
            return_20d = snapshot.get("return_20d") or Decimal("0")
            if score > self.min_spread and return_20d >= self.min_return_20d:
                eligible.append(
                    (
                        symbol,
                        score,
                        snapshot,
                        [
                            f"{self.fast_window}d SMA crossed above {self.slow_window}d SMA",
                            f"return_20d={return_20d}",
                        ],
                    )
                )
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
                        snapshot=snapshot,
                        reasons=[
                            f"score={score}",
                            f"return_20d={return_20d}",
                            "Moving-average filters were not met",
                        ],
                    )
                )

        ranked = sorted(eligible, key=lambda item: (-item[1], item[0]))
        rankings = [
            self._ranking(
                trade_date=trade_date,
                symbol=symbol,
                action_intent="HOLD" if symbol in current_positions else "BUY",
                score=score,
                rank=index,
                eligibility_status="eligible",
                snapshot=snapshot,
                reasons=[*reasons, f"score={score}"],
            )
            for index, (symbol, score, snapshot, reasons) in enumerate(ranked, start=1)
        ]
        ranked_symbols_seen = {ranking.symbol for ranking in rankings}
        for symbol in sorted(
            current_positions - set(features_by_symbol) - ranked_symbols_seen
        ):
            rankings.append(
                self._ranking(
                    trade_date=trade_date,
                    symbol=symbol,
                    action_intent="SELL",
                    score=None,
                    rank=None,
                    eligibility_status="ineligible",
                    snapshot=None,
                    reasons=["Missing feature snapshot for current position"],
                )
            )
        return [*rankings, *sorted(ineligible, key=lambda ranking: ranking.symbol)]

    def select_targets(
        self,
        *,
        trade_date: date,
        features_by_symbol: dict[str, FeatureSnapshot],
        current_positions: set[str],
        target_limit: int | None = None,
    ) -> tuple[set[str], list[StrategySignal]]:
        rankings = self.rank_universe(
            trade_date=trade_date,
            features_by_symbol=features_by_symbol,
            current_positions=current_positions,
        )
        targets = ranked_symbols(rankings, target_limit=target_limit)
        score_by_symbol = {
            ranking.symbol: ranking.raw_strategy_score
            for ranking in rankings
            if ranking.raw_strategy_score is not None
        }
        return targets, self._signals(
            trade_date=trade_date,
            targets=targets,
            current_positions=current_positions,
            features_by_symbol=features_by_symbol,
            score_by_symbol=score_by_symbol,
        )

    def _score(self, snapshot: FeatureSnapshot) -> Decimal | None:
        fast = snapshot.get(f"sma_{self.fast_window}")
        slow = snapshot.get(f"sma_{self.slow_window}")
        if fast is None or slow is None or slow == 0:
            return None
        return ((fast / slow) - Decimal("1")).quantize(SCORE_VALUE)

    def _signals(
        self,
        *,
        trade_date: date,
        targets: set[str],
        current_positions: set[str],
        features_by_symbol: dict[str, FeatureSnapshot],
        score_by_symbol: dict[str, Decimal],
    ) -> list[StrategySignal]:
        signals: list[StrategySignal] = []
        for symbol in sorted(targets | current_positions):
            snapshot = features_by_symbol.get(symbol)
            score = score_by_symbol.get(symbol, Decimal("0"))
            if symbol in targets and symbol not in current_positions:
                signals.append(
                    self._signal(
                        trade_date=trade_date,
                        symbol=symbol,
                        action="BUY",
                        score=score,
                        snapshot=snapshot,
                        reason=f"{self.fast_window}d SMA crossed above {self.slow_window}d SMA",
                    )
                )
            elif symbol in current_positions and symbol not in targets:
                signals.append(
                    self._signal(
                        trade_date=trade_date,
                        symbol=symbol,
                        action="SELL",
                        score=score,
                        snapshot=snapshot,
                        reason="Moving-average candidate no longer selected by legacy target cap",
                    )
                )
        return signals

    def _ranking(
        self,
        *,
        trade_date: date,
        symbol: str,
        action_intent: str,
        score: Decimal | None,
        rank: int | None,
        eligibility_status: str,
        snapshot: FeatureSnapshot | None,
        reasons: list[str],
    ) -> StrategyRanking:
        snapshot_id = snapshot.snapshot_id if snapshot is not None else ""
        return StrategyRanking(
            trade_date=trade_date,
            symbol=symbol,
            action_intent=action_intent,
            raw_strategy_score=score,
            normalized_score=None,
            rank=rank,
            eligibility_status=eligibility_status,
            reasons=[*reasons, f"feature_snapshot_id={snapshot_id}"],
            invalidation_rules=[
                f"sma_{self.fast_window} <= sma_{self.slow_window}",
                f"return_20d < {self.min_return_20d}",
            ],
            feature_snapshot_id=snapshot_id,
            metadata={
                "strategy_type": "moving_average_crossover",
                "fast_window": self.fast_window,
                "slow_window": self.slow_window,
                "min_spread": str(self.min_spread),
            },
        )

    def _signal(
        self,
        *,
        trade_date: date,
        symbol: str,
        action: str,
        score: Decimal,
        snapshot: FeatureSnapshot | None,
        reason: str,
    ) -> StrategySignal:
        snapshot_id = snapshot.snapshot_id if snapshot is not None else ""
        reasons = [
            reason,
            f"score={score}",
            f"feature_snapshot_id={snapshot_id}",
        ]
        invalidation_rules = [
            f"sma_{self.fast_window} <= sma_{self.slow_window}",
            f"return_20d < {self.min_return_20d}",
        ]
        return StrategySignal(
            trade_date=trade_date,
            symbol=symbol,
            action=action,
            score=score,
            reason="; ".join(reasons),
            explanation=SignalExplanation(
                feature_snapshot_id=snapshot_id,
                reasons=reasons,
                invalidation_rules=invalidation_rules,
            ),
        )
