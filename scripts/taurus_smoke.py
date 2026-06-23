from __future__ import annotations

import json
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from scripts.backup_local import backup_local
from scripts.import_mock_news import run_import
from scripts.migrate import run_migrations
from scripts.replay_decision import replay_decision
from scripts.run_analysts import run_mock_analysts
from scripts.run_backtest import run_mock_backtest
from scripts.run_final_approval import run_mock_final_approval
from scripts.run_paper_loop import run_paper_loop
from scripts.run_paper_once import run_mock_paper_once
from scripts.run_research_debate import run_mock_research_debate
from scripts.run_risk_review import run_mock_risk_review
from scripts.run_trader_proposal import run_mock_trader_proposal
from taurus_core.config import Settings, get_settings
from taurus_core.db.models import (
    AnalystReportModel,
    BacktestRunModel,
    CompanyEventModel,
    DebateReportModel,
    FinalDecisionModel,
    PaperFillModel,
    PaperOrderModel,
    PaperRunModel,
    RiskReviewModel,
    TraderProposalModel,
)
from taurus_core.db.repositories import TaurusProfileRepository
from taurus_core.db.session import build_session_factory
from taurus_core.logging import configure_logging
from taurus_core.profiles.schemas import TaurusProfileCreate


def run_taurus_smoke(
    *,
    settings: Settings | None = None,
    symbol: str = "INFY",
    profile_smoke_id: str = "smoke-profile",
) -> dict[str, Any]:
    settings = settings or get_settings()
    symbol = symbol.upper()
    _assert_paper_only(settings)

    run_migrations(settings)
    news = run_import(settings)
    backtest = run_mock_backtest(settings)
    reports = run_mock_analysts(symbol=symbol, settings=settings)
    debate = run_mock_research_debate(symbol=symbol, settings=settings)
    proposal = run_mock_trader_proposal(symbol=symbol, settings=settings)
    risk_review = run_mock_risk_review(symbol=symbol, settings=settings)
    final_decision = run_mock_final_approval(symbol=symbol, settings=settings)
    paper_once = run_mock_paper_once(symbol=symbol, settings=settings)
    paper_loop = run_paper_loop(symbols=[symbol], settings=settings, iterations=1)
    profile_smoke = _profile_smoke(
        settings,
        symbol=symbol,
        profile_id=profile_smoke_id,
    )

    decision_id = str(paper_once["final_decision"]["decision_id"])
    replay = replay_decision(decision_id=decision_id, settings=settings, symbol=symbol)
    backup = backup_local(settings)
    api = _api_smoke(settings, symbol=symbol, decision_id=decision_id)
    counts = _artifact_counts(settings)

    _assert_outputs(
        symbol=symbol,
        news=news.to_dict(),
        backtest_run_id=backtest.run_id,
        reports=reports,
        debate=debate,
        proposal=proposal,
        risk_review=risk_review,
        final_decision=final_decision,
        paper_once=paper_once,
        paper_loop=paper_loop,
        replay=replay,
        backup=backup,
        api=api,
        counts=counts,
        expected_report_count=len(settings.enabled_analyst_keys),
    )

    return {
        "status": "passed",
        "symbol": symbol,
        "safety": {
            "taurus_mode": settings.taurus_mode,
            "live_trading_enabled": settings.live_trading_enabled,
            "broker_provider": settings.broker_provider,
            "market_data_provider": settings.taurus_market_data_provider,
            "llm_provider": settings.taurus_llm_provider,
            "alert_provider": settings.taurus_alert_provider,
        },
        "artifacts": {
            "backtest_run_id": backtest.run_id,
            "analyst_report_count": len(reports),
            "debate_id": debate["debate_id"],
            "proposal_id": proposal["proposal_id"],
            "risk_check_id": risk_review["risk_check_id"],
            "final_decision_id": final_decision["final_decision_id"],
            "decision_id": decision_id,
            "paper_order_id": paper_once["order"]["order_id"],
            "paper_loop_run_id": paper_loop[0]["run_id"],
            "backup_dir": backup["backup_dir"],
        },
        "counts": counts,
        "api": api,
        "profile_smoke": profile_smoke,
    }


def _assert_paper_only(settings: Settings) -> None:
    if settings.live_trading_enabled:
        raise AssertionError("LIVE_TRADING_ENABLED must remain false.")
    if settings.broker_provider != "paper":
        raise AssertionError("BROKER_PROVIDER must remain paper.")
    if settings.taurus_mode != "paper":
        raise AssertionError("TAURUS_MODE must remain paper for the MVP smoke run.")


def _api_smoke(
    settings: Settings, *, symbol: str, decision_id: str
) -> dict[str, object]:
    client = TestClient(create_app(settings))
    endpoints = {
        "health": "/health",
        "ready": "/ready",
        "metrics": "/metrics",
        "instruments": "/data/instruments",
        "events": "/events",
        "agent_reports": f"/agent-reports?symbol={symbol}",
        "debates": "/debates",
        "trader_proposals": "/trader-proposals",
        "risk_checks": "/risk-checks",
        "final_decisions": "/final-decisions",
        "paper_orders": "/paper/orders",
        "paper_fills": "/paper/fills",
        "paper_positions": "/paper/positions",
        "paper_account": "/paper/account",
        "runs": "/runs",
        "replay": f"/replay/{decision_id}",
    }
    statuses: dict[str, int] = {}
    for name, path in endpoints.items():
        response = client.get(path)
        statuses[name] = response.status_code
        if response.status_code != 200:
            raise AssertionError(
                f"API smoke endpoint {path} returned {response.status_code}."
            )

    alert_response = client.post("/alerts/test")
    statuses["alert_test"] = alert_response.status_code
    if (
        alert_response.status_code != 200
        or alert_response.json().get("delivered") is not True
    ):
        raise AssertionError("Mock alert API smoke failed.")

    metrics_body = client.get("/metrics").text
    if "taurus_live_trading_enabled 0.0" not in metrics_body:
        raise AssertionError("Metrics must confirm live trading is disabled.")

    return statuses


def _profile_smoke(
    settings: Settings,
    *,
    symbol: str,
    profile_id: str,
) -> dict[str, object]:
    _ensure_smoke_profile(settings, profile_id=profile_id)
    profile_settings = _settings_for_profile(settings, profile_id=profile_id)
    runs = run_paper_loop(symbols=[symbol], settings=profile_settings, iterations=1)
    if not runs or runs[0].get("status") != "COMPLETED":
        raise AssertionError(f"Profile smoke paper loop failed for {profile_id}.")

    api = _profile_api_smoke(profile_settings, profile_id=profile_id)
    return {
        "profile_id": profile_id,
        "paper_loop_run_id": runs[0]["run_id"],
        "api": api,
    }


def _ensure_smoke_profile(settings: Settings, *, profile_id: str) -> None:
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        repo = TaurusProfileRepository(session)
        profile = repo.get_profile(profile_id)
        if profile is None:
            profile = repo.create_profile(
                TaurusProfileCreate(
                    profile_id=profile_id,
                    display_name="Smoke Profile",
                    starting_corpus_inr=Decimal("150000"),
                    description="Deterministic smoke-test paper profile.",
                )
            )
        if profile.status != "ACTIVE":
            raise AssertionError(f"Smoke profile {profile_id} must be ACTIVE.")
        session.commit()


def _settings_for_profile(settings: Settings, *, profile_id: str) -> Settings:
    return settings.model_copy(
        update={
            "taurus_profile_id": profile_id,
            "taurus_paper_portfolio_id": profile_id,
        }
    )


def _profile_api_smoke(settings: Settings, *, profile_id: str) -> dict[str, int]:
    client = TestClient(create_app(settings))
    endpoints = {
        "profiles": "/profiles",
        "paper_account": f"/paper/account?profile_id={profile_id}",
        "paper_orders": f"/paper/orders?profile_id={profile_id}",
        "ui_overview": f"/ui/overview?profile_id={profile_id}",
        "ui_history": f"/ui/history?profile_id={profile_id}",
        "ui_portfolio": f"/ui/portfolio?profile_id={profile_id}",
    }
    statuses: dict[str, int] = {}
    payloads: dict[str, Any] = {}
    for name, path in endpoints.items():
        response = client.get(path)
        statuses[name] = response.status_code
        if response.status_code != 200:
            raise AssertionError(
                f"Profile API smoke endpoint {path} returned {response.status_code}."
            )
        payloads[name] = response.json()

    profiles = payloads["profiles"]
    if profile_id not in {profile["profile_id"] for profile in profiles}:
        raise AssertionError(f"Profile smoke did not list {profile_id}.")
    if payloads["paper_account"]["portfolio_id"] != profile_id:
        raise AssertionError("Profile paper account returned another profile.")
    if not payloads["paper_orders"]:
        raise AssertionError("Profile paper loop did not create a paper order.")
    if {order["portfolio_id"] for order in payloads["paper_orders"]} != {profile_id}:
        raise AssertionError("Profile paper orders leaked another profile.")
    if payloads["ui_overview"]["active_profile"]["profile_id"] != profile_id:
        raise AssertionError("Profile overview did not select the smoke profile.")
    if {run["profile_id"] for run in payloads["ui_history"]["runs"]} != {profile_id}:
        raise AssertionError("Profile history leaked another profile.")
    if payloads["ui_portfolio"]["active_profile"]["profile_id"] != profile_id:
        raise AssertionError("Profile portfolio did not select the smoke profile.")
    return statuses


def _artifact_counts(settings: Settings) -> dict[str, int]:
    session_factory = build_session_factory(settings)
    models = {
        "backtest_runs": BacktestRunModel,
        "company_events": CompanyEventModel,
        "analyst_reports": AnalystReportModel,
        "debate_reports": DebateReportModel,
        "trader_proposals": TraderProposalModel,
        "risk_reviews": RiskReviewModel,
        "final_decisions": FinalDecisionModel,
        "paper_orders": PaperOrderModel,
        "paper_fills": PaperFillModel,
        "paper_runs": PaperRunModel,
    }
    with session_factory() as session:
        return {
            name: int(session.scalar(select(func.count()).select_from(model)) or 0)
            for name, model in models.items()
        }


def _assert_outputs(
    *,
    symbol: str,
    news: dict[str, Any],
    backtest_run_id: str,
    reports: list[dict[str, Any]],
    debate: dict[str, Any],
    proposal: dict[str, Any],
    risk_review: dict[str, Any],
    final_decision: dict[str, Any],
    paper_once: dict[str, Any],
    paper_loop: list[dict[str, Any]],
    replay: dict[str, Any],
    backup: dict[str, str],
    api: dict[str, object],
    counts: dict[str, int],
    expected_report_count: int,
) -> None:
    if news["event_count"] < 1:
        raise AssertionError("Mock news import did not produce events.")
    if not backtest_run_id.startswith("bt-"):
        raise AssertionError("Backtest did not produce a Taurus run_id.")
    if len(reports) != expected_report_count:
        raise AssertionError(
            f"Analyst suite produced {len(reports)} report(s), expected {expected_report_count}."
        )
    if (
        debate["symbol"] != symbol
        or not debate["bull_thesis"]
        or not debate["bear_thesis"]
    ):
        raise AssertionError("Debate output is incomplete.")
    if (
        proposal["is_order"] is not False
        or proposal["requires_risk_approval"] is not True
    ):
        raise AssertionError("Trader proposal must remain a proposal, not an order.")
    if (
        risk_review["is_order"] is not False
        or risk_review["can_send_to_broker"] is not False
    ):
        raise AssertionError("Risk review must not be broker-routable.")
    if final_decision["status"] != "APPROVED_FOR_PAPER":
        raise AssertionError("Final decision was not approved for paper trading.")
    if (
        final_decision["is_order"] is not False
        or final_decision["can_send_to_broker"] is not True
    ):
        raise AssertionError("Final decision broker flags are inconsistent.")

    order = paper_once["order"]
    if not isinstance(order, dict) or order["status"] != "PENDING_NEXT_OPEN":
        raise AssertionError(
            "Paper once did not queue a pending next-open paper order."
        )
    if order["filled_quantity"] != 0:
        raise AssertionError(
            "Pending next-open paper order should not fill immediately."
        )
    if not paper_loop or paper_loop[0]["status"] != "COMPLETED":
        raise AssertionError("Paper loop did not complete.")
    if replay["decision_id"] != paper_once["final_decision"]["decision_id"]:
        raise AssertionError("Replay did not reconstruct the requested decision.")
    if (
        not Path(backup["artifact_path"]).exists()
        or not Path(backup["manifest_path"]).exists()
    ):
        raise AssertionError("Backup artifact or manifest is missing.")
    if not api or any(status != 200 for status in api.values()):
        raise AssertionError("API smoke did not return all 200 responses.")
    for name, count in counts.items():
        if name == "paper_fills":
            if count != 0:
                raise AssertionError(
                    "M47 smoke expected no paper fills before settlement."
                )
            continue
        if count < 1:
            raise AssertionError(f"Expected at least one persisted {name} row.")


if __name__ == "__main__":
    configure_logging()
    payload = run_taurus_smoke(
        symbol=os.environ.get("SYMBOL", "INFY"),
        profile_smoke_id=os.environ.get("TAURUS_SMOKE_PROFILE_ID", "smoke-profile"),
    )
    print(json.dumps(payload, sort_keys=True))
