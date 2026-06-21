from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from taurus_core.allocation_schemas import AllocationDecision


DrawdownGovernorAction = Literal[
    "reduce_new_position_sizes_25_pct",
    "reduce_new_position_sizes_50_pct",
    "stop_experimental_new_entries",
    "freeze_new_buys_allow_exits",
]


@dataclass(frozen=True, slots=True)
class PositionLimitPolicy:
    max_stock_pct_nav: Decimal
    max_open_positions: int
    source: str


class SleevePolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    sleeve_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    target_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    role: str = Field(min_length=1)
    drawdown_reduce_threshold_pct: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("100"),
    )
    drawdown_reduce_size_pct: Decimal = Field(
        default=Decimal("50.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
    )
    drawdown_freeze_threshold_pct: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("100"),
    )
    new_entry_risk_cap_pct_nav: Decimal | None = Field(
        default=None,
        ge=Decimal("0"),
        le=Decimal("100"),
    )

    @field_validator("sleeve_id")
    @classmethod
    def normalize_sleeve_id(cls, value: str) -> str:
        return value.strip().lower()


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


class AllocationScoreWeightsPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    strategy_score: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    trader_confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    liquidity: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    volatility: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    diversification: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    recent_sleeve_performance: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))

    @model_validator(mode="after")
    def validate_weight_sum(self) -> AllocationScoreWeightsPolicy:
        total = sum(
            (
                self.strategy_score,
                self.trader_confidence,
                self.liquidity,
                self.volatility,
                self.diversification,
                self.recent_sleeve_performance,
            ),
            Decimal("0"),
        )
        if total != Decimal("1.00"):
            raise ValueError("allocation score weights must sum to 1.00.")
        return self


class AllocationScoreBandsPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    reject_below: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    half_normal_below: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    normal_below: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))

    @model_validator(mode="after")
    def validate_band_order(self) -> AllocationScoreBandsPolicy:
        if not (self.reject_below < self.half_normal_below < self.normal_below):
            raise ValueError(
                "allocation score bands must satisfy reject_below < "
                "half_normal_below < normal_below."
            )
        return self


class AllocationScoringPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    weights: AllocationScoreWeightsPolicy
    score_bands: AllocationScoreBandsPolicy


class DrawdownGovernorPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    drawdown_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    action: DrawdownGovernorAction

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value: object) -> str:
        return str(value).strip().lower()


class RebalanceThresholdPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    sleeve_drift_threshold_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    min_rebalance_notional_inr: Decimal = Field(ge=Decimal("0"))
    review_frequency: str = Field(min_length=1)
    core_rebalance_frequency: str = Field(min_length=1)


class RebalanceCapacityPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    hard_cash_reserve_pct_nav: Decimal = Field(
        default=Decimal("5.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
    )
    same_run_proceeds_haircut_pct: Decimal = Field(
        default=Decimal("80.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
    )
    buy_price_buffer_pct: Decimal = Field(
        default=Decimal("5.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
    )
    soft_borrowing_enabled: bool = True
    borrowable_sleeve_ids: tuple[str, ...] = Field(default_factory=tuple)
    borrower_sleeve_ids: tuple[str, ...] = Field(default_factory=tuple)
    max_borrowed_capacity_pct_nav: Decimal | None = Field(
        default=Decimal("20.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
    )
    max_borrowed_capacity_inr: Decimal | None = Field(default=None, ge=Decimal("0"))
    repay_priority_sleeve_ids: tuple[str, ...] = Field(default_factory=tuple)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "borrowable_sleeve_ids",
        "borrower_sleeve_ids",
        "repay_priority_sleeve_ids",
        mode="before",
    )
    @classmethod
    def normalize_sleeve_ids(cls, value: object) -> tuple[str, ...]:
        if value is None:
            return tuple()
        if not isinstance(value, list | tuple):
            raise ValueError("rebalance capacity sleeve IDs must be a list.")
        normalized: list[str] = []
        for item in value:
            sleeve_id = str(item).strip().lower()
            if sleeve_id:
                normalized.append(sleeve_id)
        return tuple(dict.fromkeys(normalized))


class MoneyManagementPolicy(BaseModel):
    model_config = ConfigDict(frozen=True)

    policy_version: str = Field(min_length=1)
    shariah_universe_path: str = Field(min_length=1)
    sleeves: tuple[SleevePolicy, ...]
    strategy_mappings: tuple[StrategySleeveMapping, ...] = Field(default_factory=tuple)
    limits: ExposureLimitsPolicy
    trade_risk: TradeRiskDefaultsPolicy
    allocation_scoring: AllocationScoringPolicy
    drawdown_governors: tuple[DrawdownGovernorPolicy, ...] = Field(default_factory=tuple)
    rebalance: RebalanceThresholdPolicy
    rebalance_capacity: RebalanceCapacityPolicy = Field(
        default_factory=RebalanceCapacityPolicy
    )

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

        if "cash_buffer" not in sleeve_ids:
            raise ValueError("money-management policy requires a cash_buffer sleeve.")

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

        explicit_borrowable = tuple(self.rebalance_capacity.borrowable_sleeve_ids)
        explicit_borrowers = tuple(self.rebalance_capacity.borrower_sleeve_ids)
        explicit_repay = tuple(self.rebalance_capacity.repay_priority_sleeve_ids)

        known_sleeves = set(sleeve_ids)
        unknown_capacity_refs = sorted(
            (
                set(explicit_borrowable)
                | set(explicit_borrowers)
                | set(explicit_repay)
            )
            - known_sleeves
        )
        if unknown_capacity_refs:
            raise ValueError(
                "rebalance capacity references unknown sleeves: "
                + ", ".join(unknown_capacity_refs)
            )
        if "cash_buffer" in explicit_borrowable:
            raise ValueError("cash_buffer cannot be a borrowable sleeve.")
        overlap = sorted(set(explicit_borrowable) & set(explicit_borrowers))
        if overlap:
            raise ValueError(
                "rebalance capacity borrower sleeves cannot also be borrowable: "
                + ", ".join(overlap)
            )

        borrower_ids = explicit_borrowers
        if not borrower_ids and "active_strategy" in known_sleeves:
            borrower_ids = ("active_strategy",)
        borrowable_ids = explicit_borrowable
        if not borrowable_ids:
            borrower_set = set(borrower_ids)
            borrowable_ids = tuple(
                sleeve_id
                for sleeve_id in sleeve_ids
                if sleeve_id != "cash_buffer" and sleeve_id not in borrower_set
            )
        repay_ids = explicit_repay or borrowable_ids
        capacity = self.rebalance_capacity.model_copy(
            update={
                "borrower_sleeve_ids": borrower_ids,
                "borrowable_sleeve_ids": borrowable_ids,
                "repay_priority_sleeve_ids": repay_ids,
            }
        )
        object.__setattr__(self, "rebalance_capacity", capacity)
        return self

    @property
    def cash_buffer_target_pct(self) -> Decimal:
        return next(
            sleeve.target_weight_pct
            for sleeve in self.sleeves
            if sleeve.sleeve_id == "cash_buffer"
        )

    @property
    def hard_cash_reserve_pct_nav(self) -> Decimal:
        return self.rebalance_capacity.hard_cash_reserve_pct_nav

    def to_metadata(self) -> dict[str, Any]:
        return self.model_dump(mode="json")


class SleeveSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)

    portfolio_id: str
    sleeve_id: str
    as_of: datetime
    target_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    current_weight_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    nav_inr: Decimal = Field(ge=Decimal("0"))
    cash_inr: Decimal = Field(ge=Decimal("0"))
    starting_nav_estimate_inr: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    current_exposure_inr: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    realized_pnl_inr: Decimal = Decimal("0")
    unrealized_pnl_inr: Decimal = Decimal("0")
    drawdown_pct: Decimal = Field(default=Decimal("0"), ge=Decimal("0"), le=Decimal("100"))
    open_position_count: int = Field(ge=0)
    open_trade_risk_inr: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    turnover_inr: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
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
    return policy


def load_money_management_policy_for_settings(settings: Any) -> MoneyManagementPolicy:
    return load_money_management_policy(settings.taurus_money_management_config_path)


def position_limits_for_settings(settings: Any) -> PositionLimitPolicy:
    if bool(settings.taurus_money_management_enabled):
        policy = load_money_management_policy_for_settings(settings)
        return PositionLimitPolicy(
            max_stock_pct_nav=policy.limits.max_stock_pct_nav,
            max_open_positions=policy.limits.max_open_positions,
            source="money_management_policy",
        )
    return PositionLimitPolicy(
        max_stock_pct_nav=Decimal(str(settings.taurus_max_position_pct)),
        max_open_positions=int(settings.taurus_max_open_positions),
        source="settings",
    )


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
        "portfolio_drawdown_pct": "0.0000",
        "portfolio_governor_reasons": [],
        "sleeve_statuses": initial_sleeve_governor_statuses(
            policy,
            nav_inr=Decimal(str(settings.taurus_initial_capital_inr)),
        ),
        "fractional_kelly": {
            "status": "deferred_pending_paper_trade_history",
            "required_history_source": "allocation_decisions_and_sleeve_snapshots",
        },
    }
    return metadata


def initial_sleeve_governor_statuses(
    policy: MoneyManagementPolicy,
    *,
    nav_inr: Decimal,
) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for sleeve in policy.sleeves:
        starting_nav = (nav_inr * sleeve.target_weight_pct / Decimal("100")).quantize(
            Decimal("0.01")
        )
        statuses.append(
            {
                "sleeve_id": sleeve.sleeve_id,
                "sleeve_name": sleeve.name,
                "target_weight_pct": str(sleeve.target_weight_pct),
                "starting_nav_estimate_inr": str(starting_nav),
                "current_exposure_inr": "0.00",
                "realized_pnl_inr": "0.00",
                "unrealized_pnl_inr": "0.00",
                "drawdown_pct": "0.0000",
                "open_position_count": 0,
                "open_trade_risk_inr": "0.00",
                "turnover_inr": "0.00",
                "new_entry_scale_factor": "1.0000",
                "new_entries_frozen": False,
                "governor_reasons": [],
                "new_entry_risk_cap_pct_nav": (
                    str(sleeve.new_entry_risk_cap_pct_nav)
                    if sleeve.new_entry_risk_cap_pct_nav is not None
                    else None
                ),
                "fractional_kelly_ready": False,
            }
        )
    return statuses
