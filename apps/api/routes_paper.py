from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.db.repositories import ExecutionRepository
from taurus_core.execution.schemas import PaperAccount, PaperFill, PaperOrder, PaperPosition

router = APIRouter(prefix="/paper", tags=["paper"])


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/orders", response_model=list[PaperOrder])
def list_paper_orders(
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[PaperOrder]:
    rows = ExecutionRepository(session).list_orders(symbol=symbol, limit=limit)
    return [PaperOrder.model_validate(row.payload) for row in rows]


@router.get("/fills", response_model=list[PaperFill])
def list_paper_fills(
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[PaperFill]:
    rows = ExecutionRepository(session).list_fills(symbol=symbol, limit=limit)
    return [PaperFill.model_validate(row.payload) for row in rows]


@router.get("/positions", response_model=list[PaperPosition])
def list_paper_positions(
    symbol: str | None = Query(default=None, min_length=1),
    session: Session = Depends(get_db_session),
) -> list[PaperPosition]:
    rows = ExecutionRepository(session).list_positions(symbol=symbol)
    return [PaperPosition.model_validate(row.payload) for row in rows]


@router.get("/account", response_model=PaperAccount)
def get_paper_account(
    run_id: str | None = Query(default=None, min_length=1),
    session: Session = Depends(get_db_session),
) -> PaperAccount:
    row = ExecutionRepository(session).latest_account(run_id=run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Paper account not found.")
    return PaperAccount.model_validate(row.payload)
