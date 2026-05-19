from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.db.repositories import RiskRepository
from taurus_core.risk.schemas import FinalDecision, RiskReview

router = APIRouter(tags=["risk"])


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/risk-checks", response_model=list[RiskReview])
@router.get("/risk-reviews", response_model=list[RiskReview])
def list_risk_reviews(
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[RiskReview]:
    reviews = RiskRepository(session).list_risk_reviews(symbol=symbol, limit=limit)
    return [RiskReview.model_validate(review.payload) for review in reviews]


@router.get("/risk-checks/{risk_check_id}", response_model=RiskReview)
@router.get("/risk-reviews/{risk_check_id}", response_model=RiskReview)
def get_risk_review(
    risk_check_id: str,
    session: Session = Depends(get_db_session),
) -> RiskReview:
    review = RiskRepository(session).get_risk_review(risk_check_id)
    if review is None:
        raise HTTPException(status_code=404, detail="Risk review not found.")
    return RiskReview.model_validate(review.payload)


@router.get("/final-decisions", response_model=list[FinalDecision])
def list_final_decisions(
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[FinalDecision]:
    decisions = RiskRepository(session).list_final_decisions(symbol=symbol, limit=limit)
    return [FinalDecision.model_validate(decision.payload) for decision in decisions]


@router.get("/final-decisions/{final_decision_id}", response_model=FinalDecision)
def get_final_decision(
    final_decision_id: str,
    session: Session = Depends(get_db_session),
) -> FinalDecision:
    decision = RiskRepository(session).get_final_decision(final_decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="Final decision not found.")
    return FinalDecision.model_validate(decision.payload)
