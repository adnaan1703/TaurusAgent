from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    strategy_name: str = "moving_average_crossover_v1"
    strategy_type: str = "moving_average_crossover"
    strategy_config_path: str | None = None
    strategy_parameters: Mapping[str, object] = field(default_factory=dict)
    seed: int = 42
    initial_capital_inr: Decimal = Decimal("1000000")
    max_open_positions: int = 8
    target_positions: int = 3
    lookback_days: int = 60
    rebalance_every_days: int = 21
    cost_bps: Decimal = Decimal("10")
    slippage_bps: Decimal = Decimal("5")
    timeframe: str = "1d"
    graph_enabled: bool = False

    def __post_init__(self) -> None:
        if self.initial_capital_inr <= 0:
            raise ValueError("initial_capital_inr must be positive")
        if self.max_open_positions <= 0:
            raise ValueError("max_open_positions must be positive")
        if self.target_positions <= 0:
            raise ValueError("target_positions must be positive")
        if self.lookback_days <= 0:
            raise ValueError("lookback_days must be positive")
        if self.rebalance_every_days <= 0:
            raise ValueError("rebalance_every_days must be positive")
        if self.cost_bps < 0:
            raise ValueError("cost_bps cannot be negative")
        if self.slippage_bps < 0:
            raise ValueError("slippage_bps cannot be negative")
        if self.strategy_type == "graph_aware_score" and not self.graph_enabled:
            object.__setattr__(self, "graph_enabled", True)


@dataclass(frozen=True, slots=True)
class BacktestResult:
    run_id: str
    start_date: date
    end_date: date
    metrics: dict[str, object]
    feature_value_count: int
    signal_count: int
    order_count: int
    fill_count: int
    position_count: int
    equity_point_count: int
    audit_row_count: int
