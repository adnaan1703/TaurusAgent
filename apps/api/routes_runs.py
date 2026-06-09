from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from apps.api.profile_context import active_profile
from apps.api.profile_context import profile_for_run
from taurus_core.config import Settings
from taurus_core.db.repositories import PaperRunRepository
from taurus_core.paper_trading.schemas import PaperRun

router = APIRouter(tags=["runs"])


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/runs", response_model=list[PaperRun])
def list_runs(
    request: Request,
    profile_id: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[PaperRun]:
    settings: Settings = request.app.state.settings
    profile = active_profile(session, settings, profile_id=profile_id)
    rows = PaperRunRepository(session).list(profile_id=profile.profile_id, limit=limit)
    return [PaperRun.model_validate(row.payload) for row in rows]


@router.get("/runs/{run_id}", response_model=PaperRun)
def get_run(
    run_id: str,
    request: Request,
    profile_id: str | None = Query(default=None, min_length=1),
    session: Session = Depends(get_db_session),
) -> PaperRun:
    row = PaperRunRepository(session).get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Paper run not found.")
    settings: Settings = request.app.state.settings
    profile_for_run(session, settings, row, profile_id=profile_id)
    return PaperRun.model_validate(row.payload)
