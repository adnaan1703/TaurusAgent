from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.db.repositories import (
    CandleRepository,
    InstrumentRepository,
    MarketPriceSnapshotRepository,
)

router = APIRouter(prefix="/data", tags=["data"])


class InstrumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    name: str
    exchange: str
    segment: str
    currency: str
    lot_size: int
    tick_size: Decimal
    active: bool


class CandleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    timeframe: str
    trade_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source: str
    data_available_time: datetime


class MarketPriceSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    symbol: str
    provider: str
    exchange: str
    provider_symbol: str
    instrument_token: str | None
    last_price: Decimal
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int | None
    fetched_at: datetime
    source: str


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.get("/instruments", response_model=list[InstrumentResponse])
def list_instruments(session: Session = Depends(get_db_session)) -> list[InstrumentResponse]:
    instruments = InstrumentRepository(session).list(active_only=True)
    return [InstrumentResponse.model_validate(instrument) for instrument in instruments]


@router.get("/instruments/{symbol}", response_model=InstrumentResponse)
def get_instrument(symbol: str, session: Session = Depends(get_db_session)) -> InstrumentResponse:
    instrument = InstrumentRepository(session).get(symbol)
    if instrument is None:
        raise HTTPException(status_code=404, detail=f"Instrument {symbol.upper()} not found")
    return InstrumentResponse.model_validate(instrument)


@router.get("/candles", response_model=list[CandleResponse])
def list_candles(
    symbol: str = Query(..., min_length=1),
    timeframe: Literal["1d"] = "1d",
    start_date: date | None = None,
    end_date: date | None = None,
    session: Session = Depends(get_db_session),
) -> list[CandleResponse]:
    instrument_repo = InstrumentRepository(session)
    if instrument_repo.get(symbol) is None:
        raise HTTPException(status_code=404, detail=f"Instrument {symbol.upper()} not found")

    candles = CandleRepository(session).get_by_symbol_and_date_range(
        symbol=symbol,
        timeframe=timeframe,
        start_date=start_date,
        end_date=end_date,
    )
    return [CandleResponse.model_validate(candle) for candle in candles]


@router.get("/quotes/latest", response_model=MarketPriceSnapshotResponse)
def latest_quote(
    symbol: str = Query(..., min_length=1),
    session: Session = Depends(get_db_session),
) -> MarketPriceSnapshotResponse:
    snapshot = MarketPriceSnapshotRepository(session).latest(symbol=symbol)
    if snapshot is None:
        raise HTTPException(
            status_code=404,
            detail=f"Latest quote snapshot for {symbol.upper()} not found",
        )
    return MarketPriceSnapshotResponse.model_validate(snapshot)
