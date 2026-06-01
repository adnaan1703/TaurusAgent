from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from taurus_core.data.universe import load_market_data_universe


class SleevePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    sleeve_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    target_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    role: str = Field(min_length=1)
    core_symbols: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("sleeve_id")
    @classmethod
    def normalize_sleeve_id(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("core_symbols", mode="before")
    @classmethod
    def normalize_core_symbols(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return tuple()
        if not isinstance(value, list | tuple):
            raise ValueError("core_symbols must be a list of symbols.")
        return tuple(str(symbol).strip().upper() for symbol in value if str(symbol).strip())


class StrategySleeveMapping(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_name: str = Field(min_length=1)
    sleeve_id: str = Field(min_length=1)

    @field_validator("strategy_name")
    @classmethod
    def normalize_strategy_name(cls, value: str) -> str:
        return value.strip()

    @field_validator("sleeve_id")
    @classmethod
    def normalize_sleeve_id(cls, value: str) -> str:
        return value.strip().lower()


class ExposureLimitsPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    max_stock_pct_nav: Decimal = Field(gt=Decimal("0"), le=Decimal("100"))
    max_stock_hard_cap_pct_nav: Decimal = Field(gt=Decimal("0"), le=Decimal("100"))
    max_sector_pct_nav: Decimal = Field(gt=Decimal("0"), le=Decimal("100"))
    max_graph_cluster_pct_nav: Decimal = Field(gt=Decimal("0"), le=Decimal("100"))
    max_open_positions: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_stock_caps(self) -> ExposureLimitsPolicy:
        if self.max_stock_hard_cap_pct_nav < self.max_stock_pct_nav:
            raise ValueError("max stock hard cap must be greater than or equal to normal cap.")
        return self


class TradeRiskDefaultsPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    normal_trade_risk_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    strong_trade_risk_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    max_single_trade_risk_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    max_total_open_trade_risk_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))


class DrawdownGovernorPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    drawdown_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    action: str = Field(min_length=1)


class RebalanceThresholdPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    sleeve_drift_threshold_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    position_drift_threshold_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    min_rebalance_notional_inr: Decimal = Field(ge=Decimal("0"))
    review_frequency: str = Field(min_length=1)
    core_rebalance_frequency: str = Field(min_length=1)


class MoneyManagementPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str = Field(min_length=1)
    shariah_universe_path: str = Field(min_length=1)
    sleeves: tuple[SleevePolicy, ...]
    strategy_mappings: tuple[StrategySleeveMapping, ...] = Field(default_factory=tuple)
    cash_buffer_target_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    limits: ExposureLimitsPolicy
    trade_risk: TradeRiskDefaultsPolicy
    drawdown_governors: tuple[DrawdownGovernorPolicy, ...] = Field(default_factory=tuple)
    rebalance: RebalanceThresholdPolicy

    @field_validator("sleeves")
    @classmethod
    def require_sleeves(cls, value: tuple[SleevePolicy, ...]) -> tuple[SleevePolicy, ...]:
        if not value:
            raise ValueError("money-management policy requires at least one sleeve.")
        return value

    @model_validator(mode="after")
    def validate_policy(self) -> MoneyManagementPolicy:
        sleeve_ids = [sleeve.sleeve_id for sleeve in self.sleeves]
        if len(sleeve_ids) != len(set(sleeve_ids)):
            raise ValueError("sleeve IDs must be unique.")

        total = sum((sleeve.target_weight_pct for sleeve in self.sleeves), Decimal("0"))
        if total != Decimal("100"):
            raise ValueError("sleeve weights must sum to 100%.")

        missing_sleeves = sorted(
            {
                mapping.sleeve_id
                for mapping in self.strategy_mappings
                if mapping.sleeve_id not in set(sleeve_ids)
            }
        )
        if missing_sleeves:
            raise ValueError(
                "strategy mappings reference unknown sleeves: " + ", ".join(missing_sleeves)
            )
        return self

    @property
    def core_symbols(self) -> tuple[str, ...]:
        symbols = {
            symbol
            for sleeve in self.sleeves
            for symbol in sleeve.core_symbols
            if symbol.strip()
        }
        return tuple(sorted(symbols))

    def to_metadata(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload["core_symbols"] = list(self.core_symbols)
        return payload


class AllocationDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    strategy_name: str
    sleeve_id: str
    status: Literal["approved", "rejected", "unchanged"]
    requested_notional_inr: Decimal = Field(ge=Decimal("0"))
    approved_notional_inr: Decimal = Field(ge=Decimal("0"))
    approved_quantity: int = Field(ge=0)
    binding_constraint: str | None = None
    rationale: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("sleeve_id")
    @classmethod
    def normalize_sleeve_id(cls, value: str) -> str:
        return value.strip().lower()


class SleeveSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    portfolio_id: str
    sleeve_id: str
    as_of: datetime
    target_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    current_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    nav_inr: Decimal = Field(ge=Decimal("0"))
    cash_inr: Decimal = Field(ge=Decimal("0"))
    open_position_count: int = Field(ge=0)
    symbols: tuple[str, ...] = Field(default_factory=tuple)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("sleeve_id")
    @classmethod
    def normalize_sleeve_id(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return tuple()
        if not isinstance(value, list | tuple):
            raise ValueError("symbols must be a list of symbols.")
        return tuple(str(symbol).strip().upper() for symbol in value if str(symbol).strip())


PortfolioPolicy = MoneyManagementPolicy
StrategyMapping = StrategySleeveMapping


def load_money_management_policy(path: str | Path) -> MoneyManagementPolicy:
    source_path = Path(path).expanduser()
    if not source_path.exists():
        raise ValueError(f"Money-management policy file not found: {source_path}")
    if not source_path.is_file():
        raise ValueError(f"Money-management policy path is not a file: {source_path}")

    with source_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)
    if not isinstance(payload, dict):
        raise ValueError("Money-management policy must be a YAML mapping.")

    policy = MoneyManagementPolicy.model_validate(payload)
    _validate_core_symbols(policy)
    return policy


def load_money_management_policy_for_settings(settings: Any) -> MoneyManagementPolicy:
    return load_money_management_policy(settings.taurus_money_management_config_path)


def money_management_metadata(settings: Any) -> dict[str, Any]:
    enabled = bool(settings.taurus_money_management_enabled)
    metadata: dict[str, Any] = {
        "enabled": enabled,
        "config_path": settings.taurus_money_management_config_path,
    }
    if not enabled:
        return metadata

    policy = load_money_management_policy_for_settings(settings)
    metadata["policy"] = policy.to_metadata()
    metadata["state"] = {
        "snapshot_source": "not_persisted",
        "sleeve_snapshot_count": 0,
        "allocation_decision_count": 0,
    }
    return metadata


def _validate_core_symbols(policy: MoneyManagementPolicy) -> None:
    if not policy.core_symbols:
        return
    universe = load_market_data_universe(policy.shariah_universe_path)
    enabled_symbols = set(universe.enabled_symbols())
    missing = [symbol for symbol in policy.core_symbols if symbol not in enabled_symbols]
    if missing:
        raise ValueError(
            "Configured core symbols are not enabled in the Shariah universe: "
            + ", ".join(missing)
        )
