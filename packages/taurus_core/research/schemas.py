from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taurus_core.agents.schemas import ReportHorizon
from taurus_core.intelligence.documents import stable_id

ConsensusLabel = Literal["bullish", "mild_bullish", "neutral", "mild_bearish", "bearish"]
TraderAction = Literal["BUY", "SELL", "HOLD", "NO_TRADE", "REDUCE", "EXIT"]
TraderOrderType = Literal["LIMIT", "MARKET", "NONE"]


class BullThesis(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    key_points: list[str] = Field(min_length=1)
    conditions: list[str] = Field(min_length=1)
    source_report_ids: list[str] = Field(min_length=1)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("key_points", "conditions", "source_report_ids")
    @classmethod
    def clean_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class BearThesis(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    key_points: list[str] = Field(min_length=1)
    risk_flags: list[str] = Field(min_length=1)
    source_report_ids: list[str] = Field(min_length=1)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("key_points", "risk_flags", "source_report_ids")
    @classmethod
    def clean_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class DebateRound(BaseModel):
    model_config = ConfigDict(frozen=True)

    round_number: int = Field(ge=1)
    bull_argument: str = Field(min_length=1)
    bear_argument: str = Field(min_length=1)
    manager_note: str = Field(min_length=1)


class ResearchManagerSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    consensus_label: ConsensusLabel
    consensus_score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    summary: str = Field(min_length=1)
    unresolved_uncertainties: list[str] = Field(min_length=1)

    @field_validator("unresolved_uncertainties")
    @classmethod
    def clean_uncertainties(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class DebateReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    debate_id: str
    run_id: str
    symbol: str
    as_of: datetime
    rounds_requested: int = Field(ge=1, le=10)
    bull_thesis: BullThesis
    bear_thesis: BearThesis
    rounds: list[DebateRound] = Field(min_length=1)
    manager_summary: ResearchManagerSummary
    source_report_ids: list[str] = Field(min_length=1)
    model_version: str

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("source_report_ids")
    @classmethod
    def clean_source_ids(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


class TraderProposal(BaseModel):
    model_config = ConfigDict(frozen=True)

    proposal_id: str
    run_id: str
    symbol: str
    debate_id: str
    as_of: datetime
    action: TraderAction
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    horizon: ReportHorizon
    requested_position_pct_nav: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    order_type: TraderOrderType
    entry_rule: str = Field(min_length=1)
    stop_loss_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    take_profit_pct: Decimal = Field(ge=Decimal("0"), le=Decimal("100"))
    reason_summary: str = Field(min_length=1)
    invalid_if: list[str] = Field(min_length=1)
    source_report_ids: list[str] = Field(min_length=1)
    is_order: bool = False
    requires_risk_approval: bool = True
    model_version: str

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("invalid_if", "source_report_ids")
    @classmethod
    def clean_lists(cls, value: list[str]) -> list[str]:
        return _clean_list(value)


def debate_report_id(
    *,
    run_id: str,
    symbol: str,
    rounds_requested: int,
    source_report_ids: list[str],
) -> str:
    return stable_id(
        "deb",
        run_id,
        symbol.upper(),
        rounds_requested,
        ",".join(sorted(source_report_ids)),
    )


def trader_proposal_id(
    *,
    run_id: str,
    symbol: str,
    debate_id: str,
    source_report_ids: list[str],
) -> str:
    return stable_id(
        "tp",
        run_id,
        symbol.upper(),
        debate_id,
        ",".join(sorted(source_report_ids)),
    )


def _clean_list(value: list[str]) -> list[str]:
    cleaned = [item.strip() for item in value if item.strip()]
    if not cleaned:
        raise ValueError("at least one non-empty item is required")
    return cleaned
