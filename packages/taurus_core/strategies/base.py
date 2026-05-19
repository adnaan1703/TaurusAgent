from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Protocol

from taurus_core.features.store import FeatureSnapshot


@dataclass(frozen=True, slots=True)
class SignalExplanation:
    feature_snapshot_id: str
    reasons: list[str]
    invalidation_rules: list[str]

    def to_dict(self) -> dict[str, object]:
        return {
            "feature_snapshot_id": self.feature_snapshot_id,
            "reasons": self.reasons,
            "invalidation_rules": self.invalidation_rules,
        }


@dataclass(frozen=True, slots=True)
class StrategySignal:
    trade_date: date
    symbol: str
    action: str
    score: Decimal
    reason: str
    explanation: SignalExplanation


class Strategy(Protocol):
    @property
    def name(self) -> str:
        ...

    def select_targets(
        self,
        *,
        trade_date: date,
        features_by_symbol: dict[str, FeatureSnapshot],
        current_positions: set[str],
    ) -> tuple[set[str], list[StrategySignal]]:
        ...


def decimal_param(parameters: dict[str, object], name: str, default: str) -> Decimal:
    value = parameters.get(name, default)
    return Decimal(str(value))


def int_param(parameters: dict[str, object], name: str, default: int) -> int:
    return int(parameters.get(name, default))
