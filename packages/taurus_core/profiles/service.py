from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.db.models import TaurusProfileModel
from taurus_core.db.repositories import TaurusProfileRepository
from taurus_core.profiles.schemas import TaurusProfileCreate


def ensure_default_profile(session: Session) -> TaurusProfileModel:
    return TaurusProfileRepository(session).ensure_default_profile()


def get_profile(session: Session, profile_id: str) -> TaurusProfileModel | None:
    return TaurusProfileRepository(session).get_profile(profile_id)


def list_profiles(
    session: Session,
    *,
    include_archived: bool = False,
) -> list[TaurusProfileModel]:
    return TaurusProfileRepository(session).list_profiles(include_archived=include_archived)


def create_profile(session: Session, profile: TaurusProfileCreate) -> TaurusProfileModel:
    return TaurusProfileRepository(session).create_profile(profile)


def archive_profile(session: Session, profile_id: str) -> TaurusProfileModel:
    return TaurusProfileRepository(session).archive_profile(profile_id)


def update_profile_corpus(
    session: Session,
    profile_id: str,
    starting_corpus_inr: Decimal | int | str,
) -> TaurusProfileModel:
    return TaurusProfileRepository(session).update_profile_corpus(
        profile_id,
        starting_corpus_inr,
    )

