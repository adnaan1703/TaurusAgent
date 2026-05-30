from __future__ import annotations

from datetime import datetime, timezone
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
from taurus_core.config import Settings
from taurus_core.db.models import AuditLogModel
from taurus_core.db.session import build_session_factory
from taurus_core.ops import backup as backup_module
from taurus_core.ops.backup import create_backup, restore_backup
from taurus_core.risk.schemas import HardRuleResult, RiskPersonaReview, RiskReview
from tests.llm_fakes import FakeLLMProvider

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
    assert _stage_count(replay, "paper_fills") == 2

    session_factory = build_session_factory(settings)
    with session_factory() as session:
        alert_types = set(
            session.scalars(
                select(AuditLogModel.event_type).where(AuditLogModel.event_type.like("alert.%"))
            )
        )

    assert "alert.paper_fill" in alert_types
    assert "alert.alert_smoke_test" in alert_types


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
        taurus_paper_partial_fill_threshold=1,
    )


def _stage_count(replay: dict[str, object], name: str) -> int:
    stages = replay["stages"]
    assert isinstance(stages, list)
    for stage in stages:
        if stage["name"] == name:
            return int(stage["artifact_count"])
    raise AssertionError(f"Replay stage {name} not found.")


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
