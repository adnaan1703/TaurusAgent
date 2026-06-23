from __future__ import annotations

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy.orm import Session

from taurus_core.config import Settings
from taurus_core.db.models import PaperRunModel, TaurusProfileModel
from taurus_core.db.repositories import TaurusProfileRepository
from taurus_core.profiles.schemas import TaurusProfileResponse, validate_profile_id


def active_profile(
    session: Session,
    settings: Settings,
    *,
    profile_id: str | None,
) -> TaurusProfileModel:
    selected_profile_id = _validated_profile_id(
        profile_id or settings.effective_profile_id
    )
    model = TaurusProfileRepository(session).get_profile(selected_profile_id)
    if model is None:
        raise HTTPException(
            status_code=404, detail=f"Profile {selected_profile_id} not found."
        )
    if model.status != "ACTIVE":
        raise HTTPException(
            status_code=422, detail=f"Profile {selected_profile_id} is archived."
        )
    return model


def profile_for_run(
    session: Session,
    settings: Settings,
    run: PaperRunModel,
    *,
    profile_id: str | None,
) -> TaurusProfileModel:
    run_profile_id = _validated_profile_id(
        run.portfolio_id or settings.effective_profile_id
    )
    if profile_id is not None:
        requested = active_profile(session, settings, profile_id=profile_id)
        if requested.profile_id != run_profile_id:
            raise HTTPException(
                status_code=404, detail="Paper run not found for selected profile."
            )
        return requested

    model = TaurusProfileRepository(session).get_profile(run_profile_id)
    if model is None:
        raise HTTPException(
            status_code=404, detail=f"Profile {run_profile_id} not found."
        )
    return model


def available_profile_responses(session: Session) -> list[TaurusProfileResponse]:
    profiles = TaurusProfileRepository(session).list_profiles(include_archived=False)
    return [TaurusProfileResponse.model_validate(profile) for profile in profiles]


def profile_response(profile: TaurusProfileModel) -> TaurusProfileResponse:
    return TaurusProfileResponse.model_validate(profile)


def _validated_profile_id(profile_id: str) -> str:
    try:
        return validate_profile_id(profile_id)
    except (ValidationError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                "profile_id must be 1-64 characters using only lowercase a-z, "
                "0-9, '-', and '_'."
            ),
        ) from exc
