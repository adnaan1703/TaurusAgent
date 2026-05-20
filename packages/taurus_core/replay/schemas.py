from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ReplayStage(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    artifact_count: int = Field(ge=0)
    artifacts: list[dict[str, object]] = Field(default_factory=list)


class DecisionReplay(BaseModel):
    model_config = ConfigDict(frozen=True)

    decision_id: str
    run_id: str
    symbol: str
    status: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    note: str
    stages: list[ReplayStage]

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()
