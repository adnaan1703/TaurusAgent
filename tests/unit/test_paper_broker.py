from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from scripts.run_final_approval import run_mock_final_approval
from taurus_core.agents.portfolio_manager import PortfolioManagerAgent
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID, run_analyst_suite
from taurus_core.agents.trader_agent import TraderAgent
from taurus_core.config import Settings
from taurus_core.db.models import (
    PaperAccountModel,
    PaperFillModel,
    PaperOrderModel,
    PaperPositionModel,
)
from taurus_core.db.repositories import (
    CandleRepository,
    ExecutionRepository,
    IntelligenceRepository,
    ResearchRepository,
    RiskRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.execution.schemas import (
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
    paper_fill_id,
    paper_order_id,
)
from taurus_core.intelligence.documents import NewsEvent, RawDocument, document_checksum, stable_id
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from tests.llm_fakes import FakeLLMProvider
from taurus_core.research.debate_service import ResearchDebateService
from taurus_core.research.schemas import TraderProposal, trader_proposal_id
from taurus_core.risk.review_service import RiskReviewService
from taurus_core.risk.schemas import FinalDecision
from tests.market_data_fixtures import seed_test_market_data


@pytest.fixture(autouse=True)
def fake_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.run_trader_proposal.build_llm_provider",
        lambda settings: FakeLLMProvider(),
    )
    monkeypatch.setattr(
        "scripts.run_final_approval.build_llm_provider",
        lambda settings: FakeLLMProvider(),
    )


def test_paper_broker_executes_approved_decision_and_api_returns_artifacts(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    _prepare_market_data_db(settings)
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
        repo = ExecutionRepository(session)
        account = PaperAccount.model_validate(
            repo.latest_account_by_portfolio(
                portfolio_id=settings.taurus_paper_portfolio_id,
            ).payload
        )
        position = PaperPosition.model_validate(
            repo.latest_open_positions_by_portfolio(
                portfolio_id=settings.taurus_paper_portfolio_id,
            )[0].payload
        )

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


def test_paper_order_schema_preserves_legacy_payload_defaults() -> None:
    as_of = datetime(2026, 6, 4, 10, 0, tzinfo=timezone.utc)

    order = PaperOrder.model_validate(
        {
            "order_id": "po-legacy",
            "final_decision_id": "final-legacy",
            "decision_id": "decision-legacy",
            "run_id": "run-legacy",
            "portfolio_id": "local-paper",
            "symbol": "infy",
            "side": "BUY",
            "quantity": 10,
            "order_type": "MARKET",
            "status": "FILLED",
            "filled_quantity": 10,
            "remaining_quantity": 0,
            "average_fill_price_inr": "100.0000",
            "gross_value_inr": "1000.0000",
            "total_cost_inr": "10.0000",
            "total_slippage_inr": "1.0000",
            "slippage_bps": "5.0000",
            "rejection_reason": "",
            "status_history": ["CREATED", "ACCEPTED", "FILLED"],
            "submitted_at": as_of.isoformat(),
            "updated_at": as_of.isoformat(),
            "model_version": "paper_broker_v1",
        }
    )

    assert order.symbol == "INFY"
    assert order.execution_policy == "immediate"
    assert order.signal_trade_date is None
    assert order.scheduled_fill_session is None
    assert order.filled_trade_date is None


def test_pending_next_open_order_repository_and_api_round_trip(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    _prepare_market_data_db(settings)
    run_mock_final_approval(symbol="INFY", settings=settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        decision = _latest_final_decision(session, "INFY")
        pending = _pending_order_from_decision(
            decision,
            portfolio_id=settings.taurus_paper_portfolio_id,
            signal_trade_date=date(2024, 12, 17),
        )
        ExecutionRepository(session).store_pending_next_open_order(order=pending)
        session.commit()

    with session_factory() as session:
        repo = ExecutionRepository(session)
        pending_rows = repo.list_pending_next_open_orders(
            portfolio_id=settings.taurus_paper_portfolio_id,
            symbol="infy",
        )
        listed_rows = repo.list_orders(
            portfolio_id=settings.taurus_paper_portfolio_id,
            symbol="INFY",
            limit=None,
        )
        row = repo.get_order(pending.order_id)

    assert len(pending_rows) == 1
    assert len(listed_rows) == 1
    assert row is not None
    assert pending_rows[0].order_id == pending.order_id
    assert row.status == "PENDING_NEXT_OPEN"
    validated = PaperOrder.model_validate(row.payload)
    assert validated.execution_policy == "next_open"
    assert validated.signal_trade_date == date(2024, 12, 17)
    assert validated.scheduled_fill_session == "next_open"

    response = TestClient(create_app(settings)).get("/paper/orders?symbol=INFY")

    assert response.status_code == 200
    assert response.json()[0]["order_id"] == pending.order_id
    assert response.json()[0]["status"] == "PENDING_NEXT_OPEN"
    assert response.json()[0]["execution_policy"] == "next_open"
    assert response.json()[0]["signal_trade_date"] == "2024-12-17"
    assert response.json()[0]["scheduled_fill_session"] == "next_open"

    filled_trade_date = date(2024, 12, 18)
    settled = _filled_pending_order(pending, filled_trade_date=filled_trade_date)
    fill = _fill_for_order(settled, trade_date=filled_trade_date)
    with session_factory() as session:
        updated = ExecutionRepository(session).replace_pending_next_open_order(
            order_id=pending.order_id,
            order=settled,
            fills=[fill],
        )
        session.commit()
        assert updated.order_id == pending.order_id

    with session_factory() as session:
        repo = ExecutionRepository(session)
        updated_row = repo.get_order(pending.order_id)
        updated_fills = repo.list_fills(order_id=pending.order_id, limit=None)
        pending_rows = repo.list_pending_next_open_orders(
            portfolio_id=settings.taurus_paper_portfolio_id,
            symbol="INFY",
        )

    assert updated_row is not None
    assert updated_row.order_id == pending.order_id
    assert updated_row.status == "FILLED"
    assert PaperOrder.model_validate(updated_row.payload).filled_trade_date == filled_trade_date
    assert [fill.order_id for fill in updated_fills] == [pending.order_id]
    assert pending_rows == []


def test_after_close_buy_decision_creates_pending_order_without_fills(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory, decision, order = _route_default_after_close_buy(settings)

    with session_factory() as session:
        fills = ExecutionRepository(session).list_fills(
            final_decision_id=decision.final_decision_id,
            limit=None,
        )

    assert decision.final_action == "BUY"
    assert order is not None
    assert order.filled_quantity == 0
    assert order.remaining_quantity == decision.approved_quantity
    assert order.gross_value_inr == Decimal("0.0000")
    assert order.total_cost_inr == Decimal("0.0000")
    assert fills == []


def test_after_close_buy_decision_preserves_cash_until_next_open(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory, decision, order = _route_default_after_close_buy(settings)

    with session_factory() as session:
        account_model = ExecutionRepository(session).latest_account_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
        )
        account = PaperAccount.model_validate(account_model.payload)

    assert decision.final_action == "BUY"
    assert order is not None
    assert account.available_cash_inr == account.starting_cash_inr


def test_after_close_buy_order_status_waits_for_next_open(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    _session_factory, decision, order = _route_default_after_close_buy(settings)

    assert decision.final_action == "BUY"
    assert order is not None
    assert order.status == "PENDING_NEXT_OPEN"
    assert order.status_history == ["CREATED", "ACCEPTED", "PENDING_NEXT_OPEN"]


def test_after_close_order_does_not_fill_at_same_day_candle_open(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    _prepare_market_data_db(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        latest_candle = _latest_candle(session, "INFY")

    run_mock_final_approval(symbol="INFY", settings=settings)
    with session_factory() as session:
        decision = _latest_final_decision(session, "INFY")
        assert _proposal_evaluation_mode(session, decision) == "after_close"
        order = ExecutionRouter(session, settings).route_decision(decision)

    with session_factory() as session:
        fills = ExecutionRepository(session).list_fills(
            final_decision_id=decision.final_decision_id,
            limit=None,
        )

    assert order is not None
    same_day_open_fills = [
        fill
        for fill in fills
        if fill.trade_date == latest_candle.trade_date
        and fill.reference_price_inr == latest_candle.open
    ]
    assert same_day_open_fills == []


def test_market_hours_monitor_decision_still_routes_immediately(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    _prepare_market_data_db(settings)
    run_mock_final_approval(symbol="INFY", settings=settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        decision = _latest_final_decision(session, "INFY")
        _mark_proposal_as_market_hours(session, decision)

    with session_factory() as session:
        decision = _latest_final_decision(session, "INFY")
        assert _proposal_evaluation_mode(session, decision) == "market_hours"
        order = ExecutionRouter(session, settings).route_decision(decision)

    with session_factory() as session:
        fills = ExecutionRepository(session).list_fills(
            final_decision_id=decision.final_decision_id,
            limit=None,
        )

    assert order is not None
    assert order.status == "FILLED"
    assert order.filled_quantity == decision.approved_quantity
    assert fills


def test_paper_execution_is_deterministic_and_not_duplicated(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    _prepare_market_data_db(settings)
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
    _prepare_market_data_db(settings)
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
        decision = PortfolioManagerAgent(
            session,
            settings,
            enable_llm_explanation=False,
        ).run(symbol="INFY", risk_review=review)
    with session_factory() as session:
        order = ExecutionRouter(session, settings).route_decision(decision)
        order_count = session.scalar(select(func.count()).select_from(PaperOrderModel))

    assert decision.status == "BLOCKED"
    assert decision.can_send_to_broker is False
    assert order is None
    assert order_count == 0


def test_paper_broker_exits_position_opened_in_prior_run(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    _prepare_market_data_db(settings)
    run_mock_final_approval(symbol="INFY", settings=settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        buy_decision = _latest_final_decision(session, "INFY")
        buy_order = ExecutionRouter(session, settings).route_decision(buy_decision)
    assert buy_order is not None
    assert buy_order.side == "BUY"

    with session_factory() as session:
        repo = ExecutionRepository(session)
        position = PaperPosition.model_validate(
            repo.latest_open_position_by_portfolio_symbol(
                portfolio_id=settings.taurus_paper_portfolio_id,
                symbol="INFY",
            ).payload
        )
        original_quantity = position.quantity
        proposal = _exit_proposal_from_latest(session, settings, position)
        ResearchRepository(session).replace_trader_proposal_for_run_symbol(proposal)
        session.commit()

    with session_factory() as session:
        review = RiskReviewService(session, settings).run(
            symbol="INFY",
            run_id="exit-run",
            proposal=proposal,
        )
    with session_factory() as session:
        decision = PortfolioManagerAgent(
            session,
            settings,
            enable_llm_explanation=False,
        ).run(
            symbol="INFY",
            run_id="exit-run",
            risk_review=review,
        )
    with session_factory() as session:
        exit_order = ExecutionRouter(session, settings).route_decision(decision)

    with session_factory() as session:
        repo = ExecutionRepository(session)
        open_positions = repo.latest_open_positions_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
        )
        fills = repo.list_fills_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
            symbol="INFY",
        )
        account = PaperAccount.model_validate(
            repo.latest_account_by_portfolio(
                portfolio_id=settings.taurus_paper_portfolio_id,
            ).payload
        )

    assert review.status == "APPROVED"
    assert decision.status == "APPROVED_FOR_PAPER"
    assert decision.final_action == "EXIT"
    assert decision.approved_quantity == original_quantity
    assert exit_order is not None
    assert exit_order.side == "SELL"
    assert exit_order.filled_quantity == original_quantity
    assert open_positions == []
    assert {fill.side for fill in fills} == {"BUY", "SELL"}
    assert account.portfolio_id == settings.taurus_paper_portfolio_id


def _prepare_paper_db(settings: Settings):
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_test_market_data(session, candle_count=252)
        import_mock_news(session, MockNewsProvider())
    return session_factory


def _prepare_market_data_db(settings: Settings):
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_test_market_data(session, candle_count=252)
    return session_factory


def _build_trader_proposal(session_factory) -> TraderProposal:
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id=DEFAULT_ANALYST_RUN_ID,
        )
    with session_factory() as session:
        debate = ResearchDebateService(session, llm_provider=FakeLLMProvider()).run(
            symbol="INFY",
            rounds_requested=2,
        )
    with session_factory() as session:
        return TraderAgent(
            session,
            Settings(),
            llm_provider=FakeLLMProvider(),
        ).run(symbol="INFY", debate=debate)


def _exit_proposal_from_latest(
    session,
    settings: Settings,
    position: PaperPosition,
) -> TraderProposal:
    base = ResearchRepository(session).latest_trader_proposal(
        run_id=DEFAULT_ANALYST_RUN_ID,
        symbol=position.symbol,
    )
    assert base is not None
    proposal = TraderProposal.model_validate(base.payload)
    source_report_ids = list(proposal.source_report_ids)
    return proposal.model_copy(
        update={
            "proposal_id": trader_proposal_id(
                run_id="exit-run",
                symbol=position.symbol,
                debate_id=proposal.debate_id,
                source_report_ids=source_report_ids,
            ),
            "run_id": "exit-run",
            "portfolio_id": settings.taurus_paper_portfolio_id,
            "action": "EXIT",
            "requested_position_pct_nav": Decimal("0.0000"),
            "current_position_quantity": position.quantity,
            "current_position_pct_nav": Decimal("2.0000"),
            "target_position_pct_nav": Decimal("0.0000"),
            "lifecycle_trigger": "thesis_invalidated",
            "evaluation_mode": "after_close",
            "order_type": "LIMIT",
            "position_management_summary": "Test exit of prior-run paper position.",
        }
    )


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


def _route_default_after_close_buy(settings: Settings):
    _prepare_market_data_db(settings)
    run_mock_final_approval(symbol="INFY", settings=settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        decision = _latest_final_decision(session, "INFY")
        assert _proposal_evaluation_mode(session, decision) == "after_close"
        order = ExecutionRouter(session, settings).route_decision(decision)
    return session_factory, decision, order


def _proposal_evaluation_mode(session, decision: FinalDecision) -> str:
    proposal_model = ResearchRepository(session).get_trader_proposal(decision.proposal_id)
    assert proposal_model is not None
    return proposal_model.evaluation_mode


def _mark_proposal_as_market_hours(session, decision: FinalDecision) -> None:
    proposal_model = ResearchRepository(session).get_trader_proposal(decision.proposal_id)
    assert proposal_model is not None
    payload = dict(proposal_model.payload)
    payload["evaluation_mode"] = "market_hours"
    payload["market_session_date"] = "2024-12-17"
    proposal_model.evaluation_mode = "market_hours"
    proposal_model.payload = payload
    session.commit()


def _latest_candle(session, symbol: str):
    candles = CandleRepository(session).get_by_symbol_and_date_range(symbol=symbol)
    assert candles
    return candles[-1]


def _pending_order_from_decision(
    decision: FinalDecision,
    *,
    portfolio_id: str,
    signal_trade_date: date,
) -> PaperOrder:
    timestamp = decision.as_of
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    side = "BUY" if decision.final_action == "BUY" else "SELL"
    return PaperOrder(
        order_id=paper_order_id(
            final_decision_id=decision.final_decision_id,
            decision_id=decision.decision_id,
            quantity=decision.approved_quantity,
        ),
        final_decision_id=decision.final_decision_id,
        decision_id=decision.decision_id,
        run_id=decision.run_id,
        portfolio_id=portfolio_id,
        symbol=decision.symbol,
        side=side,
        quantity=decision.approved_quantity,
        order_type="MARKET",
        status="PENDING_NEXT_OPEN",
        execution_policy="next_open",
        filled_quantity=0,
        remaining_quantity=decision.approved_quantity,
        average_fill_price_inr=Decimal("0.0000"),
        gross_value_inr=Decimal("0.0000"),
        total_cost_inr=Decimal("0.0000"),
        total_slippage_inr=Decimal("0.0000"),
        slippage_bps=Decimal("5.0000"),
        rejection_reason="",
        status_history=["CREATED", "ACCEPTED", "PENDING_NEXT_OPEN"],
        signal_trade_date=signal_trade_date,
        scheduled_fill_session="next_open",
        filled_trade_date=None,
        submitted_at=timestamp,
        updated_at=timestamp,
        model_version="paper_broker_v1",
    )


def _filled_pending_order(order: PaperOrder, *, filled_trade_date: date) -> PaperOrder:
    fill_price = Decimal("100.5000")
    gross_value = Decimal(order.quantity) * fill_price
    return order.model_copy(
        update={
            "status": "FILLED",
            "filled_quantity": order.quantity,
            "remaining_quantity": 0,
            "average_fill_price_inr": fill_price,
            "gross_value_inr": gross_value,
            "status_history": [*order.status_history, "FILLED"],
            "filled_trade_date": filled_trade_date,
            "updated_at": order.updated_at + timedelta(minutes=1),
        }
    )


def _fill_for_order(order: PaperOrder, *, trade_date: date) -> PaperFill:
    reference_price = Decimal("100.0000")
    fill_price = Decimal("100.5000")
    gross_value = Decimal(order.quantity) * fill_price
    return PaperFill(
        fill_id=paper_fill_id(
            order_id=order.order_id,
            fill_sequence=1,
            quantity=order.quantity,
            reference_price=reference_price,
        ),
        order_id=order.order_id,
        final_decision_id=order.final_decision_id,
        run_id=order.run_id,
        portfolio_id=order.portfolio_id,
        symbol=order.symbol,
        trade_date=trade_date,
        side=order.side,
        quantity=order.quantity,
        reference_price_inr=reference_price,
        fill_price_inr=fill_price,
        gross_value_inr=gross_value,
        brokerage_inr=Decimal("0.0000"),
        exchange_txn_charge_inr=Decimal("0.0000"),
        tax_levy_inr=Decimal("0.0000"),
        cost_inr=Decimal("0.0000"),
        slippage_bps=Decimal("5.0000"),
        slippage_inr=Decimal("0.0000"),
        fill_sequence=1,
        filled_at=order.updated_at,
        model_version="paper_broker_v1",
    )


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(
        taurus_paper_partial_fill_threshold=1,
    )
