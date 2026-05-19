from __future__ import annotations

from decimal import Decimal

from taurus_core.agents.base import BaseAnalystAgent, fallback_output, utc_now
from taurus_core.agents.schemas import AnalystReport
from taurus_core.db.repositories import InstrumentRepository


class FundamentalsAnalystAgent(BaseAnalystAgent):
    agent_name = "FundamentalsAnalystAgent"

    def run(self, *, symbol: str, run_id: str) -> AnalystReport:
        symbol = symbol.upper()
        instrument = InstrumentRepository(self.session).get(symbol)
        display_name = instrument.name if instrument is not None else symbol
        key_points = [
            f"{display_name} fundamentals report is neutral until Screener import is available.",
            "No revenue, margin, balance sheet, or valuation feed is connected in M4.",
        ]
        risks = [
            "Fundamentals are mocked in M4.",
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
            as_of=utc_now(),
            fallback=fallback,
            context=context,
            source_ids=["fundamentals:mock"],
        )
