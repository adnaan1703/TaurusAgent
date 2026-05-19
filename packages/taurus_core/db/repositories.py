from __future__ import annotations

from datetime import date

from sqlalchemy import Select, delete, func, select
from sqlalchemy.orm import Session

from taurus_core.db.models import (
    AnalystReportModel,
    AuditLogModel,
    BacktestEquityPointModel,
    BacktestFillModel,
    BacktestOrderModel,
    BacktestPositionModel,
    BacktestRunModel,
    BacktestSignalModel,
    CompanyEventModel,
    DailyCandleModel,
    FeatureValueModel,
    InstrumentModel,
    RawDocumentModel,
    SentimentScoreModel,
)
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle
from taurus_core.intelligence.documents import NewsEvent, RawDocument, SentimentScore
from taurus_core.agents.schemas import AnalystReport


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


class IntelligenceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert_raw_document(self, document: RawDocument) -> RawDocumentModel:
        model = self.session.get(RawDocumentModel, document.document_id)
        if model is None:
            model = _raw_document_to_model(document)
            self.session.add(model)
        else:
            model.source = document.source
            model.source_url = document.source_url
            model.title = document.title
            model.body = document.body
            model.published_at = document.published_at
            model.symbols = list(document.symbols)
            model.entities = list(document.entities)
            model.checksum = document.checksum
            model.document_metadata = document.metadata
        self.session.flush()
        return model

    def upsert_event(self, event: NewsEvent) -> CompanyEventModel:
        model = self.session.get(CompanyEventModel, event.event_id)
        if model is None:
            model = _event_to_model(event)
            self.session.add(model)
        else:
            model.document_id = event.document_id
            model.symbol = event.symbol
            model.event_type = event.event_type
            model.event_time = event.event_time
            model.headline = event.headline
            model.summary = event.summary
            model.severity = event.severity
            model.horizon = event.horizon
            model.source_confidence = event.source_confidence
            model.event_metadata = event.metadata
        self.session.flush()
        return model

    def upsert_sentiment_score(self, score: SentimentScore) -> SentimentScoreModel:
        model = self.session.get(SentimentScoreModel, score.score_id)
        if model is None:
            model = _sentiment_to_model(score)
            self.session.add(model)
        else:
            model.event_id = score.event_id
            model.symbol = score.symbol
            model.as_of = score.as_of
            model.sentiment_score = score.sentiment_score
            model.event_score = score.event_score
            model.decayed_score = score.decayed_score
            model.confidence = score.confidence
            model.severity = score.severity
            model.horizon = score.horizon
            model.rationale = score.rationale
            model.model_version = score.model_version
        self.session.flush()
        return model

    def list_events(
        self,
        *,
        symbol: str | None = None,
        limit: int | None = None,
    ) -> list[CompanyEventModel]:
        statement = select(CompanyEventModel).order_by(
            CompanyEventModel.event_time.desc(),
            CompanyEventModel.event_id,
        )
        if symbol is not None:
            statement = statement.where(CompanyEventModel.symbol == symbol.upper())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_sentiment_scores(
        self,
        *,
        symbol: str | None = None,
        event_ids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[SentimentScoreModel]:
        if event_ids is not None and not event_ids:
            return []
        statement = select(SentimentScoreModel).order_by(
            SentimentScoreModel.as_of.desc(),
            SentimentScoreModel.score_id,
        )
        if symbol is not None:
            statement = statement.where(SentimentScoreModel.symbol == symbol.upper())
        if event_ids is not None:
            statement = statement.where(SentimentScoreModel.event_id.in_(event_ids))
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))


class AnalystReportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_for_run_symbol(
        self,
        *,
        run_id: str,
        symbol: str,
        reports: list[AnalystReport],
    ) -> list[AnalystReportModel]:
        self.session.execute(
            delete(AnalystReportModel).where(
                AnalystReportModel.run_id == run_id,
                AnalystReportModel.symbol == symbol.upper(),
            )
        )
        models = [_analyst_report_to_model(report) for report in reports]
        self.session.add_all(models)
        self.session.flush()
        return models

    def upsert(self, report: AnalystReport) -> AnalystReportModel:
        model = self.session.get(AnalystReportModel, report.report_id)
        if model is None:
            model = _analyst_report_to_model(report)
            self.session.add(model)
        else:
            model.run_id = report.run_id
            model.decision_id = report.decision_id
            model.symbol = report.symbol
            model.agent_name = report.agent_name
            model.as_of = report.as_of
            model.score = report.score
            model.confidence = report.confidence
            model.stance = report.stance
            model.horizon = report.horizon
            model.key_points = list(report.key_points)
            model.risks = list(report.risks)
            model.source_ids = list(report.source_ids)
            model.model_version = report.model_version
            model.payload = report.model_dump(mode="json")
        self.session.flush()
        return model

    def list(
        self,
        *,
        symbol: str | None = None,
        limit: int | None = 100,
    ) -> list[AnalystReportModel]:
        statement = select(AnalystReportModel).order_by(
            AnalystReportModel.as_of.desc(),
            AnalystReportModel.agent_name,
        )
        if symbol is not None:
            statement = statement.where(AnalystReportModel.symbol == symbol.upper())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))


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


def _raw_document_to_model(document: RawDocument) -> RawDocumentModel:
    return RawDocumentModel(
        document_id=document.document_id,
        source=document.source,
        source_url=document.source_url,
        title=document.title,
        body=document.body,
        published_at=document.published_at,
        symbols=list(document.symbols),
        entities=list(document.entities),
        checksum=document.checksum,
        document_metadata=document.metadata,
    )


def _event_to_model(event: NewsEvent) -> CompanyEventModel:
    return CompanyEventModel(
        event_id=event.event_id,
        document_id=event.document_id,
        symbol=event.symbol.upper(),
        event_type=event.event_type,
        event_time=event.event_time,
        headline=event.headline,
        summary=event.summary,
        severity=event.severity,
        horizon=event.horizon,
        source_confidence=event.source_confidence,
        event_metadata=event.metadata,
    )


def _sentiment_to_model(score: SentimentScore) -> SentimentScoreModel:
    return SentimentScoreModel(
        score_id=score.score_id,
        event_id=score.event_id,
        symbol=score.symbol.upper(),
        as_of=score.as_of,
        sentiment_score=score.sentiment_score,
        event_score=score.event_score,
        decayed_score=score.decayed_score,
        confidence=score.confidence,
        severity=score.severity,
        horizon=score.horizon,
        rationale=score.rationale,
        model_version=score.model_version,
    )


def _analyst_report_to_model(report: AnalystReport) -> AnalystReportModel:
    return AnalystReportModel(
        report_id=report.report_id,
        run_id=report.run_id,
        decision_id=report.decision_id,
        symbol=report.symbol.upper(),
        agent_name=report.agent_name,
        as_of=report.as_of,
        score=report.score,
        confidence=report.confidence,
        stance=report.stance,
        horizon=report.horizon,
        key_points=list(report.key_points),
        risks=list(report.risks),
        source_ids=list(report.source_ids),
        model_version=report.model_version,
        payload=report.model_dump(mode="json"),
    )
