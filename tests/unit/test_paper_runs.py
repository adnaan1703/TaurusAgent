from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

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
    FinalDecisionModel,
    PaperOrderModel,
    PaperRunModel,
    RiskReviewModel,
    TraderProposalModel,
)
from taurus_core.db.repositories import ExecutionRepository, GraphRepository, InstrumentRepository
from taurus_core.db.repositories import ResearchRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.execution.order_router import ExecutionRouter
from taurus_core.paper_trading.schemas import PaperRunUniverse
from taurus_core.paper_trading.service import (
    ANALYSIS_STAGE_NAMES,
    FINALIZATION_STAGE_NAMES,
    PaperSymbolAnalysis,
    PaperRunService,
    _sleeve_snapshots_for_allocation,
    _symbol_artifact_from_results,
)
from taurus_core.portfolio import ActiveAllocationPosition, load_money_management_policy
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


def test_paper_run_service_executes_full_chain_and_api_returns_runs(tmp_path: Path) -> None:
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
    assert run.artifacts["symbols"]["INFY"]["final_status"] == "APPROVED_FOR_PAPER"
    assert run.artifacts["symbols"]["INFY"]["order_status"] == "PENDING_NEXT_OPEN"
    assert run.artifacts["symbols"]["INFY"]["order_reason"] == "queued_for_next_open_settlement"
    assert run.artifacts["symbols"]["INFY"]["analyst_roster"] == {
        "enabled": ["technical"],
        "skipped": ["news", "sentiment", "fundamentals", "graph"],
        "report_count": 1,
        "min_required": 1,
        "status": "enough_reports",
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
            row.agent_name
            for row in session.scalars(select(AnalystReportModel))
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
    assert second.artifacts["strategy"]["symbol_selection"]["INFY"][
        "included_from_open_position"
    ] is True
    assert second.artifacts["strategy"]["symbol_selection"]["TCS"]["requested_explicitly"] is True


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

    first = PaperRunService(settings, schedule_name="m48_buy_queue").run_once(symbols=["INFY"])
    assert first.status == "COMPLETED"
    assert first.artifacts["settlement"]["settled"] == 0
    assert first.artifacts["symbols"]["INFY"]["order_status"] == "PENDING_NEXT_OPEN"

    candle_count["value"] = 253
    forced_actions = {"INFY": "EXIT"}
    _force_trader_actions(monkeypatch, forced_actions)
    second = PaperRunService(settings, schedule_name="m48_buy_settle_exit_queue").run_once(
        symbols=["INFY"]
    )
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
        second_positions = ExecutionRepository(session).latest_open_positions_by_portfolio(
            portfolio_id=settings.taurus_paper_portfolio_id,
        )

    assert [fill.side for fill in second_fills] == ["BUY"]
    assert {position.symbol: position.quantity for position in second_positions}["INFY"] > 0

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
        latest_positions = ExecutionRepository(session).latest_open_positions_by_portfolio(
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
    assert api_overview["latest_run"]["settlement_summary"]["status_counts"] == {"FILLED": 1}
    assert second_detail["symbols"][0]["order_status"] == "FILLED"
    assert second_detail["artifacts"]["symbols"]["INFY"]["proposal_action"] == "EXIT"
    assert second_detail["artifacts"]["symbols"]["INFY"]["order_status"] == "PENDING_NEXT_OPEN"
    assert third_detail["artifacts"]["settlement"]["settled"] == 1
    assert third_detail["artifacts"]["settlement"]["details"][0]["side"] == "SELL"
    assert third_detail["artifacts"]["settlement"]["details"][0]["status"] == "FILLED"


def test_eod_paper_run_records_pending_orders_waiting_for_newer_candle(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path, enabled_analysts="technical")
    first = PaperRunService(settings, schedule_name="m48_waiting_seed").run_once(symbols=["INFY"])
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
    assert settlement["still_pending_orders"][0]["outcome_reason"] == "waiting_for_next_candle"
    assert "INFY" in scope["pending_next_open_order_symbols"]
    assert "INFY" in scope["analyzed_symbols"]
    assert second.artifacts["strategy"]["symbol_selection"]["INFY"][
        "included_from_pending_next_open_order"
    ] is True


def test_money_management_paper_run_creates_shariah_equity_core_decisions(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path, money_management_enabled=True)
    run = PaperRunService(settings).run_once(symbols=["INFY"])
    universe = load_market_data_universe("configs/market_data/nifty_500_shariah.yaml")
    universe_by_symbol = {entry.symbol: entry for entry in universe.symbols}

    core = run.artifacts["money_management"]["core_shariah_basket"]
    decision_symbols = {decision["symbol"] for decision in core["decisions"]}

    assert run.status == "COMPLETED"
    assert core["strategy_name"] == "core_shariah_basket_v1"
    assert set(core["selected_symbols"]).issubset(set(universe_by_symbol))
    assert decision_symbols == set(core["target_weights"])
    assert decision_symbols
    for symbol in decision_symbols:
        universe_symbol = universe_by_symbol[symbol]
        assert universe_symbol.exchange == "NSE"
        assert universe_symbol.segment == "EQUITY"
    assert all(
        Decimal(str(weight)) <= Decimal("7.5")
        for weight in core["target_weights"].values()
    )


def test_sleeve_snapshots_attribute_runtime_core_basket_holdings(tmp_path: Path) -> None:
    policy_path = _write_active_allocation_policy(tmp_path, max_stock_pct=Decimal("5.0"))
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
    assert by_sleeve["diversifying_strategy"].current_exposure_inr == Decimal("50000.00")
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
    assert strategy["graph_strategy_config_path"] == "configs/strategies/graph_aware_score_v1.yaml"
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
            row.agent_name
            for row in session.scalars(select(AnalystReportModel))
        }
        risk_review = session.scalars(select(RiskReviewModel)).first()

    assert "GraphAnalystAgent" in agent_names
    assert risk_review is not None
    hard_rules = {row["rule"] for row in risk_review.hard_rule_results}
    assert "graph_correlated_cluster_concentration" in hard_rules


def test_graph_enabled_money_management_run_adds_active_allocation_metadata(
    tmp_path: Path,
) -> None:
    policy_path = _write_active_allocation_policy(tmp_path, max_stock_pct=Decimal("1.0"))
    settings = _settings_for_temp_db(
        tmp_path,
        enabled_analysts="technical,graph",
        graph_enabled=True,
        graph_risk_enabled=True,
        money_management_enabled=True,
        money_management_config_path=str(policy_path),
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

    assert proposal.payload["allocation_decision"]["binding_constraint"] == "stock_exposure"
    assert risk_review.payload["allocation_decision"]["binding_constraint"] == "stock_exposure"
    assert final_decision.payload["allocation_decision"]["binding_constraint"] == "stock_exposure"


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
    assert run.artifacts == {}


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
                select(TraderProposalModel).where(TraderProposalModel.run_id == run.run_id)
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
    policy_path = _write_active_allocation_policy(tmp_path, max_stock_pct=Decimal("5.0"))
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
    assert allocation["policy_source"] == "money_management_policy"
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
                select(FinalDecisionModel).where(FinalDecisionModel.run_id == run.run_id)
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
                select(FinalDecisionModel).where(FinalDecisionModel.run_id == run.run_id)
            )
        }

    client = TestClient(create_app(settings))
    selected_replay = client.get(f"/replay/{decision_ids[selected_symbol]}").json()
    not_selected_replay = client.get(f"/replay/{decision_ids[not_selected_symbol]}").json()

    selected_allocation = _replay_stage(selected_replay, "allocation_ledger")["artifacts"][0]
    selected_execution = _replay_stage(selected_replay, "deferred_execution")["artifacts"]
    not_selected_allocation = _replay_stage(not_selected_replay, "allocation_ledger")[
        "artifacts"
    ][0]
    not_selected_execution = _replay_stage(not_selected_replay, "deferred_execution")[
        "artifacts"
    ]
    not_selected_final = _replay_stage(not_selected_replay, "final_decision")["artifacts"][0]

    assert _replay_stage(selected_replay, "strategy_ranking")["artifact_count"] >= 1
    assert selected_allocation["ledger_entry"]["status"] in {
        "selected",
        "allocation_reduced",
    }
    assert {item["kind"] for item in selected_execution} >= {"execution_set"}
    assert _replay_stage(not_selected_replay, "strategy_ranking")["artifact_count"] >= 1
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
                select(TraderProposalModel).where(TraderProposalModel.run_id == run.run_id)
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
                select(TraderProposalModel).where(TraderProposalModel.run_id == second.run_id)
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

    run = PaperRunService(settings, schedule_name=f"lifecycle_{action.lower()}").run_once(
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
        assert execution["skipped_symbols"][0]["reason"] == "hold_no_paper_order_expected"


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


def _force_trader_actions(
    monkeypatch: pytest.MonkeyPatch,
    action_by_symbol: dict[str, str],
) -> None:
    original_analyze_symbol = PaperRunService.analyze_symbol

    def patched_analyze_symbol(self: PaperRunService, *args, **kwargs) -> PaperSymbolAnalysis:
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
) -> Settings:
    return Settings(
        taurus_paper_partial_fill_threshold=1,
        taurus_enabled_analysts=enabled_analysts,
        taurus_graph_enabled=graph_enabled,
        taurus_graph_risk_enabled=graph_risk_enabled,
        taurus_money_management_enabled=money_management_enabled,
        taurus_money_management_config_path=money_management_config_path,
        taurus_paper_analysis_scope=paper_analysis_scope,
        taurus_paper_execution_scope=paper_execution_scope,
        taurus_max_open_positions=max_open_positions,
    )


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


def _replay_stage(replay: dict[str, object], name: str) -> dict[str, object]:
    stages = replay["stages"]
    assert isinstance(stages, list)
    for stage in stages:
        if stage["name"] == name:
            return stage
    raise AssertionError(f"Replay stage {name} not found.")


def _seed_paper_graph_fixture(settings: Settings) -> None:
    latest_candle_date = FakeKiteMarketDataProvider().get_daily_candles("INFY")[-1].trade_date
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        for instrument in TEST_INSTRUMENTS:
            instrument_repo.upsert(Instrument(symbol=instrument.symbol, name=instrument.name))
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
