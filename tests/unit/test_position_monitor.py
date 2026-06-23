from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from fastapi.testclient import TestClient

from apps.api.main import create_app
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID, run_analyst_suite
from taurus_core.agents.portfolio_manager import PortfolioManagerAgent
from taurus_core.agents.trader_agent import TAKE_PROFIT_PCT, TraderAgent
from taurus_core.config import Settings
from taurus_core.db.models import AuditLogModel
from taurus_core.db.repositories import (
    CandleRepository,
    ExecutionRepository,
    InstrumentRepository,
    MarketPriceSnapshotRepository,
    ResearchRepository,
    RiskRepository,
    TaurusProfileRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle, MarketPriceSnapshot
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.execution.schemas import PaperAccount, PaperPosition, paper_account_id
from taurus_core.position_monitor import PositionMonitorService
from taurus_core.profiles.schemas import TaurusProfileCreate
from taurus_core.research.schemas import (
    BearThesis,
    BullThesis,
    DebateReport,
    DebateRound,
    ResearchManagerSummary,
    TraderProposal,
)
from taurus_core.research.debate_service import ResearchDebateService
from taurus_core.risk.review_service import RiskReviewService
from tests.llm_fakes import FakeLLMProvider


class FakeQuoteProvider:
    def __init__(self, prices: dict[str, Decimal], *, fail: bool = False) -> None:
        self.prices = {symbol.upper(): price for symbol, price in prices.items()}
        self.fail = fail
        self.requests: list[list[str]] = []

    def get_latest_snapshots(self, symbols: list[str]) -> list[MarketPriceSnapshot]:
        self.requests.append([symbol.upper() for symbol in symbols])
        if self.fail:
            raise RuntimeError("quote outage")
        now = datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc)
        return [
            MarketPriceSnapshot(
                symbol=symbol.upper(),
                provider="kite",
                exchange="NSE",
                provider_symbol=symbol.upper(),
                instrument_token="408065",
                last_price=self.prices[symbol.upper()],
                open=self.prices[symbol.upper()],
                high=self.prices[symbol.upper()],
                low=self.prices[symbol.upper()],
                close=self.prices[symbol.upper()],
                volume=1000,
                fetched_at=now,
                source="test-fake-kite:quote:NSE",
                raw={"test": True},
            )
            for symbol in symbols
        ]


def test_stop_loss_trigger_creates_exit_flow(postgres_test_settings: Settings) -> None:
    settings = _settings()
    session_factory = build_session_factory(settings)
    _seed_monitor_fixture(settings)

    result = PositionMonitorService(
        settings,
        quote_provider=FakeQuoteProvider({"INFY": Decimal("930.0000")}),
        llm_provider=FakeLLMProvider(),
        now_func=lambda: datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc),
    ).run_once()

    assert result.status == "COMPLETED"
    assert result.proposals_created == 1
    with session_factory() as session:
        proposals = ResearchRepository(session).list_trader_proposals(
            symbol="INFY",
            portfolio_id=settings.taurus_paper_portfolio_id,
            limit=5,
        )
        monitor_proposal = TraderProposal.model_validate(proposals[0].payload)
        final = RiskRepository(session).latest_final_decision(
            symbol="INFY",
            run_id=result.run_id or "",
        )
        order = ExecutionRepository(session).list_orders(
            run_id=result.run_id, symbol="INFY"
        )[0]

    assert monitor_proposal.evaluation_mode == "market_hours"
    assert monitor_proposal.lifecycle_trigger == "stop_loss"
    assert monitor_proposal.action == "EXIT"
    assert monitor_proposal.latest_price_inr == Decimal("930.0000")
    assert final is not None
    assert final.final_action == "EXIT"
    assert order.side == "SELL"


def test_market_hours_monitor_remains_open_position_only_under_full_universe_scope(
    postgres_test_settings: Settings,
) -> None:
    settings = _settings(paper_analysis_scope="full_universe")
    _seed_monitor_fixture(settings)
    now = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
    with build_session_factory(settings)() as session:
        InstrumentRepository(session).upsert(
            Instrument(
                symbol="TCS",
                name="Tata Consultancy Services Ltd",
                exchange="NSE",
                segment="EQUITY",
                currency="INR",
                lot_size=1,
                tick_size=Decimal("0.05"),
                active=True,
            )
        )
        CandleRepository(session).upsert(
            [
                DailyCandle(
                    symbol="TCS",
                    trade_date=date(2026, 5, 28),
                    open=Decimal("3500.0000"),
                    high=Decimal("3510.0000"),
                    low=Decimal("3490.0000"),
                    close=Decimal("3500.0000"),
                    volume=100000,
                    source="test",
                    data_available_time=now,
                )
            ]
        )
        session.commit()
    quote_provider = FakeQuoteProvider(
        {
            "INFY": Decimal("1000.0000"),
            "TCS": Decimal("3500.0000"),
        }
    )

    result = PositionMonitorService(
        settings,
        quote_provider=quote_provider,
        llm_provider=FakeLLMProvider(),
        now_func=lambda: datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc),
    ).run_once()

    with build_session_factory(settings)() as session:
        latest_run = (
            session.query(AuditLogModel)
            .filter(AuditLogModel.event_type == "position_monitor.iteration_started")
            .order_by(AuditLogModel.created_at.desc())
            .first()
        )

    assert result.status == "COMPLETED"
    assert result.symbols_seen == ["INFY"]
    assert quote_provider.requests == [["INFY"]]
    assert result.skipped["INFY"] == "no_threshold_crossed"
    assert latest_run is not None
    assert latest_run.payload["symbols"] == ["INFY"]


def test_position_monitor_only_watches_selected_profile(
    postgres_test_settings: Settings,
) -> None:
    settings = _settings(profile_id="client-a")
    session_factory = build_session_factory(settings)
    now = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        TaurusProfileRepository(session).create_profile(
            TaurusProfileCreate(
                profile_id="client-a",
                display_name="Client A",
                starting_corpus_inr=Decimal("250000"),
            )
        )
        _seed_manual_monitor_position(
            session,
            profile_id="local-paper",
            symbol="INFY",
            price=Decimal("1000.0000"),
            as_of=now,
        )
        _seed_manual_monitor_position(
            session,
            profile_id="client-a",
            symbol="TCS",
            price=Decimal("3500.0000"),
            as_of=now,
        )
        session.commit()

    quote_provider = FakeQuoteProvider(
        {
            "INFY": Decimal("930.0000"),
            "TCS": Decimal("3500.0000"),
        }
    )
    result = PositionMonitorService(
        settings,
        quote_provider=quote_provider,
        llm_provider=FakeLLMProvider(),
        now_func=lambda: datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc),
    ).run_once()

    with session_factory() as session:
        latest_run = (
            session.query(AuditLogModel)
            .filter(AuditLogModel.event_type == "position_monitor.iteration_started")
            .order_by(AuditLogModel.created_at.desc())
            .first()
        )
        client_positions = ExecutionRepository(
            session
        ).latest_open_positions_by_portfolio(portfolio_id="client-a")
        local_positions = ExecutionRepository(
            session
        ).latest_open_positions_by_portfolio(portfolio_id="local-paper")

    assert result.status == "COMPLETED"
    assert result.symbols_seen == ["TCS"]
    assert result.skipped == {"TCS": "no_threshold_crossed"}
    assert quote_provider.requests == [["TCS"]]
    assert latest_run is not None
    assert latest_run.payload["portfolio_id"] == "client-a"
    assert latest_run.payload["symbols"] == ["TCS"]
    assert [position.symbol for position in client_positions] == ["TCS"]
    assert [position.symbol for position in local_positions] == ["INFY"]


def test_take_profit_trigger_creates_reduce_flow(
    postgres_test_settings: Settings,
) -> None:
    settings = _settings()
    _seed_monitor_fixture(settings)

    result = PositionMonitorService(
        settings,
        quote_provider=FakeQuoteProvider({"INFY": Decimal("1130.0000")}),
        llm_provider=FakeLLMProvider(),
        now_func=lambda: datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc),
    ).run_once()

    with build_session_factory(settings)() as session:
        proposal = ResearchRepository(session).latest_trader_proposal(
            symbol="INFY",
            run_id=result.run_id or "",
        )
        order = ExecutionRepository(session).list_orders(
            run_id=result.run_id, symbol="INFY"
        )[0]

    assert proposal is not None
    payload = TraderProposal.model_validate(proposal.payload)
    assert payload.lifecycle_trigger == "take_profit"
    assert payload.action in {"REDUCE", "EXIT"}
    assert payload.action == "REDUCE"
    assert order.side == "SELL"

    client = TestClient(create_app(settings))
    portfolio = client.get("/ui/portfolio")
    risk = client.get("/ui/risk")
    assert portfolio.status_code == 200
    assert risk.status_code == 200
    assert portfolio.json()["monitor_status"]["latest_event_type"].startswith(
        "position_monitor."
    )
    assert portfolio.json()["positions"][0]["latest_quote_ltp_inr"] == 1130.0
    assert portfolio.json()["positions"][0]["stop_loss_price_inr"] is not None
    assert risk.json()["latest_risk_reviews"][0]["evaluation_mode"] == "market_hours"


def test_duplicate_trigger_is_skipped_in_same_session(
    postgres_test_settings: Settings,
) -> None:
    settings = _settings()
    _seed_monitor_fixture(settings)
    service = PositionMonitorService(
        settings,
        quote_provider=FakeQuoteProvider({"INFY": Decimal("1130.0000")}),
        llm_provider=FakeLLMProvider(),
        now_func=lambda: datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc),
    )

    first = service.run_once()
    second = service.run_once()

    assert first.proposals_created == 1
    assert second.proposals_created == 0
    assert second.skipped["INFY"] == "duplicate_trigger_same_market_session"


def test_quote_fetch_failure_audits_and_skips_symbol(
    postgres_test_settings: Settings,
) -> None:
    settings = _settings()
    _seed_monitor_fixture(settings)

    result = PositionMonitorService(
        settings,
        quote_provider=FakeQuoteProvider({}, fail=True),
        llm_provider=FakeLLMProvider(),
        now_func=lambda: datetime(2026, 6, 1, 5, 0, tzinfo=timezone.utc),
    ).run_once()

    with build_session_factory(settings)() as session:
        snapshots = MarketPriceSnapshotRepository(session).latest(symbol="INFY")
        audit_count = (
            session.query(AuditLogModel)
            .filter(AuditLogModel.event_type == "position_monitor.quote_fetch_failed")
            .count()
        )

    assert result.quote_failures == 1
    assert snapshots is None
    assert audit_count == 1


def _settings(
    *,
    paper_analysis_scope: str = "strategy_selected",
    profile_id: str = "local-paper",
) -> Settings:
    return Settings(
        taurus_profile_id=profile_id,
        taurus_position_monitor_enabled=True,
        taurus_position_monitor_market_hours_only=False,
        taurus_position_monitor_max_iterations=1,
        taurus_alert_provider="disabled",
        taurus_initial_capital_inr=1_000_000,
        taurus_paper_partial_fill_threshold=1,
        taurus_paper_analysis_scope=paper_analysis_scope,
    )


def _seed_monitor_fixture(settings: Settings) -> None:
    session_factory = build_session_factory(settings)
    now = datetime(2026, 5, 29, 10, 0, tzinfo=timezone.utc)
    with session_factory() as session:
        TaurusProfileRepository(session).update_profile_corpus(
            settings.effective_profile_id,
            Decimal("250000"),
        )
        session.commit()

    with session_factory() as session:
        InstrumentRepository(session).upsert(
            Instrument(
                symbol="INFY",
                name="Infosys Ltd",
                exchange="NSE",
                segment="EQUITY",
                currency="INR",
                lot_size=1,
                tick_size=Decimal("0.05"),
                active=True,
            )
        )
        CandleRepository(session).upsert(
            [
                DailyCandle(
                    symbol="INFY",
                    trade_date=date(2026, 5, 28),
                    open=Decimal("1000.0000"),
                    high=Decimal("1010.0000"),
                    low=Decimal("990.0000"),
                    close=Decimal("1000.0000"),
                    volume=100000,
                    source="test",
                    data_available_time=now,
                )
            ]
        )
        session.commit()

    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            run_id=DEFAULT_ANALYST_RUN_ID,
            llm_provider=FakeLLMProvider(),
            enabled_analysts=("technical",),
        )
    with session_factory() as session:
        debate = ResearchDebateService(session, llm_provider=FakeLLMProvider()).run(
            symbol="INFY",
            rounds_requested=2,
        )
        debate = debate.model_copy(
            update={
                "manager_summary": debate.manager_summary.model_copy(
                    update={
                        "consensus_label": "bullish",
                        "consensus_score": Decimal("0.5000"),
                    }
                )
            }
        )
    with session_factory() as session:
        proposal = TraderAgent(session, settings, llm_provider=FakeLLMProvider()).run(
            symbol="INFY",
            debate=debate,
        )
        assert proposal.take_profit_pct == TAKE_PROFIT_PCT
    with session_factory() as session:
        review = RiskReviewService(session, settings).run(
            symbol="INFY", proposal=proposal
        )
    with session_factory() as session:
        decision = PortfolioManagerAgent(
            session,
            settings,
            llm_provider=FakeLLMProvider(),
        ).run(symbol="INFY", risk_review=review)
    with session_factory() as session:
        order = ExecutionRouter(session, settings).route_decision(
            decision,
            execution_policy="immediate",
        )
        assert order is not None
        assert order.status == "FILLED"


def _seed_manual_monitor_position(
    session,
    *,
    profile_id: str,
    symbol: str,
    price: Decimal,
    quantity: int = 1,
    as_of: datetime,
) -> None:
    symbol = symbol.upper()
    InstrumentRepository(session).upsert(
        Instrument(
            symbol=symbol,
            name=f"{symbol} Ltd",
            exchange="NSE",
            segment="EQUITY",
            currency="INR",
            lot_size=1,
            tick_size=Decimal("0.05"),
            active=True,
        )
    )
    CandleRepository(session).upsert(
        [
            DailyCandle(
                symbol=symbol,
                trade_date=date(2026, 5, 28),
                open=price,
                high=price,
                low=price,
                close=price,
                volume=100000,
                source="test",
                data_available_time=as_of,
            )
        ]
    )
    run_id = f"seed-{profile_id}-{symbol.lower()}"
    run_analyst_suite(
        session,
        symbol=symbol,
        run_id=run_id,
        llm_provider=FakeLLMProvider(),
        enabled_analysts=("technical",),
    )
    market_value = price * Decimal(quantity)
    account = PaperAccount(
        account_id=paper_account_id(portfolio_id=profile_id, run_id=run_id),
        run_id=run_id,
        portfolio_id=profile_id,
        starting_cash_inr=Decimal("250000.0000"),
        available_cash_inr=Decimal("246500.0000"),
        reserved_cash_inr=Decimal("0.0000"),
        realized_pnl_inr=Decimal("0.0000"),
        unrealized_pnl_inr=Decimal("0.0000"),
        gross_exposure_inr=market_value,
        equity_inr=Decimal("250000.0000"),
        updated_at=as_of,
    )
    position = PaperPosition(
        run_id=run_id,
        portfolio_id=profile_id,
        symbol=symbol,
        quantity=quantity,
        average_cost_inr=price,
        last_price_inr=price,
        market_value_inr=market_value,
        realized_pnl_inr=Decimal("0.0000"),
        unrealized_pnl_inr=Decimal("0.0000"),
        updated_at=as_of,
    )
    source_report_ids = [f"ar-{profile_id}-{symbol.lower()}"]
    debate_id = f"deb-{profile_id}-{symbol.lower()}"
    ResearchRepository(session).replace_debate_for_run_symbol(
        DebateReport(
            debate_id=debate_id,
            run_id=run_id,
            portfolio_id=profile_id,
            symbol=symbol,
            as_of=as_of,
            rounds_requested=1,
            bull_thesis=BullThesis(
                symbol=symbol,
                score=Decimal("0.1000"),
                confidence=Decimal("0.8000"),
                key_points=["Existing monitored position."],
                conditions=["Hold while thesis remains valid."],
                source_report_ids=source_report_ids,
            ),
            bear_thesis=BearThesis(
                symbol=symbol,
                score=Decimal("-0.1000"),
                confidence=Decimal("0.8000"),
                key_points=["Monitor downside risk."],
                risk_flags=["Position thesis changes."],
                source_report_ids=source_report_ids,
            ),
            rounds=[
                DebateRound(
                    round_number=1,
                    bull_argument="Existing position remains acceptable.",
                    bear_argument="Monitor for threshold breaches.",
                    manager_note="Seeded monitor fixture.",
                )
            ],
            manager_summary=ResearchManagerSummary(
                consensus_label="neutral",
                consensus_score=Decimal("0.0000"),
                confidence=Decimal("0.8000"),
                summary="Seeded debate for monitor fixture.",
                unresolved_uncertainties=["Next market move."],
            ),
            source_report_ids=source_report_ids,
            model_version="test_monitor_seed",
        )
    )
    ResearchRepository(session).replace_trader_proposal_for_run_symbol(
        TraderProposal(
            proposal_id=f"tp-{profile_id}-{symbol.lower()}",
            run_id=run_id,
            portfolio_id=profile_id,
            symbol=symbol,
            debate_id=debate_id,
            as_of=as_of,
            action="HOLD",
            confidence=Decimal("0.8000"),
            horizon="medium",
            requested_position_pct_nav=Decimal("0.0000"),
            current_position_quantity=quantity,
            current_position_pct_nav=Decimal("2.0000"),
            target_position_pct_nav=Decimal("2.0000"),
            lifecycle_trigger="hold_review",
            evaluation_mode="after_close",
            order_type="NONE",
            entry_rule="Existing monitored position.",
            stop_loss_pct=Decimal("6.0000"),
            take_profit_pct=Decimal("12.0000"),
            reason_summary="Existing monitored position.",
            invalid_if=["Position thesis changes."],
            position_management_summary="Existing monitored position.",
            source_report_ids=source_report_ids,
            is_order=False,
            requires_risk_approval=True,
            model_version="test_monitor_seed",
        )
    )
    ExecutionRepository(session).replace_account_state(
        run_id=run_id,
        portfolio_id=profile_id,
        account=account,
        positions=[position],
    )
