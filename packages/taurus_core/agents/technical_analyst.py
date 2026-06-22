from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from taurus_core.agents.base import BaseAnalystAgent, fallback_output, utc_now
from taurus_core.agents.schemas import AnalystReport, AnalystScoreMetadata
from taurus_core.db.models import BacktestSignalModel, FeatureValueModel
from taurus_core.db.repositories import CandleRepository
from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.store import FeatureSnapshot, TechnicalFeatureService
from taurus_core.features.technical_signal import (
    TechnicalBacktestSignal,
    TechnicalSignalService,
)


class TechnicalAnalystAgent(BaseAnalystAgent):
    agent_name = "TechnicalAnalystAgent"

    def run(self, *, symbol: str, run_id: str) -> AnalystReport:
        symbol = symbol.upper()
        snapshot = self._latest_feature_snapshot(symbol)
        latest_signal = _technical_backtest_signal(self._latest_signal(symbol))
        signal_result = TechnicalSignalService().score_analyst_rule(
            snapshot,
            latest_signal,
            symbol=symbol,
        )
        if (
            signal_result.raw_score is None
            or signal_result.score is None
            or signal_result.confidence is None
        ):
            raise RuntimeError("Technical analyst rule result must include score fields.")
        raw_score = signal_result.raw_score
        score = signal_result.score
        confidence = signal_result.confidence
        source_ids = list(signal_result.source_ids)
        context_source_ids = (
            [] if source_ids == ["technical:none"] else list(signal_result.source_ids)
        )
        key_points = list(signal_result.key_points)
        context = {
            "score": str(score),
            "confidence": str(confidence.quantize(Decimal("0.01"))),
            "horizon": "medium",
            "key_points": key_points,
            "risks": [
                "Technical signals can reverse quickly when volatility rises.",
                "Mock technical analysis is not an execution instruction.",
            ],
            "source_ids": context_source_ids,
        }
        fallback = fallback_output(
            score=score,
            confidence=confidence,
            horizon="medium",
            key_points=key_points,
            risks=[
                "Technical signals can reverse quickly when volatility rises.",
                "Mock technical analysis is not an execution instruction.",
            ],
            model_version=signal_result.score_source,
        )
        as_of = (
            datetime.combine(snapshot.as_of_date, time.min, tzinfo=timezone.utc)
            if snapshot is not None
            else utc_now()
        )
        report = self._build_report(
            symbol=symbol,
            run_id=run_id,
            as_of=as_of,
            fallback=fallback,
            context=context,
            source_ids=source_ids,
            score_metadata=AnalystScoreMetadata(
                raw_signal_score=raw_score,
                bounded_report_score=score,
                score_source=signal_result.score_source,
                notes=(
                    "Raw technical rule score is stored before bounded analyst report clamping.",
                ),
            ),
        )
        return report.model_copy(update={"model_version": signal_result.score_source})

    def _latest_feature_snapshot(self, symbol: str) -> FeatureSnapshot | None:
        persisted = self._persisted_feature_snapshot(symbol)
        if persisted is not None:
            return persisted
        candles = CandleRepository(self.session).get_by_symbol_and_date_range(symbol=symbol)
        if not candles:
            return None
        history = [
            DailyCandle(
                symbol=candle.symbol,
                trade_date=candle.trade_date,
                open=candle.open,
                high=candle.high,
                low=candle.low,
                close=candle.close,
                volume=candle.volume,
                source=candle.source,
                timeframe=candle.timeframe,
            )
            for candle in candles
        ]
        as_of_date = history[-1].trade_date + timedelta(days=1)
        return TechnicalFeatureService().build_snapshot(
            symbol=symbol,
            as_of_date=as_of_date,
            history=history,
        )

    def _persisted_feature_snapshot(self, symbol: str) -> FeatureSnapshot | None:
        snapshot_id = self.session.scalar(
            select(FeatureValueModel.snapshot_id)
            .where(FeatureValueModel.symbol == symbol)
            .order_by(FeatureValueModel.feature_time.desc(), FeatureValueModel.created_at.desc())
            .limit(1)
        )
        if snapshot_id is None:
            return None
        rows = list(
            self.session.scalars(
                select(FeatureValueModel)
                .where(FeatureValueModel.snapshot_id == snapshot_id)
                .order_by(FeatureValueModel.feature_name)
            )
        )
        if not rows:
            return None
        values = {row.feature_name: row.feature_value for row in rows}
        first = rows[0]
        return FeatureSnapshot(
            snapshot_id=snapshot_id,
            symbol=symbol,
            as_of_date=first.data_available_time.date(),
            feature_time=first.feature_time,
            values=values,
            rows=tuple(),
        )

    def _latest_signal(self, symbol: str) -> BacktestSignalModel | None:
        return self.session.scalar(
            select(BacktestSignalModel)
            .where(BacktestSignalModel.symbol == symbol)
            .order_by(BacktestSignalModel.trade_date.desc(), BacktestSignalModel.id.desc())
            .limit(1)
        )


def _technical_backtest_signal(
    signal: BacktestSignalModel | None,
) -> TechnicalBacktestSignal | None:
    if signal is None:
        return None
    return TechnicalBacktestSignal(
        signal_id=signal.id,
        action=signal.action,
        score=signal.score,
    )
