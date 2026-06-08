from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from taurus_core.db.repositories import TaurusProfileRepository
from taurus_core.profiles.schemas import normalize_money, validate_profile_id

if TYPE_CHECKING:
    from taurus_core.config import Settings


class RuntimeProfileError(ValueError):
    """Raised when a selected paper profile cannot be used at runtime."""


@dataclass(frozen=True, slots=True)
class RuntimeProfile:
    profile_id: str
    starting_corpus_inr: Decimal
    currency: str

    def to_artifact(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "starting_corpus_inr": str(self.starting_corpus_inr),
            "currency": self.currency,
        }


def resolve_runtime_profile(
    session: Session,
    settings: "Settings",
    *,
    profile_id: str | None = None,
) -> RuntimeProfile:
    selected_profile_id = validate_profile_id(profile_id or settings.effective_profile_id)
    model = TaurusProfileRepository(session).get_profile(selected_profile_id)
    if model is None:
        raise RuntimeProfileError(
            f"Profile {selected_profile_id} not found. Create it before running paper execution."
        )
    if model.status != "ACTIVE":
        raise RuntimeProfileError(
            f"Profile {selected_profile_id} is archived and cannot run paper execution."
        )
    return RuntimeProfile(
        profile_id=model.profile_id,
        starting_corpus_inr=normalize_money(model.starting_corpus_inr),
        currency=model.currency,
    )


def resolve_starting_corpus_inr(
    session: Session,
    settings: "Settings",
    *,
    profile_id: str | None = None,
    legacy_fallback_inr: Decimal | int | str | None = None,
) -> Decimal:
    try:
        return resolve_runtime_profile(
            session,
            settings,
            profile_id=profile_id,
        ).starting_corpus_inr
    except RuntimeProfileError:
        if legacy_fallback_inr is None:
            raise
        return normalize_money(legacy_fallback_inr)
