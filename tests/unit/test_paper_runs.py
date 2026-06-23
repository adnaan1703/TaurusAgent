from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.exc import DataError

from apps.api.main import create_app
from apps.dashboard.data import list_paper_runs
from scripts.run_paper_loop import _resolve_symbols_from_env, run_paper_loop
from taurus_core.config import Settings
from taurus_core.data.universe import load_market_data_universe
from taurus_core.brokers.paper_broker import PaperBroker
from taurus_core.db.models import (
    AnalystReportModel,
    AuditLogModel,
    DebateReportModel,
    FinalDecisionModel,
    PaperOrderModel,
    PaperRunModel,
    RiskReviewModel,
    TraderProposalModel,
)
from taurus_core.db.repositories import (
    ExecutionRepository,
    GraphRepository,
    InstrumentRepository,
    TaurusProfileRepository,
)
from taurus_core.db.repositories import (
    PaperRunRepository,
    ResearchRepository,
    RiskRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.execution.schemas import (
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
    paper_account_id,
    paper_fill_id,
    paper_order_id,
)
from taurus_core.features.technical_signal import OHLCV_V2_PROFILE
from taurus_core.paper_trading.schemas import PaperRun, PaperRunUniverse, paper_run_id
from taurus_core.paper_trading.service import (
    ANALYSIS_STAGE_NAMES,
    FINALIZATION_STAGE_NAMES,
    PaperSymbolAnalysis,
    PaperRunService,
    _execution_symbol_order,
    _sleeve_snapshots_for_allocation,
    _symbol_artifact_from_results,
)
from taurus_core.portfolio import (
    ActiveAllocationPosition,
    PortfolioRebalancePlanInput,
    PortfolioRebalancePlanService,
    RunAllocationResult,
    load_money_management_policy,
)
from taurus_core.portfolio.run_allocation import AllocationLedgerEntry
from taurus_core.profiles.runtime import RuntimeProfileError
from taurus_core.profiles.schemas import TaurusProfileCreate
from taurus_core.research.schemas import (
    BearThesis,
    BullThesis,
    DebateReport,
    DebateRound,
    ResearchManagerSummary,
    TraderProposal,
)
from taurus_core.risk.schemas import (
    FinalDecision,
    HardRuleResult,
    RiskPersonaReview,
    RiskReview,
)
from tests.llm_fakes import FakeLLMProvider
from tests.market_data_fixtures import (
    FakeKiteMarketDataProvider,
    TEST_INSTRUMENTS,
    build_test_candles_for_symbol,
)


@pytest.fixture(autouse=True)
def fake_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_llm_provider",
        lambda settings: FakeLLMProvider(),
    )
    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_market_data_provider",
        lambda settings: FakeKiteMarketDataProvider(),
    )


def test_execution_symbol_order_queues_sell_side_before_buys() -> None:
    allocation_result = RunAllocationResult(
        proposals=tuple(),
        ledger=(
            _ledger_entry(
                symbol="AAA", action="BUY", status="selected", planner_rank=1
            ),
            _ledger_entry(
                symbol="TCS",
                action="EXIT",
                status="open_position_management",
                planner_rank=99,
            ),
        ),
        summary={},
        binding_constraints={},
        policy_source="portfolio_plan",
    )
    finalizations = {
        "AAA": SimpleNamespace(
            final_decision=_final_decision(symbol="AAA", action="BUY")
        ),
        "TCS": SimpleNamespace(
            final_decision=_final_decision(symbol="TCS", action="EXIT")
        ),
    }

    assert _execution_symbol_order(
        finalizations, allocation_result=allocation_result
    ) == [
        "TCS",
        "AAA",
    ]


def test_paper_run_service_executes_full_chain_and_api_returns_runs(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["INFY"])

    assert run.run_id.startswith("pr-")
    assert run.status == "COMPLETED"
    assert run.succeeded_symbols == ["INFY"]
    assert run.failed_symbols == []
    assert run.completed_at is not None
    assert run.market_data_summary["provider_name"] == "kite"
    assert run.market_data_summary["candle_count"] >= 252
    assert run.artifacts["strategy"]["strategy_name"]
    assert run.artifacts["portfolio_plan"]["run_id"] == run.run_id
    assert run.artifacts["portfolio_plan"]["portfolio_id"] == "local-paper"
    assert (
        run.artifacts["portfolio_plan"]["model_version"]
        == "portfolio_rebalance_plan_v3"
    )
    assert run.artifacts["portfolio_plan"]["planned_trades"][0]["symbol"] == "INFY"
    assert run.artifacts["symbols"]["INFY"]["final_status"] == "APPROVED_FOR_PAPER"
    assert run.artifacts["symbols"]["INFY"]["order_status"] == "PENDING_NEXT_OPEN"
    assert (
        run.artifacts["symbols"]["INFY"]["order_reason"]
        == "queued_for_next_open_settlement"
    )
    assert run.artifacts["symbols"]["INFY"]["analyst_roster"] == {
        "enabled": ["technical"],
        "skipped": ["news", "sentiment", "fundamentals", "graph"],
        "report_count": 1,
        "min_required": 1,
        "status": "enough_reports",
    }
    llm_usage = run.artifacts["llm_usage"]
    assert llm_usage["provider"] == "fake"
    assert llm_usage["request_count"] == 6
    assert llm_usage["input_tokens"] == 6000
    assert llm_usage["output_tokens"] == 1500
    assert llm_usage["total_tokens"] == 7500
    assert llm_usage["cached_input_tokens"] == 0
    assert llm_usage["reasoning_tokens"] == 0
    assert llm_usage["elapsed_seconds"] == 3.0
    assert {row["agent_name"] for row in llm_usage["by_agent"]} == {
        "BearResearcherAgent",
        "BullResearcherAgent",
        "PortfolioManagerAgent",
        "ResearchManagerAgent",
        "TechnicalAnalystAgent",
        "TraderAgent",
    }

    client = TestClient(create_app(settings))
    runs_response = client.get("/runs")
    run_response = client.get(f"/runs/{run.run_id}")

    assert runs_response.status_code == 200
    assert run_response.status_code == 200
    assert runs_response.json()[0]["run_id"] == run.run_id
    assert run_response.json()["status"] == "COMPLETED"

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        dashboard_runs = list_paper_runs(session)
        order_count = session.scalar(select(func.count()).select_from(PaperOrderModel))

    assert dashboard_runs[0]["run_id"] == run.run_id
    assert dashboard_runs[0]["status"] == "COMPLETED"
    assert order_count == 1


def test_paper_run_profile_lineage_and_repository_filters(tmp_path: Path) -> None:
    client_settings = _settings_for_temp_db(tmp_path, profile_id="client-a")
    local_settings = _settings_for_temp_db(tmp_path, profile_id="local-paper")
    session_factory = build_session_factory(client_settings)
    _create_profile(
        session_factory, profile_id="client-a", corpus_inr=Decimal("250000")
    )
    client_run = PaperRunService(client_settings).run_once(symbols=["INFY"])
    local_run = PaperRunService(local_settings).run_once(symbols=["INFY"])

    assert client_run.portfolio_id == "client-a"
    assert local_run.portfolio_id == "local-paper"
    assert client_run.artifacts["profile"] == {
        "profile_id": "client-a",
        "starting_corpus_inr": "250000.0000",
        "currency": "INR",
    }
    assert client_run.run_id == paper_run_id(
        started_at=client_run.started_at,
        symbols=client_run.symbols,
        schedule_name=client_run.schedule_name,
        portfolio_id="client-a",
    )
    assert client_run.run_id != paper_run_id(
        started_at=client_run.started_at,
        symbols=client_run.symbols,
        schedule_name=client_run.schedule_name,
    )

    with session_factory() as session:
        stored_run = session.get(PaperRunModel, client_run.run_id)
        assert stored_run is not None
        assert stored_run.portfolio_id == "client-a"
        assert stored_run.payload["portfolio_id"] == "client-a"

        audit_payloads = [
            row.payload
            for row in session.scalars(
                select(AuditLogModel)
                .where(AuditLogModel.payload["run_id"].as_string() == client_run.run_id)
                .where(
                    AuditLogModel.event_type.in_(
                        ["paper_run.started", "paper_run.completed"]
                    )
                )
            )
        ]
        assert audit_payloads
        assert {payload["portfolio_id"] for payload in audit_payloads} == {"client-a"}

        assert {
            run.run_id
            for run in PaperRunRepository(session).list(profile_id="client-a")
        } == {client_run.run_id}
        assert {
            run.run_id
            for run in PaperRunRepository(session).list(profile_id="local-paper")
        } == {local_run.run_id}

        research_repo = ResearchRepository(session)
        risk_repo = RiskRepository(session)
        assert {
            debate.run_id
            for debate in research_repo.list_debates(profile_id="client-a", limit=None)
        } == {client_run.run_id}
        assert {
            proposal.run_id
            for proposal in research_repo.list_trader_proposals(
                profile_id="client-a", limit=None
            )
        } == {client_run.run_id}
        assert {
            review.run_id
            for review in risk_repo.list_risk_reviews(profile_id="client-a", limit=None)
        } == {client_run.run_id}
        assert {
            decision.run_id
            for decision in risk_repo.list_final_decisions(
                profile_id="client-a", limit=None
            )
        } == {client_run.run_id}
        assert {
            decision.run_id
            for decision in risk_repo.list_final_decisions(
                profile_id="local-paper", limit=None
            )
        } == {local_run.run_id}

        for model in (
            session.scalars(
                select(AnalystReportModel).where(
                    AnalystReportModel.run_id == client_run.run_id
                )
            ).all(),
            session.scalars(
                select(DebateReportModel).where(
                    DebateReportModel.run_id == client_run.run_id
                )
            ).all(),
            session.scalars(
                select(TraderProposalModel).where(
                    TraderProposalModel.run_id == client_run.run_id
                )
            ).all(),
            session.scalars(
                select(RiskReviewModel).where(
                    RiskReviewModel.run_id == client_run.run_id
                )
            ).all(),
            session.scalars(
                select(FinalDecisionModel).where(
                    FinalDecisionModel.run_id == client_run.run_id
                )
            ).all(),
        ):
            assert model
            assert {row.portfolio_id for row in model} == {"client-a"}
            assert {row.payload["portfolio_id"] for row in model} == {"client-a"}

        client_account = ExecutionRepository(session).latest_account_by_portfolio(
            portfolio_id="client-a"
        )
        local_account = ExecutionRepository(session).latest_account_by_portfolio(
            portfolio_id="local-paper"
        )
        assert client_account is not None
        assert local_account is not None
        assert client_account.starting_cash_inr == Decimal("250000.0000")
        assert local_account.starting_cash_inr == Decimal("10000.0000")


def test_paper_run_rejects_missing_runtime_profile(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path, profile_id="missing-profile")

    with pytest.raises(RuntimeProfileError, match="Profile missing-profile not found"):
        PaperRunService(settings).run_once(symbols=["INFY"])


def test_paper_run_rejects_archived_runtime_profile(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path, profile_id="client-a")
    session_factory = build_session_factory(settings)
    _create_profile(
        session_factory, profile_id="client-a", corpus_inr=Decimal("250000")
    )
    with session_factory() as session:
        TaurusProfileRepository(session).archive_profile("client-a")
        session.commit()

    with pytest.raises(RuntimeProfileError, match="Profile client-a is archived"):
        PaperRunService(settings).run_once(symbols=["INFY"])


def test_legacy_paper_run_payload_without_profile_defaults_to_local_paper(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    as_of = datetime(2026, 6, 8, 15, 30, tzinfo=timezone.utc)
    legacy_payload = {
        "run_id": "pr-legacy-no-profile",
        "schedule_name": "daily_after_close",
        "status": "COMPLETED",
        "started_at": as_of.isoformat(),
        "completed_at": as_of.isoformat(),
        "symbols": ["INFY"],
        "succeeded_symbols": ["INFY"],
        "failed_symbols": [],
        "errors": [],
        "market_data_summary": {},
        "artifacts": {},
        "timezone": "Asia/Kolkata",
        "run_after_market_close": True,
        "universe": None,
        "model_version": "paper_run_v1",
    }
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        session.add(
            PaperRunModel(
                run_id="pr-legacy-no-profile",
                portfolio_id="local-paper",
                schedule_name="daily_after_close",
                status="COMPLETED",
                started_at=as_of,
                completed_at=as_of,
                symbols=["INFY"],
                succeeded_symbols=["INFY"],
                failed_symbols=[],
                errors=[],
                market_data_summary={},
                artifacts={},
                timezone="Asia/Kolkata",
                run_after_market_close=True,
                payload=legacy_payload,
            )
        )
        session.commit()

    with session_factory() as session:
        stored_run = PaperRunRepository(session).get("pr-legacy-no-profile")
        assert stored_run is not None
        assert PaperRun.model_validate(stored_run.payload).portfolio_id == "local-paper"


def test_paper_run_records_symbol_failure_without_losing_success(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["INFY", "MISSING"])

    assert run.status == "PARTIAL_FAILED"
    assert run.succeeded_symbols == ["INFY"]
    assert run.failed_symbols == ["MISSING"]
    assert run.errors[0].symbol == "MISSING"
    assert run.errors[0].stage == "symbol_pipeline"

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        stored_run = session.get(PaperRunModel, run.run_id)
        order_count = session.scalar(select(func.count()).select_from(PaperOrderModel))
        failure_audits = session.scalar(
            select(func.count())
            .select_from(AuditLogModel)
            .where(AuditLogModel.event_type == "paper_run.symbol_failed")
        )

    assert stored_run is not None
    assert stored_run.status == "PARTIAL_FAILED"
    assert order_count == 1
    assert failure_audits == 1


def test_paper_run_aborts_on_systemic_symbol_persistence_error(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings_for_temp_db(tmp_path, paper_analysis_scope="full_universe")
    attempted_symbols: list[str] = []

    def fail_trader_persistence(
        agent,
        *,
        symbol: str,
        run_id: str,
        debate,
    ):
        attempted_symbols.append(symbol)
        raise DataError(
            "INSERT INTO trader_proposals",
            {},
            Exception("value too long for type character varying(128)"),
        )

    monkeypatch.setattr(
        "taurus_core.paper_trading.service.TraderAgent.run",
        fail_trader_persistence,
    )

    run = PaperRunService(settings).run_once(
        symbols=["INFY", "TCS", "RELIANCE"],
        universe=_paper_run_universe(
            source="market_data_universe",
            symbols=["INFY", "TCS", "RELIANCE"],
        ),
    )

    assert run.status == "FAILED"
    assert run.completed_at is not None
    assert run.failed_symbols == ["INFY"]
    assert len(run.errors) == 1
    assert run.errors[0].error_type == "DataError"
    assert attempted_symbols == ["INFY"]

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        stored_run = session.get(PaperRunModel, run.run_id)
        proposal_count = session.scalar(
            select(func.count())
            .select_from(TraderProposalModel)
            .where(TraderProposalModel.run_id == run.run_id)
        )

    assert stored_run is not None
    assert stored_run.status == "FAILED"
    assert proposal_count == 0


def test_paper_run_succeeds_without_fundamentals(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical,news,sentiment",
    )
    run = PaperRunService(settings).run_once(symbols=["INFY"])

    roster = run.artifacts["symbols"]["INFY"]["analyst_roster"]

    assert run.status == "COMPLETED"
    assert roster == {
        "enabled": ["technical", "news", "sentiment"],
        "skipped": ["fundamentals", "graph"],
        "report_count": 3,
        "min_required": 1,
        "status": "enough_reports",
    }

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        agent_names = {
            row.agent_name for row in session.scalars(select(AnalystReportModel))
        }

    assert agent_names == {
        "TechnicalAnalystAgent",
        "NewsAnalystAgent",
        "SentimentAnalystAgent",
    }


def test_paper_run_succeeds_with_technical_only_roster(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path, enabled_analysts="technical")
    run = PaperRunService(settings).run_once(symbols=["INFY"])

    roster = run.artifacts["symbols"]["INFY"]["analyst_roster"]

    assert run.status == "COMPLETED"
    assert run.succeeded_symbols == ["INFY"]
    assert roster == {
        "enabled": ["technical"],
        "skipped": ["news", "sentiment", "fundamentals", "graph"],
        "report_count": 1,
        "min_required": 1,
        "status": "enough_reports",
    }


def test_paper_run_includes_open_position_symbols_across_runs(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path, enabled_analysts="technical")
    first = PaperRunService(
        settings,
        schedule_name="open_position_seed",
        run_after_market_close=False,
    ).run_once(symbols=["INFY"])
    second = PaperRunService(settings, schedule_name="open_position_review").run_once(
        symbols=["TCS"]
    )

    assert first.status == "COMPLETED"
    assert "INFY" in second.symbols
    assert "TCS" in second.symbols
    assert (
        second.artifacts["strategy"]["symbol_selection"]["INFY"][
            "included_from_open_position"
        ]
        is True
    )
    assert (
        second.artifacts["strategy"]["symbol_selection"]["TCS"]["requested_explicitly"]
        is True
    )


def test_eod_paper_run_settles_prior_pending_orders_before_new_decisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings_for_temp_db(tmp_path, enabled_analysts="technical")
    candle_count = {"value": 252}

    class AdvancingFakeKiteMarketDataProvider(FakeKiteMarketDataProvider):
        def get_daily_candles(self, symbol: str):
            symbols = [instrument.symbol for instrument in TEST_INSTRUMENTS]
            symbol_index = symbols.index(symbol.upper())
            return build_test_candles_for_symbol(
                symbol=symbol.upper(),
                symbol_index=symbol_index,
                candle_count=candle_count["value"],
                source="kite:historical:NSE",
            )

    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_market_data_provider",
        lambda settings: AdvancingFakeKiteMarketDataProvider(),
    )

    first = PaperRunService(settings, schedule_name="m48_buy_queue").run_once(
        symbols=["INFY"]
    )
    assert first.status == "COMPLETED"
    assert first.artifacts["settlement"]["settled"] == 0
    assert first.artifacts["symbols"]["INFY"]["order_status"] == "PENDING_NEXT_OPEN"

    candle_count["value"] = 253
    forced_actions = {"INFY": "EXIT"}
    _force_trader_actions(monkeypatch, forced_actions)
    second = PaperRunService(
        settings, schedule_name="m48_buy_settle_exit_queue"
    ).run_once(symbols=["INFY"])
    second_settlement = second.artifacts["settlement"]
    second_symbol = second.artifacts["symbols"]["INFY"]

    assert second.status == "COMPLETED"
    assert second_settlement["settled"] == 1
    assert second_settlement["rejected"] == 0
    assert second_settlement["still_pending"] == 0
    assert second_settlement["details"][0]["side"] == "BUY"
    assert second_settlement["details"][0]["status"] == "FILLED"
    assert second_symbol["settlement"]["settled"] == 1
    assert second_symbol["current_position_quantity"] > 0
    assert second_symbol["proposal_action"] == "EXIT"
    assert second_symbol["order_status"] == "PENDING_NEXT_OPEN"
    assert second_symbol["order_reason"] == "queued_for_next_open_settlement"

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        second_fills = ExecutionRepository(session).list_fills_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
            symbol="INFY",
        )
        second_positions = ExecutionRepository(
            session
        ).latest_open_positions_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
        )

    assert [fill.side for fill in second_fills] == ["BUY"]
    assert {position.symbol: position.quantity for position in second_positions}[
        "INFY"
    ] > 0

    candle_count["value"] = 254
    forced_actions["INFY"] = "NO_TRADE"
    third = PaperRunService(settings, schedule_name="m48_exit_settle").run_once(
        symbols=["INFY"]
    )
    third_settlement = third.artifacts["settlement"]

    with session_factory() as session:
        third_fills = ExecutionRepository(session).list_fills_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
            symbol="INFY",
        )
        latest_account = ExecutionRepository(session).latest_account_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
        )
        latest_positions = ExecutionRepository(
            session
        ).latest_open_positions_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
        )

    assert third.status == "COMPLETED"
    assert third_settlement["settled"] == 1
    assert third_settlement["details"][0]["side"] == "SELL"
    assert third_settlement["details"][0]["status"] == "FILLED"
    assert [fill.side for fill in third_fills] == ["BUY", "SELL"]
    assert latest_account is not None
    assert Decimal(str(latest_account.realized_pnl_inr)) != Decimal("0")
    assert latest_positions == []

    client = TestClient(create_app(settings))
    orders_response = client.get("/paper/orders?symbol=INFY")
    fills_response = client.get("/paper/fills?symbol=INFY")
    positions_response = client.get("/paper/positions?symbol=INFY")
    account_response = client.get("/paper/account")
    overview_response = client.get("/ui/overview")
    second_detail_response = client.get(f"/ui/runs/{second.run_id}")
    third_detail_response = client.get(f"/ui/runs/{third.run_id}")

    assert orders_response.status_code == 200
    assert fills_response.status_code == 200
    assert positions_response.status_code == 200
    assert account_response.status_code == 200
    assert overview_response.status_code == 200
    assert second_detail_response.status_code == 200
    assert third_detail_response.status_code == 200

    api_orders = orders_response.json()
    api_fills = fills_response.json()
    api_account = account_response.json()
    api_overview = overview_response.json()
    second_detail = second_detail_response.json()
    third_detail = third_detail_response.json()
    orders_by_side = {order["side"]: order for order in api_orders}
    fill_sides = {fill["side"] for fill in api_fills}

    assert len(api_orders) == 2
    assert set(orders_by_side) == {"BUY", "SELL"}
    assert orders_by_side["BUY"]["status"] == "FILLED"
    assert orders_by_side["SELL"]["status"] == "FILLED"
    assert orders_by_side["BUY"]["execution_policy"] == "next_open"
    assert orders_by_side["SELL"]["execution_policy"] == "next_open"
    assert (
        orders_by_side["BUY"]["signal_trade_date"]
        < orders_by_side["BUY"]["filled_trade_date"]
    )
    assert (
        orders_by_side["SELL"]["signal_trade_date"]
        < orders_by_side["SELL"]["filled_trade_date"]
    )
    assert len(api_fills) == 2
    assert fill_sides == {"BUY", "SELL"}
    assert positions_response.json() == []
    assert api_account["run_id"] == third.run_id
    assert Decimal(str(api_account["realized_pnl_inr"])) != Decimal("0")
    assert api_overview["latest_run"]["run_id"] == third.run_id
    assert api_overview["latest_run"]["settlement_summary"]["settled"] == 1
    assert api_overview["latest_run"]["settlement_summary"]["status_counts"] == {
        "FILLED": 1
    }
    assert second_detail["symbols"][0]["order_status"] == "FILLED"
    assert second_detail["artifacts"]["symbols"]["INFY"]["proposal_action"] == "EXIT"
    assert (
        second_detail["artifacts"]["symbols"]["INFY"]["order_status"]
        == "PENDING_NEXT_OPEN"
    )
    assert third_detail["artifacts"]["settlement"]["settled"] == 1
    assert third_detail["artifacts"]["settlement"]["details"][0]["side"] == "SELL"
    assert third_detail["artifacts"]["settlement"]["details"][0]["status"] == "FILLED"


def test_m55_multi_profile_regression_keeps_settled_dashboard_state_isolated(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    local_settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical",
        profile_id="local-paper",
    )
    client_settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical",
        profile_id="client-a",
    )
    candle_count = {"value": 252}

    class AdvancingFakeKiteMarketDataProvider(FakeKiteMarketDataProvider):
        def get_daily_candles(self, symbol: str):
            symbols = [instrument.symbol for instrument in TEST_INSTRUMENTS]
            symbol_index = symbols.index(symbol.upper())
            return build_test_candles_for_symbol(
                symbol=symbol.upper(),
                symbol_index=symbol_index,
                candle_count=candle_count["value"],
                source="kite:historical:NSE",
            )

    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_market_data_provider",
        lambda settings: AdvancingFakeKiteMarketDataProvider(),
    )

    session_factory = build_session_factory(local_settings)
    _create_profile(
        session_factory, profile_id="client-a", corpus_inr=Decimal("250000")
    )
    with session_factory() as session:
        TaurusProfileRepository(session).update_profile_corpus(
            "local-paper",
            Decimal("100000"),
        )
        session.commit()

    client = TestClient(create_app(local_settings))
    local_first = PaperRunService(
        local_settings,
        schedule_name="m55_local_buy_queue",
    ).run_once(symbols=["INFY"])
    client_first = PaperRunService(
        client_settings,
        schedule_name="m55_client_buy_queue",
    ).run_once(symbols=["INFY"])

    for profile_id, run in [
        ("local-paper", local_first),
        ("client-a", client_first),
    ]:
        orders = client.get(f"/paper/orders?profile_id={profile_id}").json()
        fills = client.get(f"/paper/fills?profile_id={profile_id}").json()
        account = client.get(f"/paper/account?profile_id={profile_id}").json()
        assert run.artifacts["symbols"]["INFY"]["order_status"] == "PENDING_NEXT_OPEN"
        assert [order["status"] for order in orders] == ["PENDING_NEXT_OPEN"]
        assert fills == []
        assert account["portfolio_id"] == profile_id
        assert account["run_id"] == run.run_id

    assert _decimal(
        client.get("/paper/account?profile_id=local-paper").json()["starting_cash_inr"]
    ) == Decimal("100000.0000")
    assert _decimal(
        client.get("/paper/account?profile_id=client-a").json()["starting_cash_inr"]
    ) == Decimal("250000.0000")

    candle_count["value"] = 253
    forced_actions = {"INFY": "EXIT"}
    _force_trader_actions(monkeypatch, forced_actions)
    local_second = PaperRunService(
        local_settings,
        schedule_name="m55_local_buy_settle_exit_queue",
    ).run_once(symbols=["INFY"])
    client_second = PaperRunService(
        client_settings,
        schedule_name="m55_client_buy_settle_exit_queue",
    ).run_once(symbols=["INFY"])

    local_after_buy = client.get("/paper/account?profile_id=local-paper").json()
    client_after_buy = client.get("/paper/account?profile_id=client-a").json()
    assert local_second.artifacts["settlement"]["details"][0]["side"] == "BUY"
    assert client_second.artifacts["settlement"]["details"][0]["side"] == "BUY"
    assert _decimal(local_after_buy["unrealized_pnl_inr"]) != Decimal("0.0000")
    assert _decimal(client_after_buy["unrealized_pnl_inr"]) != Decimal("0.0000")
    assert _decimal(local_after_buy["unrealized_pnl_inr"]) != _decimal(
        client_after_buy["unrealized_pnl_inr"]
    )
    assert {
        order["side"]: order["status"]
        for order in client.get("/paper/orders?profile_id=local-paper").json()
    } == {
        "BUY": "FILLED",
        "SELL": "PENDING_NEXT_OPEN",
    }
    assert {
        order["side"]: order["status"]
        for order in client.get("/paper/orders?profile_id=client-a").json()
    } == {
        "BUY": "FILLED",
        "SELL": "PENDING_NEXT_OPEN",
    }
    assert {
        position["portfolio_id"]
        for position in client.get("/paper/positions?profile_id=local-paper").json()
    } == {"local-paper"}
    assert {
        position["portfolio_id"]
        for position in client.get("/paper/positions?profile_id=client-a").json()
    } == {"client-a"}
    assert {
        fill["portfolio_id"]
        for fill in client.get("/paper/fills?profile_id=local-paper").json()
    } == {"local-paper"}
    assert {
        fill["portfolio_id"]
        for fill in client.get("/paper/fills?profile_id=client-a").json()
    } == {"client-a"}

    candle_count["value"] = 254
    forced_actions["INFY"] = "NO_TRADE"
    local_third = PaperRunService(
        local_settings,
        schedule_name="m55_local_exit_settle",
    ).run_once(symbols=["INFY"])
    client_third = PaperRunService(
        client_settings,
        schedule_name="m55_client_exit_settle",
    ).run_once(symbols=["INFY"])

    local_orders = client.get("/paper/orders?profile_id=local-paper").json()
    client_orders = client.get("/paper/orders?profile_id=client-a").json()
    local_fills = client.get("/paper/fills?profile_id=local-paper").json()
    client_fills = client.get("/paper/fills?profile_id=client-a").json()
    local_account = client.get("/paper/account?profile_id=local-paper").json()
    client_account = client.get("/paper/account?profile_id=client-a").json()
    local_history = client.get("/ui/history?profile_id=local-paper").json()
    client_history = client.get("/ui/history?profile_id=client-a").json()
    local_overview = client.get("/ui/overview?profile_id=local-paper").json()
    client_overview = client.get("/ui/overview?profile_id=client-a").json()
    local_portfolio = client.get("/ui/portfolio?profile_id=local-paper").json()
    client_portfolio = client.get("/ui/portfolio?profile_id=client-a").json()

    assert local_third.artifacts["settlement"]["details"][0]["side"] == "SELL"
    assert client_third.artifacts["settlement"]["details"][0]["side"] == "SELL"
    assert {order["side"]: order["status"] for order in local_orders} == {
        "BUY": "FILLED",
        "SELL": "FILLED",
    }
    assert {order["side"]: order["status"] for order in client_orders} == {
        "BUY": "FILLED",
        "SELL": "FILLED",
    }
    assert {fill["side"] for fill in local_fills} == {"BUY", "SELL"}
    assert {fill["side"] for fill in client_fills} == {"BUY", "SELL"}
    assert client.get("/paper/positions?profile_id=local-paper").json() == []
    assert client.get("/paper/positions?profile_id=client-a").json() == []
    assert local_account["portfolio_id"] == "local-paper"
    assert client_account["portfolio_id"] == "client-a"
    assert local_account["run_id"] == local_third.run_id
    assert client_account["run_id"] == client_third.run_id
    assert _decimal(local_account["realized_pnl_inr"]) != Decimal("0.0000")
    assert _decimal(client_account["realized_pnl_inr"]) != Decimal("0.0000")
    assert _decimal(local_account["realized_pnl_inr"]) != _decimal(
        client_account["realized_pnl_inr"]
    )

    assert [run["run_id"] for run in local_history["runs"]] == [
        local_third.run_id,
        local_second.run_id,
        local_first.run_id,
    ]
    assert [run["run_id"] for run in client_history["runs"]] == [
        client_third.run_id,
        client_second.run_id,
        client_first.run_id,
    ]
    assert {run["profile_id"] for run in local_history["runs"]} == {"local-paper"}
    assert {run["profile_id"] for run in client_history["runs"]} == {"client-a"}
    assert local_overview["active_profile"]["profile_id"] == "local-paper"
    assert client_overview["active_profile"]["profile_id"] == "client-a"
    assert local_overview["latest_run"]["run_id"] == local_third.run_id
    assert client_overview["latest_run"]["run_id"] == client_third.run_id
    assert local_overview["latest_account"]["portfolio_id"] == "local-paper"
    assert client_overview["latest_account"]["portfolio_id"] == "client-a"
    assert local_overview["latest_final_decision"]["portfolio_id"] == "local-paper"
    assert client_overview["latest_final_decision"]["portfolio_id"] == "client-a"
    assert local_overview["latest_order"]["portfolio_id"] == "local-paper"
    assert client_overview["latest_order"]["portfolio_id"] == "client-a"
    assert local_portfolio["latest_account"]["portfolio_id"] == "local-paper"
    assert client_portfolio["latest_account"]["portfolio_id"] == "client-a"
    assert {order["portfolio_id"] for order in local_portfolio["orders"]} == {
        "local-paper"
    }
    assert {order["portfolio_id"] for order in client_portfolio["orders"]} == {
        "client-a"
    }
    assert {fill["portfolio_id"] for fill in local_portfolio["fills"]} == {
        "local-paper"
    }
    assert {fill["portfolio_id"] for fill in client_portfolio["fills"]} == {"client-a"}

    assert (
        client.get(f"/ui/runs/{client_third.run_id}?profile_id=local-paper").status_code
        == 404
    )
    assert (
        client.get(
            f"/paper/account?profile_id=client-a&run_id={local_third.run_id}"
        ).status_code
        == 404
    )
    assert client.get("/ui/overview?profile_id=missing-profile").status_code == 404
    assert client.get("/paper/orders?profile_id=missing-profile").status_code == 404


def test_eod_paper_run_records_pending_orders_waiting_for_newer_candle(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path, enabled_analysts="technical")
    first = PaperRunService(settings, schedule_name="m48_waiting_seed").run_once(
        symbols=["INFY"]
    )
    second = PaperRunService(settings, schedule_name="m48_waiting_review").run_once(
        symbols=["TCS"]
    )

    settlement = second.artifacts["settlement"]
    scope = second.artifacts["symbol_scope"]

    assert first.artifacts["symbols"]["INFY"]["order_status"] == "PENDING_NEXT_OPEN"
    assert second.status == "COMPLETED"
    assert settlement["settled"] == 0
    assert settlement["still_pending"] == 1
    assert settlement["still_pending_order_count"] == 1
    assert settlement["still_pending_orders"][0]["symbol"] == "INFY"
    assert (
        settlement["still_pending_orders"][0]["outcome_reason"]
        == "waiting_for_next_candle"
    )
    assert "INFY" in scope["pending_next_open_order_symbols"]
    assert "INFY" in scope["analyzed_symbols"]
    assert (
        second.artifacts["strategy"]["symbol_selection"]["INFY"][
            "included_from_pending_next_open_order"
        ]
        is True
    )


def test_money_management_paper_run_creates_shariah_equity_core_decisions(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        money_management_enabled=True,
        profile_id="client-a",
    )
    _create_profile(
        build_session_factory(settings),
        profile_id="client-a",
        corpus_inr=Decimal("1000000"),
    )
    run = PaperRunService(settings).run_once(symbols=["INFY"])
    universe = load_market_data_universe("configs/market_data/nifty_500_shariah.yaml")
    universe_by_symbol = {entry.symbol: entry for entry in universe.symbols}

    core = run.artifacts["money_management"]["core_shariah_basket"]
    plan = run.artifacts["portfolio_plan"]
    decision_symbols = {decision["symbol"] for decision in core["decisions"]}
    core_candidate_symbols = {
        candidate["symbol"]
        for candidate in plan["candidates"]
        if candidate["source"] == "core_shariah_basket_v1"
    }

    assert run.status == "COMPLETED"
    assert core["strategy_name"] == "core_shariah_basket_v1"
    assert set(core["selected_symbols"]).issubset(set(universe_by_symbol))
    assert decision_symbols == set(core["target_weights"])
    assert core_candidate_symbols == decision_symbols
    assert decision_symbols
    for symbol in decision_symbols:
        universe_symbol = universe_by_symbol[symbol]
        assert universe_symbol.exchange == "NSE"
        assert universe_symbol.segment == "EQUITY"
    assert all(
        Decimal(str(weight)) <= Decimal("7.5")
        for weight in core["target_weights"].values()
    )


def test_sleeve_snapshots_attribute_runtime_core_basket_holdings(
    tmp_path: Path,
) -> None:
    policy_path = _write_active_allocation_policy(
        tmp_path, max_stock_pct=Decimal("5.0")
    )
    policy = load_money_management_policy(policy_path)

    snapshots = _sleeve_snapshots_for_allocation(
        policy=policy,
        nav_inr=Decimal("1000000"),
        positions=(
            ActiveAllocationPosition(
                symbol="INFY",
                quantity=1000,
                market_value_inr=Decimal("100000.00"),
            ),
            ActiveAllocationPosition(
                symbol="TCS",
                quantity=500,
                market_value_inr=Decimal("50000.00"),
            ),
        ),
        core_basket_symbols={"INFY"},
        sleeve_by_symbol={"TCS": "diversifying_strategy"},
    )
    by_sleeve = {snapshot.sleeve_id: snapshot for snapshot in snapshots}

    assert by_sleeve["core_shariah"].current_exposure_inr == Decimal("100000.00")
    assert by_sleeve["core_shariah"].open_position_count == 1
    assert by_sleeve["active_strategy"].current_exposure_inr == Decimal("0.00")
    assert by_sleeve["active_strategy"].open_position_count == 0
    assert by_sleeve["diversifying_strategy"].current_exposure_inr == Decimal(
        "50000.00"
    )
    assert by_sleeve["diversifying_strategy"].open_position_count == 1


def test_graph_enabled_kite_paper_run_uses_graph_roster_strategy_and_risk(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical,graph",
        graph_enabled=True,
        graph_risk_enabled=True,
    )
    _seed_paper_graph_fixture(settings)

    run = PaperRunService(settings).run_once(
        symbols=["INFY"],
        strategy_config_path="configs/strategies/graph_aware_score_v1.yaml",
    )
    strategy = run.artifacts["strategy"]
    roster = run.artifacts["symbols"]["INFY"]["analyst_roster"]

    assert run.status == "COMPLETED"
    assert strategy["graph_enabled_profile"] is True
    assert strategy["graph_risk_enabled"] is True
    assert strategy["graph_signal_count"] >= 1
    assert "INFY" in strategy["symbols_with_graph_signals"]
    assert (
        strategy["graph_strategy_config_path"]
        == "configs/strategies/graph_aware_score_v1.yaml"
    )
    assert strategy["select_targets_with_graph_called"] is True
    assert strategy["eligible_symbol_count"] >= 1
    assert strategy["ranked_symbol_count"] >= 1
    assert strategy["ranked_candidates"]
    assert "INFY" in strategy["strategy_score_by_symbol"]
    assert strategy["symbol_selection"]["INFY"]["selection_source"] == "explicit_symbol"
    assert strategy["symbol_selection"]["INFY"]["has_graph_signal"] is True
    assert roster["enabled"] == ["technical", "graph"]

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        agent_names = {
            row.agent_name for row in session.scalars(select(AnalystReportModel))
        }
        risk_review = session.scalars(select(RiskReviewModel)).first()

    assert "GraphAnalystAgent" in agent_names
    assert risk_review is not None
    hard_rules = {row["rule"] for row in risk_review.hard_rule_results}
    assert "graph_correlated_cluster_concentration" in hard_rules


def test_graph_aware_v2_paper_run_passes_universe_context_to_technical_analyst(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical,graph",
        graph_enabled=True,
        graph_risk_enabled=True,
        paper_analysis_scope="full_universe",
    )
    _seed_paper_graph_fixture(settings)

    class LongHistoryFakeKiteMarketDataProvider(FakeKiteMarketDataProvider):
        def get_daily_candles(self, symbol: str):
            symbols = [instrument.symbol for instrument in TEST_INSTRUMENTS]
            symbol_index = symbols.index(symbol.upper())
            return build_test_candles_for_symbol(
                symbol=symbol.upper(),
                symbol_index=symbol_index,
                candle_count=756,
                source="kite:historical:NSE",
            )

    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_market_data_provider",
        lambda settings: LongHistoryFakeKiteMarketDataProvider(),
    )
    latest_candle_date = (
        LongHistoryFakeKiteMarketDataProvider().get_daily_candles("INFY")[-1].trade_date
    )
    with build_session_factory(settings)() as session:
        GraphRepository(session).upsert_edge_stats(
            edge_key="peer:INFY:RELIANCE",
            window="60d",
            as_of_date=latest_candle_date,
            sample_size=60,
            raw_correlation=Decimal("0.8200"),
            residual_correlation=Decimal("0.7600"),
            lead_lag_score=Decimal("0.4200"),
            stability_score=Decimal("0.9000"),
        )
        session.commit()

    run = PaperRunService(settings).run_once(
        symbols=["INFY", "RELIANCE"],
        strategy_config_path="configs/strategies/graph_aware_score_v2.yaml",
    )
    strategy = run.artifacts["strategy"]

    assert run.status == "COMPLETED"
    assert strategy["strategy_name"] == "graph_aware_score_v2"
    assert strategy["technical_analyst_profile"] == OHLCV_V2_PROFILE
    assert strategy["feature_snapshot_count"] >= 2

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        report_models = list(
            session.scalars(
                select(AnalystReportModel).where(
                    AnalystReportModel.agent_name == "TechnicalAnalystAgent"
                )
            )
        )

    assert report_models
    for report_model in report_models:
        payload = report_model.payload
        score_metadata = payload["score_metadata"]
        technical_v2 = score_metadata["technical_v2"]
        assert payload["model_version"] == OHLCV_V2_PROFILE
        assert Decimal(str(payload["score"])) == Decimal(
            technical_v2["composite_score"]
        )
        assert Decimal(str(payload["confidence"])) == Decimal(
            technical_v2["confidence"]
        )
        assert technical_v2["metadata"]["universe_context_available"] is True
        assert technical_v2["metadata"]["symbol_context_available"] is True
        assert technical_v2["metadata"]["universe_size"] >= 2
        assert technical_v2["top_contributors"]


def test_graph_enabled_money_management_run_adds_active_allocation_metadata(
    tmp_path: Path,
) -> None:
    policy_path = _write_active_allocation_policy(
        tmp_path, max_stock_pct=Decimal("1.0")
    )
    settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical,graph",
        graph_enabled=True,
        graph_risk_enabled=True,
        money_management_enabled=True,
        money_management_config_path=str(policy_path),
        profile_id="client-a",
    )
    _create_profile(
        build_session_factory(settings),
        profile_id="client-a",
        corpus_inr=Decimal("1000000"),
    )
    _seed_paper_graph_fixture(settings)

    run = PaperRunService(settings).run_once(
        symbols=["INFY"],
        strategy_config_path="configs/strategies/graph_aware_score_v1.yaml",
    )

    symbol_artifact = run.artifacts["symbols"]["INFY"]
    allocation = symbol_artifact["allocation_decision"]

    assert run.status == "COMPLETED"
    assert allocation["strategy_name"] == "graph_aware_score_v1"
    assert allocation["sleeve_id"] == "active_strategy"
    assert allocation["binding_constraint"] == "stock_exposure"
    assert Decimal(allocation["approved_position_pct_nav"]) <= Decimal("1.0000")
    assert Decimal(allocation["approved_notional_inr"]) < Decimal(
        allocation["requested_notional_inr"]
    )
    assert allocation["approved_quantity"] > 0

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        proposal = session.scalars(select(TraderProposalModel)).one()
        risk_review = session.scalars(select(RiskReviewModel)).one()
        final_decision = session.scalars(select(FinalDecisionModel)).one()

    assert (
        proposal.payload["allocation_decision"]["binding_constraint"]
        == "stock_exposure"
    )
    assert (
        risk_review.payload["allocation_decision"]["binding_constraint"]
        == "stock_exposure"
    )
    assert (
        final_decision.payload["allocation_decision"]["binding_constraint"]
        == "stock_exposure"
    )


def test_graph_enabled_kite_paper_run_fails_fast_without_graph_nodes(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical,graph",
        graph_enabled=True,
        graph_risk_enabled=True,
    )

    run = PaperRunService(settings).run_once(
        symbols=["INFY"],
        strategy_config_path="configs/strategies/graph_aware_score_v1.yaml",
    )

    assert run.status == "FAILED"
    assert run.errors[0].stage == "data_update"
    assert run.errors[0].error_type == "GraphReadinessError"
    assert "make import-taurus-graph" in run.errors[0].message
    assert set(run.artifacts) == {"profile"}
    assert run.artifacts["profile"] == {
        "profile_id": "local-paper",
        "starting_corpus_inr": "10000.0000",
        "currency": "INR",
    }


def test_strategy_selected_market_universe_uses_strategy_targets(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        paper_analysis_scope="strategy_selected",
        max_open_positions=1,
    )
    universe = _paper_run_universe(
        source="market_data_universe",
        symbols=["INFY", "TCS", "RELIANCE"],
    )

    run = PaperRunService(settings).run_once(
        symbols=universe.symbols,
        universe=universe,
    )

    scope = run.artifacts["symbol_scope"]
    targets = set(run.artifacts["strategy"]["targets"])

    assert run.status == "COMPLETED"
    assert scope["analysis_scope"] == "strategy_selected"
    assert scope["requested_universe_symbols"] == ["INFY", "TCS", "RELIANCE"]
    assert len(targets) == 1
    assert set(scope["analyzed_symbols"]) == targets
    assert set(scope["finalization_symbols"]) == targets
    assert set(run.artifacts["analysis"]) == targets
    assert set(run.artifacts["symbols"]) == targets


def test_full_universe_analysis_records_proposals_for_requested_market_universe(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        paper_analysis_scope="full_universe",
        paper_execution_scope="allocated_only",
        max_open_positions=1,
    )
    universe = _paper_run_universe(
        source="market_data_universe",
        symbols=["INFY", "TCS", "RELIANCE"],
    )

    run = PaperRunService(settings).run_once(
        symbols=universe.symbols,
        universe=universe,
    )

    scope = run.artifacts["symbol_scope"]
    analysis_artifacts = run.artifacts["analysis"]

    assert run.status == "COMPLETED"
    assert scope["analysis_scope"] == "full_universe"
    assert scope["execution_scope"] == "allocated_only"
    assert scope["effective_execution_scope"] == "allocated_only"
    assert scope["requested_universe_symbols"] == ["INFY", "TCS", "RELIANCE"]
    assert set(scope["analyzed_symbols"]) == {"INFY", "TCS", "RELIANCE"}
    assert set(scope["finalization_symbols"]) == {"INFY", "TCS", "RELIANCE"}
    assert set(analysis_artifacts) == {"INFY", "TCS", "RELIANCE"}
    assert set(run.artifacts["symbols"]) == {"INFY", "TCS", "RELIANCE"}
    assert run.artifacts["allocation"]["ledger_count"] == 3
    assert run.artifacts["final_decisions"]["total_count"] == 3
    assert run.artifacts["execution"]["execution_set_count"] <= 1

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        proposal_symbols = {
            row.symbol
            for row in session.scalars(
                select(TraderProposalModel).where(
                    TraderProposalModel.run_id == run.run_id
                )
            )
        }
        final_decision_count = session.scalar(
            select(func.count())
            .select_from(FinalDecisionModel)
            .where(FinalDecisionModel.run_id == run.run_id)
        )
        order_count = session.scalar(
            select(func.count())
            .select_from(PaperOrderModel)
            .where(PaperOrderModel.run_id == run.run_id)
        )

    assert proposal_symbols == {"INFY", "TCS", "RELIANCE"}
    assert final_decision_count == 3
    assert order_count == run.artifacts["execution"]["routed_order_count"]


def test_full_universe_money_management_run_completes_allocation_pipeline(
    tmp_path: Path,
) -> None:
    policy_path = _write_active_allocation_policy(
        tmp_path, max_stock_pct=Decimal("5.0")
    )
    settings = _settings_for_temp_db(
        tmp_path,
        money_management_enabled=True,
        money_management_config_path=str(policy_path),
        paper_analysis_scope="full_universe",
        paper_execution_scope="allocated_only",
    )
    universe = _paper_run_universe(
        source="market_data_universe",
        symbols=["INFY", "TCS", "RELIANCE"],
    )

    run = PaperRunService(settings).run_once(
        symbols=universe.symbols,
        universe=universe,
    )

    allocation = run.artifacts["allocation"]
    execution = run.artifacts["execution"]
    ledger_counts = allocation["ledger_counts"]

    assert run.status == "COMPLETED"
    assert run.failed_symbols == []
    assert "money_management" in run.artifacts
    assert "portfolio_plan" in run.artifacts
    assert allocation["policy_source"] == "portfolio_plan"
    assert (
        run.artifacts["portfolio_plan"]["policy_version"] == "active_integration_policy"
    )
    plan_candidates = run.artifacts["portfolio_plan"]["candidates"]
    assert (
        sum(
            1
            for candidate in plan_candidates
            if candidate["source"] == "trader_proposal"
        )
        == 3
    )
    assert allocation["ledger_count"] == 3
    assert sum(ledger_counts.values()) == 3
    assert (
        ledger_counts.get("selected", 0)
        + ledger_counts.get("allocation_reduced", 0)
        + ledger_counts.get("not_selected", 0)
        + ledger_counts.get("allocation_rejected", 0)
        + ledger_counts.get("unchanged_lifecycle", 0)
    ) == 3
    assert run.artifacts["final_decisions"]["total_count"] == 3
    assert execution["execution_set_count"] == (
        ledger_counts.get("selected", 0) + ledger_counts.get("allocation_reduced", 0)
    )
    assert execution["routed_order_count"] == execution["execution_set_count"]


def test_m61_portfolio_rebalance_e2e_regression_covers_plan_routing_and_settlement(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    policy_path = _write_m61_rebalance_policy(tmp_path)
    settings = _settings_for_temp_db(
        tmp_path,
        money_management_enabled=True,
        money_management_config_path=str(policy_path),
        paper_analysis_scope="full_universe",
        paper_execution_scope="allocated_only",
    )
    candle_count = {"value": 252}

    class AdvancingFakeKiteMarketDataProvider(FakeKiteMarketDataProvider):
        def get_daily_candles(self, symbol: str):
            symbols = [instrument.symbol for instrument in TEST_INSTRUMENTS]
            symbol_index = symbols.index(symbol.upper())
            return build_test_candles_for_symbol(
                symbol=symbol.upper(),
                symbol_index=symbol_index,
                candle_count=candle_count["value"],
                source="kite:historical:NSE",
            )

    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_market_data_provider",
        lambda settings: AdvancingFakeKiteMarketDataProvider(),
    )
    service = PaperRunService(settings)
    service._load_latest_inputs()
    _seed_m61_rebalance_account_state(settings)

    forced_actions = {
        "INFY": "BUY",
        "ICICIBANK": "BUY",
        "TCS": "HOLD",
        "RELIANCE": "HOLD",
    }
    forced_targets = {
        "INFY": Decimal("24.0000"),
        "ICICIBANK": Decimal("22.0000"),
    }
    _force_m61_rebalance_inputs(
        monkeypatch,
        action_by_symbol=forced_actions,
        target_pct_by_symbol=forced_targets,
    )
    universe = _paper_run_universe(
        source="market_data_universe",
        symbols=["INFY", "ICICIBANK"],
    )

    first = PaperRunService(settings, schedule_name="m61_rebalance").run_once(
        symbols=universe.symbols,
        universe=universe,
    )

    plan = first.artifacts["portfolio_plan"]
    allocation = first.artifacts["allocation"]
    ledger = {row["symbol"]: row for row in allocation["ledger"]}
    candidates = {row["symbol"]: row for row in plan["candidates"]}
    planned_trades = {row["symbol"]: row for row in plan["planned_trades"]}
    sleeve_budgets = {row["sleeve_id"]: row for row in plan["sleeve_budgets"]}
    cash_budget = {row["row_id"]: row for row in plan["cash_budget"]}
    routed_by_symbol = {
        row["symbol"]: row for row in first.artifacts["execution"]["routed_orders"]
    }
    execution_symbols = [
        row["symbol"] for row in first.artifacts["execution"]["routed_orders"]
    ]

    assert first.status == "COMPLETED"
    assert first.failed_symbols == []
    assert plan["policy_version"] == "m61_rebalance_policy"
    assert plan["model_version"] == "portfolio_rebalance_plan_v3"
    assert {row["symbol"] for row in plan["positions"]} == {"TCS", "RELIANCE"}
    assert candidates["INFY"]["raw_strategy_score"] == "0.1800"
    assert candidates["ICICIBANK"]["raw_strategy_score"] == "0.1450"
    assert (
        candidates["INFY"]["allocation_score_component"]
        != candidates["ICICIBANK"]["allocation_score_component"]
    )
    assert candidates["LT"]["source"] == "core_shariah_basket_v1"
    assert planned_trades["LT"]["side"] == "BUY"
    assert planned_trades["TCS"]["side"] == "SELL"
    assert planned_trades["TCS"]["action"] == "EXIT"
    assert candidates["TCS"]["score_evidence"]["threshold_reason"] == (
        "strategy_score_below_exit_threshold"
    )
    assert _decimal(plan["same_run_sell_proceeds_haircut_pct"]) == Decimal("80.0000")
    assert _decimal(plan["same_run_sell_proceeds_spendable_inr"]) > Decimal("0")
    assert _decimal(plan["same_run_sell_proceeds_safety_reserve_inr"]) > Decimal("0")
    assert cash_budget["spendable_same_run_proceeds"]["spendable"] is True
    assert _decimal(plan["hard_cash_reserve_pct_nav"]) == Decimal("5.0000")
    assert plan["hard_cash_reserve_inr"] == "5000.00"
    assert _decimal(plan["buy_price_buffer_pct"]) == Decimal("5.0000")
    assert sleeve_budgets["active_strategy"]["borrowed_capacity_inr"] != "0.00"
    assert sleeve_budgets["cash_buffer"]["protected_capacity_inr"] == "5000.00"
    assert sleeve_budgets["cash_buffer"]["borrowable_capacity_inr"] == "0.00"
    assert any(
        row.get("borrowed_by_sleeve_id") == "active_strategy"
        for row in plan["sleeve_budgets"]
    )
    assert ledger["TCS"]["proposal_source"] == "trader_proposal"
    assert ledger["TCS"]["portfolio_plan_trade_id"] == planned_trades["TCS"]["trade_id"]
    assert ledger["TCS"]["status"] == "open_position_management"
    assert ledger["LT"]["proposal_source"] == "portfolio_plan_core"
    assert ledger["LT"]["portfolio_plan_trade_id"] == "trade-core-lt"
    assert any(
        _decimal(row["same_run_proceeds_used_inr"]) > Decimal("0")
        for row in allocation["ledger"]
        if row["action"] == "BUY"
    )
    assert any(
        row["capacity_source"] == "borrowed_sleeve_capacity"
        for row in allocation["ledger"]
        if row["action"] == "BUY"
    )
    assert execution_symbols[0] == "TCS"
    assert "LT" in execution_symbols[1:]
    assert routed_by_symbol["TCS"]["order_status"] == "PENDING_NEXT_OPEN", (
        routed_by_symbol["TCS"].get("reason")
    )
    assert routed_by_symbol["LT"]["order_status"] == "PENDING_NEXT_OPEN"

    client = TestClient(create_app(settings))
    overview = client.get("/ui/overview")
    detail = client.get(f"/ui/runs/{first.run_id}")
    trail = client.get(f"/ui/runs/{first.run_id}/symbols/LT/decision-trail")
    replay = client.get(f"/ui/replay/{trail.json()['decision_id']}")
    portfolio = client.get("/ui/portfolio")

    assert overview.status_code == 200
    assert detail.status_code == 200
    assert trail.status_code == 200
    assert replay.status_code == 200
    assert portfolio.status_code == 200
    assert _decimal(
        overview.json()["allocation"]["portfolio_plan"][
            "same_run_sell_proceeds_haircut_pct"
        ]
    ) == Decimal("80.0000")
    assert detail.json()["artifacts"]["portfolio_plan"]["plan_id"] == plan["plan_id"]
    assert (
        trail.json()["allocation_decision"]["proposal_source"] == "portfolio_plan_core"
    )
    assert _replay_stage(replay.json(), "portfolio_plan")["status"] == "complete"
    assert _decimal(
        portfolio.json()["allocation"]["portfolio_plan"]["buy_price_buffer_pct"]
    ) == Decimal("5.0000")

    candle_count["value"] = 253
    forced_actions.update(
        {
            "INFY": "HOLD",
            "ICICIBANK": "HOLD",
            "LT": "HOLD",
            "RELIANCE": "HOLD",
            "TCS": "HOLD",
        }
    )
    second = PaperRunService(settings, schedule_name="m61_settlement").run_once(
        symbols=["INFY"],
        universe=_paper_run_universe(source="manual_symbols", symbols=["INFY"]),
    )
    settlement = second.artifacts["settlement"]

    assert second.status == "COMPLETED"
    assert settlement["settled"] >= 2
    assert settlement["rejected"] == 0
    assert {detail["status"] for detail in settlement["details"]} == {"FILLED"}
    assert settlement["details"][0]["side"] == "SELL"
    assert {detail["side"] for detail in settlement["details"]} == {"BUY", "SELL"}


def test_portfolio_plan_core_buy_generates_risk_final_and_pending_order_records(
    tmp_path: Path,
) -> None:
    policy_path = _write_active_allocation_policy(
        tmp_path, max_stock_pct=Decimal("50.0")
    )
    settings = _settings_for_temp_db(
        tmp_path,
        money_management_enabled=True,
        money_management_config_path=str(policy_path),
        paper_analysis_scope="strategy_selected",
        paper_execution_scope="allocated_only",
    )
    service = PaperRunService(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        TaurusProfileRepository(session).update_profile_corpus(
            "local-paper",
            Decimal("1000000"),
        )
        session.commit()
    service._load_latest_inputs()
    policy = load_money_management_policy(policy_path)
    run_id = "pr-core-plan-routing"
    plan = PortfolioRebalancePlanService().build(
        PortfolioRebalancePlanInput(
            run_id=run_id,
            portfolio_id=settings.taurus_paper_portfolio_id,
            as_of=datetime(2026, 6, 22, tzinfo=timezone.utc),
            strategy_name="moving_average_crossover_v1",
            proposals=tuple(),
            nav_inr=Decimal("1000000.00"),
            current_cash_inr=Decimal("1000000.00"),
            histories_by_symbol={
                "INFY": tuple(
                    build_test_candles_for_symbol(
                        symbol="INFY",
                        symbol_index=0,
                        candle_count=252,
                        source="test",
                    )
                ),
            },
            core_basket_artifact={
                "target_weights": {"INFY": "5.0000"},
                "decisions": [
                    {
                        "symbol": "INFY",
                        "side": "BUY",
                        "status": "approved",
                        "target_weight_pct_nav": "5.0000",
                        "current_weight_pct_nav": "0.0000",
                        "drift_pct_nav": "5.0000",
                        "trade_notional_inr": "50000.00",
                    }
                ],
                "selection_scores": [{"symbol": "INFY", "rank_score": "95.0000"}],
            },
            core_basket_symbols=("INFY",),
            money_management_policy=policy,
        )
    )

    allocation_result = service._allocate_run_proposals(
        run_id=run_id,
        strategy_summary={"strategy_name": "moving_average_crossover_v1"},
        core_basket_symbols={"INFY"},
        portfolio_plan=plan,
        proposals=tuple(),
    )
    proposal = allocation_result.proposal_by_symbol()["INFY"]
    finalization = service.finalize_symbol(
        symbol="INFY",
        run_id=run_id,
        strategy_summary={"strategy_name": "moving_average_crossover_v1"},
        core_basket_symbols={"INFY"},
        proposal=proposal,
        apply_allocation=False,
    )

    core_symbol = "INFY"
    allocation = proposal.allocation_decision
    with session_factory() as session:
        proposal = session.scalar(
            select(TraderProposalModel).where(
                TraderProposalModel.run_id == run_id,
                TraderProposalModel.symbol == core_symbol,
            )
        )
        risk_review = session.scalar(
            select(RiskReviewModel).where(
                RiskReviewModel.run_id == run_id,
                RiskReviewModel.symbol == core_symbol,
            )
        )
        final_decision = session.scalar(
            select(FinalDecisionModel).where(
                FinalDecisionModel.run_id == run_id,
                FinalDecisionModel.symbol == core_symbol,
            )
        )
        order = session.scalar(
            select(PaperOrderModel).where(
                PaperOrderModel.run_id == run_id,
                PaperOrderModel.symbol == core_symbol,
            )
        )

    assert allocation is not None
    assert allocation.portfolio_plan_id == plan.plan_id
    assert allocation.portfolio_plan_trade_id == "trade-core-infy"
    assert allocation.planner_source == "core_shariah_basket_v1"
    assert finalization.proposal.lifecycle_trigger == "portfolio_rebalance"
    assert finalization.order is not None
    assert finalization.order.status == "PENDING_NEXT_OPEN"
    assert proposal is not None
    assert (
        proposal.payload["target_sizing_metadata"]["proposal_source"]
        == "portfolio_plan_core"
    )
    assert risk_review is not None
    assert (
        risk_review.payload["allocation_decision"]["portfolio_plan_trade_id"]
        == "trade-core-infy"
    )
    assert final_decision is not None
    assert (
        final_decision.payload["allocation_decision"]["portfolio_plan_trade_id"]
        == "trade-core-infy"
    )
    assert order is not None
    assert order.status == "PENDING_NEXT_OPEN"


def test_full_universe_finalizes_all_symbols_before_allocated_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        paper_analysis_scope="full_universe",
        max_open_positions=1,
    )
    universe = _paper_run_universe(
        source="market_data_universe",
        symbols=["INFY", "TCS", "RELIANCE"],
    )
    route_final_counts: list[int] = []
    broker_decisions: list[tuple[str, str, str | None]] = []

    _force_trader_actions(
        monkeypatch,
        {
            "INFY": "BUY",
            "TCS": "BUY",
            "RELIANCE": "BUY",
        },
    )

    original_route = ExecutionRouter.route_decision
    original_place_order = PaperBroker.place_order

    def recording_route(router, decision, **kwargs):
        session_factory = build_session_factory(settings)
        with session_factory() as session:
            route_final_counts.append(
                session.scalar(
                    select(func.count())
                    .select_from(FinalDecisionModel)
                    .where(FinalDecisionModel.run_id == decision.run_id)
                )
                or 0
            )
        return original_route(router, decision, **kwargs)

    def recording_place_order(broker, decision, **kwargs):
        broker_decisions.append(
            (
                decision.symbol,
                decision.status,
                decision.allocation_decision.status
                if decision.allocation_decision is not None
                else None,
            )
        )
        return original_place_order(broker, decision, **kwargs)

    monkeypatch.setattr(
        "taurus_core.execution.order_router.ExecutionRouter.route_decision",
        recording_route,
    )
    monkeypatch.setattr(
        "taurus_core.brokers.paper_broker.PaperBroker.place_order",
        recording_place_order,
    )

    run = PaperRunService(settings).run_once(
        symbols=universe.symbols,
        universe=universe,
    )

    skipped = run.artifacts["execution"]["skipped_symbols"]
    not_selected_skips = [
        item for item in skipped if item["reason"] == "not_selected_by_run_allocation"
    ]

    assert run.status == "COMPLETED"
    assert run.artifacts["final_decisions"]["total_count"] == 3
    assert route_final_counts == [3]
    assert len(broker_decisions) == 1
    assert broker_decisions[0][1] == "APPROVED_FOR_PAPER"
    assert broker_decisions[0][2] in {"selected", "allocation_reduced"}
    assert len(not_selected_skips) == 2
    not_selected_symbols = {skip["symbol"] for skip in not_selected_skips}
    assert all(
        item["order_id"] is None
        for item in run.artifacts["symbols"].values()
        if item["symbol"] in not_selected_symbols
    )

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        decisions = {
            row.symbol: row.payload
            for row in session.scalars(
                select(FinalDecisionModel).where(
                    FinalDecisionModel.run_id == run.run_id
                )
            )
        }

    for skip in not_selected_skips:
        decision = decisions[skip["symbol"]]
        assert decision["status"] == "NO_ACTION"
        assert decision["final_action"] == "NO_TRADE"
        assert "not_selected_by_run_allocation" in decision["reason"]


def test_replay_includes_run_level_context_for_selected_and_not_selected_decisions(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        paper_analysis_scope="full_universe",
        max_open_positions=1,
    )
    universe = _paper_run_universe(
        source="market_data_universe",
        symbols=["INFY", "TCS", "RELIANCE"],
    )
    _force_trader_actions(
        monkeypatch,
        {
            "INFY": "BUY",
            "TCS": "BUY",
            "RELIANCE": "BUY",
        },
    )

    run = PaperRunService(settings).run_once(
        symbols=universe.symbols,
        universe=universe,
    )

    execution = run.artifacts["execution"]
    selected_symbol = execution["execution_set"][0]["symbol"]
    not_selected_symbol = next(
        item["symbol"]
        for item in execution["skipped_symbols"]
        if item["reason"] == "not_selected_by_run_allocation"
    )
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        decision_ids = {
            row.symbol: row.decision_id
            for row in session.scalars(
                select(FinalDecisionModel).where(
                    FinalDecisionModel.run_id == run.run_id
                )
            )
        }

    client = TestClient(create_app(settings))
    selected_replay = client.get(f"/replay/{decision_ids[selected_symbol]}").json()
    not_selected_replay = client.get(
        f"/replay/{decision_ids[not_selected_symbol]}"
    ).json()

    selected_allocation = _replay_stage(selected_replay, "allocation_ledger")[
        "artifacts"
    ][0]
    selected_plan = _replay_stage(selected_replay, "portfolio_plan")["artifacts"][0]
    selected_execution = _replay_stage(selected_replay, "deferred_execution")[
        "artifacts"
    ]
    not_selected_allocation = _replay_stage(not_selected_replay, "allocation_ledger")[
        "artifacts"
    ][0]
    not_selected_plan = _replay_stage(not_selected_replay, "portfolio_plan")[
        "artifacts"
    ][0]
    not_selected_execution = _replay_stage(not_selected_replay, "deferred_execution")[
        "artifacts"
    ]
    not_selected_final = _replay_stage(not_selected_replay, "final_decision")[
        "artifacts"
    ][0]

    assert _replay_stage(selected_replay, "strategy_ranking")["artifact_count"] >= 1
    assert selected_plan["candidate"]["symbol"] == selected_symbol
    assert selected_plan["planned_trades"]
    assert selected_allocation["ledger_entry"]["status"] in {
        "selected",
        "allocation_reduced",
    }
    assert {item["kind"] for item in selected_execution} >= {"execution_set"}
    assert _replay_stage(not_selected_replay, "strategy_ranking")["artifact_count"] >= 1
    assert not_selected_plan["candidate"]["symbol"] == not_selected_symbol
    assert not_selected_allocation["ledger_entry"]["status"] == "not_selected"
    assert not_selected_final["status"] == "NO_ACTION"
    assert not_selected_final["final_action"] == "NO_TRADE"
    assert not_selected_execution[0]["kind"] == "skipped_symbol"
    assert not_selected_execution[0]["reason"] == "not_selected_by_run_allocation"


def test_full_universe_graph_selection_does_not_narrow_analysis(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        graph_enabled=True,
        graph_risk_enabled=True,
        paper_analysis_scope="full_universe",
        max_open_positions=1,
    )
    _seed_paper_graph_fixture(settings)
    universe = _paper_run_universe(
        source="market_data_universe",
        symbols=["INFY", "TCS", "RELIANCE"],
    )

    run = PaperRunService(settings).run_once(
        symbols=universe.symbols,
        universe=universe,
        strategy_config_path="configs/strategies/graph_aware_score_v1.yaml",
    )

    scope = run.artifacts["symbol_scope"]
    analyzed = set(scope["analyzed_symbols"])
    graph_selected = set(scope["graph_selected_symbols"])

    assert run.status == "COMPLETED"
    assert analyzed == {"INFY", "TCS", "RELIANCE"}
    assert graph_selected != analyzed
    assert graph_selected.issubset(analyzed)
    assert len(graph_selected) < len(analyzed)
    assert set(run.artifacts["analysis"]) == analyzed
    assert set(run.artifacts["symbols"]) == analyzed
    assert run.artifacts["final_decisions"]["total_count"] == len(analyzed)

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        proposal_symbols = {
            row.symbol
            for row in session.scalars(
                select(TraderProposalModel).where(
                    TraderProposalModel.run_id == run.run_id
                )
            )
        }

    assert proposal_symbols == {"INFY", "TCS", "RELIANCE"}


def test_full_universe_manual_symbols_remain_explicit_plus_open_positions(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(
        tmp_path,
        paper_analysis_scope="full_universe",
    )
    first = PaperRunService(
        settings,
        schedule_name="manual_open_seed",
        run_after_market_close=False,
    ).run_once(
        symbols=["INFY"],
        universe=_paper_run_universe(source="manual_symbols", symbols=["INFY"]),
    )

    second = PaperRunService(settings, schedule_name="manual_scope_review").run_once(
        symbols=["TCS"],
        universe=_paper_run_universe(source="manual_symbols", symbols=["TCS"]),
    )

    scope = second.artifacts["symbol_scope"]

    assert first.status == "COMPLETED"
    assert second.status == "COMPLETED"
    assert scope["manual_symbols"] == ["TCS"]
    assert scope["requested_universe_symbols"] == []
    assert set(scope["analyzed_symbols"]) == {"TCS", "INFY"}
    assert set(scope["finalization_symbols"]) == {"TCS", "INFY"}
    assert set(second.artifacts["analysis"]) == {"TCS", "INFY"}

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        proposal_symbols = {
            row.symbol
            for row in session.scalars(
                select(TraderProposalModel).where(
                    TraderProposalModel.run_id == second.run_id
                )
            )
        }

    assert proposal_symbols == {"TCS", "INFY"}


@pytest.mark.parametrize(
    ("action", "expect_order"),
    [
        ("HOLD", False),
        ("REDUCE", True),
        ("EXIT", True),
    ],
)
def test_open_position_lifecycle_actions_survive_full_universe_finalization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    expect_order: bool,
) -> None:
    settings = _settings_for_temp_db(tmp_path, paper_analysis_scope="full_universe")
    seed = PaperRunService(
        settings,
        schedule_name=f"seed_{action.lower()}",
        run_after_market_close=False,
    ).run_once(symbols=["INFY"])
    assert seed.status == "COMPLETED"
    assert seed.artifacts["symbols"]["INFY"]["order_status"] == "FILLED"

    _force_trader_actions(monkeypatch, {"INFY": action})

    run = PaperRunService(
        settings, schedule_name=f"lifecycle_{action.lower()}"
    ).run_once(
        symbols=["INFY"],
        universe=_paper_run_universe(source="manual_symbols", symbols=["INFY"]),
    )
    symbol_artifact = run.artifacts["symbols"]["INFY"]
    execution = run.artifacts["execution"]
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        fill_sides = {
            row.side
            for row in ExecutionRepository(session).list_fills_by_portfolio(
                portfolio_id=settings.taurus_paper_portfolio_id,
                symbol="INFY",
            )
        }

    assert run.status == "COMPLETED"
    assert symbol_artifact["proposal_action"] == action
    assert symbol_artifact["final_action"] == action
    if expect_order:
        assert execution["execution_set"][0]["reason"] == "open_position_lifecycle"
        assert symbol_artifact["order_status"] == "PENDING_NEXT_OPEN"
        assert symbol_artifact["order_reason"] == "queued_for_next_open_settlement"
        assert fill_sides == {"BUY"}
    else:
        assert symbol_artifact["no_paper_order_expected"] is True
        assert symbol_artifact["order_id"] is None
        assert (
            execution["skipped_symbols"][0]["reason"] == "hold_no_paper_order_expected"
        )


def test_paper_loop_records_manual_symbol_universe_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("SYMBOLS", "infy")
    monkeypatch.setenv("SYMBOL", "")
    settings = _settings_for_temp_db(tmp_path)
    resolved = _resolve_symbols_from_env(settings)

    payload = run_paper_loop(
        symbols=resolved.symbols,
        settings=settings,
        iterations=1,
        universe=resolved.universe,
    )

    universe = payload[0]["universe"]
    assert universe["source"] == "manual_symbols"
    assert universe["provider"] == "kite"
    assert universe["selected_symbol_count"] == 1
    assert universe["symbols"] == ["INFY"]

    client = TestClient(create_app(settings))
    overview = client.get("/ui/overview")
    assert overview.status_code == 200
    assert overview.json()["latest_run"]["universe"]["source"] == "manual_symbols"


def test_decomposed_symbol_analysis_and_stored_finalization_keep_legacy_artifact(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_id = "m37-decomposed-symbol"
    events: list[tuple[str, dict[str, object]]] = []
    service = PaperRunService(
        settings,
        progress=lambda event, payload: events.append((event, dict(payload))),
    )
    service._load_latest_inputs()
    strategy_summary = service._generate_strategy_summary(
        symbols=["INFY"],
        universe=None,
        strategy_config_path=None,
    )

    analysis = service.analyze_symbol(symbol="INFY", run_id=run_id)

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        proposal_count = session.scalar(
            select(func.count())
            .select_from(TraderProposalModel)
            .where(TraderProposalModel.run_id == run_id)
        )
        risk_count = session.scalar(
            select(func.count())
            .select_from(RiskReviewModel)
            .where(RiskReviewModel.run_id == run_id)
        )
        final_count = session.scalar(
            select(func.count())
            .select_from(FinalDecisionModel)
            .where(FinalDecisionModel.run_id == run_id)
        )
        order_count = session.scalar(
            select(func.count())
            .select_from(PaperOrderModel)
            .where(PaperOrderModel.run_id == run_id)
        )

    assert analysis.proposal.symbol == "INFY"
    assert proposal_count == 1
    assert risk_count == 0
    assert final_count == 0
    assert order_count == 0

    finalization = service.finalize_symbol(
        symbol="INFY",
        run_id=run_id,
        strategy_summary=strategy_summary,
        core_basket_symbols=set(),
    )
    artifact = _symbol_artifact_from_results(analysis, finalization)

    with session_factory() as session:
        risk_count = session.scalar(
            select(func.count())
            .select_from(RiskReviewModel)
            .where(RiskReviewModel.run_id == run_id)
        )
        final_count = session.scalar(
            select(func.count())
            .select_from(FinalDecisionModel)
            .where(FinalDecisionModel.run_id == run_id)
        )
        order_count = session.scalar(
            select(func.count())
            .select_from(PaperOrderModel)
            .where(PaperOrderModel.run_id == run_id)
        )

    assert finalization.proposal_source == "stored"
    assert finalization.proposal.proposal_id == analysis.proposal.proposal_id
    assert artifact["symbol"] == "INFY"
    assert set(artifact) == {
        "symbol",
        "report_ids",
        "analyst_roster",
        "debate_id",
        "proposal_id",
        "proposal_source",
        "proposal_action",
        "portfolio_id",
        "lifecycle_trigger",
        "evaluation_mode",
        "current_position_quantity",
        "current_position_pct_nav",
        "target_position_pct_nav",
        "position_management_summary",
        "risk_check_id",
        "final_decision_id",
        "final_status",
        "final_action",
        "no_paper_order_expected",
        "order_id",
        "order_status",
        "order_reason",
        "account_id",
    }
    assert artifact["final_status"] == "APPROVED_FOR_PAPER"
    assert artifact["order_status"] == "PENDING_NEXT_OPEN"
    assert artifact["order_reason"] == "queued_for_next_open_settlement"
    assert risk_count == 1
    assert final_count == 1
    assert order_count == 1

    stage_payloads = [
        payload for event, payload in events if event == "paper.symbol.stage_started"
    ]
    assert [payload["stage"] for payload in stage_payloads] == [
        *ANALYSIS_STAGE_NAMES,
        *FINALIZATION_STAGE_NAMES,
    ]
    assert [payload["phase"] for payload in stage_payloads] == [
        "analysis",
        "analysis",
        "analysis",
        "finalization",
        "finalization",
        "finalization",
        "finalization",
    ]


def test_paper_loop_emits_iteration_and_symbol_stage_progress_events(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    events: list[tuple[str, dict[str, object]]] = []

    payload = run_paper_loop(
        symbols=["INFY"],
        settings=settings,
        iterations=1,
        universe=PaperRunUniverse(
            source="manual_symbols",
            provider="kite",
            selected_symbol_count=1,
            symbols=["INFY"],
        ),
        progress=lambda event, payload: events.append((event, dict(payload))),
    )

    event_names = [event for event, _payload in events]
    stage_names = [
        str(payload["stage"])
        for event, payload in events
        if event == "paper.symbol.stage_started"
    ]
    terminal_stage_names = [
        str(payload["terminal_stage"])
        for event, payload in events
        if event == "paper.symbol.stage_started"
    ]
    phase_names = [
        str(payload["phase"])
        for event, payload in events
        if event == "paper.symbol.stage_started"
    ]
    iteration_completed = next(
        payload for event, payload in events if event == "paper.iteration.completed"
    )

    assert payload[0]["status"] == "COMPLETED"
    assert "paper.loop.started" in event_names
    assert "paper.iteration.started" in event_names
    assert "paper.run.setup_started" in event_names
    assert "paper.symbol.completed" in event_names
    assert "paper.iteration.completed" in event_names
    assert "paper.loop.completed" in event_names
    assert stage_names == [
        *ANALYSIS_STAGE_NAMES,
        *FINALIZATION_STAGE_NAMES,
    ]
    assert terminal_stage_names == [
        "analysts",
        "debate",
        "trader",
        "allocation",
        "risk",
        "portfolio_manager",
        "execution",
    ]
    assert phase_names == [
        "analysis",
        "analysis",
        "analysis",
        "finalization",
        "finalization",
        "finalization",
        "finalization",
    ]
    assert iteration_completed["succeeded_count"] == 1
    assert iteration_completed["failed_count"] == 0
    assert iteration_completed["status"] == "COMPLETED"


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _force_m61_rebalance_inputs(
    monkeypatch: pytest.MonkeyPatch,
    *,
    action_by_symbol: dict[str, str],
    target_pct_by_symbol: dict[str, Decimal],
) -> None:
    original_generate_strategy_summary = PaperRunService._generate_strategy_summary
    original_analyze_symbol = PaperRunService.analyze_symbol

    def patched_generate_strategy_summary(self: PaperRunService, *args, **kwargs):
        summary = original_generate_strategy_summary(self, *args, **kwargs)
        score_by_symbol = {
            "INFY": Decimal("0.1800"),
            "ICICIBANK": Decimal("0.1450"),
            "RELIANCE": Decimal("0.0400"),
            "LT": Decimal("0.0350"),
            "TCS": Decimal("-0.2500"),
        }
        rank_by_symbol = {
            "INFY": 1,
            "ICICIBANK": 2,
            "RELIANCE": 3,
            "LT": 4,
            "TCS": 5,
        }
        ranked_candidates = []
        for item in summary.get("ranked_candidates", []):
            if not isinstance(item, dict):
                continue
            candidate = dict(item)
            symbol = str(candidate.get("symbol") or "").upper()
            if symbol in score_by_symbol:
                candidate["raw_strategy_score"] = str(score_by_symbol[symbol])
                candidate["rank"] = rank_by_symbol[symbol]
                candidate["eligibility_status"] = "eligible"
                candidate["action_intent"] = (
                    "BUY" if symbol in {"INFY", "ICICIBANK"} else "HOLD"
                )
            ranked_candidates.append(candidate)
        summary["ranked_candidates"] = ranked_candidates
        strategy_scores = dict(summary.get("strategy_score_by_symbol") or {})
        strategy_scores.update(
            {symbol: str(score) for symbol, score in score_by_symbol.items()}
        )
        summary["strategy_score_by_symbol"] = strategy_scores
        summary["strategy_ranked_symbols"] = [
            symbol
            for symbol, _rank in sorted(
                rank_by_symbol.items(), key=lambda item: item[1]
            )
        ]
        summary["targets"] = ["INFY", "ICICIBANK"]
        return summary

    def patched_analyze_symbol(
        self: PaperRunService, *args, **kwargs
    ) -> PaperSymbolAnalysis:
        analysis = original_analyze_symbol(self, *args, **kwargs)
        symbol = analysis.symbol.upper()
        action = action_by_symbol.get(symbol)
        if action is None:
            return analysis

        current = analysis.proposal.current_position_pct_nav
        target = (
            target_pct_by_symbol[symbol].quantize(Decimal("0.0001"))
            if action == "BUY" and symbol in target_pct_by_symbol
            else current.quantize(Decimal("0.0001"))
        )
        order_type = "NONE" if action in {"HOLD", "NO_TRADE"} else "MARKET"
        trigger_by_action = {
            "BUY": "new_entry",
            "HOLD": "hold_review",
            "NO_TRADE": "new_entry",
            "REDUCE": "take_profit",
            "EXIT": "stop_loss",
        }
        proposal = analysis.proposal.model_copy(
            update={
                "action": action,
                "confidence": Decimal("0.9500")
                if action == "BUY"
                else analysis.proposal.confidence,
                "requested_position_pct_nav": target,
                "target_position_pct_nav": target,
                "lifecycle_trigger": trigger_by_action[action],
                "order_type": order_type,
                "entry_rule": f"Forced {action} proposal for M61 rebalance regression.",
                "reason_summary": f"Forced {action} proposal for M61 rebalance regression.",
                "position_management_summary": (
                    f"Forced {action} lifecycle proposal for M61 rebalance regression."
                ),
            }
        )
        with self.session_factory() as session:
            ResearchRepository(session).replace_trader_proposal_for_run_symbol(proposal)
            session.commit()
        return PaperSymbolAnalysis(
            symbol=analysis.symbol,
            enabled_analysts=analysis.enabled_analysts,
            reports=analysis.reports,
            debate=analysis.debate,
            proposal=proposal,
        )

    monkeypatch.setattr(
        PaperRunService, "_generate_strategy_summary", patched_generate_strategy_summary
    )
    monkeypatch.setattr(PaperRunService, "analyze_symbol", patched_analyze_symbol)


def _force_trader_actions(
    monkeypatch: pytest.MonkeyPatch,
    action_by_symbol: dict[str, str],
) -> None:
    original_analyze_symbol = PaperRunService.analyze_symbol

    def patched_analyze_symbol(
        self: PaperRunService, *args, **kwargs
    ) -> PaperSymbolAnalysis:
        analysis = original_analyze_symbol(self, *args, **kwargs)
        action = action_by_symbol.get(analysis.symbol)
        if action is None:
            return analysis

        current = analysis.proposal.current_position_pct_nav
        target_by_action = {
            "BUY": max(
                analysis.proposal.target_position_pct_nav,
                current + Decimal("1.0000"),
                Decimal("1.0000"),
            ).quantize(Decimal("0.0001")),
            "HOLD": current.quantize(Decimal("0.0001")),
            "NO_TRADE": Decimal("0.0000"),
            "REDUCE": (current / Decimal("2")).quantize(Decimal("0.0001")),
            "EXIT": Decimal("0.0000"),
        }
        trigger_by_action = {
            "BUY": "new_entry",
            "HOLD": "hold_review",
            "NO_TRADE": "new_entry",
            "REDUCE": "take_profit",
            "EXIT": "stop_loss",
        }
        target = target_by_action[action]
        order_type = "NONE" if action in {"HOLD", "NO_TRADE"} else "MARKET"
        proposal = analysis.proposal.model_copy(
            update={
                "action": action,
                "requested_position_pct_nav": target,
                "target_position_pct_nav": target,
                "lifecycle_trigger": trigger_by_action[action],
                "order_type": order_type,
                "entry_rule": f"Forced {action} proposal for M40 regression coverage.",
                "reason_summary": f"Forced {action} proposal for M40 regression coverage.",
                "position_management_summary": (
                    f"Forced {action} lifecycle proposal for M40 regression coverage."
                ),
            }
        )
        with self.session_factory() as session:
            ResearchRepository(session).replace_trader_proposal_for_run_symbol(proposal)
            session.commit()
        return PaperSymbolAnalysis(
            symbol=analysis.symbol,
            enabled_analysts=analysis.enabled_analysts,
            reports=analysis.reports,
            debate=analysis.debate,
            proposal=proposal,
        )

    monkeypatch.setattr(PaperRunService, "analyze_symbol", patched_analyze_symbol)


def _ledger_entry(
    *,
    symbol: str,
    action: str,
    status: str,
    planner_rank: int,
) -> AllocationLedgerEntry:
    return AllocationLedgerEntry(
        symbol=symbol,
        proposal_id=f"tp-{symbol.lower()}",
        action=action,
        status=status,
        selected=status in {"selected", "allocation_reduced"},
        strategy_rank=planner_rank,
        strategy_score=Decimal("0.1000"),
        trader_confidence=Decimal("0.9000"),
        candidate_score=Decimal("90.0000"),
        score_band="test",
        requested_position_pct_nav=Decimal("0.0000"),
        approved_position_pct_nav=Decimal("0.0000"),
        requested_notional_inr=Decimal("100.00"),
        approved_notional_inr=Decimal("100.00"),
        approved_quantity=1,
        binding_constraint=None,
        portfolio_plan_id="plan-test",
        portfolio_plan_trade_id=f"trade-{symbol.lower()}",
        planner_candidate_id=f"candidate-{symbol.lower()}",
        planner_source="portfolio_rebalance_threshold",
        planner_rank=planner_rank,
        proposal_source="portfolio_plan_threshold",
    )


def _final_decision(*, symbol: str, action: str) -> FinalDecision:
    return FinalDecision(
        final_decision_id=f"fd-{symbol.lower()}",
        decision_id=f"dec-{symbol.lower()}",
        run_id="run-order-test",
        portfolio_id="local-paper",
        symbol=symbol,
        proposal_id=f"tp-{symbol.lower()}",
        risk_check_id=f"risk-{symbol.lower()}",
        as_of=datetime(2026, 6, 22, tzinfo=timezone.utc),
        final_action=action,  # type: ignore[arg-type]
        status="APPROVED_FOR_PAPER",
        approved_quantity=1,
        approved_position_pct_nav=Decimal("0.0000"),
        reason="Approved for ordering test.",
        is_order=True,
        can_send_to_broker=True,
        model_version="test_final_decision",
    )


def _settings_for_temp_db(
    tmp_path: Path,
    *,
    enabled_analysts: str = "technical",
    graph_enabled: bool = False,
    graph_risk_enabled: bool = False,
    money_management_enabled: bool = False,
    money_management_config_path: str = "configs/portfolio/money_management_v1.yaml",
    paper_analysis_scope: str = "strategy_selected",
    paper_execution_scope: str = "allocated_only",
    max_open_positions: int = 8,
    profile_id: str = "local-paper",
) -> Settings:
    return Settings(
        taurus_profile_id=profile_id,
        taurus_paper_partial_fill_threshold=1,
        taurus_enabled_analysts=enabled_analysts,
        taurus_initial_capital_inr=1_000_000,
        taurus_graph_enabled=graph_enabled,
        taurus_graph_risk_enabled=graph_risk_enabled,
        taurus_money_management_enabled=money_management_enabled,
        taurus_money_management_config_path=money_management_config_path,
        taurus_paper_analysis_scope=paper_analysis_scope,
        taurus_paper_execution_scope=paper_execution_scope,
        taurus_max_open_positions=max_open_positions,
    )


def _create_profile(session_factory, *, profile_id: str, corpus_inr: Decimal) -> None:
    with session_factory() as session:
        TaurusProfileRepository(session).create_profile(
            TaurusProfileCreate(
                profile_id=profile_id,
                display_name=profile_id.replace("-", " ").title(),
                starting_corpus_inr=corpus_inr,
            )
        )
        session.commit()


def _paper_run_universe(*, source: str, symbols: list[str]) -> PaperRunUniverse:
    normalized = [symbol.upper() for symbol in symbols]
    return PaperRunUniverse(
        source=source,  # type: ignore[arg-type]
        provider="kite",
        universe_name="test_shariah" if source == "market_data_universe" else None,
        yaml_path="configs/market_data/test_shariah.yaml"
        if source == "market_data_universe"
        else None,
        available_symbol_count=len(normalized)
        if source == "market_data_universe"
        else None,
        selected_symbol_count=len(normalized),
        symbols=normalized,
    )


def _seed_m61_rebalance_account_state(settings: Settings) -> None:
    provider = FakeKiteMarketDataProvider()
    latest_candle_by_symbol = {
        symbol: provider.get_daily_candles(symbol)[-1] for symbol in ("TCS", "RELIANCE")
    }
    price_by_symbol = {
        symbol: candle.close for symbol, candle in latest_candle_by_symbol.items()
    }
    quantities = {"TCS": 300, "RELIANCE": 82}
    market_values = {
        symbol: (price_by_symbol[symbol] * Decimal(quantity)).quantize(Decimal("0.01"))
        for symbol, quantity in quantities.items()
    }
    equity = Decimal("100000.00")
    gross_exposure = sum(market_values.values(), Decimal("0.00")).quantize(
        Decimal("0.01")
    )
    available_cash = (equity - gross_exposure).quantize(Decimal("0.01"))
    seed_run_id = "m61-seeded-account"
    updated_at = datetime(2026, 6, 22, tzinfo=timezone.utc)
    order_times = {
        "TCS": updated_at,
        "RELIANCE": updated_at.replace(minute=1),
    }
    account = PaperAccount(
        account_id=paper_account_id(
            portfolio_id=settings.taurus_paper_portfolio_id,
            run_id=seed_run_id,
        ),
        run_id=seed_run_id,
        portfolio_id=settings.taurus_paper_portfolio_id,
        starting_cash_inr=equity,
        available_cash_inr=available_cash,
        reserved_cash_inr=Decimal("0.00"),
        realized_pnl_inr=Decimal("0.00"),
        unrealized_pnl_inr=Decimal("0.00"),
        gross_exposure_inr=gross_exposure,
        equity_inr=equity,
        updated_at=updated_at,
    )
    positions = [
        PaperPosition(
            run_id=seed_run_id,
            portfolio_id=settings.taurus_paper_portfolio_id,
            symbol=symbol,
            quantity=quantity,
            average_cost_inr=price_by_symbol[symbol],
            last_price_inr=price_by_symbol[symbol],
            market_value_inr=market_values[symbol],
            realized_pnl_inr=Decimal("0.00"),
            unrealized_pnl_inr=Decimal("0.00"),
            updated_at=updated_at,
        )
        for symbol, quantity in sorted(quantities.items())
    ]
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        TaurusProfileRepository(session).update_profile_corpus(
            settings.taurus_paper_portfolio_id,
            equity,
        )
        research_repo = ResearchRepository(session)
        risk_repo = RiskRepository(session)
        execution_repo = ExecutionRepository(session)
        for symbol, quantity in sorted(quantities.items()):
            decision_id = f"dec-seed-{symbol.lower()}"
            final_decision_id = f"fd-seed-{symbol.lower()}"
            proposal_id = f"tp-seed-{symbol.lower()}"
            risk_check_id = f"risk-seed-{symbol.lower()}"
            debate_id = f"debate-seed-{symbol.lower()}"
            source_report_ids = [f"seed-report-{symbol.lower()}"]
            price = price_by_symbol[symbol]
            gross_value = (price * Decimal(quantity)).quantize(Decimal("0.01"))
            target_pct = ((market_values[symbol] / equity) * Decimal("100")).quantize(
                Decimal("0.0001")
            )
            research_repo.replace_debate_for_run_symbol(
                DebateReport(
                    debate_id=debate_id,
                    run_id=seed_run_id,
                    portfolio_id=settings.taurus_paper_portfolio_id,
                    symbol=symbol,
                    as_of=order_times[symbol],
                    rounds_requested=1,
                    bull_thesis=BullThesis(
                        symbol=symbol,
                        score=Decimal("0.1000"),
                        confidence=Decimal("0.8000"),
                        key_points=["Seeded opening position for M61 regression."],
                        conditions=["Used only for deterministic paper account setup."],
                        source_report_ids=source_report_ids,
                    ),
                    bear_thesis=BearThesis(
                        symbol=symbol,
                        score=Decimal("-0.1000"),
                        confidence=Decimal("0.8000"),
                        key_points=[
                            "Seeded setup carries no live trading implication."
                        ],
                        risk_flags=["Regression fixture only."],
                        source_report_ids=source_report_ids,
                    ),
                    rounds=[
                        DebateRound(
                            round_number=1,
                            bull_argument="Seeded position exists before rebalance.",
                            bear_argument="No new live exposure is implied.",
                            manager_note="Fixture parent row for opening paper fill.",
                        )
                    ],
                    manager_summary=ResearchManagerSummary(
                        consensus_label="neutral",
                        consensus_score=Decimal("0.0000"),
                        confidence=Decimal("0.8000"),
                        summary="Seeded opening position for M61 rebalance regression.",
                        unresolved_uncertainties=["Fixture-only setup."],
                    ),
                    source_report_ids=source_report_ids,
                    model_version="m61_seed_debate_v1",
                )
            )
            research_repo.replace_trader_proposal_for_run_symbol(
                TraderProposal(
                    proposal_id=proposal_id,
                    run_id=seed_run_id,
                    portfolio_id=settings.taurus_paper_portfolio_id,
                    symbol=symbol,
                    debate_id=debate_id,
                    as_of=order_times[symbol],
                    action="BUY",
                    confidence=Decimal("0.8000"),
                    horizon="medium",
                    requested_position_pct_nav=target_pct,
                    current_position_quantity=0,
                    current_position_pct_nav=Decimal("0.0000"),
                    target_position_pct_nav=target_pct,
                    lifecycle_trigger="new_entry",
                    order_type="MARKET",
                    entry_rule="Seeded opening paper position for M61 regression.",
                    stop_loss_pct=Decimal("8.0000"),
                    take_profit_pct=Decimal("16.0000"),
                    reason_summary="Seeded opening position used by paper broker state rebuild.",
                    invalid_if=["Fixture-only setup should not drive operator action."],
                    position_management_summary="Seeded opening paper position.",
                    source_report_ids=source_report_ids,
                    is_order=True,
                    requires_risk_approval=True,
                    model_version="m61_seed_proposal_v1",
                )
            )
            risk_repo.replace_risk_review_for_run_symbol(
                RiskReview(
                    risk_check_id=risk_check_id,
                    decision_id=decision_id,
                    run_id=seed_run_id,
                    portfolio_id=settings.taurus_paper_portfolio_id,
                    symbol=symbol,
                    proposal_id=proposal_id,
                    debate_id=debate_id,
                    as_of=order_times[symbol],
                    status="APPROVED",
                    requested_position_pct_nav=target_pct,
                    approved_position_pct_nav=target_pct,
                    hard_rule_results=[
                        HardRuleResult(
                            rule="fixture_seed",
                            status="passed",
                            details="Seeded opening paper position for M61 regression.",
                        )
                    ],
                    persona_reviews=[
                        RiskPersonaReview(
                            agent_name="FixtureRisk",
                            recommendation="allow",
                            score=Decimal("0.0000"),
                            confidence=Decimal("0.8000"),
                            key_points=[
                                "Seed row exists only to satisfy paper execution lineage."
                            ],
                            required_conditions=["Paper-only regression setup."],
                            model_version="m61_seed_risk_v1",
                        )
                    ],
                    risk_committee_summary="Approved fixture seed position for paper state rebuild.",
                    source_report_ids=source_report_ids,
                    is_order=True,
                    can_send_to_broker=True,
                    model_version="m61_seed_risk_v1",
                )
            )
            risk_repo.replace_final_decision_for_run_symbol(
                FinalDecision(
                    final_decision_id=final_decision_id,
                    decision_id=decision_id,
                    run_id=seed_run_id,
                    portfolio_id=settings.taurus_paper_portfolio_id,
                    symbol=symbol,
                    proposal_id=proposal_id,
                    risk_check_id=risk_check_id,
                    as_of=order_times[symbol],
                    final_action="BUY",
                    status="APPROVED_FOR_PAPER",
                    approved_quantity=quantity,
                    approved_position_pct_nav=target_pct,
                    reason="Approved fixture seed position for paper broker state rebuild.",
                    is_order=True,
                    can_send_to_broker=True,
                    model_version="m61_seed_final_decision_v1",
                )
            )
            order_id = paper_order_id(
                final_decision_id=final_decision_id,
                decision_id=decision_id,
                quantity=quantity,
            )
            fill = PaperFill(
                fill_id=paper_fill_id(
                    order_id=order_id,
                    fill_sequence=1,
                    quantity=quantity,
                    reference_price=price,
                ),
                order_id=order_id,
                final_decision_id=final_decision_id,
                run_id=seed_run_id,
                portfolio_id=settings.taurus_paper_portfolio_id,
                symbol=symbol,
                trade_date=latest_candle_by_symbol[symbol].trade_date,
                side="BUY",
                quantity=quantity,
                reference_price_inr=price,
                fill_price_inr=price,
                gross_value_inr=gross_value,
                brokerage_inr=Decimal("0.00"),
                exchange_txn_charge_inr=Decimal("0.00"),
                tax_levy_inr=Decimal("0.00"),
                cost_inr=Decimal("0.00"),
                slippage_bps=Decimal("0.00"),
                slippage_inr=Decimal("0.00"),
                fill_sequence=1,
                filled_at=order_times[symbol],
            )
            order = PaperOrder(
                order_id=order_id,
                final_decision_id=final_decision_id,
                decision_id=decision_id,
                run_id=seed_run_id,
                portfolio_id=settings.taurus_paper_portfolio_id,
                symbol=symbol,
                side="BUY",
                quantity=quantity,
                order_type="MARKET",
                status="FILLED",
                execution_policy="immediate",
                filled_quantity=quantity,
                remaining_quantity=0,
                average_fill_price_inr=price,
                gross_value_inr=gross_value,
                total_cost_inr=Decimal("0.00"),
                total_slippage_inr=Decimal("0.00"),
                slippage_bps=Decimal("0.00"),
                rejection_reason="",
                status_history=["CREATED", "ACCEPTED", "FILLED"],
                filled_trade_date=latest_candle_by_symbol[symbol].trade_date,
                submitted_at=order_times[symbol],
                updated_at=order_times[symbol],
            )
            execution_repo.replace_order_execution(
                order=order,
                fills=[fill],
                account=account,
                positions=positions,
            )
        session.commit()


def _replay_stage(replay: dict[str, object], name: str) -> dict[str, object]:
    stages = replay["stages"]
    assert isinstance(stages, list)
    for stage in stages:
        if stage.get("name") == name or stage.get("id") == name:
            return stage
    raise AssertionError(f"Replay stage {name} not found.")


def _seed_paper_graph_fixture(settings: Settings) -> None:
    latest_candle_date = (
        FakeKiteMarketDataProvider().get_daily_candles("INFY")[-1].trade_date
    )
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        for instrument in TEST_INSTRUMENTS:
            instrument_repo.upsert(
                Instrument(symbol=instrument.symbol, name=instrument.name)
            )
        graph_repo = GraphRepository(session)
        for symbol in ("INFY", "RELIANCE"):
            graph_repo.upsert_node(
                node_key=f"company:{symbol}",
                node_type="company",
                display_name=f"{symbol} Limited",
                symbol=symbol,
            )
        graph_repo.upsert_edge(
            edge_key="peer:INFY:RELIANCE",
            source_node_key="company:INFY",
            target_node_key="company:RELIANCE",
            edge_type="peer_momentum",
            provenance_type="derived",
            direction="bidirectional",
            expected_sign="positive",
            strength=Decimal("0.8500"),
            confidence=Decimal("0.9000"),
            evidence_type="operator_reviewed",
            mechanism="Reviewed real-data paper graph relation.",
            tradability_relevance="signal",
            status="active",
            valid_from=date(2024, 1, 1),
        )
        graph_repo.upsert_edge_evidence(
            edge_key="peer:INFY:RELIANCE",
            evidence_id="evidence:peer:INFY:RELIANCE",
            claim_type="peer_mapping",
            claim_summary="Reviewed test fixture for paper graph path.",
            source_date=date(2024, 1, 1),
            confidence=Decimal("0.9000"),
        )
        graph_repo.upsert_edge_stats(
            edge_key="peer:INFY:RELIANCE",
            window="60d",
            as_of_date=latest_candle_date,
            sample_size=60,
            raw_correlation=Decimal("0.8200"),
            residual_correlation=Decimal("0.7600"),
            lead_lag_score=Decimal("0.4200"),
            stability_score=Decimal("0.9000"),
        )
        session.commit()


def _write_active_allocation_policy(tmp_path: Path, *, max_stock_pct: Decimal) -> Path:
    universe_path = tmp_path / "active_shariah.yaml"
    universe_path.write_text(
        "universe_name: active_test_shariah\n"
        "default_exchange: NSE\n"
        "default_segment: EQUITY\n"
        "symbols:\n"
        "  - symbol: INFY\n"
        "    name: Infosys Ltd.\n"
        "    enabled: true\n"
        "    providers:\n"
        "      kite:\n"
        "        exchange: NSE\n"
        "        tradingsymbol: INFY\n",
        encoding="utf-8",
    )
    policy_path = tmp_path / "money_management_active.yaml"
    policy_path.write_text(
        "policy_version: active_integration_policy\n"
        f"shariah_universe_path: {universe_path}\n"
        "sleeves:\n"
        "  - sleeve_id: core_shariah\n"
        "    name: Core\n"
        "    target_weight_pct: 40.0\n"
        "    role: Core sleeve\n"
        "  - sleeve_id: active_strategy\n"
        "    name: Active\n"
        "    target_weight_pct: 35.0\n"
        "    role: Active sleeve\n"
        "  - sleeve_id: diversifying_strategy\n"
        "    name: Diversifying\n"
        "    target_weight_pct: 15.0\n"
        "    role: Diversifying sleeve\n"
        "  - sleeve_id: experimental_models\n"
        "    name: Experimental\n"
        "    target_weight_pct: 5.0\n"
        "    role: Experimental sleeve\n"
        "  - sleeve_id: cash_buffer\n"
        "    name: Cash\n"
        "    target_weight_pct: 5.0\n"
        "    role: Cash buffer\n"
        "strategy_mappings:\n"
        "  - strategy_name: core_shariah_basket_v1\n"
        "    sleeve_id: core_shariah\n"
        "  - strategy_name: graph_aware_score_v1\n"
        "    sleeve_id: active_strategy\n"
        "  - strategy_name: moving_average_crossover_v1\n"
        "    sleeve_id: active_strategy\n"
        "limits:\n"
        f"  max_stock_pct_nav: {max_stock_pct}\n"
        f"  max_stock_hard_cap_pct_nav: {max_stock_pct}\n"
        "  max_sector_pct_nav: 25.0\n"
        "  max_graph_cluster_pct_nav: 35.0\n"
        "  max_open_positions: 20\n"
        "trade_risk:\n"
        "  normal_trade_risk_pct_nav: 0.50\n"
        "  strong_trade_risk_pct_nav: 0.75\n"
        "  max_single_trade_risk_pct_nav: 1.00\n"
        "  max_total_open_trade_risk_pct_nav: 5.00\n"
        "allocation_scoring:\n"
        "  weights:\n"
        "    strategy_score: 0.30\n"
        "    trader_confidence: 0.25\n"
        "    liquidity: 0.15\n"
        "    volatility: 0.15\n"
        "    diversification: 0.10\n"
        "    recent_sleeve_performance: 0.05\n"
        "  score_bands:\n"
        "    reject_below: 60.0\n"
        "    half_normal_below: 75.0\n"
        "    normal_below: 85.0\n"
        "rebalance:\n"
        "  sleeve_drift_threshold_pct: 20.0\n"
        "  min_rebalance_notional_inr: 5000\n"
        "  review_frequency: daily_after_close\n"
        "  core_rebalance_frequency: monthly\n",
        encoding="utf-8",
    )
    return policy_path


def _write_m61_rebalance_policy(tmp_path: Path) -> Path:
    universe_path = tmp_path / "m61_core_shariah.yaml"
    universe_path.write_text(
        "universe_name: m61_core_test_shariah\n"
        "default_exchange: NSE\n"
        "default_segment: EQUITY\n"
        "symbols:\n"
        "  - symbol: LT\n"
        "    name: Larsen & Toubro Ltd.\n"
        "    enabled: true\n"
        "    providers:\n"
        "      kite:\n"
        "        exchange: NSE\n"
        "        tradingsymbol: LT\n"
        "  - symbol: RELIANCE\n"
        "    name: Reliance Industries Ltd.\n"
        "    enabled: true\n"
        "    providers:\n"
        "      kite:\n"
        "        exchange: NSE\n"
        "        tradingsymbol: RELIANCE\n",
        encoding="utf-8",
    )
    policy_path = tmp_path / "money_management_m61.yaml"
    policy_path.write_text(
        "policy_version: m61_rebalance_policy\n"
        f"shariah_universe_path: {universe_path}\n"
        "sleeves:\n"
        "  - sleeve_id: core_shariah\n"
        "    name: Core\n"
        "    target_weight_pct: 40.0\n"
        "    role: Core sleeve\n"
        "  - sleeve_id: active_strategy\n"
        "    name: Active\n"
        "    target_weight_pct: 35.0\n"
        "    role: Active sleeve\n"
        "  - sleeve_id: diversifying_strategy\n"
        "    name: Diversifying\n"
        "    target_weight_pct: 15.0\n"
        "    role: Diversifying sleeve\n"
        "  - sleeve_id: experimental_models\n"
        "    name: Experimental\n"
        "    target_weight_pct: 5.0\n"
        "    role: Experimental sleeve\n"
        "  - sleeve_id: cash_buffer\n"
        "    name: Cash\n"
        "    target_weight_pct: 5.0\n"
        "    role: Cash buffer\n"
        "strategy_mappings:\n"
        "  - strategy_name: core_shariah_basket_v1\n"
        "    sleeve_id: core_shariah\n"
        "  - strategy_name: moving_average_crossover_v1\n"
        "    sleeve_id: active_strategy\n"
        "limits:\n"
        "  max_stock_pct_nav: 20.0\n"
        "  max_stock_hard_cap_pct_nav: 20.0\n"
        "  max_sector_pct_nav: 60.0\n"
        "  max_graph_cluster_pct_nav: 60.0\n"
        "  max_open_positions: 20\n"
        "trade_risk:\n"
        "  normal_trade_risk_pct_nav: 5.00\n"
        "  strong_trade_risk_pct_nav: 7.50\n"
        "  max_single_trade_risk_pct_nav: 8.00\n"
        "  max_total_open_trade_risk_pct_nav: 25.00\n"
        "allocation_scoring:\n"
        "  weights:\n"
        "    strategy_score: 0.30\n"
        "    trader_confidence: 0.25\n"
        "    liquidity: 0.15\n"
        "    volatility: 0.15\n"
        "    diversification: 0.10\n"
        "    recent_sleeve_performance: 0.05\n"
        "  score_bands:\n"
        "    reject_below: 60.0\n"
        "    half_normal_below: 75.0\n"
        "    normal_below: 85.0\n"
        "rebalance:\n"
        "  sleeve_drift_threshold_pct: 10.0\n"
        "  min_rebalance_notional_inr: 1000\n"
        "  min_trade_drift_pct_nav: 0.25\n"
        "  score_below_exit_threshold: -0.20\n"
        "  score_below_trim_threshold: 0.00\n"
        "  over_hard_cap_trim_enabled: true\n"
        "  stale_unmapped_exit_enabled: true\n"
        "  review_frequency: daily_after_close\n"
        "  core_rebalance_frequency: monthly\n"
        "rebalance_capacity:\n"
        "  hard_cash_reserve_pct_nav: 5.0\n"
        "  same_run_proceeds_haircut_pct: 80.0\n"
        "  buy_price_buffer_pct: 5.0\n"
        "  soft_borrowing_enabled: true\n"
        "  borrowable_sleeve_ids:\n"
        "    - diversifying_strategy\n"
        "    - experimental_models\n"
        "    - core_shariah\n"
        "  borrower_sleeve_ids:\n"
        "    - active_strategy\n"
        "  max_borrowed_capacity_pct_nav: 30.0\n"
        "  max_borrowed_capacity_inr:\n"
        "  repay_priority_sleeve_ids:\n"
        "    - core_shariah\n"
        "    - diversifying_strategy\n"
        "    - experimental_models\n",
        encoding="utf-8",
    )
    return policy_path
