from __future__ import annotations

from taurus_core.strategies.base import Strategy
from taurus_core.strategies.blended_score import BlendedScoreStrategy
from taurus_core.strategies.config import StrategyConfig
from taurus_core.strategies.graph_aware import GraphAwareScoreStrategy
from taurus_core.strategies.moving_average_crossover import MovingAverageCrossoverStrategy


def build_strategy(config: StrategyConfig) -> Strategy:
    if config.strategy_type == "moving_average_crossover":
        return MovingAverageCrossoverStrategy(
            name=config.strategy_name,
            target_positions=config.target_positions,
            parameters=config.parameters,
        )
    if config.strategy_type == "blended_score":
        return BlendedScoreStrategy(
            name=config.strategy_name,
            target_positions=config.target_positions,
            parameters=config.parameters,
        )
    if config.strategy_type == "graph_aware_score":
        return GraphAwareScoreStrategy(
            name=config.strategy_name,
            target_positions=config.target_positions,
            parameters=config.parameters,
        )
    raise ValueError(f"Unsupported strategy_type: {config.strategy_type}")
