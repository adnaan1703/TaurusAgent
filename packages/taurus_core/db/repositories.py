from __future__ import annotations

from datetime import date, datetime, time, timezone
from decimal import Decimal
from typing import Any

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
    DebateReportModel,
    FeatureValueModel,
    FinalDecisionModel,
    FundamentalImportModel,
    FundamentalScoreModel,
    FundamentalSnapshotModel,
    HalalStockComplianceModel,
    HalalStockImportModel,
    InstrumentProviderMappingModel,
    InstrumentModel,
    MarketPriceSnapshotModel,
    PaperRunModel,
    PaperAccountModel,
    PaperFillModel,
    PaperOrderModel,
    PaperPositionModel,
    RawDocumentModel,
    RiskReviewModel,
    SentimentScoreModel,
    TraderProposalModel,
)
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle, MarketPriceSnapshot
from taurus_core.intelligence.documents import NewsEvent, RawDocument, SentimentScore
from taurus_core.agents.schemas import AnalystReport
from taurus_core.research.schemas import DebateReport, TraderProposal
from taurus_core.risk.schemas import FinalDecision, RiskReview
from taurus_core.execution.schemas import PaperAccount, PaperFill, PaperOrder, PaperPosition
from taurus_core.paper_trading.schemas import PaperRun


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
                model.source = candle.source
                model.data_available_time = _candle_available_time(candle)
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


class InstrumentProviderMappingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(
        self,
        *,
        provider: str,
        symbol: str,
        exchange: str,
        provider_symbol: str,
        instrument_token: str | None,
        segment: str,
        currency: str,
        lot_size: int,
        tick_size: Decimal,
        active: bool = True,
        raw: dict[str, object] | None = None,
        synced_at: datetime | None = None,
    ) -> InstrumentProviderMappingModel:
        normalized_provider = provider.lower()
        normalized_symbol = symbol.upper()
        statement = select(InstrumentProviderMappingModel).where(
            InstrumentProviderMappingModel.provider == normalized_provider,
            InstrumentProviderMappingModel.symbol == normalized_symbol,
        )
        model = self.session.scalar(statement)
        if model is None:
            model = InstrumentProviderMappingModel(
                provider=normalized_provider,
                symbol=normalized_symbol,
                exchange=exchange.upper(),
                provider_symbol=provider_symbol,
                instrument_token=instrument_token,
                segment=segment,
                currency=currency,
                lot_size=lot_size,
                tick_size=tick_size,
                active=active,
                raw=_json_safe(raw or {}),
                synced_at=synced_at or _utc_now(),
            )
            self.session.add(model)
        else:
            model.exchange = exchange.upper()
            model.provider_symbol = provider_symbol
            model.instrument_token = instrument_token
            model.segment = segment
            model.currency = currency
            model.lot_size = lot_size
            model.tick_size = tick_size
            model.active = active
            model.raw = _json_safe(raw or {})
            model.synced_at = synced_at or _utc_now()
        self.session.flush()
        return model

    def list(self, *, provider: str | None = None, active_only: bool = False) -> list[InstrumentProviderMappingModel]:
        statement = select(InstrumentProviderMappingModel).order_by(
            InstrumentProviderMappingModel.provider,
            InstrumentProviderMappingModel.symbol,
        )
        if provider is not None:
            statement = statement.where(InstrumentProviderMappingModel.provider == provider.lower())
        if active_only:
            statement = statement.where(InstrumentProviderMappingModel.active.is_(True))
        return list(self.session.scalars(statement))

    def get(self, *, provider: str, symbol: str) -> InstrumentProviderMappingModel | None:
        statement = select(InstrumentProviderMappingModel).where(
            InstrumentProviderMappingModel.provider == provider.lower(),
            InstrumentProviderMappingModel.symbol == symbol.upper(),
        )
        return self.session.scalar(statement)


class MarketPriceSnapshotRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def insert_many(self, snapshots: list[MarketPriceSnapshot]) -> list[MarketPriceSnapshotModel]:
        models = [_snapshot_to_model(snapshot) for snapshot in snapshots]
        self.session.add_all(models)
        self.session.flush()
        return models

    def latest(
        self,
        *,
        symbol: str,
        provider: str | None = None,
    ) -> MarketPriceSnapshotModel | None:
        statement = select(MarketPriceSnapshotModel).where(
            MarketPriceSnapshotModel.symbol == symbol.upper()
        )
        if provider is not None:
            statement = statement.where(MarketPriceSnapshotModel.provider == provider.lower())
        statement = statement.order_by(
            MarketPriceSnapshotModel.fetched_at.desc(),
            MarketPriceSnapshotModel.id.desc(),
        )
        return self.session.scalar(statement.limit(1))


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

    def list_for_run_symbol(
        self,
        *,
        run_id: str,
        symbol: str,
    ) -> list[AnalystReportModel]:
        statement = (
            select(AnalystReportModel)
            .where(
                AnalystReportModel.run_id == run_id,
                AnalystReportModel.symbol == symbol.upper(),
            )
            .order_by(AnalystReportModel.agent_name)
        )
        return list(self.session.scalars(statement))


class FundamentalsRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_import(
        self,
        *,
        import_row: FundamentalImportModel,
        snapshots: list[FundamentalSnapshotModel],
        scores: list[FundamentalScoreModel],
    ) -> FundamentalImportModel:
        self.session.execute(
            delete(FundamentalScoreModel).where(
                FundamentalScoreModel.import_id == import_row.import_id
            )
        )
        self.session.execute(
            delete(FundamentalSnapshotModel).where(
                FundamentalSnapshotModel.import_id == import_row.import_id
            )
        )
        self.session.execute(
            delete(FundamentalImportModel).where(
                FundamentalImportModel.import_id == import_row.import_id
            )
        )
        self.session.add(import_row)
        self.session.flush()
        self.session.add_all(snapshots)
        self.session.add_all(scores)
        self.session.flush()
        return import_row

    def latest_score(self, *, symbol: str) -> FundamentalScoreModel | None:
        statement = (
            select(FundamentalScoreModel)
            .where(FundamentalScoreModel.symbol == symbol.upper())
            .order_by(
                FundamentalScoreModel.data_available_time.desc(),
                FundamentalScoreModel.created_at.desc(),
                FundamentalScoreModel.score_id,
            )
            .limit(1)
        )
        return self.session.scalar(statement)

    def list_scores(
        self,
        *,
        symbol: str | None = None,
        limit: int | None = 100,
    ) -> list[FundamentalScoreModel]:
        statement = select(FundamentalScoreModel).order_by(
            FundamentalScoreModel.data_available_time.desc(),
            FundamentalScoreModel.symbol,
        )
        if symbol is not None:
            statement = statement.where(FundamentalScoreModel.symbol == symbol.upper())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_snapshots(
        self,
        *,
        symbol: str | None = None,
        import_id: str | None = None,
        limit: int | None = 500,
    ) -> list[FundamentalSnapshotModel]:
        statement = select(FundamentalSnapshotModel).order_by(
            FundamentalSnapshotModel.data_available_time.desc(),
            FundamentalSnapshotModel.symbol,
            FundamentalSnapshotModel.metric_name,
        )
        if symbol is not None:
            statement = statement.where(FundamentalSnapshotModel.symbol == symbol.upper())
        if import_id is not None:
            statement = statement.where(FundamentalSnapshotModel.import_id == import_id)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_imports(self, *, limit: int | None = 50) -> list[FundamentalImportModel]:
        statement = select(FundamentalImportModel).order_by(
            FundamentalImportModel.imported_at.desc(),
            FundamentalImportModel.import_id,
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))


class HalalStockComplianceRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_import(
        self,
        *,
        import_row: HalalStockImportModel,
        rows: list[Any],
        seen_at: datetime,
    ) -> tuple[int, int]:
        self.session.execute(
            delete(HalalStockImportModel).where(
                HalalStockImportModel.import_id == import_row.import_id
            )
        )
        self.session.add(import_row)
        self.session.flush()

        seen_source_keys: set[str] = set()
        for row in rows:
            seen_source_keys.add(row.source_key)
            model = self.session.get(HalalStockComplianceModel, row.source_key)
            if model is None:
                model = HalalStockComplianceModel(
                    source_key=row.source_key,
                    name=row.name,
                    bse_code=row.bse_code,
                    nse_code=row.nse_code,
                    industry=row.industry,
                    compliance_status=row.compliance_status,
                    status_icon_url=row.status_icon_url,
                    details_url=row.details_url,
                    source_url=row.source_url,
                    active=True,
                    first_seen_at=seen_at,
                    last_seen_at=seen_at,
                    status_changed_at=seen_at,
                    raw_metadata=_json_safe(row.raw_metadata),
                )
                self.session.add(model)
            else:
                if model.compliance_status != row.compliance_status:
                    model.status_changed_at = seen_at
                model.name = row.name
                model.bse_code = row.bse_code
                model.nse_code = row.nse_code
                model.industry = row.industry
                model.compliance_status = row.compliance_status
                model.status_icon_url = row.status_icon_url
                model.details_url = row.details_url
                model.source_url = row.source_url
                model.active = True
                model.last_seen_at = seen_at
                model.raw_metadata = _json_safe(row.raw_metadata)

        inactive_count = 0
        statement = select(HalalStockComplianceModel).where(
            HalalStockComplianceModel.source_url == import_row.source_url,
            HalalStockComplianceModel.active.is_(True),
        )
        for model in self.session.scalars(statement):
            if model.source_key in seen_source_keys:
                continue
            model.active = False
            model.last_seen_at = seen_at
            inactive_count += 1

        self.session.flush()
        return len(seen_source_keys), inactive_count

    def list_active(
        self,
        *,
        compliance_status: str | None = None,
    ) -> list[HalalStockComplianceModel]:
        statement = select(HalalStockComplianceModel).where(
            HalalStockComplianceModel.active.is_(True)
        )
        if compliance_status is not None:
            statement = statement.where(
                HalalStockComplianceModel.compliance_status == compliance_status
            )
        return list(
            self.session.scalars(
                statement.order_by(
                    HalalStockComplianceModel.nse_code,
                    HalalStockComplianceModel.name,
                )
            )
        )

    def list_imports(self, *, limit: int | None = 50) -> list[HalalStockImportModel]:
        statement = select(HalalStockImportModel).order_by(
            HalalStockImportModel.imported_at.desc(),
            HalalStockImportModel.import_id,
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))


class ResearchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_debate_for_run_symbol(self, debate: DebateReport) -> DebateReportModel:
        _delete_paper_artifacts_for_run_symbol(
            self.session,
            run_id=debate.run_id,
            symbol=debate.symbol,
        )
        self.session.execute(
            delete(FinalDecisionModel).where(
                FinalDecisionModel.run_id == debate.run_id,
                FinalDecisionModel.symbol == debate.symbol.upper(),
            )
        )
        self.session.execute(
            delete(RiskReviewModel).where(
                RiskReviewModel.run_id == debate.run_id,
                RiskReviewModel.symbol == debate.symbol.upper(),
            )
        )
        self.session.execute(
            delete(TraderProposalModel).where(
                TraderProposalModel.run_id == debate.run_id,
                TraderProposalModel.symbol == debate.symbol.upper(),
            )
        )
        self.session.execute(
            delete(DebateReportModel).where(
                DebateReportModel.run_id == debate.run_id,
                DebateReportModel.symbol == debate.symbol.upper(),
            )
        )
        model = _debate_report_to_model(debate)
        self.session.add(model)
        self.session.flush()
        return model

    def replace_trader_proposal_for_run_symbol(
        self,
        proposal: TraderProposal,
    ) -> TraderProposalModel:
        _delete_paper_artifacts_for_run_symbol(
            self.session,
            run_id=proposal.run_id,
            symbol=proposal.symbol,
        )
        self.session.execute(
            delete(FinalDecisionModel).where(
                FinalDecisionModel.run_id == proposal.run_id,
                FinalDecisionModel.symbol == proposal.symbol.upper(),
            )
        )
        self.session.execute(
            delete(RiskReviewModel).where(
                RiskReviewModel.run_id == proposal.run_id,
                RiskReviewModel.symbol == proposal.symbol.upper(),
            )
        )
        self.session.execute(
            delete(TraderProposalModel).where(
                TraderProposalModel.run_id == proposal.run_id,
                TraderProposalModel.symbol == proposal.symbol.upper(),
            )
        )
        model = _trader_proposal_to_model(proposal)
        self.session.add(model)
        self.session.flush()
        return model

    def get_debate(self, debate_id: str) -> DebateReportModel | None:
        return self.session.get(DebateReportModel, debate_id)

    def latest_debate(
        self,
        *,
        run_id: str,
        symbol: str,
    ) -> DebateReportModel | None:
        statement = (
            select(DebateReportModel)
            .where(
                DebateReportModel.run_id == run_id,
                DebateReportModel.symbol == symbol.upper(),
            )
            .order_by(DebateReportModel.as_of.desc(), DebateReportModel.created_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def list_debates(
        self,
        *,
        symbol: str | None = None,
        limit: int | None = 100,
    ) -> list[DebateReportModel]:
        statement = select(DebateReportModel).order_by(
            DebateReportModel.as_of.desc(),
            DebateReportModel.debate_id,
        )
        if symbol is not None:
            statement = statement.where(DebateReportModel.symbol == symbol.upper())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_trader_proposals(
        self,
        *,
        run_id: str | None = None,
        symbol: str | None = None,
        limit: int | None = 100,
    ) -> list[TraderProposalModel]:
        statement = select(TraderProposalModel).order_by(
            TraderProposalModel.as_of.desc(),
            TraderProposalModel.proposal_id,
        )
        if run_id is not None:
            statement = statement.where(TraderProposalModel.run_id == run_id)
        if symbol is not None:
            statement = statement.where(TraderProposalModel.symbol == symbol.upper())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def latest_trader_proposal(
        self,
        *,
        run_id: str,
        symbol: str,
    ) -> TraderProposalModel | None:
        statement = (
            select(TraderProposalModel)
            .where(
                TraderProposalModel.run_id == run_id,
                TraderProposalModel.symbol == symbol.upper(),
            )
            .order_by(TraderProposalModel.as_of.desc(), TraderProposalModel.created_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)


class RiskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_risk_review_for_run_symbol(self, review: RiskReview) -> RiskReviewModel:
        _delete_paper_artifacts_for_run_symbol(
            self.session,
            run_id=review.run_id,
            symbol=review.symbol,
        )
        self.session.execute(
            delete(FinalDecisionModel).where(
                FinalDecisionModel.run_id == review.run_id,
                FinalDecisionModel.symbol == review.symbol.upper(),
            )
        )
        self.session.execute(
            delete(RiskReviewModel).where(
                RiskReviewModel.run_id == review.run_id,
                RiskReviewModel.symbol == review.symbol.upper(),
            )
        )
        model = _risk_review_to_model(review)
        self.session.add(model)
        self.session.flush()
        return model

    def replace_final_decision_for_run_symbol(self, decision: FinalDecision) -> FinalDecisionModel:
        _delete_paper_artifacts_for_run_symbol(
            self.session,
            run_id=decision.run_id,
            symbol=decision.symbol,
        )
        self.session.execute(
            delete(FinalDecisionModel).where(
                FinalDecisionModel.run_id == decision.run_id,
                FinalDecisionModel.symbol == decision.symbol.upper(),
            )
        )
        model = _final_decision_to_model(decision)
        self.session.add(model)
        self.session.flush()
        return model

    def get_risk_review(self, risk_check_id: str) -> RiskReviewModel | None:
        return self.session.get(RiskReviewModel, risk_check_id)

    def get_final_decision(self, final_decision_id: str) -> FinalDecisionModel | None:
        return self.session.get(FinalDecisionModel, final_decision_id)

    def latest_risk_review(
        self,
        *,
        run_id: str,
        symbol: str,
    ) -> RiskReviewModel | None:
        statement = (
            select(RiskReviewModel)
            .where(
                RiskReviewModel.run_id == run_id,
                RiskReviewModel.symbol == symbol.upper(),
            )
            .order_by(RiskReviewModel.as_of.desc(), RiskReviewModel.created_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def latest_final_decision(
        self,
        *,
        run_id: str,
        symbol: str,
    ) -> FinalDecisionModel | None:
        statement = (
            select(FinalDecisionModel)
            .where(
                FinalDecisionModel.run_id == run_id,
                FinalDecisionModel.symbol == symbol.upper(),
            )
            .order_by(FinalDecisionModel.as_of.desc(), FinalDecisionModel.created_at.desc())
            .limit(1)
        )
        return self.session.scalar(statement)

    def list_risk_reviews(
        self,
        *,
        run_id: str | None = None,
        symbol: str | None = None,
        limit: int | None = 100,
    ) -> list[RiskReviewModel]:
        statement = select(RiskReviewModel).order_by(
            RiskReviewModel.as_of.desc(),
            RiskReviewModel.risk_check_id,
        )
        if run_id is not None:
            statement = statement.where(RiskReviewModel.run_id == run_id)
        if symbol is not None:
            statement = statement.where(RiskReviewModel.symbol == symbol.upper())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_final_decisions(
        self,
        *,
        run_id: str | None = None,
        symbol: str | None = None,
        limit: int | None = 100,
    ) -> list[FinalDecisionModel]:
        statement = select(FinalDecisionModel).order_by(
            FinalDecisionModel.as_of.desc(),
            FinalDecisionModel.final_decision_id,
        )
        if run_id is not None:
            statement = statement.where(FinalDecisionModel.run_id == run_id)
        if symbol is not None:
            statement = statement.where(FinalDecisionModel.symbol == symbol.upper())
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))


class PaperRunRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def upsert(self, run: PaperRun) -> PaperRunModel:
        model = self.session.get(PaperRunModel, run.run_id)
        if model is None:
            model = _paper_run_to_model(run)
            self.session.add(model)
        else:
            model.schedule_name = run.schedule_name
            model.status = run.status
            model.started_at = run.started_at
            model.completed_at = run.completed_at
            model.symbols = list(run.symbols)
            model.succeeded_symbols = list(run.succeeded_symbols)
            model.failed_symbols = list(run.failed_symbols)
            model.errors = [error.model_dump(mode="json") for error in run.errors]
            model.market_data_summary = dict(run.market_data_summary)
            model.artifacts = dict(run.artifacts)
            model.timezone = run.timezone
            model.run_after_market_close = run.run_after_market_close
            model.payload = run.model_dump(mode="json")
        self.session.flush()
        return model

    def get(self, run_id: str) -> PaperRunModel | None:
        return self.session.get(PaperRunModel, run_id)

    def list(self, *, limit: int | None = 100) -> list[PaperRunModel]:
        statement = select(PaperRunModel).order_by(
            PaperRunModel.started_at.desc(),
            PaperRunModel.run_id,
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))


class ExecutionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def replace_order_execution(
        self,
        *,
        order: PaperOrder,
        fills: list[PaperFill],
        account: PaperAccount,
        positions: list[PaperPosition],
    ) -> PaperOrderModel:
        self.delete_execution_for_final_decision(order.final_decision_id)
        order_model = _paper_order_to_model(order)
        self.session.add(order_model)
        self.session.flush()
        self.session.add_all([_paper_fill_to_model(fill) for fill in fills])
        self.replace_account_state(
            run_id=order.run_id,
            account=account,
            positions=positions,
        )
        self.session.add(
            AuditLogModel(
                event_type="paper.order_executed",
                actor="PaperBroker",
                payload={
                    "order_id": order.order_id,
                    "final_decision_id": order.final_decision_id,
                    "decision_id": order.decision_id,
                    "run_id": order.run_id,
                    "symbol": order.symbol,
                    "status": order.status,
                    "filled_quantity": order.filled_quantity,
                },
                note="PaperBroker simulated execution stored.",
            )
        )
        self.session.flush()
        return order_model

    def store_rejected_order(
        self,
        *,
        order: PaperOrder,
        account: PaperAccount,
        positions: list[PaperPosition],
    ) -> PaperOrderModel:
        self.delete_execution_for_final_decision(order.final_decision_id)
        order_model = _paper_order_to_model(order)
        self.session.add(order_model)
        self.replace_account_state(
            run_id=order.run_id,
            account=account,
            positions=positions,
        )
        self.session.add(
            AuditLogModel(
                event_type="paper.order_rejected",
                actor="PaperBroker",
                payload={
                    "order_id": order.order_id,
                    "final_decision_id": order.final_decision_id,
                    "decision_id": order.decision_id,
                    "run_id": order.run_id,
                    "symbol": order.symbol,
                    "reason": order.rejection_reason,
                },
                note="PaperBroker rejected an approved paper decision.",
            )
        )
        self.session.flush()
        return order_model

    def delete_execution_for_final_decision(self, final_decision_id: str) -> None:
        self.session.execute(
            delete(PaperFillModel).where(
                PaperFillModel.final_decision_id == final_decision_id,
            )
        )
        self.session.execute(
            delete(PaperOrderModel).where(
                PaperOrderModel.final_decision_id == final_decision_id,
            )
        )
        self.session.execute(
            delete(AuditLogModel).where(
                AuditLogModel.event_type.like("paper.%"),
                AuditLogModel.payload["final_decision_id"].as_string() == final_decision_id,
            )
        )

    def replace_account_state(
        self,
        *,
        run_id: str,
        account: PaperAccount,
        positions: list[PaperPosition],
    ) -> None:
        self.session.execute(delete(PaperPositionModel).where(PaperPositionModel.run_id == run_id))
        self.session.add_all([_paper_position_to_model(position) for position in positions])

        model = self.session.get(PaperAccountModel, account.account_id)
        if model is None:
            self.session.add(_paper_account_to_model(account))
        else:
            model.run_id = account.run_id
            model.starting_cash_inr = account.starting_cash_inr
            model.available_cash_inr = account.available_cash_inr
            model.reserved_cash_inr = account.reserved_cash_inr
            model.realized_pnl_inr = account.realized_pnl_inr
            model.unrealized_pnl_inr = account.unrealized_pnl_inr
            model.gross_exposure_inr = account.gross_exposure_inr
            model.equity_inr = account.equity_inr
            model.currency = account.currency
            model.updated_at = account.updated_at
            model.payload = account.model_dump(mode="json")
        self.session.flush()

    def get_order(self, order_id: str) -> PaperOrderModel | None:
        return self.session.get(PaperOrderModel, order_id)

    def list_orders(
        self,
        *,
        run_id: str | None = None,
        symbol: str | None = None,
        decision_id: str | None = None,
        final_decision_id: str | None = None,
        limit: int | None = 100,
    ) -> list[PaperOrderModel]:
        statement = select(PaperOrderModel).order_by(
            PaperOrderModel.submitted_at.desc(),
            PaperOrderModel.order_id,
        )
        if run_id is not None:
            statement = statement.where(PaperOrderModel.run_id == run_id)
        if symbol is not None:
            statement = statement.where(PaperOrderModel.symbol == symbol.upper())
        if decision_id is not None:
            statement = statement.where(PaperOrderModel.decision_id == decision_id)
        if final_decision_id is not None:
            statement = statement.where(PaperOrderModel.final_decision_id == final_decision_id)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_fills(
        self,
        *,
        run_id: str | None = None,
        symbol: str | None = None,
        order_id: str | None = None,
        final_decision_id: str | None = None,
        limit: int | None = 100,
    ) -> list[PaperFillModel]:
        statement = select(PaperFillModel).order_by(
            PaperFillModel.filled_at.desc(),
            PaperFillModel.fill_sequence,
        )
        if run_id is not None:
            statement = statement.where(PaperFillModel.run_id == run_id)
        if symbol is not None:
            statement = statement.where(PaperFillModel.symbol == symbol.upper())
        if order_id is not None:
            statement = statement.where(PaperFillModel.order_id == order_id)
        if final_decision_id is not None:
            statement = statement.where(PaperFillModel.final_decision_id == final_decision_id)
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))

    def list_positions(
        self,
        *,
        run_id: str | None = None,
        symbol: str | None = None,
    ) -> list[PaperPositionModel]:
        statement = select(PaperPositionModel).order_by(PaperPositionModel.symbol)
        if run_id is not None:
            statement = statement.where(PaperPositionModel.run_id == run_id)
        if symbol is not None:
            statement = statement.where(PaperPositionModel.symbol == symbol.upper())
        return list(self.session.scalars(statement))

    def latest_account(self, *, run_id: str | None = None) -> PaperAccountModel | None:
        statement = select(PaperAccountModel).order_by(
            PaperAccountModel.updated_at.desc(),
            PaperAccountModel.account_id,
        )
        if run_id is not None:
            statement = statement.where(PaperAccountModel.run_id == run_id)
        return self.session.scalar(statement.limit(1))


class AuditLogRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def list_for_run_symbol(
        self,
        *,
        run_id: str,
        symbol: str,
        limit: int | None = 100,
    ) -> list[AuditLogModel]:
        normalized_symbol = symbol.upper()
        statement = (
            select(AuditLogModel)
            .where(AuditLogModel.payload["run_id"].as_string() == run_id)
            .order_by(AuditLogModel.created_at, AuditLogModel.id)
        )
        rows = list(self.session.scalars(statement))
        filtered = [
            row
            for row in rows
            if _audit_payload_matches_symbol(row.payload, normalized_symbol)
        ]
        return filtered[:limit] if limit is not None else filtered

    def list_for_decision(
        self,
        *,
        decision_id: str,
        run_id: str | None = None,
        symbol: str | None = None,
        limit: int | None = 100,
    ) -> list[AuditLogModel]:
        filters = [AuditLogModel.payload["decision_id"].as_string() == decision_id]
        if run_id is not None:
            filters.append(AuditLogModel.payload["run_id"].as_string() == run_id)
        if symbol is not None:
            filters.append(AuditLogModel.payload["symbol"].as_string() == symbol.upper())
        statement = select(AuditLogModel).where(*filters).order_by(
            AuditLogModel.created_at,
            AuditLogModel.id,
        )
        if limit is not None:
            statement = statement.limit(limit)
        return list(self.session.scalars(statement))


def _audit_payload_matches_symbol(payload: dict[str, object], symbol: str) -> bool:
    payload_symbol = payload.get("symbol")
    if payload_symbol is not None:
        return str(payload_symbol).upper() == symbol
    payload_symbols = payload.get("symbols")
    if isinstance(payload_symbols, list):
        return symbol in {str(item).upper() for item in payload_symbols}
    return True


def _delete_paper_artifacts_for_run_symbol(
    session: Session,
    *,
    run_id: str,
    symbol: str,
) -> None:
    normalized_symbol = symbol.upper()
    session.execute(
        delete(PaperFillModel).where(
            PaperFillModel.run_id == run_id,
            PaperFillModel.symbol == normalized_symbol,
        )
    )
    session.execute(
        delete(PaperOrderModel).where(
            PaperOrderModel.run_id == run_id,
            PaperOrderModel.symbol == normalized_symbol,
        )
    )
    session.execute(
        delete(PaperPositionModel).where(
            PaperPositionModel.run_id == run_id,
            PaperPositionModel.symbol == normalized_symbol,
        )
    )
    session.execute(
        delete(AuditLogModel).where(
            AuditLogModel.event_type.like("paper.%"),
            AuditLogModel.payload["run_id"].as_string() == run_id,
            AuditLogModel.payload["symbol"].as_string() == normalized_symbol,
        )
    )
    remaining_fills = int(
        session.scalar(
            select(func.count()).select_from(PaperFillModel).where(PaperFillModel.run_id == run_id)
        )
        or 0
    )
    if remaining_fills == 0:
        session.execute(delete(PaperAccountModel).where(PaperAccountModel.run_id == run_id))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_to_model(snapshot: MarketPriceSnapshot) -> MarketPriceSnapshotModel:
    return MarketPriceSnapshotModel(
        provider=snapshot.provider.lower(),
        symbol=snapshot.symbol.upper(),
        exchange=snapshot.exchange.upper(),
        provider_symbol=snapshot.provider_symbol,
        instrument_token=snapshot.instrument_token,
        last_price=snapshot.last_price,
        open=snapshot.open,
        high=snapshot.high,
        low=snapshot.low,
        close=snapshot.close,
        volume=snapshot.volume,
        fetched_at=snapshot.fetched_at,
        source=snapshot.source,
        raw=_json_safe(snapshot.raw or {}),
    )


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _paper_run_to_model(run: PaperRun) -> PaperRunModel:
    return PaperRunModel(
        run_id=run.run_id,
        schedule_name=run.schedule_name,
        status=run.status,
        started_at=run.started_at,
        completed_at=run.completed_at,
        symbols=list(run.symbols),
        succeeded_symbols=list(run.succeeded_symbols),
        failed_symbols=list(run.failed_symbols),
        errors=[error.model_dump(mode="json") for error in run.errors],
        market_data_summary=dict(run.market_data_summary),
        artifacts=dict(run.artifacts),
        timezone=run.timezone,
        run_after_market_close=run.run_after_market_close,
        payload=run.model_dump(mode="json"),
    )


def _paper_order_to_model(order: PaperOrder) -> PaperOrderModel:
    return PaperOrderModel(
        order_id=order.order_id,
        final_decision_id=order.final_decision_id,
        decision_id=order.decision_id,
        run_id=order.run_id,
        symbol=order.symbol.upper(),
        side=order.side,
        quantity=order.quantity,
        order_type=order.order_type,
        status=order.status,
        filled_quantity=order.filled_quantity,
        remaining_quantity=order.remaining_quantity,
        average_fill_price_inr=order.average_fill_price_inr,
        gross_value_inr=order.gross_value_inr,
        total_cost_inr=order.total_cost_inr,
        total_slippage_inr=order.total_slippage_inr,
        slippage_bps=order.slippage_bps,
        rejection_reason=order.rejection_reason,
        submitted_at=order.submitted_at,
        updated_at=order.updated_at,
        payload=order.model_dump(mode="json"),
    )


def _paper_fill_to_model(fill: PaperFill) -> PaperFillModel:
    return PaperFillModel(
        fill_id=fill.fill_id,
        order_id=fill.order_id,
        final_decision_id=fill.final_decision_id,
        run_id=fill.run_id,
        symbol=fill.symbol.upper(),
        trade_date=fill.trade_date,
        side=fill.side,
        quantity=fill.quantity,
        reference_price_inr=fill.reference_price_inr,
        fill_price_inr=fill.fill_price_inr,
        gross_value_inr=fill.gross_value_inr,
        brokerage_inr=fill.brokerage_inr,
        exchange_txn_charge_inr=fill.exchange_txn_charge_inr,
        tax_levy_inr=fill.tax_levy_inr,
        cost_inr=fill.cost_inr,
        slippage_bps=fill.slippage_bps,
        slippage_inr=fill.slippage_inr,
        fill_sequence=fill.fill_sequence,
        filled_at=fill.filled_at,
        payload=fill.model_dump(mode="json"),
    )


def _paper_position_to_model(position: PaperPosition) -> PaperPositionModel:
    return PaperPositionModel(
        run_id=position.run_id,
        symbol=position.symbol.upper(),
        quantity=position.quantity,
        average_cost_inr=position.average_cost_inr,
        last_price_inr=position.last_price_inr,
        market_value_inr=position.market_value_inr,
        realized_pnl_inr=position.realized_pnl_inr,
        unrealized_pnl_inr=position.unrealized_pnl_inr,
        updated_at=position.updated_at,
        payload=position.model_dump(mode="json"),
    )


def _paper_account_to_model(account: PaperAccount) -> PaperAccountModel:
    return PaperAccountModel(
        account_id=account.account_id,
        run_id=account.run_id,
        starting_cash_inr=account.starting_cash_inr,
        available_cash_inr=account.available_cash_inr,
        reserved_cash_inr=account.reserved_cash_inr,
        realized_pnl_inr=account.realized_pnl_inr,
        unrealized_pnl_inr=account.unrealized_pnl_inr,
        gross_exposure_inr=account.gross_exposure_inr,
        equity_inr=account.equity_inr,
        currency=account.currency,
        updated_at=account.updated_at,
        payload=account.model_dump(mode="json"),
    )


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
        source=candle.source,
        data_available_time=_candle_available_time(candle),
    )


def _candle_available_time(candle: DailyCandle) -> datetime:
    if candle.data_available_time is not None:
        if candle.data_available_time.tzinfo is None:
            return candle.data_available_time.replace(tzinfo=timezone.utc)
        return candle.data_available_time
    return datetime.combine(candle.trade_date, time(18, 0), tzinfo=timezone.utc)


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


def _debate_report_to_model(debate: DebateReport) -> DebateReportModel:
    return DebateReportModel(
        debate_id=debate.debate_id,
        run_id=debate.run_id,
        symbol=debate.symbol.upper(),
        as_of=debate.as_of,
        rounds_requested=debate.rounds_requested,
        consensus_label=debate.manager_summary.consensus_label,
        consensus_score=debate.manager_summary.consensus_score,
        confidence=debate.manager_summary.confidence,
        bull_thesis=debate.bull_thesis.model_dump(mode="json"),
        bear_thesis=debate.bear_thesis.model_dump(mode="json"),
        rounds=[round_.model_dump(mode="json") for round_ in debate.rounds],
        manager_summary=debate.manager_summary.model_dump(mode="json"),
        source_report_ids=list(debate.source_report_ids),
        model_version=debate.model_version,
        payload=debate.model_dump(mode="json"),
    )


def _trader_proposal_to_model(proposal: TraderProposal) -> TraderProposalModel:
    return TraderProposalModel(
        proposal_id=proposal.proposal_id,
        run_id=proposal.run_id,
        symbol=proposal.symbol.upper(),
        debate_id=proposal.debate_id,
        as_of=proposal.as_of,
        action=proposal.action,
        confidence=proposal.confidence,
        horizon=proposal.horizon,
        requested_position_pct_nav=proposal.requested_position_pct_nav,
        order_type=proposal.order_type,
        entry_rule=proposal.entry_rule,
        stop_loss_pct=proposal.stop_loss_pct,
        take_profit_pct=proposal.take_profit_pct,
        reason_summary=proposal.reason_summary,
        invalid_if=list(proposal.invalid_if),
        source_report_ids=list(proposal.source_report_ids),
        is_order=proposal.is_order,
        requires_risk_approval=proposal.requires_risk_approval,
        model_version=proposal.model_version,
        payload=proposal.model_dump(mode="json"),
    )


def _risk_review_to_model(review: RiskReview) -> RiskReviewModel:
    return RiskReviewModel(
        risk_check_id=review.risk_check_id,
        decision_id=review.decision_id,
        run_id=review.run_id,
        symbol=review.symbol.upper(),
        proposal_id=review.proposal_id,
        debate_id=review.debate_id,
        as_of=review.as_of,
        status=review.status,
        requested_position_pct_nav=review.requested_position_pct_nav,
        approved_position_pct_nav=review.approved_position_pct_nav,
        hard_rule_results=[result.model_dump(mode="json") for result in review.hard_rule_results],
        persona_reviews=[persona.model_dump(mode="json") for persona in review.persona_reviews],
        risk_committee_summary=review.risk_committee_summary,
        source_report_ids=list(review.source_report_ids),
        is_order=review.is_order,
        can_send_to_broker=review.can_send_to_broker,
        model_version=review.model_version,
        payload=review.model_dump(mode="json"),
    )


def _final_decision_to_model(decision: FinalDecision) -> FinalDecisionModel:
    return FinalDecisionModel(
        final_decision_id=decision.final_decision_id,
        decision_id=decision.decision_id,
        run_id=decision.run_id,
        symbol=decision.symbol.upper(),
        proposal_id=decision.proposal_id,
        risk_check_id=decision.risk_check_id,
        as_of=decision.as_of,
        final_action=decision.final_action,
        status=decision.status,
        approved_quantity=decision.approved_quantity,
        approved_position_pct_nav=decision.approved_position_pct_nav,
        reason=decision.reason,
        is_order=decision.is_order,
        can_send_to_broker=decision.can_send_to_broker,
        model_version=decision.model_version,
        payload=decision.model_dump(mode="json"),
    )
