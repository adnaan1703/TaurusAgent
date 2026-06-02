from __future__ import annotations

from datetime import date
from decimal import Decimal

from taurus_core.features.store import FeatureSnapshot
from taurus_core.strategies.base import (
    SignalExplanation,
    StrategyRanking,
    StrategySignal,
    decimal_param,
    ranked_symbols,
)

SCORE_VALUE = Decimal("0.00000001")

DEFAULT_WEIGHTS: dict[str, Decimal] = {
    "return_20d": Decimal("2.0"),
    "return_5d": Decimal("1.0"),
    "ema_trend": Decimal("1.5"),
    "rsi": Decimal("0.5"),
    "volatility_penalty": Decimal("1.0"),
    "volume_confirmation": Decimal("0.1"),
}


class BlendedScoreStrategy:
    def __init__(
        self,
        *,
        name: str,
        parameters: dict[str, object],
    ) -> None:
        self._name = name
        raw_weights = parameters.get("weights", {})
        if not isinstance(raw_weights, dict):
            raise ValueError("weights must be a mapping")
        self.weights = DEFAULT_WEIGHTS | {
            key: Decimal(str(value)) for key, value in raw_weights.items()
        }
        self.min_score = decimal_param(parameters, "min_score", "-0.10")
        self.min_return_20d = decimal_param(parameters, "min_return_20d", "-1")
        self.min_rsi = decimal_param(parameters, "min_rsi", "35")
        self.max_rsi = decimal_param(parameters, "max_rsi", "75")

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
            rsi = snapshot.get("rsi_14")
            return_20d = snapshot.get("return_20d")
            if score is None or rsi is None or return_20d is None:
                ineligible.append(
                    self._ranking(
                        trade_date=trade_date,
                        symbol=symbol,
                        action_intent="SELL" if symbol in current_positions else "NO_TRADE",
                        score=score,
                        rank=None,
                        eligibility_status="ineligible",
                        snapshot=snapshot,
                        reasons=["Missing blended-score features"],
                    )
                )
                continue
            if (
                score > self.min_score
                and return_20d >= self.min_return_20d
                and self.min_rsi <= rsi <= self.max_rsi
            ):
                eligible.append(
                    (
                        symbol,
                        score,
                        snapshot,
                        [
                            "Blended technical score passed filters",
                            f"return_20d={return_20d}",
                            f"rsi_14={rsi}",
                        ],
                    )
                )
            else:
                ineligible.append(
                    self._ranking(
                        trade_date=trade_date,
                        symbol=symbol,
                        action_intent="SELL" if symbol in current_positions else "NO_TRADE",
                        score=score,
                        rank=None,
                        eligibility_status="ineligible",
                        snapshot=snapshot,
                        reasons=[
                            f"score={score}",
                            f"return_20d={return_20d}",
                            f"rsi_14={rsi}",
                            "Blended-score filters were not met",
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
        for symbol in sorted(current_positions - set(features_by_symbol)):
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
        return_20d = snapshot.get("return_20d")
        return_5d = snapshot.get("return_5d")
        ema_12 = snapshot.get("ema_12")
        ema_26 = snapshot.get("ema_26")
        rsi = snapshot.get("rsi_14")
        volatility = snapshot.get("volatility_20")
        volume_z = snapshot.get("volume_z_score_20") or Decimal("0")
        if (
            return_20d is None
            or return_5d is None
            or ema_12 is None
            or ema_26 is None
            or ema_26 == 0
            or rsi is None
            or volatility is None
        ):
            return None

        ema_trend = (ema_12 / ema_26) - Decimal("1")
        rsi_component = (rsi - Decimal("50")) / Decimal("50")
        volume_component = max(min(volume_z, Decimal("3")), Decimal("-3")) / Decimal("10")
        score = (
            (return_20d * self.weights["return_20d"])
            + (return_5d * self.weights["return_5d"])
            + (ema_trend * self.weights["ema_trend"])
            + (rsi_component * self.weights["rsi"])
            - (volatility * self.weights["volatility_penalty"])
            + (volume_component * self.weights["volume_confirmation"])
        )
        return score.quantize(SCORE_VALUE)

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
                        reason="Blended technical score ranked inside target set",
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
                        reason="Blended technical score no longer selected by legacy target cap",
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
                f"score <= {self.min_score}",
                f"return_20d < {self.min_return_20d}",
                f"rsi_14 outside [{self.min_rsi}, {self.max_rsi}]",
            ],
            feature_snapshot_id=snapshot_id,
            metadata={
                "strategy_type": "blended_score",
                "weights": {key: str(value) for key, value in sorted(self.weights.items())},
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
            f"score <= {self.min_score}",
            f"return_20d < {self.min_return_20d}",
            f"rsi_14 outside [{self.min_rsi}, {self.max_rsi}]",
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
