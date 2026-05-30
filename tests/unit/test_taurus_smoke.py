from __future__ import annotations

from pathlib import Path

import pytest

from scripts.taurus_smoke import run_taurus_smoke
from taurus_core.agents.roster import ANALYST_KEYS
from taurus_core.config import Settings
from tests.llm_fakes import FakeLLMProvider

FULL_ANALYST_ROSTER = ",".join(ANALYST_KEYS)


def test_taurus_smoke_covers_paper_mvp_release_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    fake_provider = FakeLLMProvider()
    monkeypatch.setattr("scripts.run_analysts.build_llm_provider", lambda settings: fake_provider)
    monkeypatch.setattr("scripts.run_research_debate.build_llm_provider", lambda settings: fake_provider)
    monkeypatch.setattr("scripts.run_trader_proposal.build_llm_provider", lambda settings: fake_provider)
    monkeypatch.setattr("taurus_core.paper_trading.service.build_llm_provider", lambda settings: fake_provider)
    settings = Settings(
        taurus_alert_provider="mock",
        taurus_enabled_analysts=FULL_ANALYST_ROSTER,
        taurus_paper_partial_fill_threshold=1,
    )

    result = run_taurus_smoke(settings=settings, symbol="INFY")

    assert result["status"] == "passed"
    assert result["safety"]["live_trading_enabled"] is False
    assert result["safety"]["broker_provider"] == "paper"
    assert result["artifacts"]["backtest_run_id"].startswith("bt-")
    assert result["artifacts"]["paper_order_id"].startswith("po-")
    assert result["artifacts"]["paper_loop_run_id"].startswith("pr-")
    assert result["counts"]["paper_orders"] >= 1
    assert result["counts"]["paper_fills"] >= 1
