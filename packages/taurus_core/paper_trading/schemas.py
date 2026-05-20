from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taurus_core.intelligence.documents import stable_id

PaperRunStatus = Literal["RUNNING", "COMPLETED", "PARTIAL_FAILED", "FAILED"]


class PaperRunError(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    stage: str
    message: str
    error_type: str

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class PaperRun(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    schedule_name: str = "daily_after_close"
    status: PaperRunStatus
    started_at: datetime
    completed_at: datetime | None = None
    symbols: list[str] = Field(default_factory=list)
    succeeded_symbols: list[str] = Field(default_factory=list)
    failed_symbols: list[str] = Field(default_factory=list)
    errors: list[PaperRunError] = Field(default_factory=list)
    market_data_summary: dict[str, object] = Field(default_factory=dict)
    artifacts: dict[str, object] = Field(default_factory=dict)
    timezone: str = "Asia/Kolkata"
    run_after_market_close: bool = True
    model_version: str = "paper_run_v1"

    @field_validator("symbols", "succeeded_symbols", "failed_symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        return [symbol.upper() for symbol in value if symbol.strip()]


def paper_run_id(*, started_at: datetime, symbols: list[str], schedule_name: str) -> str:
    return stable_id(
        "pr",
        started_at.isoformat(),
        ",".join(sorted(symbol.upper() for symbol in symbols)),
        schedule_name,
    )
