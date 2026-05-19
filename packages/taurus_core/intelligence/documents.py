from __future__ import annotations

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

EventHorizon = Literal["intraday", "short", "medium", "long"]


class RawDocument(BaseModel):
    model_config = ConfigDict(frozen=True)

    document_id: str
    source: str
    source_url: str = ""
    title: str
    body: str
    published_at: datetime
    symbols: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    checksum: str
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("symbols")
    @classmethod
    def normalize_symbols(cls, value: list[str]) -> list[str]:
        return sorted({symbol.upper() for symbol in value})


class NewsEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    event_id: str
    document_id: str
    symbol: str
    event_type: str
    event_time: datetime
    headline: str
    summary: str
    severity: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    horizon: EventHorizon
    source_confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


class SentimentScore(BaseModel):
    model_config = ConfigDict(frozen=True)

    score_id: str
    event_id: str
    symbol: str
    as_of: datetime
    sentiment_score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    event_score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    decayed_score: Decimal = Field(ge=Decimal("-1"), le=Decimal("1"))
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    severity: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    horizon: EventHorizon
    rationale: str = ""
    model_version: str = "event_scoring_v1"

    @field_validator("symbol")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()


def stable_id(prefix: str, *parts: object) -> str:
    payload = json.dumps([str(part) for part in parts], sort_keys=True)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:16]}"


def document_checksum(*parts: object) -> str:
    payload = json.dumps([str(part) for part in parts], sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
