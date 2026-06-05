from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from apps.api.main import create_app
from scripts.migrate import run_migrations
from taurus_core.compliance import import_halal_stock_compliance, parse_halal_stock_rows
from taurus_core.config import Settings
from taurus_core.db.repositories import ExecutionRepository, PaperRunRepository
from taurus_core.db.session import build_session_factory
from taurus_core.execution.schemas import (
    PaperAccount,
    PaperFill,
    PaperOrder,
    PaperPosition,
    paper_account_id,
    paper_fill_id,
)
from taurus_core.paper_trading.schemas import PaperRun
from taurus_core.paper_trading.service import PaperRunService
from tests.llm_fakes import FakeLLMProvider
from tests.market_data_fixtures import FakeKiteMarketDataProvider, seed_test_market_data


EXPECTED_TRAIL_STAGES = [
    "inputs",
    "analyst_reports",
    "debate_report",
    "trader_proposal",
    "risk_review",
    "final_decision",
    "paper_order",
    "paper_fills",
    "audit_log",
]


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


def test_ui_aggregate_endpoints_return_completed_run_trail(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["INFY"])
    client = TestClient(create_app(settings))

    overview = client.get("/ui/overview")
    history = client.get("/ui/history")
    detail = client.get(f"/ui/runs/{run.run_id}")
    trail = client.get(f"/ui/runs/{run.run_id}/symbols/INFY/decision-trail")
    risk = client.get("/ui/risk")
    portfolio = client.get("/ui/portfolio")

    assert overview.status_code == 200
    assert overview.json()["safety"]["live_trading_enabled"] is False
    assert overview.json()["safety"]["broker_provider"] == "paper"
    assert overview.json()["safety"]["llm_provider"] == "lmstudio"
    assert overview.json()["safety"]["llm_model_version"] == "lmstudio:local-model"
    assert overview.json()["allocation"]["enabled"] is False
    assert overview.json()["latest_run"]["run_id"] == run.run_id
    assert overview.json()["latest_trader_proposal"]["evaluation_mode"] == "after_close"
    assert overview.json()["latest_trader_proposal"]["lifecycle_trigger"] == "new_entry"
    assert overview.json()["latest_run"]["universe_count"] == 1
    assert overview.json()["latest_run"]["analyzed_count"] == 1
    assert overview.json()["latest_run"]["ranked_count"] == 1
    assert overview.json()["latest_run"]["proposal_count"] == 1
    assert overview.json()["latest_run"]["selected_count"] == 1
    assert overview.json()["latest_run"]["not_selected_count"] == 0
    assert overview.json()["latest_run"]["allocation_rejected_count"] == 0
    assert overview.json()["latest_run"]["risk_rejected_count"] == 0
    assert overview.json()["latest_run"]["executed_count"] == 1
    selection_preview = overview.json()["latest_run"]["selection_preview"]
    assert selection_preview[0]["symbol"] == "INFY"
    assert selection_preview[0]["allocation_status"] == "selected"
    assert selection_preview[0]["final_status"] == "APPROVED_FOR_PAPER"
    assert selection_preview[0]["execution_status"] == "PENDING_NEXT_OPEN"
    assert selection_preview[0]["reason"] == "paper_order_status:pending_next_open"
    assert overview.json()["latest_run"]["final_status_counts"] == {"APPROVED_FOR_PAPER": 1}
    assert overview.json()["latest_run"]["order_status_counts"] == {"PENDING_NEXT_OPEN": 1}
    assert overview.json()["latest_run"]["settlement_summary"] == {
        "settled": 0,
        "rejected": 0,
        "still_pending": 0,
        "skipped": 0,
        "detail_count": 0,
        "status_counts": {},
        "still_pending_order_count": 0,
        "pending_next_open_order_symbols": [],
        "has_activity": False,
    }

    assert history.status_code == 200
    assert history.json()["runs"][0]["run_id"] == run.run_id

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["run"]["status"] == "COMPLETED"
    assert detail_payload["artifacts"]["settlement"]["settled"] == 0
    assert detail_payload["artifacts"]["settlement"]["details"] == []
    assert detail_payload["selection_ledger"][0]["symbol"] == "INFY"
    assert detail_payload["selection_ledger"][0]["reason"] == "paper_order_status:pending_next_open"
    assert detail_payload["symbols"][0]["symbol"] == "INFY"
    assert detail_payload["symbols"][0]["pipeline_status"] == "running"
    assert detail_payload["symbols"][0]["order_status"] == "PENDING_NEXT_OPEN"
    assert detail_payload["symbols"][0]["analyst_roster"] == {
        "enabled": ["technical"],
        "skipped": ["news", "sentiment", "fundamentals", "graph"],
        "report_count": 1,
        "min_required": 1,
        "status": "enough_reports",
    }

    assert trail.status_code == 200
    trail_payload = trail.json()
    assert [stage["id"] for stage in trail_payload["stages"]] == EXPECTED_TRAIL_STAGES
    assert trail_payload["final_status"] == "APPROVED_FOR_PAPER"
    assert trail_payload["selection_decision"]["allocation_status"] == "selected"
    assert trail_payload["decision_reason"] == "paper_order_status:pending_next_open"
    proposal_stage = _stage_artifacts(trail_payload, "trader_proposal")[0]
    assert proposal_stage["evaluation_mode"] == "after_close"
    assert proposal_stage["lifecycle_trigger"] == "new_entry"
    assert trail_payload["analyst_roster"] == detail_payload["symbols"][0]["analyst_roster"]
    assert _stage_status(trail_payload, "paper_order") == "running"
    assert _stage_status(trail_payload, "paper_fills") == "running"
    assert trail_payload["decision_id"]

    replay = client.get(f"/ui/replay/{trail_payload['decision_id']}")
    assert replay.status_code == 200
    replay_payload = replay.json()
    assert replay_payload["decision_id"] == trail_payload["decision_id"]
    assert _stage_artifact_count(replay_payload, "final_decision") == 1
    assert _stage_status(replay_payload, "paper_order") == "running"
    assert _stage_status(replay_payload, "paper_fills") == "running"
    replay_order = _stage_artifacts(replay_payload, "paper_order")[0]
    assert replay_order["status"] == "PENDING_NEXT_OPEN"
    assert replay_order["signal_trade_date"]
    assert _find_stage(replay_payload, "paper_fills")["metrics"]["status"] == "PENDING_NEXT_OPEN"
    assert replay_payload["stages"][0]["raw"] is not None

    assert risk.status_code == 200
    assert risk.json()["status_counts"] == {"APPROVED": 1}
    assert risk.json()["money_management"] == {
        "enabled": False,
        "config_path": "configs/portfolio/money_management_v1.yaml",
    }
    assert risk.json()["allocation"]["enabled"] is False

    assert portfolio.status_code == 200
    assert portfolio.json()["latest_account"]["run_id"] == run.run_id
    assert portfolio.json()["money_management"] == risk.json()["money_management"]
    assert portfolio.json()["allocation"]["enabled"] is False
    assert len(portfolio.json()["orders"]) == 1
    assert portfolio.json()["fills"] == []


def test_ui_aggregate_endpoints_stage_pending_next_open_orders_as_running(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["INFY"])
    session_factory = build_session_factory(settings)
    _queue_latest_order_for_next_open(
        session_factory,
        settings,
        run_id=run.run_id,
        symbol="INFY",
    )
    client = TestClient(create_app(settings))

    overview = client.get("/ui/overview")
    detail = client.get(f"/ui/runs/{run.run_id}")
    trail = client.get(f"/ui/runs/{run.run_id}/symbols/INFY/decision-trail")

    assert overview.status_code == 200
    latest_run = overview.json()["latest_run"]
    assert latest_run["executed_count"] == 1
    assert latest_run["order_status_counts"] == {"PENDING_NEXT_OPEN": 1}
    assert latest_run["selection_preview"][0]["execution_status"] == "PENDING_NEXT_OPEN"
    assert latest_run["selection_preview"][0]["reason"] == "paper_order_status:pending_next_open"

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["symbols"][0]["pipeline_status"] == "running"
    assert detail_payload["symbols"][0]["order_status"] == "PENDING_NEXT_OPEN"
    assert detail_payload["selection_ledger"][0]["reason"] == "paper_order_status:pending_next_open"

    assert trail.status_code == 200
    trail_payload = trail.json()
    assert trail_payload["decision_reason"] == "paper_order_status:pending_next_open"
    assert _stage_status(trail_payload, "paper_order") == "running"
    assert _stage_status(trail_payload, "paper_fills") == "running"
    order_artifact = _stage_artifacts(trail_payload, "paper_order")[0]
    assert order_artifact["execution_policy"] == "next_open"
    assert order_artifact["scheduled_fill_session"] == "next_open"
    fill_stage = _find_stage(trail_payload, "paper_fills")
    assert fill_stage["metrics"]["status"] == "PENDING_NEXT_OPEN"
    assert fill_stage["metrics"]["filled_quantity"] == 0


def test_ui_aggregate_endpoints_treat_terminal_partial_fills_as_complete(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["INFY"])
    session_factory = build_session_factory(settings)
    decision_id = _mark_latest_order_partially_filled(
        session_factory,
        run_id=run.run_id,
        symbol="INFY",
    )
    client = TestClient(create_app(settings))

    detail = client.get(f"/ui/runs/{run.run_id}")
    trail = client.get(f"/ui/runs/{run.run_id}/symbols/INFY/decision-trail")
    replay = client.get(f"/ui/replay/{decision_id}")

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["symbols"][0]["pipeline_status"] == "complete"
    assert detail_payload["symbols"][0]["order_status"] == "PARTIALLY_FILLED"

    assert trail.status_code == 200
    trail_payload = trail.json()
    assert trail_payload["decision_reason"] == "executed_by_paper_order:partially_filled"
    assert _stage_status(trail_payload, "paper_order") == "complete"
    assert _stage_status(trail_payload, "paper_fills") == "complete"
    trail_order = _stage_artifacts(trail_payload, "paper_order")[0]
    assert trail_order["status"] == "PARTIALLY_FILLED"
    assert trail_order["remaining_quantity"] > 0

    assert replay.status_code == 200
    replay_payload = replay.json()
    assert _stage_status(replay_payload, "paper_order") == "complete"
    assert _stage_status(replay_payload, "paper_fills") == "complete"
    assert _stage_artifacts(replay_payload, "paper_order")[0]["status"] == "PARTIALLY_FILLED"


def test_disabled_money_management_uses_settings_fallback_allocation(
    tmp_path: Path,
) -> None:
    settings = Settings(
        taurus_alert_provider="mock",
        taurus_graph_enabled=False,
        taurus_graph_risk_enabled=False,
        taurus_enabled_analysts="technical",
        taurus_llm_model="",
        taurus_paper_partial_fill_threshold=1,
        taurus_money_management_enabled=False,
        taurus_money_management_config_path=str(tmp_path / "missing-policy.yaml"),
    )

    run = PaperRunService(settings).run_once(symbols=["INFY"])

    assert set(run.artifacts) == {
        "allocation",
        "analysis",
        "execution",
        "final_decisions",
        "llm_usage",
        "settlement",
        "strategy",
        "symbol_scope",
        "symbols",
    }
    assert "money_management" not in run.artifacts
    assert run.artifacts["allocation"]["policy_source"] == "settings"
    assert run.artifacts["allocation"]["ledger_count"] == 1
    assert run.artifacts["allocation"]["ledger_counts"] == {"selected": 1}
    assert run.artifacts["allocation"]["summary"]["proposal_count"] == 1
    assert run.artifacts["allocation"]["summary"]["selected_count"] == 1
    assert run.artifacts["final_decisions"]["total_count"] == 1
    assert run.artifacts["execution"]["execution_set_count"] == 1
    assert run.artifacts["execution"]["routed_order_count"] == 1
    assert run.artifacts["analysis"]["INFY"]["finalization_status"] == "completed"
    assert run.artifacts["analysis"]["INFY"]["allocation_status"] == "selected"
    assert run.artifacts["symbol_scope"]["analysis_scope"] == "strategy_selected"
    assert set(run.artifacts["symbols"]["INFY"]) == {
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
        "allocation_decision",
    }
    assert (
        run.artifacts["symbols"]["INFY"]["allocation_decision"]["sleeve_id"]
        == "settings_fallback"
    )


def test_ui_risk_and_portfolio_include_money_management_metadata_when_enabled(
    tmp_path: Path,
) -> None:
    policy_path = _write_money_management_policy(tmp_path)
    settings = Settings(
        taurus_alert_provider="mock",
        taurus_graph_enabled=False,
        taurus_graph_risk_enabled=False,
        taurus_enabled_analysts="technical",
        taurus_llm_model="",
        taurus_money_management_enabled=True,
        taurus_money_management_config_path=str(policy_path),
    )
    run_migrations(settings)
    client = TestClient(create_app(settings))

    risk = client.get("/ui/risk")
    portfolio = client.get("/ui/portfolio")
    overview = client.get("/ui/overview")

    assert risk.status_code == 200
    assert portfolio.status_code == 200
    assert overview.status_code == 200
    risk_money_management = risk.json()["money_management"]
    assert risk_money_management == portfolio.json()["money_management"]
    assert risk_money_management["enabled"] is True
    assert risk_money_management["policy"]["policy_version"] == "ui_test_policy"
    assert "core_symbols" not in risk_money_management["policy"]
    state = risk_money_management["state"]
    assert state["snapshot_source"] == "not_persisted"
    assert state["sleeve_snapshot_count"] == 0
    assert state["allocation_decision_count"] == 0
    assert state["portfolio_drawdown_pct"] == "0.0000"
    assert state["portfolio_governor_reasons"] == []
    assert state["fractional_kelly"]["status"] == "deferred_pending_paper_trade_history"
    assert state["sleeve_statuses"][0]["sleeve_id"] == "core_shariah"
    assert state["sleeve_statuses"][0]["governor_reasons"] == []
    assert state["sleeve_statuses"][0]["fractional_kelly_ready"] is False
    allocation = risk.json()["allocation"]
    assert allocation == portfolio.json()["allocation"]
    assert overview.json()["allocation"]["enabled"] is True
    assert allocation["enabled"] is True
    assert allocation["policy_version"] == "ui_test_policy"
    assert allocation["cash"]["target_cash_pct_nav"] == 5
    assert allocation["cash"]["undeployed_capacity_inr"] == 950000
    assert allocation["open_risk"]["limit_pct_nav"] == 5
    assert allocation["open_risk"]["used_risk_inr"] == 0
    assert allocation["sleeves"][0]["sleeve_id"] == "core_shariah"
    assert allocation["sleeves"][0]["target_weight_pct"] == 95
    assert allocation["sleeves"][0]["open_position_count"] == 0
    assert allocation["core_basket"]["available"] is False
    assert allocation["latest_decisions"] == []
    assert allocation["drawdown_governors"]["portfolio_drawdown_pct"] == "0.0000"


def test_ui_portfolio_labels_core_positions_from_latest_runtime_basket(
    tmp_path: Path,
) -> None:
    policy_path = _write_money_management_policy(tmp_path)
    settings = Settings(
        taurus_alert_provider="mock",
        taurus_graph_enabled=False,
        taurus_graph_risk_enabled=False,
        taurus_enabled_analysts="technical",
        taurus_llm_model="",
        taurus_money_management_enabled=True,
        taurus_money_management_config_path=str(policy_path),
    )
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    as_of = datetime(2024, 5, 20, tzinfo=timezone.utc)
    run = PaperRun(
        run_id="pr-core-runtime-label",
        schedule_name="daily_after_close",
        status="COMPLETED",
        started_at=as_of,
        completed_at=as_of,
        symbols=["INFY"],
        succeeded_symbols=["INFY"],
        artifacts={
            "money_management": {
                "core_shariah_basket": {
                    "strategy_name": "core_shariah_basket_v1",
                    "sleeve_id": "core_shariah",
                    "as_of_date": "2024-05-20",
                    "selected_symbols": ["INFY", "TCS"],
                    "target_weights": {"INFY": "5.0000"},
                    "current_weights": {"INFY": "5.0000", "TCS": "2.0000"},
                    "drift": {},
                    "rebalance": {},
                    "rejected_candidates": [],
                }
            }
        },
    )
    account = PaperAccount(
        account_id=paper_account_id(
            portfolio_id=settings.taurus_paper_portfolio_id,
            run_id=run.run_id,
        ),
        run_id=run.run_id,
        portfolio_id=settings.taurus_paper_portfolio_id,
        starting_cash_inr=Decimal("1000000.00"),
        available_cash_inr=Decimal("950000.00"),
        reserved_cash_inr=Decimal("0.00"),
        realized_pnl_inr=Decimal("0.00"),
        unrealized_pnl_inr=Decimal("0.00"),
        gross_exposure_inr=Decimal("50000.00"),
        equity_inr=Decimal("1000000.00"),
        updated_at=as_of,
    )
    position = PaperPosition(
        run_id=run.run_id,
        portfolio_id=settings.taurus_paper_portfolio_id,
        symbol="INFY",
        quantity=100,
        average_cost_inr=Decimal("500.00"),
        last_price_inr=Decimal("500.00"),
        market_value_inr=Decimal("50000.00"),
        realized_pnl_inr=Decimal("0.00"),
        unrealized_pnl_inr=Decimal("0.00"),
        updated_at=as_of,
    )
    with session_factory() as session:
        seed_test_market_data(session)
        PaperRunRepository(session).upsert(run)
        ExecutionRepository(session).replace_account_state(
            run_id=run.run_id,
            portfolio_id=settings.taurus_paper_portfolio_id,
            account=account,
            positions=[position],
        )
        session.commit()

    response = TestClient(create_app(settings)).get("/ui/portfolio")

    assert response.status_code == 200
    payload = response.json()
    assert payload["positions"][0]["sleeve_id"] == "core_shariah"
    assert payload["positions"][0]["allocation_status"] == "core_position"
    assert payload["allocation"]["core_basket"]["symbols"] == ["INFY"]
    assert [row["symbol"] for row in payload["allocation"]["core_basket"]["composition"]] == [
        "INFY"
    ]


def test_ui_decision_trail_includes_allocation_decision_when_enabled(
    tmp_path: Path,
) -> None:
    policy_path = _write_money_management_policy(tmp_path)
    settings = Settings(
        taurus_alert_provider="mock",
        taurus_graph_enabled=False,
        taurus_graph_risk_enabled=False,
        taurus_enabled_analysts="technical",
        taurus_llm_model="",
        taurus_paper_partial_fill_threshold=1,
        taurus_money_management_enabled=True,
        taurus_money_management_config_path=str(policy_path),
    )
    run = PaperRunService(settings).run_once(symbols=["INFY"])
    client = TestClient(create_app(settings))

    overview = client.get("/ui/overview")
    trail = client.get(f"/ui/runs/{run.run_id}/symbols/INFY/decision-trail")

    assert overview.status_code == 200
    assert overview.json()["allocation"]["enabled"] is True
    latest_run = overview.json()["latest_run"]
    assert latest_run["selected_count"] == 0
    assert latest_run["allocation_rejected_count"] == 1
    assert latest_run["executed_count"] == 0
    assert latest_run["selection_preview"][0]["allocation_status"] == "allocation_rejected"
    assert (
        latest_run["selection_preview"][0]["reason"]
        == "allocation_rejected_by_run_allocation:strategy_unmapped"
    )
    assert overview.json()["allocation"]["latest_decisions"][0]["symbol"] == "INFY"
    assert (
        overview.json()["allocation"]["latest_decisions"][0]["reason"]
        == "allocation_rejected_by_run_allocation:strategy_unmapped"
    )
    assert trail.status_code == 200
    allocation_decision = trail.json()["allocation_decision"]
    assert allocation_decision["symbol"] == "INFY"
    assert allocation_decision["sleeve_id"] == "unmapped"
    assert allocation_decision["status"] == "allocation_rejected"
    assert allocation_decision["binding_constraint"] == "strategy_unmapped"
    assert trail.json()["selection_decision"]["allocation_status"] == "allocation_rejected"
    assert (
        trail.json()["decision_reason"]
        == "allocation_rejected_by_run_allocation:strategy_unmapped"
    )
    proposal_stage = _find_stage(trail.json(), "trader_proposal")
    assert proposal_stage["metrics"]["sleeve_id"] == "unmapped"
    assert proposal_stage["metrics"]["binding_constraint"] == "strategy_unmapped"


def test_ui_aggregate_endpoints_show_partial_failure_and_404s(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["INFY", "MISSING"])
    client = TestClient(create_app(settings))

    detail = client.get(f"/ui/runs/{run.run_id}")
    missing_trail = client.get(f"/ui/runs/{run.run_id}/symbols/MISSING/decision-trail")
    unknown_symbol = client.get(f"/ui/runs/{run.run_id}/symbols/TCS/decision-trail")
    unknown_run = client.get("/ui/runs/not-a-run")
    unknown_replay = client.get("/ui/replay/not-a-decision")

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["run"]["status"] == "PARTIAL_FAILED"
    assert {row["symbol"]: row["pipeline_status"] for row in detail_payload["symbols"]} == {
        "INFY": "running",
        "MISSING": "failed",
    }

    assert missing_trail.status_code == 200
    missing_payload = missing_trail.json()
    assert missing_payload["final_status"] is None
    assert _stage_status(missing_payload, "analyst_reports") == "missing"
    assert _stage_status(missing_payload, "paper_order") == "skipped"
    assert missing_payload["warnings"][0]["title"] == "Symbol pipeline failed"

    assert unknown_symbol.status_code == 404
    assert unknown_run.status_code == 404
    assert unknown_replay.status_code == 404


def test_ui_decision_trail_is_run_scoped_for_repeated_symbol(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    first = PaperRunService(settings, schedule_name="ui_scope_a").run_once(symbols=["INFY"])
    second = PaperRunService(settings, schedule_name="ui_scope_b").run_once(symbols=["INFY"])
    client = TestClient(create_app(settings))

    first_trail = client.get(f"/ui/runs/{first.run_id}/symbols/INFY/decision-trail")
    second_trail = client.get(f"/ui/runs/{second.run_id}/symbols/INFY/decision-trail")

    assert first_trail.status_code == 200
    assert second_trail.status_code == 200
    first_final = _stage_artifacts(first_trail.json(), "final_decision")[0]
    second_final = _stage_artifacts(second_trail.json(), "final_decision")[0]
    first_order = _stage_artifacts(first_trail.json(), "paper_order")[0]

    assert first_final["run_id"] == first.run_id
    assert second_final["run_id"] == second.run_id
    assert first_final["final_decision_id"] != second_final["final_decision_id"]
    assert first_order["run_id"] == first.run_id
    if second_final["status"] != "APPROVED_FOR_PAPER":
        assert _stage_status(second_trail.json(), "paper_order") == "skipped"
    else:
        second_order = _stage_artifacts(second_trail.json(), "paper_order")[0]
        assert second_order["run_id"] == second.run_id


def test_ui_overview_handles_migrated_empty_database(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    client = TestClient(create_app(settings))

    response = client.get("/ui/overview")

    assert response.status_code == 200
    payload = response.json()
    assert payload["latest_run"] is None
    assert payload["recent_runs"] == []
    assert payload["positions"] == []
    assert payload["warnings"][0]["id"] == "missing-paper-account"


def test_ui_run_payloads_preserve_legacy_runs_without_selection_ledger(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    as_of = datetime(2026, 5, 21, 15, 0, tzinfo=timezone.utc)
    legacy_run = PaperRun(
        run_id="pr-legacy-no-ledger",
        schedule_name="daily_after_close",
        status="COMPLETED",
        started_at=as_of,
        completed_at=as_of,
        symbols=["INFY", "TCS"],
        succeeded_symbols=["INFY", "TCS"],
        artifacts={"strategy": {"strategy_name": "legacy_strategy"}},
    )
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        PaperRunRepository(session).upsert(legacy_run)
        session.commit()

    client = TestClient(create_app(settings))
    overview = client.get("/ui/overview")
    detail = client.get(f"/ui/runs/{legacy_run.run_id}")

    assert overview.status_code == 200
    latest_run = overview.json()["latest_run"]
    assert latest_run["run_id"] == legacy_run.run_id
    assert latest_run["universe_count"] == 2
    assert latest_run["analyzed_count"] == 2
    assert latest_run["ranked_count"] == 0
    assert latest_run["proposal_count"] == 0
    assert latest_run["selected_count"] == 0
    assert latest_run["executed_count"] == 0
    assert latest_run["selection_preview"] == []

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["selection_ledger"] == []
    assert [row["symbol"] for row in detail_payload["symbols"]] == ["INFY", "TCS"]


def test_ui_shariah_returns_active_rows_search_filters_and_pagination(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    parse_result = parse_halal_stock_rows(
        _shariah_table(
            [
                _shariah_row("yes", "Alpha Foods Ltd", "543210", "ALPHA", "Food", "/alpha"),
                _shariah_row("no", "Beta Finance Ltd", "654321", "BETA", "Finance", "/beta"),
                _shariah_row("yes", "Gamma Tools Ltd", "765432", "GAMMA", "Engineering", "/gamma"),
            ]
        ),
        source_url="https://example.test/halal-list/",
    )
    session_factory = create_app(settings).state.session_factory
    with session_factory() as session:
        import_halal_stock_compliance(
            session,
            parse_result,
            source_checksum="ui-shariah",
            fetched_at=datetime(2026, 5, 24, 9, 0, tzinfo=timezone.utc),
            generated_yaml_path=str(tmp_path / "missing-halal.yaml"),
        )
        session.commit()

    client = TestClient(create_app(settings))

    all_rows = client.get("/ui/shariah?page=1&page_size=2")
    haram_rows = client.get("/ui/shariah?status=haram")
    name_search = client.get("/ui/shariah?query=alpha")
    nse_search = client.get("/ui/shariah?query=GAM")
    bse_search = client.get("/ui/shariah?query=654321")

    assert all_rows.status_code == 200
    payload = all_rows.json()
    assert payload["counts"] == {"active_total": 3, "halal": 2, "haram": 1}
    assert payload["pagination"] == {
        "page": 1,
        "page_size": 2,
        "total": 3,
        "total_pages": 2,
    }
    assert len(payload["rows"]) == 2
    assert payload["latest_import"]["rows_imported"] == 3
    assert payload["halal_universe_export"]["exported_symbol_count"] == 0

    assert haram_rows.status_code == 200
    assert [row["compliance_status"] for row in haram_rows.json()["rows"]] == ["haram"]
    assert [row["name"] for row in name_search.json()["rows"]] == ["Alpha Foods Ltd"]
    assert [row["name"] for row in nse_search.json()["rows"]] == ["Gamma Tools Ltd"]
    assert [row["name"] for row in bse_search.json()["rows"]] == ["Beta Finance Ltd"]


def test_ui_shariah_handles_empty_database(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    client = TestClient(create_app(settings))

    response = client.get("/ui/shariah")

    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == []
    assert payload["counts"] == {"active_total": 0, "halal": 0, "haram": 0}
    assert payload["latest_import"] is None


def test_ui_cors_allows_local_vite_origin(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    client = TestClient(create_app(settings))

    response = client.options(
        "/ui/overview",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(
        taurus_alert_provider="mock",
        taurus_graph_enabled=False,
        taurus_graph_risk_enabled=False,
        taurus_enabled_analysts="technical",
        taurus_llm_model="",
        taurus_paper_partial_fill_threshold=1,
    )


def _queue_latest_order_for_next_open(
    session_factory,
    settings: Settings,
    *,
    run_id: str,
    symbol: str,
) -> None:
    with session_factory() as session:
        repo = ExecutionRepository(session)
        order_model = repo.list_orders(run_id=run_id, symbol=symbol, limit=1)[0]
        order = PaperOrder.model_validate(order_model.payload)
        account_model = repo.latest_account(run_id=run_id)
        queued_account = None
        if account_model is not None:
            account = PaperAccount.model_validate(account_model.payload)
            queued_account = account.model_copy(
                update={
                    "available_cash_inr": account.starting_cash_inr,
                    "reserved_cash_inr": Decimal("0.0000"),
                    "realized_pnl_inr": Decimal("0.0000"),
                    "unrealized_pnl_inr": Decimal("0.0000"),
                    "gross_exposure_inr": Decimal("0.0000"),
                    "equity_inr": account.starting_cash_inr,
                    "updated_at": order.updated_at,
                }
            )
        pending = order.model_copy(
            update={
                "status": "PENDING_NEXT_OPEN",
                "execution_policy": "next_open",
                "filled_quantity": 0,
                "remaining_quantity": order.quantity,
                "average_fill_price_inr": Decimal("0.0000"),
                "gross_value_inr": Decimal("0.0000"),
                "total_cost_inr": Decimal("0.0000"),
                "total_slippage_inr": Decimal("0.0000"),
                "rejection_reason": "",
                "status_history": ["CREATED", "ACCEPTED", "PENDING_NEXT_OPEN"],
                "signal_trade_date": date(2024, 12, 17),
                "scheduled_fill_session": "next_open",
                "filled_trade_date": None,
            }
        )
        if queued_account is None:
            repo.store_pending_next_open_order(order=pending)
        else:
            repo.store_pending_next_open_order(
                order=pending,
                account=queued_account,
                positions=[],
            )
        session.commit()


def _mark_latest_order_partially_filled(
    session_factory,
    *,
    run_id: str,
    symbol: str,
) -> str:
    with session_factory() as session:
        repo = ExecutionRepository(session)
        order_model = repo.list_orders(run_id=run_id, symbol=symbol, limit=1)[0]
        order = PaperOrder.model_validate(order_model.payload)
        requested_quantity = max(order.quantity, 2)
        filled_quantity = 1
        reference_price = Decimal("100.0000")
        fill_price = Decimal("100.5000")
        gross_value = fill_price * Decimal(filled_quantity)
        filled_trade_date = date(2024, 12, 18)
        partial = order.model_copy(
            update={
                "quantity": requested_quantity,
                "status": "PARTIALLY_FILLED",
                "filled_quantity": filled_quantity,
                "remaining_quantity": requested_quantity - filled_quantity,
                "average_fill_price_inr": fill_price,
                "gross_value_inr": gross_value,
                "total_cost_inr": Decimal("0.0000"),
                "total_slippage_inr": Decimal("0.0000"),
                "status_history": [
                    *order.status_history,
                    "PARTIALLY_FILLED",
                ],
                "filled_trade_date": filled_trade_date,
            }
        )
        fill = PaperFill(
            fill_id=paper_fill_id(
                order_id=order.order_id,
                fill_sequence=1,
                quantity=filled_quantity,
                reference_price=reference_price,
            ),
            order_id=order.order_id,
            final_decision_id=order.final_decision_id,
            run_id=order.run_id,
            portfolio_id=order.portfolio_id,
            symbol=order.symbol,
            trade_date=filled_trade_date,
            side=order.side,
            quantity=filled_quantity,
            reference_price_inr=reference_price,
            fill_price_inr=fill_price,
            gross_value_inr=gross_value,
            brokerage_inr=Decimal("0.0000"),
            exchange_txn_charge_inr=Decimal("0.0000"),
            tax_levy_inr=Decimal("0.0000"),
            cost_inr=Decimal("0.0000"),
            slippage_bps=order.slippage_bps,
            slippage_inr=Decimal("0.0000"),
            fill_sequence=1,
            filled_at=order.updated_at,
        )
        repo.replace_pending_next_open_order(
            order_id=order.order_id,
            order=partial,
            fills=[fill],
        )
        session.commit()
        return order.decision_id


def _write_money_management_policy(tmp_path: Path) -> Path:
    universe_path = tmp_path / "nifty_500_shariah.yaml"
    universe_path.write_text(
        "universe_name: test_shariah\n"
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
    policy_path = tmp_path / "money_management.yaml"
    policy_path.write_text(
        "policy_version: ui_test_policy\n"
        f"shariah_universe_path: {universe_path}\n"
        "sleeves:\n"
        "  - sleeve_id: core_shariah\n"
        "    name: Core\n"
        "    target_weight_pct: 95.0\n"
        "    role: Core sleeve\n"
        "  - sleeve_id: cash_buffer\n"
        "    name: Cash\n"
        "    target_weight_pct: 5.0\n"
        "    role: Cash buffer\n"
        "strategy_mappings:\n"
        "  - strategy_name: core_shariah_basket_v1\n"
        "    sleeve_id: core_shariah\n"
        "limits:\n"
        "  max_stock_pct_nav: 5.0\n"
        "  max_stock_hard_cap_pct_nav: 7.5\n"
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
        "drawdown_governors:\n"
        "  - name: caution\n"
        "    drawdown_pct: 3.0\n"
        "    action: reduce_new_position_sizes_25_pct\n"
        "rebalance:\n"
        "  sleeve_drift_threshold_pct: 20.0\n"
        "  min_rebalance_notional_inr: 5000\n"
        "  review_frequency: daily_after_close\n"
        "  core_rebalance_frequency: monthly\n",
        encoding="utf-8",
    )
    return policy_path


def _shariah_row(
    status: str,
    name: str,
    bse_code: str,
    nse_code: str,
    industry: str,
    href: str,
) -> str:
    icon = {
        "yes": "https://halalstock.in/wp-content/uploads/2021/06/hs-yes.jpg",
        "no": "https://halalstock.in/wp-content/uploads/2021/06/hs-no.jpg",
    }[status]
    return (
        "<tr>"
        f'<td><img src="{icon}" /></td>'
        f"<td>{name}</td>"
        f"<td>{bse_code}</td>"
        f"<td>{nse_code}</td>"
        f"<td>{industry}</td>"
        f'<td><a href="{href}">More</a></td>'
        "</tr>"
    )


def _shariah_table(rows: list[str]) -> str:
    return (
        '<table id="tablepress-24">'
        "<thead><tr>"
        "<th>Halal</th><th>NAME</th><th>BSE-ID</th><th>NSECode</th>"
        "<th>Industry</th><th>More</th>"
        "</tr></thead>"
        f"<tbody>{''.join(rows)}</tbody>"
        "</table>"
    )


def _stage_status(payload: dict[str, object], stage_id: str) -> str:
    stage = _find_stage(payload, stage_id)
    return str(stage["status"])


def _stage_artifact_count(payload: dict[str, object], stage_id: str) -> int:
    return len(_stage_artifacts(payload, stage_id))


def _stage_artifacts(payload: dict[str, object], stage_id: str) -> list[dict[str, object]]:
    stage = _find_stage(payload, stage_id)
    artifacts = stage["artifacts"]
    assert isinstance(artifacts, list)
    return artifacts


def _find_stage(payload: dict[str, object], stage_id: str) -> dict[str, object]:
    stages = payload["stages"]
    assert isinstance(stages, list)
    for stage in stages:
        if stage["id"] == stage_id:
            return stage
    raise AssertionError(f"Stage {stage_id} not found.")
