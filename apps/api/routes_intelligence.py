from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.db.repositories import AnalystReportRepository, IntelligenceRepository

router = APIRouter(tags=["intelligence"])


class EventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    document_id: str
    symbol: str
    event_type: str
    event_time: datetime
    headline: str
    summary: str
    severity: Decimal
    horizon: str
    source_confidence: Decimal
    sentiment_score: Decimal | None = None
    event_score: Decimal | None = None
    decayed_score: Decimal | None = None


class AnalystReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: str
    run_id: str
    decision_id: str | None = None
    symbol: str
    agent_name: str
    as_of: datetime
    score: Decimal
    confidence: Decimal
    stance: str
    horizon: str
    key_points: list[str]
    risks: list[str]
    source_ids: list[str]
    model_version: str


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/events", response_model=list[EventResponse])
def list_events(
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[EventResponse]:
    repo = IntelligenceRepository(session)
    events = repo.list_events(symbol=symbol, limit=limit)
    score_by_event = {
        score.event_id: score
        for score in repo.list_sentiment_scores(event_ids=[event.event_id for event in events])
    }
    return [
        EventResponse(
            event_id=event.event_id,
            document_id=event.document_id,
            symbol=event.symbol,
            event_type=event.event_type,
            event_time=event.event_time,
            headline=event.headline,
            summary=event.summary,
            severity=event.severity,
            horizon=event.horizon,
            source_confidence=event.source_confidence,
            sentiment_score=score_by_event[event.event_id].sentiment_score
            if event.event_id in score_by_event
            else None,
            event_score=score_by_event[event.event_id].event_score
            if event.event_id in score_by_event
            else None,
            decayed_score=score_by_event[event.event_id].decayed_score
            if event.event_id in score_by_event
            else None,
        )
        for event in events
    ]


@router.get("/agent-reports", response_model=list[AnalystReportResponse])
def list_agent_reports(
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[AnalystReportResponse]:
    reports = AnalystReportRepository(session).list(symbol=symbol, limit=limit)
    return [AnalystReportResponse.model_validate(report) for report in reports]
