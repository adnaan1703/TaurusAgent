from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from scripts.migrate import run_migrations
from scripts.taurus_smoke import run_taurus_smoke
from taurus_core.agents.roster import ANALYST_KEYS
from taurus_core.config import Settings
from taurus_core.db.repositories import TaurusProfileRepository
from taurus_core.db.session import build_session_factory
from tests.llm_fakes import FakeLLMProvider
from tests.market_data_fixtures import (
    FakeKiteMarketDataProvider,
    seed_test_market_data,
)

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
    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_market_data_provider",
        lambda settings: FakeKiteMarketDataProvider(),
    )
    settings = Settings(
        taurus_alert_provider="mock",
        taurus_enabled_analysts=FULL_ANALYST_ROSTER,
        taurus_initial_capital_inr=1_000_000,
        taurus_paper_partial_fill_threshold=1,
    )
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    _set_default_profile_corpus(session_factory)
    with session_factory() as session:
        seed_test_market_data(session, candle_count=252)

    result = run_taurus_smoke(settings=settings, symbol="INFY")

    assert result["status"] == "passed"
    assert result["safety"]["live_trading_enabled"] is False
    assert result["safety"]["broker_provider"] == "paper"
    assert result["artifacts"]["backtest_run_id"].startswith("bt-")
    assert result["artifacts"]["paper_order_id"].startswith("po-")
    assert result["artifacts"]["paper_loop_run_id"].startswith("pr-")
    assert result["counts"]["paper_orders"] >= 1
    assert result["counts"]["paper_fills"] == 0
    assert result["profile_smoke"]["profile_id"] == "smoke-profile"
    assert str(result["profile_smoke"]["paper_loop_run_id"]).startswith("pr-")
    assert set(result["profile_smoke"]["api"].values()) == {200}


def _set_default_profile_corpus(session_factory) -> None:
    with session_factory() as session:
        TaurusProfileRepository(session).update_profile_corpus(
            "local-paper",
            Decimal("1000000"),
        )
        session.commit()
