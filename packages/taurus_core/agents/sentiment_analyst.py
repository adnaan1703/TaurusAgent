from __future__ import annotations

from decimal import Decimal

from taurus_core.agents.base import BaseAnalystAgent, fallback_output, utc_now
from taurus_core.agents.schemas import AnalystReport
from taurus_core.db.models import SentimentScoreModel
from taurus_core.db.repositories import IntelligenceRepository


class SentimentAnalystAgent(BaseAnalystAgent):
    agent_name = "SentimentAnalystAgent"

    def run(self, *, symbol: str, run_id: str) -> AnalystReport:
        symbol = symbol.upper()
        scores = IntelligenceRepository(self.session).list_sentiment_scores(
            symbol=symbol,
            limit=20,
        )
        aggregate_score = self._aggregate(scores)
        confidence = self._confidence(scores)
        source_ids = [score.score_id for score in scores]
        key_points = self._key_points(symbol, scores, aggregate_score)
        risks = [
            "Sentiment is based on deterministic mock events, not real-time market news.",
            "Time decay reduces stale events but does not model second-order market impact.",
        ]
        context = {
            "score": str(aggregate_score),
            "confidence": str(confidence),
            "horizon": "short",
            "key_points": key_points,
            "risks": risks,
            "source_ids": source_ids,
        }
        fallback = fallback_output(
            score=aggregate_score,
            confidence=confidence,
            horizon="short",
            key_points=key_points,
            risks=risks,
            model_version="sentiment_rule_v1",
        )
        as_of = max((score.as_of for score in scores), default=utc_now())
        return self._build_report(
            symbol=symbol,
            run_id=run_id,
            as_of=as_of,
            fallback=fallback,
            context=context,
            source_ids=source_ids or ["sentiment:none"],
        )

    def _aggregate(self, scores: list[SentimentScoreModel]) -> Decimal:
        weighted_total = Decimal("0")
        confidence_total = Decimal("0")
        for score in scores:
            weighted_total += score.decayed_score * score.confidence
            confidence_total += score.confidence
        if confidence_total == 0:
            return Decimal("0")
        return weighted_total / confidence_total

    def _confidence(self, scores: list[SentimentScoreModel]) -> Decimal:
        if not scores:
            return Decimal("0.30")
        return min(
            Decimal("0.90"),
            sum((score.confidence for score in scores), Decimal("0")) / Decimal(len(scores)),
        )

    def _key_points(
        self,
        symbol: str,
        scores: list[SentimentScoreModel],
        aggregate_score: Decimal,
    ) -> list[str]:
        if not scores:
            return [f"No stored sentiment scores were available for {symbol}."]
        return [
            f"Aggregate time-decayed sentiment score is {aggregate_score}.",
            f"Most recent event score is {scores[0].event_score} with decay to {scores[0].decayed_score}.",
        ]
