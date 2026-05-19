from __future__ import annotations

import math
from datetime import datetime, timezone
from decimal import Decimal
from typing import Iterable

from taurus_core.intelligence.documents import NewsEvent, RawDocument, SentimentScore, stable_id

SCORE_QUANT = Decimal("0.0001")

EVENT_SENTIMENT: dict[str, Decimal] = {
    "earnings_beat": Decimal("0.65"),
    "guidance_raise": Decimal("0.58"),
    "large_deal": Decimal("0.50"),
    "order_win": Decimal("0.48"),
    "asset_quality_improvement": Decimal("0.43"),
    "tariff_hike": Decimal("0.36"),
    "capacity_expansion": Decimal("0.30"),
    "analyst_upgrade": Decimal("0.32"),
    "neutral_filing": Decimal("0.00"),
    "management_change": Decimal("-0.10"),
    "demand_softness": Decimal("-0.34"),
    "margin_pressure": Decimal("-0.42"),
    "regulatory_observation": Decimal("-0.58"),
    "regulatory_probe": Decimal("-0.72"),
}

HORIZON_DECAY_DAYS: dict[str, Decimal] = {
    "intraday": Decimal("1"),
    "short": Decimal("7"),
    "medium": Decimal("30"),
    "long": Decimal("90"),
}


def event_from_document(document: RawDocument, symbol: str) -> NewsEvent:
    event_type = str(document.metadata.get("event_type") or infer_event_type(document))
    severity = _decimal_metadata(document, "severity", Decimal("0.30"))
    horizon = str(document.metadata.get("horizon") or "short")
    source_confidence = _decimal_metadata(
        document,
        "source_confidence",
        Decimal("0.70"),
    )
    return NewsEvent(
        event_id=stable_id("evt", document.document_id, symbol.upper(), event_type),
        document_id=document.document_id,
        symbol=symbol,
        event_type=event_type,
        event_time=document.published_at,
        headline=document.title,
        summary=document.body,
        severity=severity,
        horizon=horizon,  # type: ignore[arg-type]
        source_confidence=source_confidence,
        metadata={
            "source": document.source,
            "source_url": document.source_url,
            "resolver": "entity_resolver_v1",
        },
    )


def infer_event_type(document: RawDocument) -> str:
    text = f"{document.title} {document.body}".lower()
    if "regulator" in text or "probe" in text:
        return "regulatory_observation"
    if "margin pressure" in text:
        return "margin_pressure"
    if "order" in text:
        return "order_win"
    if "contract" in text or "deal" in text:
        return "large_deal"
    if "asset quality" in text:
        return "asset_quality_improvement"
    if "demand softness" in text:
        return "demand_softness"
    return "neutral_filing"


def score_event(event: NewsEvent, *, as_of: datetime | None = None) -> SentimentScore:
    as_of = as_of or event.event_time
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    base_sentiment = EVENT_SENTIMENT.get(event.event_type, Decimal("0"))
    severity_weight = Decimal("0.50") + (event.severity * Decimal("0.50"))
    raw_event_score = base_sentiment * severity_weight * event.source_confidence
    event_score = _clamp(raw_event_score, Decimal("-1"), Decimal("1")).quantize(SCORE_QUANT)
    decayed_score = (event_score * _decay_factor(event, as_of)).quantize(SCORE_QUANT)
    confidence = _clamp(
        (event.source_confidence * Decimal("0.70")) + (event.severity * Decimal("0.30")),
        Decimal("0"),
        Decimal("1"),
    ).quantize(SCORE_QUANT)
    return SentimentScore(
        score_id=stable_id("sent", event.event_id, "event_scoring_v1"),
        event_id=event.event_id,
        symbol=event.symbol,
        as_of=as_of,
        sentiment_score=base_sentiment.quantize(SCORE_QUANT),
        event_score=event_score,
        decayed_score=decayed_score,
        confidence=confidence,
        severity=event.severity.quantize(SCORE_QUANT),
        horizon=event.horizon,
        rationale=(
            f"{event.event_type} scored with severity={event.severity}, "
            f"horizon={event.horizon}, source_confidence={event.source_confidence}"
        ),
    )


def aggregate_decayed_scores(scores: Iterable[SentimentScore]) -> Decimal:
    weighted_total = Decimal("0")
    confidence_total = Decimal("0")
    for score in scores:
        weighted_total += score.decayed_score * score.confidence
        confidence_total += score.confidence
    if confidence_total == 0:
        return Decimal("0")
    return (weighted_total / confidence_total).quantize(SCORE_QUANT)


def _decay_factor(event: NewsEvent, as_of: datetime) -> Decimal:
    age_seconds = max(0.0, (as_of - event.event_time).total_seconds())
    age_days = age_seconds / 86_400
    decay_days = float(HORIZON_DECAY_DAYS.get(event.horizon, Decimal("7")))
    return Decimal(f"{math.exp(-age_days / decay_days):.8f}")


def _decimal_metadata(document: RawDocument, key: str, default: Decimal) -> Decimal:
    value = document.metadata.get(key)
    if value is None:
        return default
    return Decimal(str(value))


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(high, value))
