from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal

from taurus_core.agents.base import BaseAnalystAgent, fallback_output, utc_now
from taurus_core.agents.schemas import AnalystReport
from taurus_core.db.models import FundamentalScoreModel
from taurus_core.db.repositories import CandleRepository, FundamentalsRepository, InstrumentRepository


class FundamentalsAnalystAgent(BaseAnalystAgent):
    agent_name = "FundamentalsAnalystAgent"

    def run(self, *, symbol: str, run_id: str) -> AnalystReport:
        symbol = symbol.upper()
        instrument = InstrumentRepository(self.session).get(symbol)
        display_name = instrument.name if instrument is not None else symbol
        latest_score = FundamentalsRepository(self.session).latest_score(symbol=symbol)
        if latest_score is not None:
            return self._build_imported_report(
                symbol=symbol,
                run_id=run_id,
                display_name=display_name,
                latest_score=latest_score,
            )

        key_points = [
            f"{display_name} fundamentals report is neutral until Screener import is available.",
            "No imported revenue, margin, balance sheet, or valuation snapshot is available.",
        ]
        risks = [
            "Fundamentals are mocked because no Screener import is available for this symbol.",
            "Do not treat this report as a valuation view.",
        ]
        context = {
            "score": "0",
            "confidence": "0.40",
            "horizon": "long",
            "key_points": key_points,
            "risks": risks,
            "source_ids": ["fundamentals:mock"],
        }
        fallback = fallback_output(
            score=Decimal("0"),
            confidence=Decimal("0.40"),
            horizon="long",
            key_points=key_points,
            risks=risks,
            model_version="fundamentals_mock_v1",
        )
        return self._build_report(
            symbol=symbol,
            run_id=run_id,
            as_of=self._as_of(symbol),
            fallback=fallback,
            context=context,
            source_ids=["fundamentals:mock"],
        )

    def _build_imported_report(
        self,
        *,
        symbol: str,
        run_id: str,
        display_name: str,
        latest_score: FundamentalScoreModel,
    ) -> AnalystReport:
        source_ids = [
            f"fundamental_score:{latest_score.score_id}",
            f"fundamental_import:{latest_score.import_id}",
        ]
        metric_names = sorted((latest_score.metrics or {}).keys())
        key_points = [
            (
                f"{display_name} Screener fundamentals composite score is "
                f"{latest_score.composite_score}."
            ),
            (
                "Quality, valuation, leverage, and ownership component scores are "
                f"{_component_summary(latest_score)}."
            ),
        ]
        if metric_names:
            key_points.append(f"Imported metrics include {_join_metric_names(metric_names)}.")
        risks = [
            "Screener CSV data is a point-in-time user export and must be refreshed manually.",
            "Scoring is deterministic and should be reviewed before any real-money use.",
        ]
        if latest_score.valuation_score is not None and latest_score.valuation_score < Decimal("0"):
            risks.append("Valuation component is below neutral.")
        if (
            latest_score.leverage_risk_score is not None
            and latest_score.leverage_risk_score < Decimal("0")
        ):
            risks.append("Leverage or pledged-holding component is below neutral.")

        confidence = Decimal("0.65") if len(metric_names) >= 6 else Decimal("0.55")
        context = {
            "score": str(latest_score.composite_score),
            "confidence": str(confidence),
            "horizon": "long",
            "key_points": key_points,
            "risks": risks,
            "source_ids": source_ids,
        }
        fallback = fallback_output(
            score=latest_score.composite_score,
            confidence=confidence,
            horizon="long",
            key_points=key_points,
            risks=risks,
            model_version="fundamentals_screener_v1",
        )
        return self._build_report(
            symbol=symbol,
            run_id=run_id,
            as_of=latest_score.data_available_time,
            fallback=fallback,
            context=context,
            source_ids=source_ids,
        )

    def _as_of(self, symbol: str) -> datetime:
        candles = CandleRepository(self.session).get_by_symbol_and_date_range(symbol=symbol)
        if not candles:
            return utc_now()
        as_of_date = candles[-1].trade_date + timedelta(days=1)
        return datetime.combine(as_of_date, time.min, tzinfo=timezone.utc)


def _component_summary(score: FundamentalScoreModel) -> str:
    parts = [
        ("quality", score.quality_score),
        ("valuation", score.valuation_score),
        ("leverage", score.leverage_risk_score),
        ("ownership", score.ownership_score),
    ]
    return ", ".join(f"{name}={value}" for name, value in parts if value is not None) or "unavailable"


def _join_metric_names(metric_names: list[str], *, limit: int = 6) -> str:
    visible = metric_names[:limit]
    label = ", ".join(visible)
    if len(metric_names) > limit:
        label += f", and {len(metric_names) - limit} more"
    return label
