from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from apps.dashboard.data import (
    data_freshness,
    list_analyst_reports,
    list_backtest_equity,
    list_debates,
    list_events,
    list_final_decisions,
    list_hard_rule_results,
    list_paper_fills,
    list_paper_orders,
    list_paper_positions,
    list_risk_reviews,
    list_trader_proposals,
    overview_snapshot,
)
from scripts.run_backtest import run_mock_backtest
from scripts.run_paper_once import run_mock_paper_once
from taurus_core.agents.roster import ANALYST_KEYS
from taurus_core.config import Settings
from taurus_core.db.session import build_session_factory

FULL_ANALYST_ROSTER = ",".join(ANALYST_KEYS)


def test_dashboard_queries_and_metrics_expose_m8_panels(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'taurus.db'}",
        taurus_enabled_analysts=FULL_ANALYST_ROSTER,
        taurus_paper_partial_fill_threshold=1,
    )
    run_mock_backtest(settings)
    run_mock_paper_once(symbol="INFY", settings=settings)

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        snapshot = overview_snapshot(session, symbol="INFY")
        equity = list_backtest_equity(session)
        reports = list_analyst_reports(session, symbol="INFY")
        debates = list_debates(session, symbol="INFY")
        proposals = list_trader_proposals(session, symbol="INFY")
        reviews = list_risk_reviews(session, symbol="INFY")
        hard_rules = list_hard_rule_results(session, symbol="INFY")
        decisions = list_final_decisions(session, symbol="INFY")
        positions = list_paper_positions(session, symbol="INFY")
        orders = list_paper_orders(session, symbol="INFY")
        fills = list_paper_fills(session, symbol="INFY")
        events = list_events(session, symbol="INFY")
        freshness = data_freshness(session, symbol="INFY")

    assert snapshot["latest_account"]["equity_inr"] > 0
    assert snapshot["latest_final_decision"]["status"] == "APPROVED_FOR_PAPER"
    assert snapshot["latest_order"]["status"] == "FILLED"
    assert equity
    assert len(reports) == 4
    assert debates[0]["consensus"]
    assert proposals[0]["action"] == "BUY"
    assert reviews[0]["status"] == "APPROVED"
    assert hard_rules
    assert decisions[0]["can_send_to_broker"] is True
    assert positions[0]["quantity"] > 0
    assert orders[0]["filled"] == positions[0]["quantity"]
    assert len(fills) == 2
    assert events[0]["document_id"]
    assert any(row["source"] == "daily_candles" for row in freshness)

    response = TestClient(create_app(settings)).get("/metrics")

    assert response.status_code == 200
    body = response.text
    assert "taurus_observability_db_available 1.0" in body
    assert 'taurus_db_table_rows{table="paper_orders"} 1.0' in body
    assert "taurus_data_freshness_seconds" in body
    assert "taurus_news_documents_total" in body
    assert "taurus_agent_reports_total" in body
    assert "taurus_trading_artifacts_total" in body
    assert "taurus_paper_account_equity_inr" in body
    assert "taurus_llm_failures_total" in body


def test_grafana_dashboards_are_valid_json() -> None:
    dashboard_dir = Path("infra/grafana/dashboards")
    dashboards = sorted(dashboard_dir.glob("taurus-*.json"))

    assert {dashboard.name for dashboard in dashboards} == {
        "taurus-system.json",
        "taurus-trading.json",
    }
    for dashboard in dashboards:
        payload = json.loads(dashboard.read_text())
        assert payload["uid"].startswith("taurus-")
        assert payload["panels"]
