from __future__ import annotations

from pathlib import Path

import pytest

from scripts.taurus_smoke import run_taurus_smoke
from taurus_core.config import Settings


def test_taurus_smoke_covers_paper_mvp_release_flow(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("BACKUP_DIR", str(tmp_path / "backups"))
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'taurus.db'}",
        taurus_alert_provider="mock",
        taurus_llm_provider="mock",
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
