from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from sqlalchemy import func, select

from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.config import Settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.models import CompanyEventModel, RawDocumentModel, SentimentScoreModel
from taurus_core.db.session import build_session_factory
from taurus_core.intelligence.entity_resolver import EntityResolver
from taurus_core.intelligence.event_scoring import event_from_document, score_event
from taurus_core.intelligence.mock_news_provider import MockNewsProvider


def test_mock_news_import_stores_documents_events_and_scores(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_mock_data(session, MockMarketDataProvider(seed=42, candle_count=252))
        summary = import_mock_news(session, MockNewsProvider())

    with session_factory() as session:
        document_count = session.scalar(select(func.count()).select_from(RawDocumentModel))
        event_count = session.scalar(select(func.count()).select_from(CompanyEventModel))
        score_count = session.scalar(select(func.count()).select_from(SentimentScoreModel))
        infy_event = session.scalar(
            select(CompanyEventModel).where(CompanyEventModel.symbol == "INFY")
        )
        infy_score = session.scalar(
            select(SentimentScoreModel).where(SentimentScoreModel.symbol == "INFY")
        )

    assert summary.raw_document_count == 10
    assert summary.event_count == 10
    assert summary.sentiment_score_count == 10
    assert "INFY" in summary.symbols
    assert document_count == 10
    assert event_count == 10
    assert score_count == 10
    assert infy_event is not None
    assert infy_score is not None
    assert infy_score.event_score > 0


def test_entity_resolver_maps_company_names_symbols_and_text() -> None:
    resolver = EntityResolver(MockMarketDataProvider(seed=42).list_instruments())

    assert resolver.resolve_symbol("infy").symbol == "INFY"  # type: ignore[union-attr]
    assert resolver.resolve_symbol("Infosys Ltd").symbol == "INFY"  # type: ignore[union-attr]

    matches = resolver.resolve_text("Larsen and Toubro announced a large order.")

    assert [match.symbol for match in matches] == ["LT"]


def test_event_scoring_uses_direction_severity_confidence_and_time_decay() -> None:
    documents = MockNewsProvider().list_documents()
    positive_document = next(document for document in documents if "INFY" in document.symbols)
    negative_document = next(document for document in documents if "HDFCBANK" in document.symbols)
    positive_event = event_from_document(positive_document, "INFY")
    negative_event = event_from_document(negative_document, "HDFCBANK")

    current_positive = score_event(positive_event, as_of=positive_event.event_time)
    decayed_positive = score_event(
        positive_event,
        as_of=positive_event.event_time + timedelta(days=15),
    )
    negative_score = score_event(negative_event, as_of=negative_event.event_time)

    assert current_positive.event_score > 0
    assert decayed_positive.decayed_score < current_positive.event_score
    assert negative_score.event_score < 0
    assert current_positive.confidence > 0


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
