from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from taurus_core.intelligence.documents import stable_id

AlertEventType = Literal[
    "paper_fill",
    "order_rejection",
    "kill_switch_activation",
    "severe_event_detected",
    "scheduled_job_failure",
    "stale_data_event",
    "risk_rejection_spike",
    "alert_smoke_test",
]
AlertSeverity = Literal["info", "warning", "critical"]


class AlertEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    event_type: AlertEventType
    severity: AlertSeverity
    message: str = Field(min_length=1)
    run_id: str | None = None
    decision_id: str | None = None
    symbol: str | None = None
    source_id: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: dict[str, object] = Field(default_factory=dict)
    model_version: str = "alert_event_v1"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str | None) -> str | None:
        return value.upper() if value else value


class AlertDeliveryResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    adapter: str
    delivered: bool
    destination: str = ""
    status_code: int | None = None
    response_text: str = ""
    error: str = ""
    delivered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


def alert_event_id(
    *,
    event_type: AlertEventType,
    run_id: str | None = None,
    decision_id: str | None = None,
    symbol: str | None = None,
    source_id: str | None = None,
) -> str:
    return stable_id(
        "alert",
        event_type,
        run_id or "",
        decision_id or "",
        symbol.upper() if symbol else "",
        source_id or "",
    )
