from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from taurus_core.agents.base import BaseAnalystAgent, fallback_output, utc_now
from taurus_core.agents.schemas import AnalystReport, AnalystScoreMetadata, stance_from_score
from taurus_core.db.models import BacktestSignalModel, FeatureValueModel
from taurus_core.db.repositories import CandleRepository
from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.store import (
    FeatureSnapshot,
    TECHNICAL_OHLCV_V2_FEATURE_VERSION,
    TechnicalFeatureService,
)
from taurus_core.features.technical_context import UniverseTechnicalContext
from taurus_core.features.technical_signal import (
    ANALYST_RULE_PROFILE,
    OHLCV_V2_PROFILE,
    TechnicalBacktestSignal,
    TechnicalOhlcvSignalResult,
    TechnicalSignalService,
)

SUPPORTED_TECHNICAL_ANALYST_PROFILES = {ANALYST_RULE_PROFILE, OHLCV_V2_PROFILE}
DEFAULT_TECHNICAL_RISKS = [
    "Technical signals can reverse quickly when volatility rises.",
    "Mock technical analysis is not an execution instruction.",
]


class TechnicalAnalystAgent(BaseAnalystAgent):
    agent_name = "TechnicalAnalystAgent"

    def run(
        self,
        *,
        symbol: str,
        run_id: str,
        technical_profile: str = ANALYST_RULE_PROFILE,
        feature_snapshot: FeatureSnapshot | None = None,
        universe_technical_context: UniverseTechnicalContext | None = None,
    ) -> AnalystReport:
        symbol = symbol.upper()
        profile = _normalize_technical_profile(technical_profile)
        snapshot = feature_snapshot or self._latest_feature_snapshot(
            symbol,
            technical_profile=profile,
        )
        if profile == OHLCV_V2_PROFILE:
            return self._run_ohlcv_v2(
                symbol=symbol,
                run_id=run_id,
                snapshot=snapshot,
                universe_technical_context=universe_technical_context,
            )

        return self._run_analyst_rule(symbol=symbol, run_id=run_id, snapshot=snapshot)

    def _run_analyst_rule(
        self,
        *,
        symbol: str,
        run_id: str,
        snapshot: FeatureSnapshot | None,
    ) -> AnalystReport:
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
            "risks": DEFAULT_TECHNICAL_RISKS,
            "source_ids": context_source_ids,
        }
        fallback = fallback_output(
            score=score,
            confidence=confidence,
            horizon="medium",
            key_points=key_points,
            risks=DEFAULT_TECHNICAL_RISKS,
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

    def _run_ohlcv_v2(
        self,
        *,
        symbol: str,
        run_id: str,
        snapshot: FeatureSnapshot | None,
        universe_technical_context: UniverseTechnicalContext | None,
    ) -> AnalystReport:
        latest_signal = _technical_backtest_signal(self._latest_signal(symbol))
        signal_result = TechnicalSignalService().score_ohlcv_v2(
            snapshot,
            universe_context=universe_technical_context,
            symbol=symbol,
        )
        score = signal_result.score
        confidence = signal_result.confidence
        source_ids = list(signal_result.source_ids)
        context_source_ids = [] if source_ids == ["technical:none"] else list(source_ids)
        key_points = _ohlcv_v2_key_points(
            symbol=symbol,
            signal_result=signal_result,
            latest_signal=latest_signal,
        )
        risks = _ohlcv_v2_risks(signal_result)
        technical_v2 = _technical_v2_metadata(signal_result, latest_signal)
        context = {
            "score": str(score),
            "confidence": str(confidence),
            "horizon": "medium",
            "technical_profile": signal_result.profile_name,
            "key_points": key_points,
            "risks": risks,
            "source_ids": context_source_ids,
            "technical_v2": technical_v2,
        }
        fallback = fallback_output(
            score=score,
            confidence=confidence,
            horizon="medium",
            key_points=key_points,
            risks=risks,
            model_version=signal_result.score_source,
        )
        as_of = (
            datetime.combine(snapshot.as_of_date, time.min, tzinfo=timezone.utc)
            if snapshot is not None
            else utc_now()
        )
        score_metadata = AnalystScoreMetadata(
            raw_signal_score=signal_result.raw_score,
            bounded_report_score=score,
            score_source=signal_result.score_source,
            notes=tuple(_ohlcv_v2_metadata_notes(signal_result)),
            technical_v2=technical_v2,
        )
        report = self._build_report(
            symbol=symbol,
            run_id=run_id,
            as_of=as_of,
            fallback=fallback,
            context=context,
            source_ids=source_ids,
            score_metadata=score_metadata,
        )
        return report.model_copy(
            update={
                "score": score,
                "confidence": confidence,
                "stance": stance_from_score(score),
                "model_version": signal_result.score_source,
                "score_metadata": score_metadata,
            }
        )

    def _latest_feature_snapshot(
        self,
        symbol: str,
        *,
        technical_profile: str,
    ) -> FeatureSnapshot | None:
        persisted = self._persisted_feature_snapshot(
            symbol,
            technical_profile=technical_profile,
        )
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
        feature_service = (
            TechnicalFeatureService.ohlcv_v2()
            if technical_profile == OHLCV_V2_PROFILE
            else TechnicalFeatureService()
        )
        return feature_service.build_snapshot(
            symbol=symbol,
            as_of_date=as_of_date,
            history=history,
        )

    def _persisted_feature_snapshot(
        self,
        symbol: str,
        *,
        technical_profile: str,
    ) -> FeatureSnapshot | None:
        statement = select(FeatureValueModel.snapshot_id).where(
            FeatureValueModel.symbol == symbol
        )
        if technical_profile == OHLCV_V2_PROFILE:
            statement = statement.where(
                FeatureValueModel.feature_version == TECHNICAL_OHLCV_V2_FEATURE_VERSION
            )
        snapshot_id = self.session.scalar(
            statement.order_by(
                FeatureValueModel.feature_time.desc(),
                FeatureValueModel.created_at.desc(),
            ).limit(1)
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


def _normalize_technical_profile(profile: str) -> str:
    normalized = profile.strip() if profile else ANALYST_RULE_PROFILE
    if normalized not in SUPPORTED_TECHNICAL_ANALYST_PROFILES:
        raise ValueError(f"Unsupported technical analyst profile: {normalized}")
    return normalized


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


def _ohlcv_v2_key_points(
    *,
    symbol: str,
    signal_result: TechnicalOhlcvSignalResult,
    latest_signal: TechnicalBacktestSignal | None,
) -> list[str]:
    if not signal_result.available:
        return [
            f"No technical_ohlcv_v2 feature snapshot was available for {symbol}; neutral deterministic fallback used.",
        ]
    points = [
        (
            f"technical_ohlcv_v2 composite score is {signal_result.composite_score} "
            f"with confidence {signal_result.confidence}."
        ),
        (
            f"alpha={signal_result.alpha_score}, risk={signal_result.risk_score}, "
            f"tradability={signal_result.tradability_score}."
        ),
    ]
    if not signal_result.metadata.get("universe_context_available"):
        points.append(
            "Universe technical context was unavailable; symbol-local v2 scoring lowered confidence."
        )
    elif not signal_result.metadata.get("symbol_context_available"):
        points.append(
            "Universe technical context was available but this symbol had no context row; confidence was reduced."
        )
    else:
        points.append(
            f"Universe technical context covered {signal_result.metadata.get('universe_size', 0)} symbols."
        )
    if signal_result.top_contributors:
        contributor = signal_result.top_contributors[0]
        points.append(
            "Top contributor was "
            f"{contributor.get('label')} ({contributor.get('direction')}, "
            f"contribution {contributor.get('contribution')})."
        )
    if latest_signal is not None:
        points.append(
            "Latest strategy signal was retained as audit context only and did not "
            f"override the v2 score: {latest_signal.action} {latest_signal.score}."
        )
    return points


def _ohlcv_v2_risks(signal_result: TechnicalOhlcvSignalResult) -> list[str]:
    risks = [
        "technical_ohlcv_v2 is OHLCV-only and does not yet include official market, sector, delivery, circuit, or impact-cost data.",
        "Technical signals can reverse quickly when volatility rises.",
    ]
    if not signal_result.metadata.get("universe_context_available"):
        risks.append(
            "Missing universe context makes v2 confidence lower and cross-sectional evidence unavailable."
        )
    return risks


def _ohlcv_v2_metadata_notes(signal_result: TechnicalOhlcvSignalResult) -> list[str]:
    notes = [
        "technical_ohlcv_v2 owns stored score and confidence; LLM output may change narrative only.",
    ]
    if not signal_result.metadata.get("universe_context_available"):
        notes.append("Universe technical context was unavailable; result is symbol-local.")
    if signal_result.metadata.get("symbol_context_available") is False:
        notes.append("Symbol context was unavailable for cross-sectional scoring.")
    return notes


def _technical_v2_metadata(
    signal_result: TechnicalOhlcvSignalResult,
    latest_signal: TechnicalBacktestSignal | None,
) -> dict[str, Any]:
    metadata = {
        "profile_name": signal_result.profile_name,
        "alpha_score": str(signal_result.alpha_score),
        "risk_score": str(signal_result.risk_score),
        "tradability_score": str(signal_result.tradability_score),
        "confidence": str(signal_result.confidence),
        "composite_score": str(signal_result.composite_score),
        "coverage": str(signal_result.coverage),
        "score_source": signal_result.score_source,
        "components": {key: str(value) for key, value in signal_result.components.items()},
        "top_contributors": [dict(contributor) for contributor in signal_result.top_contributors],
        "missing_features": list(signal_result.missing_features),
        "source_ids": list(signal_result.source_ids),
        "metadata": dict(signal_result.metadata),
    }
    if latest_signal is not None:
        metadata["latest_backtest_signal_audit"] = {
            "signal_id": latest_signal.signal_id,
            "action": latest_signal.action,
            "score": str(latest_signal.score),
            "score_override_applied": False,
        }
    return metadata
