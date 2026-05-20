from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.replay.schemas import DecisionReplay
from taurus_core.replay.service import DecisionReplayService

router = APIRouter(tags=["replay"])


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/replay/{decision_id}", response_model=DecisionReplay)
def replay_decision(
    decision_id: str,
    session: Session = Depends(get_db_session),
) -> DecisionReplay:
    try:
        return DecisionReplayService(session).replay(decision_id=decision_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
