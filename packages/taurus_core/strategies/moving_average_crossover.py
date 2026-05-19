from __future__ import annotations

from datetime import date
from decimal import Decimal

from taurus_core.features.store import FeatureSnapshot
from taurus_core.strategies.base import (
    SignalExplanation,
    StrategySignal,
    decimal_param,
    int_param,
)

SCORE_VALUE = Decimal("0.00000001")


class MovingAverageCrossoverStrategy:
    def __init__(
        self,
        *,
        name: str,
        target_positions: int,
        parameters: dict[str, object],
    ) -> None:
        self._name = name
        self.target_positions = target_positions
        self.fast_window = int_param(parameters, "fast_window", 10)
        self.slow_window = int_param(parameters, "slow_window", 30)
        self.min_spread = decimal_param(parameters, "min_spread", "0")
        self.min_return_20d = decimal_param(parameters, "min_return_20d", "-1")
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be smaller than slow_window")

    @property
    def name(self) -> str:
        return self._name

    def select_targets(
        self,
        *,
        trade_date: date,
        features_by_symbol: dict[str, FeatureSnapshot],
        current_positions: set[str],
    ) -> tuple[set[str], list[StrategySignal]]:
        scored: list[tuple[str, Decimal]] = []
        score_by_symbol: dict[str, Decimal] = {}
        for symbol, snapshot in features_by_symbol.items():
            score = self._score(snapshot)
            if score is None:
                continue
            return_20d = snapshot.get("return_20d") or Decimal("0")
            if score > self.min_spread and return_20d >= self.min_return_20d:
                score_by_symbol[symbol] = score
                scored.append((symbol, score))

        ranked = sorted(scored, key=lambda item: (-item[1], item[0]))
        targets = {symbol for symbol, _score in ranked[: self.target_positions]}
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
                        reason=f"Exited top {self.target_positions} moving-average candidates",
                    )
                )
        return signals

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
