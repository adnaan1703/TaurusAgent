from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Any, Mapping, Protocol

from taurus_core.features.store import FeatureSnapshot


@dataclass(frozen=True, slots=True)
class SignalExplanation:
    feature_snapshot_id: str
    reasons: list[str]
    invalidation_rules: list[str]
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        payload = {
            "feature_snapshot_id": self.feature_snapshot_id,
            "reasons": self.reasons,
            "invalidation_rules": self.invalidation_rules,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True, slots=True)
class StrategySignal:
    trade_date: date
    symbol: str
    action: str
    score: Decimal
    reason: str
    explanation: SignalExplanation


@dataclass(frozen=True, slots=True)
class StrategyRanking:
    trade_date: date
    symbol: str
    action_intent: str
    raw_strategy_score: Decimal | None
    normalized_score: Decimal | None
    rank: int | None
    eligibility_status: str
    reasons: list[str]
    invalidation_rules: list[str]
    feature_snapshot_id: str
    metadata: dict[str, object] = field(default_factory=dict)

    @property
    def is_eligible(self) -> bool:
        return self.eligibility_status == "eligible"

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "trade_date": self.trade_date.isoformat(),
            "symbol": self.symbol,
            "action_intent": self.action_intent,
            "raw_strategy_score": str(self.raw_strategy_score)
            if self.raw_strategy_score is not None
            else None,
            "normalized_score": str(self.normalized_score)
            if self.normalized_score is not None
            else None,
            "rank": self.rank,
            "eligibility_status": self.eligibility_status,
            "reasons": list(self.reasons),
            "invalidation_rules": list(self.invalidation_rules),
            "feature_snapshot_id": self.feature_snapshot_id,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


class Strategy(Protocol):
    @property
    def name(self) -> str: ...

    def rank_universe(
        self,
        *,
        trade_date: date,
        features_by_symbol: dict[str, FeatureSnapshot],
        current_positions: set[str],
        graph_signals_by_symbol: Mapping[str, Any] | None = None,
        target_limit: int | None = None,
    ) -> list[StrategyRanking]: ...

    def select_targets(
        self,
        *,
        trade_date: date,
        features_by_symbol: dict[str, FeatureSnapshot],
        current_positions: set[str],
        target_limit: int | None = None,
    ) -> tuple[set[str], list[StrategySignal]]: ...


def ranked_symbols(
    rankings: list[StrategyRanking],
    *,
    target_limit: int | None = None,
) -> set[str]:
    if target_limit is not None and target_limit <= 0:
        raise ValueError("target_limit must be positive when provided")
    eligible = [ranking for ranking in rankings if ranking.is_eligible]
    if target_limit is not None:
        eligible = eligible[:target_limit]
    return {ranking.symbol for ranking in eligible}


def decimal_param(parameters: dict[str, object], name: str, default: str) -> Decimal:
    value = parameters.get(name, default)
    return Decimal(str(value))


def int_param(parameters: dict[str, object], name: str, default: int) -> int:
    return int(parameters.get(name, default))
