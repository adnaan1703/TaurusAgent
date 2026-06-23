from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Mapping

from taurus_core.features.store import FeatureSnapshot
from taurus_core.features.technical_context import (
    UniverseTechnicalContext,
    build_universe_technical_context,
)
from taurus_core.features.technical_signal import (
    OHLCV_V2_PROFILE,
    SMA_SPREAD_PROFILE,
    TechnicalOhlcvSignalResult,
    TechnicalSignalResult,
    TechnicalSignalService,
)
from taurus_core.strategies.base import (
    SignalExplanation,
    StrategyRanking,
    StrategySignal,
    decimal_param,
    int_param,
    ranked_symbols,
)

SCORE_VALUE = Decimal("0.00000001")
ZERO = Decimal("0")
SUPPORTED_TECHNICAL_PROFILES = {SMA_SPREAD_PROFILE, OHLCV_V2_PROFILE}


@dataclass(frozen=True, slots=True)
class _TechnicalScoreResult:
    profile_name: str
    score: Decimal | None
    signal_result: TechnicalSignalResult | TechnicalOhlcvSignalResult | None = None


class GraphAwareScoreStrategy:
    def __init__(
        self,
        *,
        name: str,
        parameters: dict[str, object],
    ) -> None:
        self._name = name
        self.fast_window = int_param(parameters, "fast_window", 10)
        self.slow_window = int_param(parameters, "slow_window", 30)
        self.technical_weight = decimal_param(parameters, "technical_weight", "1.0")
        self.graph_weight = decimal_param(parameters, "graph_weight", "0.35")
        self.min_combined_score = decimal_param(parameters, "min_combined_score", "-0.10")
        self.min_return_20d = decimal_param(parameters, "min_return_20d", "-1")
        self.min_graph_confidence = decimal_param(parameters, "min_graph_confidence", "0")
        self.require_graph_signal = bool(parameters.get("require_graph_signal", False))
        self.technical_profile = str(parameters.get("technical_profile", SMA_SPREAD_PROFILE))
        if self.technical_profile not in SUPPORTED_TECHNICAL_PROFILES:
            raise ValueError(f"Unsupported technical_profile: {self.technical_profile}")
        if self.fast_window >= self.slow_window:
            raise ValueError("fast_window must be smaller than slow_window")
        self._technical_signal_service = TechnicalSignalService()

    @property
    def name(self) -> str:
        return self._name

    def select_targets(
        self,
        *,
        trade_date: date,
        features_by_symbol: dict[str, FeatureSnapshot],
        current_positions: set[str],
        target_limit: int | None = None,
    ) -> tuple[set[str], list[StrategySignal]]:
        return self.select_targets_with_graph(
            trade_date=trade_date,
            features_by_symbol=features_by_symbol,
            current_positions=current_positions,
            graph_signals_by_symbol={},
            target_limit=target_limit,
        )

    def rank_universe(
        self,
        *,
        trade_date: date,
        features_by_symbol: dict[str, FeatureSnapshot],
        current_positions: set[str],
        graph_signals_by_symbol: Mapping[str, Any] | None = None,
        universe_technical_context: UniverseTechnicalContext | None = None,
    ) -> list[StrategyRanking]:
        graph_by_symbol = {
            key.upper(): value for key, value in (graph_signals_by_symbol or {}).items()
        }
        technical_context = self._universe_technical_context(
            features_by_symbol,
            universe_technical_context=universe_technical_context,
        )
        eligible: list[
            tuple[
                str,
                Decimal,
                FeatureSnapshot,
                Any | None,
                _TechnicalScoreResult,
                list[str],
            ]
        ] = []
        ineligible: list[StrategyRanking] = []
        for symbol, snapshot in features_by_symbol.items():
            graph_signal = graph_by_symbol.get(symbol.upper())
            technical_result = self._technical_signal(
                snapshot,
                universe_context=technical_context,
            )
            score = self._combined_score(
                snapshot=snapshot,
                graph_signal=graph_signal,
                technical_result=technical_result,
            )
            if score is None:
                ineligible.append(
                    self._ranking(
                        trade_date=trade_date,
                        symbol=symbol,
                        action_intent="SELL" if symbol in current_positions else "NO_TRADE",
                        score=None,
                        rank=None,
                        eligibility_status="ineligible",
                        snapshot=snapshot,
                        graph_signal=graph_signal,
                        technical_result=technical_result,
                        reasons=["Missing technical features or required graph signal"],
                    )
                )
                continue
            return_20d = snapshot.get("return_20d") or ZERO
            if score > self.min_combined_score and return_20d >= self.min_return_20d:
                eligible.append(
                    (
                        symbol,
                        score,
                        snapshot,
                        graph_signal,
                        technical_result,
                        [
                            "Graph-aware score passed filters",
                            f"return_20d={return_20d}",
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
                        graph_signal=graph_signal,
                        technical_result=technical_result,
                        reasons=[
                            f"combined_score={score}",
                            f"return_20d={return_20d}",
                            "Graph-aware filters were not met",
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
                graph_signal=graph_signal,
                technical_result=technical_result,
                reasons=[*reasons, f"combined_score={score}"],
            )
            for index, (
                symbol,
                score,
                snapshot,
                graph_signal,
                technical_result,
                reasons,
            ) in enumerate(
                ranked,
                start=1,
            )
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
                    graph_signal=graph_by_symbol.get(symbol.upper()),
                    technical_result=None,
                    reasons=["Missing feature snapshot for current position"],
                )
            )
        return [*rankings, *sorted(ineligible, key=lambda ranking: ranking.symbol)]

    def select_targets_with_graph(
        self,
        *,
        trade_date: date,
        features_by_symbol: dict[str, FeatureSnapshot],
        current_positions: set[str],
        graph_signals_by_symbol: Mapping[str, Any],
        target_limit: int | None = None,
    ) -> tuple[set[str], list[StrategySignal]]:
        graph_by_symbol = {key.upper(): value for key, value in graph_signals_by_symbol.items()}
        rankings = self.rank_universe(
            trade_date=trade_date,
            features_by_symbol=features_by_symbol,
            current_positions=current_positions,
            graph_signals_by_symbol=graph_by_symbol,
        )
        targets = ranked_symbols(rankings, target_limit=target_limit)
        score_by_symbol = {
            ranking.symbol: ranking.raw_strategy_score
            for ranking in rankings
            if ranking.raw_strategy_score is not None
        }
        ranking_by_symbol = {ranking.symbol: ranking for ranking in rankings}
        return targets, self._signals(
            trade_date=trade_date,
            targets=targets,
            current_positions=current_positions,
            features_by_symbol=features_by_symbol,
            score_by_symbol=score_by_symbol,
            graph_signals_by_symbol=graph_by_symbol,
            ranking_by_symbol=ranking_by_symbol,
        )

    def _combined_score(
        self,
        *,
        snapshot: FeatureSnapshot,
        graph_signal: Any | None,
        technical_result: _TechnicalScoreResult | None = None,
    ) -> Decimal | None:
        technical_score = (
            technical_result.score
            if technical_result is not None
            else self._technical_score(snapshot)
        )
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

    def _technical_score(
        self,
        snapshot: FeatureSnapshot,
        *,
        universe_context: UniverseTechnicalContext | None = None,
    ) -> Decimal | None:
        return self._technical_signal(
            snapshot,
            universe_context=universe_context,
        ).score

    def _technical_signal(
        self,
        snapshot: FeatureSnapshot,
        *,
        universe_context: UniverseTechnicalContext | None = None,
    ) -> _TechnicalScoreResult:
        if self.technical_profile == OHLCV_V2_PROFILE:
            result = self._technical_signal_service.score_ohlcv_v2(
                snapshot,
                universe_context=universe_context,
                symbol=snapshot.symbol,
            )
            return _TechnicalScoreResult(
                profile_name=result.profile_name,
                score=result.score if result.available else None,
                signal_result=result,
            )

        result = self._technical_signal_service.score_sma_spread(
            snapshot,
            fast_window=self.fast_window,
            slow_window=self.slow_window,
        )
        return _TechnicalScoreResult(
            profile_name=result.profile_name,
            score=result.score if result.available else None,
            signal_result=result,
        )

    def _universe_technical_context(
        self,
        features_by_symbol: dict[str, FeatureSnapshot],
        *,
        universe_technical_context: UniverseTechnicalContext | None,
    ) -> UniverseTechnicalContext | None:
        if self.technical_profile != OHLCV_V2_PROFILE:
            return None
        if universe_technical_context is not None:
            return universe_technical_context
        return build_universe_technical_context(features_by_symbol)

    def _signals(
        self,
        *,
        trade_date: date,
        targets: set[str],
        current_positions: set[str],
        features_by_symbol: dict[str, FeatureSnapshot],
        score_by_symbol: dict[str, Decimal],
        graph_signals_by_symbol: Mapping[str, Any],
        ranking_by_symbol: Mapping[str, StrategyRanking],
    ) -> list[StrategySignal]:
        signals: list[StrategySignal] = []
        for symbol in sorted(targets | current_positions):
            snapshot = features_by_symbol.get(symbol)
            score = score_by_symbol.get(symbol, ZERO)
            graph_signal = graph_signals_by_symbol.get(symbol.upper())
            ranking = ranking_by_symbol.get(symbol)
            if symbol in targets and symbol not in current_positions:
                signals.append(
                    self._signal(
                        trade_date=trade_date,
                        symbol=symbol,
                        action="BUY",
                        score=score,
                        snapshot=snapshot,
                        graph_signal=graph_signal,
                        ranking=ranking,
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
                        ranking=ranking,
                        reason="Graph-aware score no longer selected by legacy target cap",
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
        graph_signal: Any | None,
        technical_result: _TechnicalScoreResult | None,
        reasons: list[str],
    ) -> StrategyRanking:
        snapshot_id = snapshot.snapshot_id if snapshot is not None else ""
        technical_score = technical_result.score if technical_result is not None else None
        graph_score = graph_signal.score if graph_signal is not None else ZERO
        graph_confidence = graph_signal.confidence if graph_signal is not None else ZERO
        edge_types = graph_signal.edge_types if graph_signal is not None else ()
        metadata = {
            "strategy_type": "graph_aware_score",
            "technical_weight": str(self.technical_weight),
            "graph_weight": str(self.graph_weight),
            "technical_score": str(technical_score) if technical_score is not None else "0",
            "graph_signal": graph_signal.to_dict() if graph_signal is not None else None,
        }
        technical_v2 = _technical_v2_metadata(technical_result)
        if technical_v2 is not None:
            metadata["technical_v2"] = technical_v2
        if edge_types:
            metadata["graph_edge_types"] = list(edge_types)
        return StrategyRanking(
            trade_date=trade_date,
            symbol=symbol,
            action_intent=action_intent,
            raw_strategy_score=score,
            normalized_score=None,
            rank=rank,
            eligibility_status=eligibility_status,
            reasons=[
                *reasons,
                f"technical_score={technical_score if technical_score is not None else ZERO}",
                f"graph_score={graph_score}",
                f"graph_confidence={graph_confidence}",
                f"feature_snapshot_id={snapshot_id}",
            ],
            invalidation_rules=[
                f"combined_score <= {self.min_combined_score}",
                f"return_20d < {self.min_return_20d}",
                f"graph_confidence < {self.min_graph_confidence}",
            ],
            feature_snapshot_id=snapshot_id,
            metadata=metadata,
        )

    def _signal(
        self,
        *,
        trade_date: date,
        symbol: str,
        action: str,
        score: Decimal,
        snapshot: FeatureSnapshot | None,
        graph_signal: Any | None,
        ranking: StrategyRanking | None,
        reason: str,
    ) -> StrategySignal:
        snapshot_id = snapshot.snapshot_id if snapshot is not None else ""
        metadata = dict(ranking.metadata) if ranking is not None else {}
        technical_score = metadata.get("technical_score", "0")
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
        if not metadata:
            metadata = {
                "strategy_type": "graph_aware_score",
                "technical_weight": str(self.technical_weight),
                "graph_weight": str(self.graph_weight),
                "technical_score": str(technical_score),
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


def _technical_v2_metadata(
    technical_result: _TechnicalScoreResult | None,
) -> dict[str, object] | None:
    if not isinstance(technical_result, _TechnicalScoreResult):
        return None
    signal_result = technical_result.signal_result
    if not isinstance(signal_result, TechnicalOhlcvSignalResult):
        return None
    return {
        "profile_name": signal_result.profile_name,
        "alpha_score": str(signal_result.alpha_score),
        "risk_score": str(signal_result.risk_score),
        "tradability_score": str(signal_result.tradability_score),
        "confidence": str(signal_result.confidence),
        "composite_score": str(signal_result.composite_score),
        "coverage": str(signal_result.coverage),
        "top_contributors": [dict(contributor) for contributor in signal_result.top_contributors],
        "missing_features": list(signal_result.missing_features),
        "score_source": signal_result.score_source,
        "metadata": dict(signal_result.metadata),
    }
