from __future__ import annotations

from decimal import Decimal
from typing import Literal

AllocationStatus = Literal[
    "approved",
    "rejected",
    "unchanged",
    "selected",
    "not_selected",
    "unchanged_lifecycle",
    "allocation_rejected",
    "allocation_reduced",
    "open_position_management",
]

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AllocationDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    action: str = Field(default="BUY", min_length=1)
    strategy_name: str
    sleeve_id: str
    sleeve_name: str | None = None
    status: AllocationStatus
    candidate_score: Decimal | None = Field(default=None, ge=Decimal("0"), le=Decimal("100"))
    score_band: str | None = None
    requested_position_pct_nav: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        le=Decimal("100"),
    )
    approved_position_pct_nav: Decimal = Field(
        default=Decimal("0"),
        ge=Decimal("0"),
        le=Decimal("100"),
    )
    requested_notional_inr: Decimal = Field(ge=Decimal("0"))
    approved_notional_inr: Decimal = Field(ge=Decimal("0"))
    approved_quantity: int = Field(ge=0)
    allowed_risk_inr: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    estimated_risk_inr: Decimal = Field(default=Decimal("0"), ge=Decimal("0"))
    volatility_used: Decimal | None = Field(default=None, ge=Decimal("0"))
    governor_scale_factor: Decimal = Field(
        default=Decimal("1.0000"),
        ge=Decimal("0"),
        le=Decimal("1"),
    )
    portfolio_drawdown_pct: Decimal | None = Field(default=None, ge=Decimal("0"))
    sleeve_drawdown_pct: Decimal | None = Field(default=None, ge=Decimal("0"))
    governor_reasons: tuple[str, ...] = Field(default_factory=tuple)
    binding_constraint: str | None = None
    portfolio_plan_id: str | None = None
    portfolio_plan_trade_id: str | None = None
    planner_candidate_id: str | None = None
    planner_source: str | None = None
    planner_rank: int | None = Field(default=None, ge=1)
    capacity_source: str | None = None
    borrowed_from_sleeve_ids: tuple[str, ...] = Field(default_factory=tuple)
    proposal_source: str | None = None
    rationale: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("sleeve_id")
    @classmethod
    def normalize_sleeve_id(cls, value: str) -> str:
        return value.strip().lower()
