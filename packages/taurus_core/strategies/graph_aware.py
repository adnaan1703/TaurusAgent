from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from taurus_core.features.store import FeatureSnapshot
from taurus_core.strategies.base import (
    SignalExplanation,
    StrategySignal,
    decimal_param,
    int_param,
)

SCORE_VALUE = Decimal("0.00000001")
ZERO = Decimal("0")


class GraphAwareScoreStrategy:
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
        self.technical_weight = decimal_param(parameters, "technical_weight", "1.0")
        self.graph_weight = decimal_param(parameters, "graph_weight", "0.35")
        self.min_combined_score = decimal_param(parameters, "min_combined_score", "-0.10")
        self.min_return_20d = decimal_param(parameters, "min_return_20d", "-1")
        self.min_graph_confidence = decimal_param(parameters, "min_graph_confidence", "0")
        self.require_graph_signal = bool(parameters.get("require_graph_signal", False))
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
        return self.select_targets_with_graph(
            trade_date=trade_date,
            features_by_symbol=features_by_symbol,
            current_positions=current_positions,
            graph_signals_by_symbol={},
        )

    def select_targets_with_graph(
        self,
        *,
        trade_date: date,
        features_by_symbol: dict[str, FeatureSnapshot],
        current_positions: set[str],
        graph_signals_by_symbol: Mapping[str, Any],
    ) -> tuple[set[str], list[StrategySignal]]:
        scored: list[tuple[str, Decimal]] = []
        score_by_symbol: dict[str, Decimal] = {}
        graph_by_symbol = {key.upper(): value for key, value in graph_signals_by_symbol.items()}
        for symbol, snapshot in features_by_symbol.items():
            graph_signal = graph_by_symbol.get(symbol.upper())
            score = self._combined_score(snapshot=snapshot, graph_signal=graph_signal)
            if score is None:
                continue
            return_20d = snapshot.get("return_20d") or ZERO
            if score > self.min_combined_score and return_20d >= self.min_return_20d:
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
            graph_signals_by_symbol=graph_by_symbol,
        )

    def _combined_score(
        self,
        *,
        snapshot: FeatureSnapshot,
        graph_signal: Any | None,
    ) -> Decimal | None:
        technical_score = self._technical_score(snapshot)
        if technical_score is None:
            return None
        if graph_signal is None:
            if self.require_graph_signal:
                return None
            graph_score = ZERO
        elif graph_signal.confidence < self.min_graph_confidence:
            graph_score = ZERO
        else:
            graph_score = graph_signal.score
        combined = (technical_score * self.technical_weight) + (graph_score * self.graph_weight)
        return combined.quantize(SCORE_VALUE)

    def _technical_score(self, snapshot: FeatureSnapshot) -> Decimal | None:
        fast = snapshot.get(f"sma_{self.fast_window}")
        slow = snapshot.get(f"sma_{self.slow_window}")
        if fast is None or slow is None or slow == ZERO:
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
        graph_signals_by_symbol: Mapping[str, Any],
    ) -> list[StrategySignal]:
        signals: list[StrategySignal] = []
        for symbol in sorted(targets | current_positions):
            snapshot = features_by_symbol.get(symbol)
            score = score_by_symbol.get(symbol, ZERO)
            graph_signal = graph_signals_by_symbol.get(symbol.upper())
            if symbol in targets and symbol not in current_positions:
                signals.append(
                    self._signal(
                        trade_date=trade_date,
                        symbol=symbol,
                        action="BUY",
                        score=score,
                        snapshot=snapshot,
                        graph_signal=graph_signal,
                        reason="Graph-aware score ranked inside target set",
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
                        graph_signal=graph_signal,
                        reason="Graph-aware score fell outside target set",
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
        graph_signal: Any | None,
        reason: str,
    ) -> StrategySignal:
        snapshot_id = snapshot.snapshot_id if snapshot is not None else ""
        technical_score = self._technical_score(snapshot) if snapshot is not None else None
        graph_score = graph_signal.score if graph_signal is not None else ZERO
        graph_confidence = graph_signal.confidence if graph_signal is not None else ZERO
        edge_types = graph_signal.edge_types if graph_signal is not None else ()
        reasons = [
            reason,
            f"combined_score={score}",
            f"technical_score={technical_score if technical_score is not None else ZERO}",
            f"graph_score={graph_score}",
            f"graph_confidence={graph_confidence}",
            f"feature_snapshot_id={snapshot_id}",
        ]
        if edge_types:
            reasons.append(f"graph_edge_types={','.join(edge_types)}")
        invalidation_rules = [
            f"combined_score <= {self.min_combined_score}",
            f"return_20d < {self.min_return_20d}",
            f"graph_confidence < {self.min_graph_confidence}",
        ]
        metadata = {
            "strategy_type": "graph_aware_score",
            "technical_weight": str(self.technical_weight),
            "graph_weight": str(self.graph_weight),
            "technical_score": str(technical_score) if technical_score is not None else "0",
            "graph_signal": graph_signal.to_dict() if graph_signal is not None else None,
        }
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
                metadata=metadata,
            ),
        )
