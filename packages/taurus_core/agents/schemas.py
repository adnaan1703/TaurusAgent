from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taurus_core.intelligence.documents import stable_id

AgentStance = Literal["bullish", "bearish", "neutral"]
ReportHorizon = Literal["intraday", "short", "medium", "long"]


class LLMAnalystOutput(BaseModel):
    model_config = ConfigDict(frozen=True)

    score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    stance: AgentStance
    horizon: ReportHorizon
    key_points: list[str] = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    model_version: str

    @field_validator("key_points", "risks")
    @classmethod
    def remove_empty_items(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("at least one non-empty item is required")
        return cleaned


class AnalystReport(BaseModel):
    model_config = ConfigDict(frozen=True)

    report_id: str
    run_id: str
    decision_id: str | None = None
    symbol: str
    agent_name: str
    as_of: datetime
    score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    stance: AgentStance
    horizon: ReportHorizon
    key_points: list[str] = Field(min_length=1)
    risks: list[str] = Field(min_length=1)
    source_ids: list[str] = Field(default_factory=list)
    model_version: str

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("key_points", "risks", "source_ids")
    @classmethod
    def clean_lists(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


def stance_from_score(score: Decimal) -> AgentStance:
    if score >= Decimal("0.10"):
        return "bullish"
    if score <= Decimal("-0.10"):
        return "bearish"
    return "neutral"


def analyst_report_id(
    *,
    run_id: str,
    symbol: str,
    agent_name: str,
    as_of: datetime,
    source_ids: list[str],
) -> str:
    return stable_id(
        "ar",
        run_id,
        symbol.upper(),
        agent_name,
        as_of.isoformat(),
        ",".join(sorted(source_ids)),
    )
