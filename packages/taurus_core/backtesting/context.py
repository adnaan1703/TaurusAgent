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
    portfolio_breadth: int | None = None
    portfolio_breadth_source: str = "backtest_config"
    target_positions: int | None = None
    lookback_days: int = 60
    rebalance_every_days: int = 21
    cost_bps: Decimal = Decimal("10")
    slippage_bps: Decimal = Decimal("5")
    timeframe: str = "1d"
    graph_enabled: bool = False
    symbols: tuple[str, ...] = ()
    start_date: date | None = None
    end_date: date | None = None

    def __post_init__(self) -> None:
        if self.initial_capital_inr <= 0:
            raise ValueError("initial_capital_inr must be positive")
        if self.max_open_positions <= 0:
            raise ValueError("max_open_positions must be positive")
        if self.portfolio_breadth is not None and self.portfolio_breadth <= 0:
            raise ValueError("portfolio_breadth must be positive when provided")
        if not self.portfolio_breadth_source:
            raise ValueError("portfolio_breadth_source must be set")
        if self.target_positions is not None and self.target_positions <= 0:
            raise ValueError("target_positions must be positive when provided")
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
        if self.start_date is not None and self.end_date is not None:
            if self.start_date > self.end_date:
                raise ValueError("start_date must be on or before end_date")
        if self.symbols:
            object.__setattr__(
                self,
                "symbols",
                tuple(sorted({symbol.upper() for symbol in self.symbols})),
            )

    @property
    def effective_portfolio_breadth(self) -> int:
        requested = (
            self.portfolio_breadth or self.target_positions or self.max_open_positions
        )
        return min(requested, self.max_open_positions)


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
