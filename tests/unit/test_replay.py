from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import select

from taurus_core.config import Settings
from taurus_core.db.models import FinalDecisionModel, PaperRunModel
from taurus_core.db.session import build_session_factory
from taurus_core.paper_trading.service import PaperRunService
from taurus_core.replay.service import DecisionReplayService
from tests.llm_fakes import FakeLLMProvider
from tests.market_data_fixtures import FakeKiteMarketDataProvider


@pytest.fixture(autouse=True)
def fake_runtime_providers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_llm_provider",
        lambda settings: FakeLLMProvider(),
    )
    monkeypatch.setattr(
        "taurus_core.paper_trading.service.build_market_data_provider",
        lambda settings: FakeKiteMarketDataProvider(),
    )


def test_replay_portfolio_plan_stage_is_legacy_safe(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run = PaperRunService(settings).run_once(symbols=["INFY"])
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        decision = session.scalars(
            select(FinalDecisionModel).where(FinalDecisionModel.run_id == run.run_id)
        ).one()
        replay = DecisionReplayService(session).replay(decision_id=decision.decision_id)
        stage_names = [stage.name for stage in replay.stages]
        plan_stage = _stage(replay, "portfolio_plan")

        assert stage_names.index("portfolio_plan") == stage_names.index("strategy_ranking") + 1
        assert stage_names.index("allocation_ledger") == stage_names.index("portfolio_plan") + 1
        assert plan_stage.artifact_count == 1
        assert plan_stage.artifacts[0]["plan_id"] == f"portfolio-plan-{run.run_id}"
        assert plan_stage.artifacts[0]["candidate"]["symbol"] == "INFY"
        assert plan_stage.artifacts[0]["planned_trades"][0]["symbol"] == "INFY"
        assert plan_stage.artifacts[0]["same_run_sell_proceeds_haircut_pct"] == "80.0000"
        assert plan_stage.artifacts[0]["buy_price_buffer_pct"] == "5.0000"
        assert plan_stage.artifacts[0]["soft_borrowing_enabled"] is False

        stored_run = session.get(PaperRunModel, run.run_id)
        assert stored_run is not None
        legacy_artifacts = dict(stored_run.artifacts)
        legacy_artifacts.pop("portfolio_plan")
        stored_run.artifacts = legacy_artifacts
        stored_run.payload = {**stored_run.payload, "artifacts": legacy_artifacts}
        session.commit()

        legacy_replay = DecisionReplayService(session).replay(decision_id=decision.decision_id)
        legacy_plan_stage = _stage(legacy_replay, "portfolio_plan")

        assert legacy_plan_stage.artifact_count == 0
        assert legacy_plan_stage.artifacts == []


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(
        taurus_alert_provider="mock",
        taurus_graph_enabled=False,
        taurus_graph_risk_enabled=False,
        taurus_enabled_analysts="technical",
        taurus_llm_model="",
        taurus_paper_partial_fill_threshold=1,
    )


def _stage(replay, name: str):
    for stage in replay.stages:
        if stage.name == name:
            return stage
    raise AssertionError(f"Replay stage {name} not found.")
