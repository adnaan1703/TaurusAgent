from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.api.main import create_app
from scripts.migrate import run_migrations
from scripts.run_paper_once import run_mock_paper_once
from taurus_core.agents.roster import ANALYST_KEYS
from taurus_core.alerts.templates import risk_review_events
from taurus_core.brokers.paper_broker import PaperBroker
from taurus_core.config import Settings
from taurus_core.db.models import AuditLogModel
from taurus_core.db.repositories import (
    CandleRepository,
    ExecutionRepository,
    TaurusProfileRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.market_data import DailyCandle
from taurus_core.execution.schemas import PaperOrder
from taurus_core.ops import backup as backup_module
from taurus_core.ops.backup import create_backup, restore_backup
from taurus_core.risk.schemas import HardRuleResult, RiskPersonaReview, RiskReview
from tests.llm_fakes import FakeLLMProvider
from tests.market_data_fixtures import seed_test_market_data

FULL_ANALYST_ROSTER = ",".join(ANALYST_KEYS)


@pytest.fixture(autouse=True)
def fake_llm_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "scripts.run_trader_proposal.build_llm_provider",
        lambda settings: FakeLLMProvider(),
    )


def test_mock_alerts_are_stored_and_replay_api_reconstructs_decision_path(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    _set_default_profile_corpus(session_factory)
    with session_factory() as session:
        seed_test_market_data(session, candle_count=252)
    payload = run_mock_paper_once(symbol="INFY", settings=settings)
    decision_id = str(payload["final_decision"]["decision_id"])

    client = TestClient(create_app(settings))
    alert_response = client.post("/alerts/test")
    replay_response = client.get(f"/replay/{decision_id}")

    assert alert_response.status_code == 200
    assert alert_response.json()["adapter"] == "mock"
    assert alert_response.json()["delivered"] is True
    assert replay_response.status_code == 200
    replay = replay_response.json()
    assert replay["decision_id"] == decision_id
    assert replay["symbol"] == "INFY"
    assert _stage_count(replay, "analyst_reports") == 5
    assert _stage_count(replay, "risk_review") == 1
    assert _stage_count(replay, "final_decision") == 1
    assert _stage_count(replay, "paper_order") == 1
    assert _stage_count(replay, "paper_fills") == 0
    assert payload["order"]["status"] == "PENDING_NEXT_OPEN"

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        alert_types = set(
            session.scalars(
                select(AuditLogModel.event_type).where(
                    AuditLogModel.event_type.like("alert.%")
                )
            )
        )

    assert "alert.paper_fill" not in alert_types
    assert "alert.alert_smoke_test" in alert_types


def test_next_open_settlement_alert_and_ui_replay_show_terminal_fill(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    _set_default_profile_corpus(session_factory)
    with session_factory() as session:
        seed_test_market_data(session, candle_count=252)
    payload = run_mock_paper_once(symbol="INFY", settings=settings)
    decision_id = str(payload["final_decision"]["decision_id"])

    with session_factory() as session:
        repo = ExecutionRepository(session)
        order_row = repo.list_orders(
            portfolio_id=settings.taurus_paper_portfolio_id,
            symbol="INFY",
            limit=1,
        )[0]
        pending_order = PaperOrder.model_validate(order_row.payload)
        assert pending_order.status == "PENDING_NEXT_OPEN"
        execution_trade_date = _append_next_open_candle(session, pending_order)
        summary = PaperBroker(session, settings).settle_pending_next_open_orders(
            portfolio_id=settings.taurus_paper_portfolio_id,
            run_id="settlement-run",
            settled_at=datetime(2024, 12, 19, 4, 0, tzinfo=timezone.utc),
        )
        assert summary.settled == 1

    replay_response = TestClient(create_app(settings)).get(f"/ui/replay/{decision_id}")

    assert replay_response.status_code == 200
    replay = replay_response.json()
    assert _stage_status(replay, "paper_order") == "complete"
    assert _stage_status(replay, "paper_fills") == "complete"
    replay_order = _stage_artifacts(replay, "paper_order")[0]
    replay_fill = _stage_artifacts(replay, "paper_fills")[0]
    assert replay_order["status"] == "FILLED"
    assert replay_order["status_history"] == [
        "CREATED",
        "ACCEPTED",
        "PENDING_NEXT_OPEN",
        "FILLED",
    ]
    assert replay_order["filled_trade_date"] == execution_trade_date.isoformat()
    assert replay_fill["trade_date"] == execution_trade_date.isoformat()
    assert replay_fill["order_id"] == replay_order["order_id"]

    with session_factory() as session:
        alert_types = list(
            session.scalars(
                select(AuditLogModel.event_type).where(
                    AuditLogModel.event_type.like("alert.%")
                )
            )
        )
    assert alert_types.count("alert.paper_fill") == 1
    assert "alert.order_rejection" not in alert_types


def test_risk_alert_templates_cover_hardening_events() -> None:
    review = _risk_review(
        hard_rule_results=[
            HardRuleResult(
                rule="kill_switch",
                status="blocked",
                details="Kill switch is enabled.",
            ),
            HardRuleResult(
                rule="severe_event_block",
                status="blocked",
                details="Blocked by regulatory probe.",
            ),
            HardRuleResult(
                rule="stale_data",
                status="rejected",
                details="Proposal source data is too old.",
            ),
        ]
    )

    event_types = {event.event_type for event in risk_review_events(review)}

    assert {
        "kill_switch_activation",
        "severe_event_detected",
        "stale_data_event",
        "risk_rejection_spike",
    }.issubset(event_types)


def test_scheduled_job_failure_alert_is_recorded(tmp_path: Path) -> None:
    from taurus_core.paper_trading.service import PaperRunService

    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["MISSING"])

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        alert_count = len(
            list(
                session.scalars(
                    select(AuditLogModel).where(
                        AuditLogModel.event_type == "alert.scheduled_job_failure"
                    )
                )
            )
        )

    assert run.status == "FAILED"
    assert alert_count == 1


def test_postgres_backup_manifest_is_created(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = _settings_for_temp_db(tmp_path)

    def fake_backup_postgres(database_url: str, backup_dir: Path) -> Path:
        artifact = backup_dir / "taurus-postgres.dump"
        artifact.write_bytes(b"postgres dump")
        return artifact

    monkeypatch.setattr(backup_module, "_backup_postgres", fake_backup_postgres)

    backup = create_backup(settings, output_root=tmp_path / "backups")

    assert backup.database_kind == "postgresql"
    assert backup.artifact_path.exists()
    assert backup.manifest_path.exists()


def test_postgres_restore_requires_explicit_confirmation(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    backup_dir = tmp_path / "backups" / "taurus-test"
    backup_dir.mkdir(parents=True)
    (backup_dir / "taurus-postgres.dump").write_bytes(b"postgres dump")
    (backup_dir / "manifest.json").write_text(
        (
            '{"artifact": "taurus-postgres.dump", '
            '"database_kind": "postgresql", '
            '"database_url": "postgresql+psycopg://taurus:***@localhost:5432/taurus"}\n'
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="RESTORE_CONFIRM"):
        restore_backup(settings, backup=backup_dir)


def test_postgres_backup_uses_docker_compose_when_pg_dump_is_missing(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def fake_which(name: str) -> str | None:
        if name == "pg_dump":
            return None
        if name == "docker":
            return "/usr/local/bin/docker"
        return None

    def fake_run(args, *, stdout, check: bool) -> None:
        calls.append(list(args))
        assert check is True
        stdout.write(b"postgres dump")

    monkeypatch.setattr(backup_module.shutil, "which", fake_which)
    monkeypatch.setattr(backup_module.subprocess, "run", fake_run)

    artifact = backup_module._backup_postgres(
        "postgresql+psycopg://taurus:secret@localhost:5432/taurus",
        tmp_path,
    )

    assert artifact.read_bytes() == b"postgres dump"
    assert calls == [
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "-e",
            "PGPASSWORD=secret",
            "postgres",
            "pg_dump",
            "--format=custom",
            "--username",
            "taurus",
            "taurus",
        ]
    ]


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(
        taurus_alert_provider="mock",
        taurus_enabled_analysts=FULL_ANALYST_ROSTER,
        taurus_initial_capital_inr=1_000_000,
        taurus_paper_partial_fill_threshold=1,
    )


def _set_default_profile_corpus(session_factory) -> None:
    with session_factory() as session:
        TaurusProfileRepository(session).update_profile_corpus(
            "local-paper",
            Decimal("1000000"),
        )
        session.commit()


def _append_next_open_candle(session, order: PaperOrder):
    assert order.signal_trade_date is not None
    trade_date = order.signal_trade_date + timedelta(days=1)
    while trade_date.weekday() >= 5:
        trade_date += timedelta(days=1)
    candle = DailyCandle(
        symbol=order.symbol,
        trade_date=trade_date,
        open=Decimal("151.0000"),
        high=Decimal("152.0000"),
        low=Decimal("150.0000"),
        close=Decimal("152.0000"),
        volume=1_000_000,
        source="test_next_open_settlement",
        data_available_time=datetime.combine(
            trade_date, time(18, 0), tzinfo=timezone.utc
        ),
    )
    CandleRepository(session).upsert([candle])
    session.commit()
    return trade_date


def _stage_count(replay: dict[str, object], name: str) -> int:
    stages = replay["stages"]
    assert isinstance(stages, list)
    for stage in stages:
        if stage["name"] == name:
            return int(stage["artifact_count"])
    raise AssertionError(f"Replay stage {name} not found.")


def _stage_status(replay: dict[str, object], stage_id: str) -> str:
    return str(_ui_stage(replay, stage_id)["status"])


def _stage_artifacts(
    replay: dict[str, object], stage_id: str
) -> list[dict[str, object]]:
    artifacts = _ui_stage(replay, stage_id)["artifacts"]
    assert isinstance(artifacts, list)
    return artifacts


def _ui_stage(replay: dict[str, object], stage_id: str) -> dict[str, object]:
    stages = replay["stages"]
    assert isinstance(stages, list)
    for stage in stages:
        assert isinstance(stage, dict)
        if stage["id"] == stage_id:
            return stage
    raise AssertionError(f"UI replay stage {stage_id} not found.")


def _risk_review(*, hard_rule_results: list[HardRuleResult]) -> RiskReview:
    return RiskReview(
        risk_check_id="risk-test",
        decision_id="dec-test",
        run_id="run-test",
        symbol="INFY",
        proposal_id="tp-test",
        debate_id="deb-test",
        as_of=datetime.now(timezone.utc),
        status="BLOCKED",
        requested_position_pct_nav=Decimal("3.0000"),
        approved_position_pct_nav=Decimal("0.0000"),
        hard_rule_results=hard_rule_results,
        persona_reviews=[
            RiskPersonaReview(
                agent_name="SafeRiskAgent",
                recommendation="block",
                score=Decimal("-0.5000"),
                confidence=Decimal("0.9000"),
                key_points=["hard rule blocked"],
                required_conditions=["clear hard rule"],
                model_version="test",
            )
        ],
        risk_committee_summary="Blocked by hard rules.",
        source_report_ids=["ar-test"],
        model_version="test",
    )
