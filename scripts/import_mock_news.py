from __future__ import annotations

import json
from dataclasses import dataclass

from sqlalchemy.orm import Session

from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.config import Settings, get_settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.repositories import InstrumentRepository, IntelligenceRepository
from taurus_core.db.session import build_session_factory
from taurus_core.intelligence.entity_resolver import EntityResolver
from taurus_core.intelligence.event_scoring import event_from_document, score_event
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.intelligence.news_provider import DocumentProvider


@dataclass(frozen=True, slots=True)
class MockNewsImportSummary:
    raw_document_count: int
    event_count: int
    sentiment_score_count: int
    symbols: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "raw_document_count": self.raw_document_count,
            "event_count": self.event_count,
            "sentiment_score_count": self.sentiment_score_count,
            "symbols": list(self.symbols),
        }


def import_mock_news(
    session: Session,
    provider: DocumentProvider | None = None,
) -> MockNewsImportSummary:
    provider = provider or MockNewsProvider()
    documents = provider.list_documents()
    instruments = InstrumentRepository(session).list(active_only=True)
    resolver = EntityResolver(instruments)
    repo = IntelligenceRepository(session)
    as_of = max((document.published_at for document in documents), default=None)

    event_count = 0
    sentiment_count = 0
    symbols: set[str] = set()
    for document in documents:
        repo.upsert_raw_document(document)
        resolved_entities = resolver.resolve_document(document)
        for entity in resolved_entities:
            event = event_from_document(document, entity.symbol)
            repo.upsert_event(event)
            repo.upsert_sentiment_score(score_event(event, as_of=as_of))
            event_count += 1
            sentiment_count += 1
            symbols.add(entity.symbol)

    session.commit()
    return MockNewsImportSummary(
        raw_document_count=len(documents),
        event_count=event_count,
        sentiment_score_count=sentiment_count,
        symbols=tuple(sorted(symbols)),
    )


def run_import(settings: Settings | None = None) -> MockNewsImportSummary:
    settings = settings or get_settings()
    run_migrations(settings)
    provider = MockMarketDataProvider(
        seed=settings.taurus_mock_seed,
        candle_count=settings.taurus_mock_candle_count,
    )
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_mock_data(session, provider)
    with session_factory() as session:
        return import_mock_news(session, MockNewsProvider())


if __name__ == "__main__":
    summary = run_import()
    print(json.dumps(summary.to_dict(), sort_keys=True))
