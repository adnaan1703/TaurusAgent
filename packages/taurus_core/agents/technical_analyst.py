from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select

from taurus_core.agents.base import BaseAnalystAgent, fallback_output, utc_now
from taurus_core.agents.schemas import AnalystReport
from taurus_core.db.models import BacktestSignalModel, FeatureValueModel
from taurus_core.db.repositories import CandleRepository
from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.store import FeatureSnapshot, TechnicalFeatureService


class TechnicalAnalystAgent(BaseAnalystAgent):
    agent_name = "TechnicalAnalystAgent"

    def run(self, *, symbol: str, run_id: str) -> AnalystReport:
        symbol = symbol.upper()
        snapshot = self._latest_feature_snapshot(symbol)
        latest_signal = self._latest_signal(symbol)
        values = snapshot.values if snapshot is not None else {}
        score = self._score(values, latest_signal)
        source_ids: list[str] = []
        if snapshot is not None:
            source_ids.append(snapshot.snapshot_id)
        if latest_signal is not None:
            source_ids.append(f"signal:{latest_signal.id}")

        key_points = self._key_points(symbol, values, latest_signal)
        context = {
            "score": str(score),
            "confidence": "0.68" if values else "0.35",
            "horizon": "medium",
            "key_points": key_points,
            "risks": [
                "Technical signals can reverse quickly when volatility rises.",
                "Mock technical analysis is not an execution instruction.",
            ],
            "source_ids": source_ids,
        }
        fallback = fallback_output(
            score=score,
            confidence=Decimal("0.68") if values else Decimal("0.35"),
            horizon="medium",
            key_points=key_points,
            risks=[
                "Technical signals can reverse quickly when volatility rises.",
                "Mock technical analysis is not an execution instruction.",
            ],
            model_version="technical_rule_v1",
        )
        as_of = (
            datetime.combine(snapshot.as_of_date, time.min, tzinfo=timezone.utc)
            if snapshot is not None
            else utc_now()
        )
        return self._build_report(
            symbol=symbol,
            run_id=run_id,
            as_of=as_of,
            fallback=fallback,
            context=context,
            source_ids=source_ids or ["technical:none"],
        )

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

    def _score(
        self,
        values: dict[str, Decimal],
        latest_signal: BacktestSignalModel | None,
    ) -> Decimal:
        if latest_signal is not None:
            signed = latest_signal.score if latest_signal.action == "BUY" else -latest_signal.score
            return max(Decimal("-1"), min(Decimal("1"), signed))

        return_20d = values.get("return_20d", Decimal("0"))
        return_5d = values.get("return_5d", Decimal("0"))
        ema_12 = values.get("ema_12")
        ema_26 = values.get("ema_26")
        rsi = values.get("rsi_14", Decimal("50"))
        volatility = values.get("volatility_20", Decimal("0"))
        ema_trend = Decimal("0")
        if ema_12 is not None and ema_26 not in (None, Decimal("0")):
            ema_trend = (ema_12 / ema_26) - Decimal("1")
        score = (
            (return_20d * Decimal("1.8"))
            + (return_5d * Decimal("0.8"))
            + (ema_trend * Decimal("1.2"))
            + (((rsi - Decimal("50")) / Decimal("50")) * Decimal("0.30"))
            - (volatility * Decimal("0.75"))
        )
        return max(Decimal("-1"), min(Decimal("1"), score))

    def _key_points(
        self,
        symbol: str,
        values: dict[str, Decimal],
        latest_signal: BacktestSignalModel | None,
    ) -> list[str]:
        points: list[str] = []
        if latest_signal is not None:
            points.append(
                f"Latest strategy signal for {symbol} was {latest_signal.action} with score {latest_signal.score}."
            )
        if "return_20d" in values:
            points.append(f"20-day return feature is {values['return_20d']}.")
        if "rsi_14" in values:
            points.append(f"RSI-14 feature is {values['rsi_14']}.")
        if "volatility_20" in values:
            points.append(f"20-day volatility feature is {values['volatility_20']}.")
        return points or [f"No persisted technical features were available for {symbol}; neutral fallback used."]
