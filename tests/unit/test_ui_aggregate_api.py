from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from apps.api.main import create_app
from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.paper_trading.service import PaperRunService


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
    assert overview.json()["latest_run"]["run_id"] == run.run_id
    assert overview.json()["latest_run"]["final_status_counts"] == {"APPROVED_FOR_PAPER": 1}
    assert overview.json()["latest_run"]["order_status_counts"] == {"FILLED": 1}

    assert history.status_code == 200
    assert history.json()["runs"][0]["run_id"] == run.run_id

    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["run"]["status"] == "COMPLETED"
    assert detail_payload["symbols"][0]["symbol"] == "INFY"
    assert detail_payload["symbols"][0]["pipeline_status"] == "complete"
    assert detail_payload["symbols"][0]["order_status"] == "FILLED"

    assert trail.status_code == 200
    trail_payload = trail.json()
    assert [stage["id"] for stage in trail_payload["stages"]] == EXPECTED_TRAIL_STAGES
    assert trail_payload["final_status"] == "APPROVED_FOR_PAPER"
    assert _stage_status(trail_payload, "paper_order") == "complete"
    assert _stage_status(trail_payload, "paper_fills") == "complete"
    assert trail_payload["decision_id"]

    replay = client.get(f"/ui/replay/{trail_payload['decision_id']}")
    assert replay.status_code == 200
    replay_payload = replay.json()
    assert replay_payload["decision_id"] == trail_payload["decision_id"]
    assert _stage_artifact_count(replay_payload, "final_decision") == 1
    assert replay_payload["stages"][0]["raw"] is not None

    assert risk.status_code == 200
    assert risk.json()["status_counts"] == {"APPROVED": 1}

    assert portfolio.status_code == 200
    assert portfolio.json()["latest_account"]["run_id"] == run.run_id
    assert len(portfolio.json()["orders"]) == 1
    assert len(portfolio.json()["fills"]) == 2


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
        "INFY": "complete",
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
    second_order = _stage_artifacts(second_trail.json(), "paper_order")[0]

    assert first_final["run_id"] == first.run_id
    assert second_final["run_id"] == second.run_id
    assert first_final["final_decision_id"] != second_final["final_decision_id"]
    assert first_order["run_id"] == first.run_id
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
        database_url=f"sqlite:///{tmp_path / 'taurus.db'}",
        taurus_alert_provider="mock",
        taurus_llm_provider="mock",
        taurus_paper_partial_fill_threshold=1,
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
