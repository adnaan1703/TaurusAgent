from __future__ import annotations

from datetime import date

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from taurus_core.db.models import DailyCandleModel, InstrumentModel
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle


class InstrumentRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, instrument: Instrument) -> InstrumentModel:
        model = _instrument_to_model(instrument)
        self.session.add(model)
        self.session.flush()
        return model

    def upsert(self, instrument: Instrument) -> InstrumentModel:
        symbol = instrument.symbol.upper()
        model = self.session.get(InstrumentModel, symbol)
        if model is None:
            model = _instrument_to_model(instrument)
            self.session.add(model)
        else:
            model.name = instrument.name
            model.exchange = instrument.exchange
            model.segment = instrument.segment
            model.currency = instrument.currency
            model.lot_size = instrument.lot_size
            model.tick_size = instrument.tick_size
            model.active = instrument.active
        self.session.flush()
        return model

    def list(self, *, active_only: bool = False) -> list[InstrumentModel]:
        statement: Select[tuple[InstrumentModel]] = select(InstrumentModel).order_by(
            InstrumentModel.symbol
        )
        if active_only:
            statement = statement.where(InstrumentModel.active.is_(True))
        return list(self.session.scalars(statement))

    def get(self, symbol: str) -> InstrumentModel | None:
        return self.session.get(InstrumentModel, symbol.upper())


class CandleRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def insert(self, candles: list[DailyCandle]) -> list[DailyCandleModel]:
        models = [_candle_to_model(candle) for candle in candles]
        self.session.add_all(models)
        self.session.flush()
        return models

    def upsert(self, candles: list[DailyCandle]) -> list[DailyCandleModel]:
        models: list[DailyCandleModel] = []
        for candle in candles:
            model = self._get_one(candle.symbol, candle.trade_date, candle.timeframe)
            if model is None:
                model = _candle_to_model(candle)
                self.session.add(model)
            else:
                model.open = candle.open
                model.high = candle.high
                model.low = candle.low
                model.close = candle.close
                model.volume = candle.volume
            models.append(model)
        self.session.flush()
        return models

    def list(
        self,
        *,
        symbol: str | None = None,
        timeframe: str = "1d",
        limit: int | None = None,
    ) -> list[DailyCandleModel]:
        statement = self._base_select(symbol=symbol, timeframe=timeframe)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def get_by_symbol_and_date_range(
        self,
        *,
        symbol: str,
        start_date: date | None = None,
        end_date: date | None = None,
        timeframe: str = "1d",
    ) -> list[DailyCandleModel]:
        statement = self._base_select(symbol=symbol, timeframe=timeframe)
        if start_date is not None:
            statement = statement.where(DailyCandleModel.trade_date >= start_date)
        if end_date is not None:
            statement = statement.where(DailyCandleModel.trade_date <= end_date)
        return list(self.session.scalars(statement))

    def count_by_symbol(self, *, symbol: str, timeframe: str = "1d") -> int:
        statement = (
            select(func.count())
            .select_from(DailyCandleModel)
            .where(
                DailyCandleModel.symbol == symbol.upper(),
                DailyCandleModel.timeframe == timeframe,
            )
        )
        return int(self.session.scalar(statement) or 0)

    def _get_one(
        self,
        symbol: str,
        trade_date: date,
        timeframe: str,
    ) -> DailyCandleModel | None:
        statement = select(DailyCandleModel).where(
            DailyCandleModel.symbol == symbol.upper(),
            DailyCandleModel.timeframe == timeframe,
            DailyCandleModel.trade_date == trade_date,
        )
        return self.session.scalar(statement)

    @staticmethod
    def _base_select(symbol: str | None, timeframe: str) -> Select[tuple[DailyCandleModel]]:
        statement = select(DailyCandleModel).where(DailyCandleModel.timeframe == timeframe)
        if symbol is not None:
            statement = statement.where(DailyCandleModel.symbol == symbol.upper())
        return statement.order_by(DailyCandleModel.symbol, DailyCandleModel.trade_date)


def _instrument_to_model(instrument: Instrument) -> InstrumentModel:
    return InstrumentModel(
        symbol=instrument.symbol.upper(),
        name=instrument.name,
        exchange=instrument.exchange,
        segment=instrument.segment,
        currency=instrument.currency,
        lot_size=instrument.lot_size,
        tick_size=instrument.tick_size,
        active=instrument.active,
    )


def _candle_to_model(candle: DailyCandle) -> DailyCandleModel:
    return DailyCandleModel(
        symbol=candle.symbol.upper(),
        timeframe=candle.timeframe,
        trade_date=candle.trade_date,
        open=candle.open,
        high=candle.high,
        low=candle.low,
        close=candle.close,
        volume=candle.volume,
    )
