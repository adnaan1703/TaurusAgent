from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.db.repositories import PaperRunRepository
from taurus_core.paper_trading.schemas import PaperRun

router = APIRouter(tags=["runs"])


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/runs", response_model=list[PaperRun])
def list_runs(
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[PaperRun]:
    rows = PaperRunRepository(session).list(limit=limit)
    return [PaperRun.model_validate(row.payload) for row in rows]


@router.get("/runs/{run_id}", response_model=PaperRun)
def get_run(
    run_id: str,
    session: Session = Depends(get_db_session),
) -> PaperRun:
    row = PaperRunRepository(session).get(run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Paper run not found.")
    return PaperRun.model_validate(row.payload)
