from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

ProfileStatus = Literal["ACTIVE", "ARCHIVED"]

DEFAULT_PROFILE_ID = "local-paper"
DEFAULT_PROFILE_DISPLAY_NAME = "Local Paper"
DEFAULT_PROFILE_STARTING_CORPUS_INR = Decimal("10000.0000")
DEFAULT_PROFILE_CURRENCY = "INR"
MONEY_QUANT = Decimal("0.0001")
PROFILE_ID_PATTERN = re.compile(r"^[a-z0-9_-]{1,64}$")


def validate_profile_id(value: str) -> str:
    cleaned = value.strip()
    if not PROFILE_ID_PATTERN.fullmatch(cleaned):
        raise ValueError(
            "profile_id must be 1-64 characters using only lowercase a-z, 0-9, '-', and '_'."
        )
    return cleaned


def normalize_money(value: Decimal | int | str) -> Decimal:
    try:
        amount = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(
            "starting_corpus_inr must be a positive decimal amount."
        ) from exc
    if amount <= 0:
        raise ValueError("starting_corpus_inr must be positive.")
    return amount.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)


def _normalize_display_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("display_name must be non-empty.")
    return cleaned


def _normalize_currency(value: str) -> str:
    cleaned = value.strip().upper()
    if not cleaned:
        raise ValueError("currency must be non-empty.")
    return cleaned


class TaurusProfileCreate(BaseModel):
    model_config = ConfigDict(frozen=True)

    profile_id: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    starting_corpus_inr: Decimal
    currency: str = DEFAULT_PROFILE_CURRENCY
    status: ProfileStatus = "ACTIVE"
    description: str = ""
    profile_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("profile_id")
    @classmethod
    def validate_slug(cls, value: str) -> str:
        return validate_profile_id(value)

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str) -> str:
        return _normalize_display_name(value)

    @field_validator("starting_corpus_inr")
    @classmethod
    def validate_starting_corpus(cls, value: Decimal) -> Decimal:
        return normalize_money(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str) -> str:
        return _normalize_currency(value)


class TaurusProfileUpdate(BaseModel):
    model_config = ConfigDict(frozen=True)

    display_name: str | None = None
    starting_corpus_inr: Decimal | None = None
    currency: str | None = None
    status: ProfileStatus | None = None
    description: str | None = None
    profile_metadata: dict[str, Any] | None = None

    @field_validator("display_name")
    @classmethod
    def validate_display_name(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_display_name(value)

    @field_validator("starting_corpus_inr")
    @classmethod
    def validate_starting_corpus(cls, value: Decimal | None) -> Decimal | None:
        return None if value is None else normalize_money(value)

    @field_validator("currency")
    @classmethod
    def validate_currency(cls, value: str | None) -> str | None:
        return None if value is None else _normalize_currency(value)


class TaurusProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True, frozen=True)

    profile_id: str
    display_name: str
    starting_corpus_inr: Decimal
    currency: str
    status: ProfileStatus
    description: str
    profile_metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
