from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_STRATEGY_CONFIG_PATH = Path("configs/strategies/moving_average_crossover_v1.yaml")


@dataclass(frozen=True, slots=True)
class StrategyConfig:
    strategy_name: str
    strategy_type: str
    target_positions: int
    lookback_days: int
    rebalance_every_days: int
    parameters: dict[str, object]
    source_path: str | None = None


def load_strategy_config(path: str | Path) -> StrategyConfig:
    config_path = Path(path)
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"Strategy config must be a mapping: {config_path}")

    strategy_name = _required_str(raw, "strategy_name", config_path)
    strategy_type = _required_str(raw, "strategy_type", config_path)
    parameters = raw.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError(f"Strategy config parameters must be a mapping: {config_path}")

    return StrategyConfig(
        strategy_name=strategy_name,
        strategy_type=strategy_type,
        target_positions=_positive_int(raw, "target_positions", default=3, path=config_path),
        lookback_days=_positive_int(raw, "lookback_days", default=60, path=config_path),
        rebalance_every_days=_positive_int(
            raw,
            "rebalance_every_days",
            default=21,
            path=config_path,
        ),
        parameters=dict(parameters),
        source_path=str(config_path),
    )


def _required_str(raw: dict[str, Any], key: str, path: Path) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"Strategy config must set {key}: {path}")
    return value


def _positive_int(
    raw: dict[str, Any],
    key: str,
    *,
    default: int,
    path: Path,
) -> int:
    value = int(raw.get(key, default))
    if value <= 0:
        raise ValueError(f"Strategy config {key} must be positive: {path}")
    return value
