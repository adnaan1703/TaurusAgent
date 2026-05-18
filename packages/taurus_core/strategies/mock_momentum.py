from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from taurus_core.domain.market_data import DailyCandle


@dataclass(frozen=True, slots=True)
class MomentumSignal:
    trade_date: date
    symbol: str
    action: str
    score: Decimal
    reason: str


class MockMomentumStrategy:
    def __init__(self, *, lookback_days: int, target_positions: int) -> None:
        self.lookback_days = lookback_days
        self.target_positions = target_positions

    def select_targets(
        self,
        *,
        trade_date: date,
        history_by_symbol: dict[str, list[DailyCandle]],
        current_positions: set[str],
    ) -> tuple[set[str], list[MomentumSignal]]:
        scored: list[tuple[str, Decimal]] = []
        for symbol, history in history_by_symbol.items():
            if len(history) <= self.lookback_days:
                continue
            current_close = history[-1].close
            lookback_close = history[-self.lookback_days - 1].close
            if lookback_close <= 0:
                continue
            scored.append((symbol, (current_close / lookback_close) - Decimal("1")))

        ranked = sorted(scored, key=lambda item: (-item[1], item[0]))
        targets = {
            symbol
            for symbol, score in ranked[: self.target_positions]
            if score > Decimal("0")
        }

        signals: list[MomentumSignal] = []
        for symbol, score in ranked:
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
                        reason=f"Exited top {self.target_positions} momentum set",
                    )
                )
        return targets, signals
