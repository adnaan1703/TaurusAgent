from __future__ import annotations

from datetime import timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from scripts.seed_mock_data import seed_mock_data
from taurus_core.agents.portfolio_manager import PortfolioManagerAgent
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID, run_analyst_suite
from taurus_core.agents.trader_agent import TraderAgent
from taurus_core.config import Settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.models import BacktestOrderModel, FinalDecisionModel, RiskReviewModel
from taurus_core.db.repositories import IntelligenceRepository
from taurus_core.db.session import build_session_factory
from taurus_core.intelligence.documents import NewsEvent, RawDocument, document_checksum, stable_id
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm.mock_provider import MockLLMProvider
from taurus_core.research.debate_service import ResearchDebateService
from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.engine import RiskEngine
from taurus_core.risk.review_service import RiskReviewService
from taurus_core.risk.schemas import decision_id_for_proposal, risk_review_id


def test_risk_review_is_deterministic_stores_rules_and_does_not_create_orders(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory)

    with session_factory() as session:
        first = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    with session_factory() as session:
        second = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)

    with session_factory() as session:
        review_count = session.scalar(select(func.count()).select_from(RiskReviewModel))
        order_count = session.scalar(select(func.count()).select_from(BacktestOrderModel))

    rule_names = {result.rule for result in first.hard_rule_results}
    persona_names = {review.agent_name for review in first.persona_reviews}

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.status in {"APPROVED", "APPROVED_WITH_REDUCTION"}
    assert {"RiskyRiskAgent", "NeutralRiskAgent", "SafeRiskAgent"} == persona_names
    assert {
        "live_trading_disabled",
        "max_position_pct",
        "kill_switch",
        "severe_event_block",
        "required_trace_ids",
    }.issubset(rule_names)
    assert first.is_order is False
    assert first.can_send_to_broker is False
    assert review_count == 1
    assert order_count == 0


def test_risk_engine_reduces_oversized_positions(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory).model_copy(
        update={
            "action": "BUY",
            "requested_position_pct_nav": Decimal("12.0000"),
        }
    )

    with session_factory() as session:
        result = RiskEngine(session, settings).evaluate(
            proposal=proposal,
            decision_id=_decision_id(proposal),
            risk_check_id=_risk_check_id(proposal),
        )

    assert result.status == "APPROVED_WITH_REDUCTION"
    assert result.approved_position_pct_nav == Decimal("5.0000")
    assert any(
        rule.rule == "max_position_pct" and rule.status == "reduced"
        for rule in result.hard_rule_results
    )


def test_kill_switch_blocks_risk_approval(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory)

    with session_factory() as session:
        result = RiskEngine(session, settings, kill_switch_enabled=True).evaluate(
            proposal=proposal,
            decision_id=_decision_id(proposal),
            risk_check_id=_risk_check_id(proposal),
        )

    assert result.status == "BLOCKED"
    assert result.approved_position_pct_nav == Decimal("0.0000")
    assert any(
        rule.rule == "kill_switch" and rule.status == "blocked"
        for rule in result.hard_rule_results
    )


def test_severe_negative_event_blocks_long_entry(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory).model_copy(
        update={
            "action": "BUY",
            "requested_position_pct_nav": Decimal("3.0000"),
        }
    )

    with session_factory() as session:
        _insert_severe_negative_event(session, proposal)
        result = RiskEngine(session, settings).evaluate(
            proposal=proposal,
            decision_id=_decision_id(proposal),
            risk_check_id=_risk_check_id(proposal),
        )

    assert result.status == "BLOCKED"
    assert any(
        rule.rule == "severe_event_block" and rule.status == "blocked"
        for rule in result.hard_rule_results
    )


def test_portfolio_manager_stores_final_paper_decision_and_api_returns_m6_artifacts(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory)
    with session_factory() as session:
        review = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    with session_factory() as session:
        decision = PortfolioManagerAgent(session, settings).run(
            symbol="INFY",
            risk_review=review,
        )

    with session_factory() as session:
        decision_count = session.scalar(select(func.count()).select_from(FinalDecisionModel))
        order_count = session.scalar(select(func.count()).select_from(BacktestOrderModel))

    client = TestClient(create_app(settings))
    risk_response = client.get("/risk-checks?symbol=INFY")
    final_response = client.get("/final-decisions?symbol=INFY")

    assert decision.status == "APPROVED_FOR_PAPER"
    assert decision.final_action == "BUY"
    assert decision.approved_quantity > 0
    assert decision.is_order is False
    assert decision.can_send_to_broker is True
    assert decision_count == 1
    assert order_count == 0
    assert risk_response.status_code == 200
    assert final_response.status_code == 200
    assert risk_response.json()[0]["risk_check_id"] == review.risk_check_id
    assert final_response.json()[0]["final_decision_id"] == decision.final_decision_id


def _prepare_approval_db(settings: Settings):
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_mock_data(session, MockMarketDataProvider(seed=42, candle_count=252))
        import_mock_news(session, MockNewsProvider())
    return session_factory


def _build_trader_proposal(session_factory) -> TraderProposal:
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=MockLLMProvider(),
            run_id=DEFAULT_ANALYST_RUN_ID,
        )
    with session_factory() as session:
        debate = ResearchDebateService(session).run(symbol="INFY", rounds_requested=2)
    with session_factory() as session:
        return TraderAgent(session).run(symbol="INFY", debate=debate)


def _insert_severe_negative_event(session, proposal: TraderProposal) -> None:
    published_at = proposal.as_of
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    checksum = document_checksum("risk_test", proposal.symbol, published_at.isoformat())
    document = RawDocument(
        document_id=stable_id("raw", checksum),
        source="risk_test",
        source_url="mock://risk-test/severe-negative",
        title="Infosys faces severe regulatory probe",
        body="A severe regulatory probe creates direct event risk for the long setup.",
        published_at=published_at,
        symbols=[proposal.symbol],
        entities=["Infosys Ltd"],
        checksum=checksum,
        metadata={"provider": "risk_test"},
    )
    event = NewsEvent(
        event_id=stable_id("evt", document.document_id, proposal.symbol, "regulatory_probe"),
        document_id=document.document_id,
        symbol=proposal.symbol,
        event_type="regulatory_probe",
        event_time=published_at,
        headline=document.title,
        summary=document.body,
        severity=Decimal("0.9500"),
        horizon="short",
        source_confidence=Decimal("0.9500"),
        metadata={"provider": "risk_test"},
    )
    repo = IntelligenceRepository(session)
    repo.upsert_raw_document(document)
    repo.upsert_event(event)
    session.commit()


def _decision_id(proposal: TraderProposal) -> str:
    return decision_id_for_proposal(
        run_id=proposal.run_id,
        symbol=proposal.symbol,
        proposal_id=proposal.proposal_id,
    )


def _risk_check_id(proposal: TraderProposal) -> str:
    return risk_review_id(
        run_id=proposal.run_id,
        symbol=proposal.symbol,
        proposal_id=proposal.proposal_id,
        source_report_ids=proposal.source_report_ids,
    )


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
