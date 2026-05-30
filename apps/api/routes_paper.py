from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.config import Settings
from taurus_core.db.repositories import ExecutionRepository
from taurus_core.execution.schemas import PaperAccount, PaperFill, PaperOrder, PaperPosition

router = APIRouter(prefix="/paper", tags=["paper"])


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/orders", response_model=list[PaperOrder])
def list_paper_orders(
    request: Request,
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[PaperOrder]:
    settings: Settings = request.app.state.settings
    rows = ExecutionRepository(session).list_orders(
        portfolio_id=settings.taurus_paper_portfolio_id,
        symbol=symbol,
        limit=limit,
    )
    return [PaperOrder.model_validate(row.payload) for row in rows]


@router.get("/fills", response_model=list[PaperFill])
def list_paper_fills(
    request: Request,
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[PaperFill]:
    settings: Settings = request.app.state.settings
    rows = ExecutionRepository(session).list_fills(
        portfolio_id=settings.taurus_paper_portfolio_id,
        symbol=symbol,
        limit=limit,
    )
    return [PaperFill.model_validate(row.payload) for row in rows]


@router.get("/positions", response_model=list[PaperPosition])
def list_paper_positions(
    request: Request,
    symbol: str | None = Query(default=None, min_length=1),
    session: Session = Depends(get_db_session),
) -> list[PaperPosition]:
    settings: Settings = request.app.state.settings
    rows = ExecutionRepository(session).latest_open_positions_by_portfolio(
        portfolio_id=settings.taurus_paper_portfolio_id,
    )
    if symbol is not None:
        rows = [row for row in rows if row.symbol == symbol.upper()]
    return [PaperPosition.model_validate(row.payload) for row in rows]


@router.get("/account", response_model=PaperAccount)
def get_paper_account(
    request: Request,
    run_id: str | None = Query(default=None, min_length=1),
    session: Session = Depends(get_db_session),
) -> PaperAccount:
    settings: Settings = request.app.state.settings
    repo = ExecutionRepository(session)
    row = (
        repo.latest_account(run_id=run_id)
        if run_id is not None
        else repo.latest_account_by_portfolio(portfolio_id=settings.taurus_paper_portfolio_id)
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Paper account not found.")
    return PaperAccount.model_validate(row.payload)
