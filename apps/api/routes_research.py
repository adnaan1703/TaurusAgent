from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.db.repositories import ResearchRepository
from taurus_core.research.schemas import DebateReport, TraderProposal

router = APIRouter(tags=["research"])


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/debates", response_model=list[DebateReport])
def list_debates(
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[DebateReport]:
    debates = ResearchRepository(session).list_debates(symbol=symbol, limit=limit)
    return [DebateReport.model_validate(debate.payload) for debate in debates]


@router.get("/debates/{debate_id}", response_model=DebateReport)
def get_debate(
    debate_id: str,
    session: Session = Depends(get_db_session),
) -> DebateReport:
    debate = ResearchRepository(session).get_debate(debate_id)
    if debate is None:
        raise HTTPException(status_code=404, detail="Debate not found.")
    return DebateReport.model_validate(debate.payload)


@router.get("/trader-proposals", response_model=list[TraderProposal])
def list_trader_proposals(
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[TraderProposal]:
    proposals = ResearchRepository(session).list_trader_proposals(symbol=symbol, limit=limit)
    return [TraderProposal.model_validate(proposal.payload) for proposal in proposals]
