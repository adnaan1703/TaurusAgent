from __future__ import annotations

from datetime import timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from scripts.run_final_approval import run_mock_final_approval
from scripts.seed_mock_data import seed_mock_data
from taurus_core.agents.portfolio_manager import PortfolioManagerAgent
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID, run_analyst_suite
from taurus_core.agents.trader_agent import TraderAgent
from taurus_core.config import Settings
from taurus_core.data.providers.mock_market_data import MockMarketDataProvider
from taurus_core.db.models import (
    PaperAccountModel,
    PaperFillModel,
    PaperOrderModel,
    PaperPositionModel,
)
from taurus_core.db.repositories import ExecutionRepository, IntelligenceRepository, RiskRepository
from taurus_core.db.session import build_session_factory
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.execution.schemas import PaperAccount, PaperOrder, PaperPosition
from taurus_core.intelligence.documents import NewsEvent, RawDocument, document_checksum, stable_id
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm.mock_provider import MockLLMProvider
from taurus_core.research.debate_service import ResearchDebateService
from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.review_service import RiskReviewService
from taurus_core.risk.schemas import FinalDecision


def test_paper_broker_executes_approved_decision_and_api_returns_artifacts(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_mock_final_approval(symbol="INFY", settings=settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        decision = _latest_final_decision(session, "INFY")
        order = ExecutionRouter(session, settings).route_decision(decision)

    with session_factory() as session:
        order_count = session.scalar(select(func.count()).select_from(PaperOrderModel))
        fill_count = session.scalar(select(func.count()).select_from(PaperFillModel))
        position_count = session.scalar(select(func.count()).select_from(PaperPositionModel))
        account_count = session.scalar(select(func.count()).select_from(PaperAccountModel))
        account = PaperAccount.model_validate(ExecutionRepository(session).latest_account().payload)
        position = PaperPosition.model_validate(ExecutionRepository(session).list_positions()[0].payload)

    assert order is not None
    assert order.status == "FILLED"
    assert order.filled_quantity == decision.approved_quantity
    assert order.remaining_quantity == 0
    assert order.total_cost_inr > 0
    assert order.total_slippage_inr > 0
    assert "PARTIALLY_FILLED" in order.status_history
    assert order_count == 1
    assert fill_count == 2
    assert position_count == 1
    assert account_count == 1
    assert position.symbol == "INFY"
    assert position.quantity == decision.approved_quantity
    assert account.available_cash_inr == (
        account.starting_cash_inr - order.gross_value_inr - order.total_cost_inr
    )
    assert account.gross_exposure_inr == position.market_value_inr

    client = TestClient(create_app(settings))
    orders_response = client.get("/paper/orders?symbol=INFY")
    fills_response = client.get("/paper/fills?symbol=INFY")
    positions_response = client.get("/paper/positions?symbol=INFY")
    account_response = client.get("/paper/account")

    assert orders_response.status_code == 200
    assert fills_response.status_code == 200
    assert positions_response.status_code == 200
    assert account_response.status_code == 200
    assert orders_response.json()[0]["order_id"] == order.order_id
    assert len(fills_response.json()) == 2
    assert positions_response.json()[0]["quantity"] == decision.approved_quantity
    assert account_response.json()["account_id"] == account.account_id


def test_paper_execution_is_deterministic_and_not_duplicated(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_mock_final_approval(symbol="INFY", settings=settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        first = ExecutionRouter(session, settings).route_latest_for_symbol(symbol="INFY")
    with session_factory() as session:
        second = ExecutionRouter(session, settings).route_latest_for_symbol(symbol="INFY")

    with session_factory() as session:
        order_count = session.scalar(select(func.count()).select_from(PaperOrderModel))
        fill_count = session.scalar(select(func.count()).select_from(PaperFillModel))

    assert first is not None
    assert second is not None
    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert order_count == 1
    assert fill_count == 2


def test_execution_router_does_not_send_rejected_decision_to_paper_broker(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_mock_final_approval(symbol="INFY", settings=settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        approved = _latest_final_decision(session, "INFY")
        rejected = approved.model_copy(
            update={
                "status": "REJECTED",
                "can_send_to_broker": False,
                "approved_quantity": 0,
            }
        )
        order = ExecutionRouter(session, settings).route_decision(rejected)
        order_count = session.scalar(select(func.count()).select_from(PaperOrderModel))

    assert order is None
    assert order_count == 0


def test_event_risk_blocked_final_decision_does_not_create_paper_order(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_paper_db(settings)
    proposal = _build_trader_proposal(session_factory)

    with session_factory() as session:
        _insert_severe_negative_event(session, proposal)
        review = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    with session_factory() as session:
        decision = PortfolioManagerAgent(session, settings).run(symbol="INFY", risk_review=review)
    with session_factory() as session:
        order = ExecutionRouter(session, settings).route_decision(decision)
        order_count = session.scalar(select(func.count()).select_from(PaperOrderModel))

    assert decision.status == "BLOCKED"
    assert decision.can_send_to_broker is False
    assert order is None
    assert order_count == 0


def _prepare_paper_db(settings: Settings):
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
    checksum = document_checksum("paper_test", proposal.symbol, published_at.isoformat())
    document = RawDocument(
        document_id=stable_id("raw", checksum),
        source="paper_test",
        source_url="mock://paper-test/severe-negative",
        title="Infosys faces severe regulatory probe",
        body="A severe regulatory probe should block the final paper route.",
        published_at=published_at,
        symbols=[proposal.symbol],
        entities=["Infosys Ltd"],
        checksum=checksum,
        metadata={"provider": "paper_test"},
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
        metadata={"provider": "paper_test"},
    )
    repo = IntelligenceRepository(session)
    repo.upsert_raw_document(document)
    repo.upsert_event(event)
    session.commit()


def _latest_final_decision(session, symbol: str) -> FinalDecision:
    model = RiskRepository(session).latest_final_decision(
        symbol=symbol,
        run_id=DEFAULT_ANALYST_RUN_ID,
    )
    assert model is not None
    return FinalDecision.model_validate(model.payload)


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'taurus.db'}",
        taurus_paper_partial_fill_threshold=1,
    )
