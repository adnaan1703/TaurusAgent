from __future__ import annotations

from decimal import Decimal

from taurus_core.agents.base import BaseAnalystAgent, fallback_output, utc_now
from taurus_core.agents.schemas import AnalystReport
from taurus_core.db.models import CompanyEventModel, SentimentScoreModel
from taurus_core.db.repositories import IntelligenceRepository


class NewsAnalystAgent(BaseAnalystAgent):
    agent_name = "NewsAnalystAgent"

    def run(self, *, symbol: str, run_id: str) -> AnalystReport:
        symbol = symbol.upper()
        repo = IntelligenceRepository(self.session)
        events = repo.list_events(symbol=symbol, limit=10)
        scores = repo.list_sentiment_scores(
            symbol=symbol,
            event_ids=[event.event_id for event in events],
        )
        score = self._score(events, scores)
        confidence = self._confidence(events)
        source_ids = [event.event_id for event in events]
        key_points = self._key_points(symbol, events)
        risks = [
            "Mock news does not represent a live feed.",
            "Event classification is rule-based until real providers are approved.",
        ]
        context = {
            "score": str(score),
            "confidence": str(confidence),
            "horizon": "medium",
            "key_points": key_points,
            "risks": risks,
            "source_ids": source_ids,
        }
        fallback = fallback_output(
            score=score,
            confidence=confidence,
            horizon="medium",
            key_points=key_points,
            risks=risks,
            model_version="news_rule_v1",
        )
        as_of = max((event.event_time for event in events), default=utc_now())
        return self._build_report(
            symbol=symbol,
            run_id=run_id,
            as_of=as_of,
            fallback=fallback,
            context=context,
            source_ids=source_ids or ["news:none"],
        )

    def _score(
        self,
        events: list[CompanyEventModel],
        scores: list[SentimentScoreModel],
    ) -> Decimal:
        if scores:
            return (
                sum((score.event_score for score in scores), Decimal("0")) / Decimal(len(scores))
            )
        if not events:
            return Decimal("0")
        directional = []
        for event in events:
            sign = Decimal("-1") if event.event_type.startswith("regulatory") else Decimal("1")
            directional.append(sign * event.severity * event.source_confidence)
        return sum(directional, Decimal("0")) / Decimal(len(directional))

    def _confidence(self, events: list[CompanyEventModel]) -> Decimal:
        if not events:
            return Decimal("0.30")
        return sum((event.source_confidence for event in events), Decimal("0")) / Decimal(len(events))

    def _key_points(self, symbol: str, events: list[CompanyEventModel]) -> list[str]:
        if not events:
            return [f"No mock news events were available for {symbol}."]
        return [
            f"{event.event_type}: {event.headline}"
            for event in events[:3]
        ]
