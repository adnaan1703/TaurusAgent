from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.db.repositories import TaurusProfileRepository
from taurus_core.profiles.schemas import (
    TaurusProfileCreate,
    TaurusProfileResponse,
    TaurusProfileUpdate,
)

router = APIRouter(prefix="/profiles", tags=["profiles"])


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("", response_model=list[TaurusProfileResponse])
def list_profiles(
    include_archived: bool = Query(default=False),
    session: Session = Depends(get_db_session),
) -> list[TaurusProfileResponse]:
    profiles = TaurusProfileRepository(session).list_profiles(
        include_archived=include_archived
    )
    return [TaurusProfileResponse.model_validate(profile) for profile in profiles]


@router.post("", response_model=TaurusProfileResponse, status_code=201)
def create_profile(
    profile: TaurusProfileCreate,
    session: Session = Depends(get_db_session),
) -> TaurusProfileResponse:
    repo = TaurusProfileRepository(session)
    try:
        model = repo.create_profile(profile)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    session.commit()
    return TaurusProfileResponse.model_validate(model)


@router.get("/{profile_id}", response_model=TaurusProfileResponse)
def get_profile(
    profile_id: str,
    session: Session = Depends(get_db_session),
) -> TaurusProfileResponse:
    try:
        model = TaurusProfileRepository(session).get_profile(profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if model is None:
        raise HTTPException(status_code=404, detail=f"Profile {profile_id} not found.")
    return TaurusProfileResponse.model_validate(model)


@router.patch("/{profile_id}", response_model=TaurusProfileResponse)
def update_profile(
    profile_id: str,
    update: TaurusProfileUpdate,
    session: Session = Depends(get_db_session),
) -> TaurusProfileResponse:
    repo = TaurusProfileRepository(session)
    try:
        model = repo.update_profile(profile_id, update)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 422
        raise HTTPException(status_code=status_code, detail=message) from exc
    session.commit()
    return TaurusProfileResponse.model_validate(model)


@router.post("/{profile_id}/archive", response_model=TaurusProfileResponse)
def archive_profile(
    profile_id: str,
    session: Session = Depends(get_db_session),
) -> TaurusProfileResponse:
    repo = TaurusProfileRepository(session)
    try:
        model = repo.archive_profile(profile_id)
    except ValueError as exc:
        message = str(exc)
        status_code = 404 if "not found" in message.lower() else 422
        raise HTTPException(status_code=status_code, detail=message) from exc
    session.commit()
    return TaurusProfileResponse.model_validate(model)
