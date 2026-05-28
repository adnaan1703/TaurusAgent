from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taurus_core.intelligence.documents import stable_id
from taurus_core.research.schemas import TraderAction

RiskRuleStatus = Literal["passed", "warn", "reduced", "rejected", "blocked"]
RiskRecommendation = Literal["allow", "reduce", "reject", "block"]
RiskReviewStatus = Literal["APPROVED", "APPROVED_WITH_REDUCTION", "REJECTED", "BLOCKED"]
FinalDecisionStatus = Literal["APPROVED_FOR_PAPER", "REJECTED", "BLOCKED"]


class RiskPersonaReview(BaseModel):
    model_config = ConfigDict(frozen=True)

    agent_name: str
    recommendation: RiskRecommendation
    score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    key_points: list[str] = Field(min_length=1)
    required_conditions: list[str] = Field(min_length=1)
    model_version: str

    @field_validator("key_points", "required_conditions")
    @classmethod
    def clean_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class HardRuleResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule: str
    status: RiskRuleStatus
    details: str = Field(min_length=1)


class RiskReview(BaseModel):
    model_config = ConfigDict(frozen=True)

    risk_check_id: str
    decision_id: str
    run_id: str
    symbol: str
    proposal_id: str
    debate_id: str
    as_of: datetime
    status: RiskReviewStatus
    requested_position_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    approved_position_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    hard_rule_results: list[HardRuleResult] = Field(min_length=1)
    persona_reviews: list[RiskPersonaReview] = Field(min_length=1)
    risk_committee_summary: str = Field(min_length=1)
    source_report_ids: list[str] = Field(min_length=1)
    is_order: bool = False
    can_send_to_broker: bool = False
    model_version: str

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("source_report_ids")
    @classmethod
    def clean_source_ids(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class FinalDecision(BaseModel):
    model_config = ConfigDict(frozen=True)

    final_decision_id: str
    decision_id: str
    run_id: str
    symbol: str
    proposal_id: str
    risk_check_id: str
    as_of: datetime
    final_action: TraderAction
    status: FinalDecisionStatus
    approved_quantity: int = Field(ge=0)
    approved_position_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    reason: str = Field(min_length=1)
    is_order: bool = False
    can_send_to_broker: bool = False
    model_version: str

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


def decision_id_for_proposal(*, run_id: str, symbol: str, proposal_id: str) -> str:
    return stable_id("dec", run_id, symbol.upper(), proposal_id)


def risk_review_id(
    *,
    run_id: str,
    symbol: str,
    proposal_id: str,
    source_report_ids: list[str],
) -> str:
    return stable_id(
        "risk",
        run_id,
        symbol.upper(),
        proposal_id,
        ",".join(sorted(source_report_ids)),
    )


def final_decision_id(
    *,
    run_id: str,
    symbol: str,
    proposal_id: str,
    risk_check_id: str,
) -> str:
    return stable_id("fd", run_id, symbol.upper(), proposal_id, risk_check_id)


def _clean_list(value: list[str]) -> list[str]:
    cleaned = [item.strip() for item in value if item.strip()]
    if not cleaned:
        raise ValueError("at least one non-empty item is required")
    return cleaned
