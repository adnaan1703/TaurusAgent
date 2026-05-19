from __future__ import annotations

from datetime import date

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from taurus_core.db.models import (
    AuditLogModel,
    BacktestEquityPointModel,
    BacktestFillModel,
    BacktestOrderModel,
    BacktestPositionModel,
    BacktestRunModel,
    BacktestSignalModel,
    DailyCandleModel,
    FeatureValueModel,
    InstrumentModel,
)
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


class BacktestRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_run(
        self,
        *,
        run: BacktestRunModel,
        feature_values: list[FeatureValueModel],
        signals: list[BacktestSignalModel],
        orders: list[BacktestOrderModel],
        fills_by_order_index: list[BacktestFillModel],
        positions: list[BacktestPositionModel],
        equity_points: list[BacktestEquityPointModel],
        audit_rows: list[AuditLogModel],
    ) -> BacktestRunModel:
        if len(orders) != len(fills_by_order_index):
            raise ValueError("Backtest orders and fills must have the same length.")

        self.delete_run(run.run_id)
        self.session.add(run)
        self.session.flush()
        self.session.add_all(feature_values)
        self.session.add_all(signals)
        self.session.add_all(orders)
        self.session.flush()

        for order, fill in zip(orders, fills_by_order_index, strict=True):
            fill.order_id = order.id
        self.session.add_all(fills_by_order_index)
        self.session.add_all(positions)
        self.session.add_all(equity_points)
        self.session.add_all(audit_rows)
        self.session.flush()
        return run

    def delete_run(self, run_id: str) -> None:
        for model in (
            BacktestFillModel,
            BacktestOrderModel,
            BacktestSignalModel,
            FeatureValueModel,
            BacktestPositionModel,
            BacktestEquityPointModel,
        ):
            self.session.execute(delete(model).where(model.run_id == run_id))
        self.session.execute(
            delete(AuditLogModel).where(
                AuditLogModel.event_type.like("backtest.%"),
                AuditLogModel.payload["run_id"].as_string() == run_id,
            )
        )
        self.session.execute(delete(BacktestRunModel).where(BacktestRunModel.run_id == run_id))

    def get_run(self, run_id: str) -> BacktestRunModel | None:
        return self.session.get(BacktestRunModel, run_id)

    def count_artifacts(self, run_id: str) -> dict[str, int]:
        models = {
            "feature_values": FeatureValueModel,
            "signals": BacktestSignalModel,
            "orders": BacktestOrderModel,
            "fills": BacktestFillModel,
            "positions": BacktestPositionModel,
            "equity_points": BacktestEquityPointModel,
        }
        return {
            name: int(
                self.session.scalar(
                    select(func.count()).select_from(model).where(model.run_id == run_id)
                )
                or 0
            )
            for name, model in models.items()
        } | {
            "audit_rows": int(
                self.session.scalar(
                    select(func.count())
                    .select_from(AuditLogModel)
                    .where(
                        AuditLogModel.event_type.like("backtest.%"),
                        AuditLogModel.payload["run_id"].as_string() == run_id,
                    )
                )
                or 0
            )
        }


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
