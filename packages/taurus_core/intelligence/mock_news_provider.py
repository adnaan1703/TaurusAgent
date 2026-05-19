from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from taurus_core.intelligence.documents import (
    NewsEvent,
    RawDocument,
    document_checksum,
    stable_id,
)


@dataclass(frozen=True, slots=True)
class MockNewsSpec:
    source: str
    title: str
    body: str
    published_at: datetime
    symbols: tuple[str, ...]
    entities: tuple[str, ...]
    event_type: str
    severity: Decimal
    horizon: str
    source_confidence: Decimal


class MockNewsProvider:
    """Deterministic in-memory news source for mock-mode Taurus runs."""

    def __init__(self) -> None:
        self._documents = [_document_from_spec(spec) for spec in MOCK_NEWS_SPECS]

    def list_documents(self) -> list[RawDocument]:
        return list(self._documents)

    def list_events(self) -> list[NewsEvent]:
        events: list[NewsEvent] = []
        for document in self._documents:
            event_type = str(document.metadata["event_type"])
            for symbol in document.symbols:
                events.append(
                    NewsEvent(
                        event_id=stable_id("evt", document.document_id, symbol, event_type),
                        document_id=document.document_id,
                        symbol=symbol,
                        event_type=event_type,
                        event_time=document.published_at,
                        headline=document.title,
                        summary=document.body,
                        severity=Decimal(str(document.metadata["severity"])),
                        horizon=str(document.metadata["horizon"]),  # type: ignore[arg-type]
                        source_confidence=Decimal(str(document.metadata["source_confidence"])),
                        metadata={
                            "source": document.source,
                            "source_url": document.source_url,
                            "provider": "mock_news",
                        },
                    )
                )
        return events


def _utc(year: int, month: int, day: int, hour: int) -> datetime:
    return datetime(year, month, day, hour, 0, tzinfo=timezone.utc)


MOCK_NEWS_SPECS: tuple[MockNewsSpec, ...] = (
    MockNewsSpec(
        source="taurus_mock_wire",
        title="Infosys wins a multi-year cloud transformation contract",
        body=(
            "Infosys Ltd announced a multi-year cloud transformation contract with a "
            "global manufacturing client. Management said the deal supports digital "
            "services revenue visibility over the next several quarters."
        ),
        published_at=_utc(2024, 12, 16, 9),
        symbols=("INFY",),
        entities=("Infosys Ltd", "Infosys"),
        event_type="large_deal",
        severity=Decimal("0.70"),
        horizon="medium",
        source_confidence=Decimal("0.92"),
    ),
    MockNewsSpec(
        source="taurus_mock_wire",
        title="TCS flags short-term margin pressure from wage costs",
        body=(
            "Tata Consultancy Services Ltd said wage revisions and transition costs "
            "could pressure operating margins in the near term while demand remains stable."
        ),
        published_at=_utc(2024, 12, 16, 10),
        symbols=("TCS",),
        entities=("Tata Consultancy Services Ltd", "TCS"),
        event_type="margin_pressure",
        severity=Decimal("0.46"),
        horizon="short",
        source_confidence=Decimal("0.88"),
    ),
    MockNewsSpec(
        source="taurus_mock_wire",
        title="Reliance Industries commissions new energy pilot capacity",
        body=(
            "Reliance Industries Ltd commissioned pilot capacity in its new energy "
            "business and reiterated phased capital allocation discipline."
        ),
        published_at=_utc(2024, 12, 13, 11),
        symbols=("RELIANCE",),
        entities=("Reliance Industries Ltd", "Reliance"),
        event_type="capacity_expansion",
        severity=Decimal("0.38"),
        horizon="long",
        source_confidence=Decimal("0.86"),
    ),
    MockNewsSpec(
        source="taurus_mock_wire",
        title="HDFC Bank receives regulator observations on digital onboarding",
        body=(
            "HDFC Bank Ltd received regulator observations related to a digital "
            "onboarding process and said it has begun remediation steps."
        ),
        published_at=_utc(2024, 12, 12, 15),
        symbols=("HDFCBANK",),
        entities=("HDFC Bank Ltd", "HDFC Bank"),
        event_type="regulatory_observation",
        severity=Decimal("0.58"),
        horizon="medium",
        source_confidence=Decimal("0.91"),
    ),
    MockNewsSpec(
        source="taurus_mock_wire",
        title="ICICI Bank reports stable asset quality and better fee income",
        body=(
            "ICICI Bank Ltd reported stable asset quality trends and better fee income "
            "for the quarter, offsetting mild pressure in treasury income."
        ),
        published_at=_utc(2024, 12, 12, 16),
        symbols=("ICICIBANK",),
        entities=("ICICI Bank Ltd", "ICICI Bank"),
        event_type="earnings_beat",
        severity=Decimal("0.52"),
        horizon="short",
        source_confidence=Decimal("0.89"),
    ),
    MockNewsSpec(
        source="taurus_mock_wire",
        title="Larsen and Toubro secures a large infrastructure order",
        body=(
            "Larsen & Toubro Ltd secured a large domestic infrastructure order with "
            "execution expected to support the order book over multiple quarters."
        ),
        published_at=_utc(2024, 12, 11, 9),
        symbols=("LT",),
        entities=("Larsen & Toubro Ltd", "Larsen and Toubro", "LT"),
        event_type="order_win",
        severity=Decimal("0.64"),
        horizon="medium",
        source_confidence=Decimal("0.90"),
    ),
    MockNewsSpec(
        source="taurus_mock_wire",
        title="State Bank of India notes improving retail asset quality",
        body=(
            "State Bank of India noted improving retail asset quality indicators and "
            "steady deposit traction in an analyst interaction."
        ),
        published_at=_utc(2024, 12, 10, 14),
        symbols=("SBIN",),
        entities=("State Bank of India", "SBI", "SBIN"),
        event_type="asset_quality_improvement",
        severity=Decimal("0.44"),
        horizon="medium",
        source_confidence=Decimal("0.84"),
    ),
    MockNewsSpec(
        source="taurus_mock_wire",
        title="Bharti Airtel announces selective tariff repair in prepaid plans",
        body=(
            "Bharti Airtel Ltd announced selective tariff repair in prepaid plans, "
            "which analysts expect to support average revenue per user."
        ),
        published_at=_utc(2024, 12, 9, 13),
        symbols=("BHARTIARTL",),
        entities=("Bharti Airtel Ltd", "Bharti Airtel"),
        event_type="tariff_hike",
        severity=Decimal("0.49"),
        horizon="short",
        source_confidence=Decimal("0.87"),
    ),
    MockNewsSpec(
        source="taurus_mock_wire",
        title="ITC board schedules routine investor update",
        body=(
            "ITC Ltd scheduled a routine investor update and did not disclose any "
            "material operating change in the notice."
        ),
        published_at=_utc(2024, 12, 9, 16),
        symbols=("ITC",),
        entities=("ITC Ltd", "ITC"),
        event_type="neutral_filing",
        severity=Decimal("0.16"),
        horizon="short",
        source_confidence=Decimal("0.80"),
    ),
    MockNewsSpec(
        source="taurus_mock_wire",
        title="Hindustan Unilever sees demand softness in discretionary categories",
        body=(
            "Hindustan Unilever Ltd said discretionary categories showed demand "
            "softness, though core home-care volumes remained resilient."
        ),
        published_at=_utc(2024, 12, 6, 10),
        symbols=("HINDUNILVR",),
        entities=("Hindustan Unilever Ltd", "Hindustan Unilever"),
        event_type="demand_softness",
        severity=Decimal("0.42"),
        horizon="short",
        source_confidence=Decimal("0.86"),
    ),
)


def _document_from_spec(spec: MockNewsSpec) -> RawDocument:
    checksum = document_checksum(spec.source, spec.title, spec.body, spec.published_at.isoformat())
    return RawDocument(
        document_id=stable_id("raw", checksum),
        source=spec.source,
        source_url=f"mock://news/{checksum[:16]}",
        title=spec.title,
        body=spec.body,
        published_at=spec.published_at,
        symbols=list(spec.symbols),
        entities=list(spec.entities),
        checksum=checksum,
        metadata={
            "event_type": spec.event_type,
            "severity": str(spec.severity),
            "horizon": spec.horizon,
            "source_confidence": str(spec.source_confidence),
            "provider": "mock_news",
        },
    )
