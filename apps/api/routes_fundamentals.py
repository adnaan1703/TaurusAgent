from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.db.repositories import FundamentalsRepository

router = APIRouter(tags=["fundamentals"])


class FundamentalScoreResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    score_id: str
    import_id: str
    symbol: str
    company_name: str
    as_of: date
    data_available_time: datetime
    quality_score: Decimal | None = None
    valuation_score: Decimal | None = None
    leverage_risk_score: Decimal | None = None
    ownership_score: Decimal | None = None
    composite_score: Decimal
    metrics: dict[str, object]
    model_version: str


class FundamentalImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    import_id: str
    source: str
    source_filename: str
    source_file_hash: str
    rows_seen: int
    rows_imported: int
    rows_unmapped: int
    metrics_imported: int
    scores_imported: int
    missing_required_columns: list[str]
    missing_optional_columns: list[str]
    imported_symbols: list[str]
    status: str
    data_available_time: datetime
    imported_at: datetime


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/fundamentals", response_model=list[FundamentalScoreResponse])
def list_fundamentals(
    symbol: str | None = Query(default=None, min_length=1),
    limit: int = Query(default=100, ge=1, le=500),
    session: Session = Depends(get_db_session),
) -> list[FundamentalScoreResponse]:
    scores = FundamentalsRepository(session).list_scores(symbol=symbol, limit=limit)
    return [FundamentalScoreResponse.model_validate(score) for score in scores]


@router.get("/fundamentals/imports", response_model=list[FundamentalImportResponse])
def list_fundamental_imports(
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db_session),
) -> list[FundamentalImportResponse]:
    imports = FundamentalsRepository(session).list_imports(limit=limit)
    return [FundamentalImportResponse.model_validate(import_row) for import_row in imports]
