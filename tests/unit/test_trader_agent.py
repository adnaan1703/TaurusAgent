from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID, run_analyst_suite
from taurus_core.agents.trader_agent import TraderAgent
from taurus_core.config import Settings
from taurus_core.db.models import BacktestOrderModel, TraderProposalModel
from taurus_core.db.repositories import CandleRepository, ExecutionRepository
from taurus_core.db.session import build_session_factory
from taurus_core.execution.schemas import (
    PaperAccount,
    PaperPosition,
    paper_account_id,
)
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm import LLMTraderOutput
from tests.llm_fakes import FakeLLMProvider
from taurus_core.research.debate_service import ResearchDebateService
from tests.market_data_fixtures import seed_test_market_data


def test_trader_proposal_is_structured_deterministic_and_not_an_order(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_trader_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id=DEFAULT_ANALYST_RUN_ID,
        )
    with session_factory() as session:
        debate = ResearchDebateService(session, llm_provider=FakeLLMProvider()).run(
            symbol="INFY",
            rounds_requested=2,
        )

    with session_factory() as session:
        first = TraderAgent(
            session,
            settings,
            llm_provider=FakeLLMProvider(),
        ).run(symbol="INFY", debate=debate)
    with session_factory() as session:
        second = TraderAgent(
            session,
            settings,
            llm_provider=FakeLLMProvider(),
        ).run(symbol="INFY", debate=debate)

    with session_factory() as session:
        proposal_count = session.scalar(select(func.count()).select_from(TraderProposalModel))
        order_count = session.scalar(select(func.count()).select_from(BacktestOrderModel))

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.debate_id == debate.debate_id
    assert first.source_report_ids == debate.source_report_ids
    assert first.portfolio_id == settings.taurus_paper_portfolio_id
    assert first.action in {"BUY", "HOLD", "NO_TRADE", "REDUCE", "EXIT"}
    assert first.lifecycle_trigger == "new_entry"
    assert first.evaluation_mode == "after_close"
    assert first.current_position_quantity == 0
    assert first.target_position_pct_nav == first.requested_position_pct_nav
    assert first.stop_loss_pct == Decimal("6.0000")
    assert first.take_profit_pct == Decimal("12.0000")
    assert first.position_management_summary
    assert first.confidence >= 0
    assert first.horizon in {"intraday", "short", "medium", "long"}
    assert first.entry_rule
    assert first.invalid_if
    assert first.is_order is False
    assert first.requires_risk_approval is True
    assert proposal_count == 1
    assert order_count == 0


def test_trader_new_entry_target_metadata_keeps_raw_and_capped_values(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_trader_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id="target-cap-run",
        )
    with session_factory() as session:
        debate = ResearchDebateService(session, llm_provider=FakeLLMProvider()).run(
            symbol="INFY",
            run_id="target-cap-run",
            rounds_requested=2,
        )
        debate = debate.model_copy(
            update={
                "manager_summary": debate.manager_summary.model_copy(
                    update={
                        "consensus_label": "bullish",
                        "consensus_score": Decimal("0.9000"),
                    }
                )
            }
        )

    with session_factory() as session:
        proposal = TraderAgent(
            session,
            settings,
            llm_provider=FakeLLMProvider(),
            max_requested_position_pct_nav=Decimal("5.0000"),
        ).run(symbol="INFY", run_id="target-cap-run", debate=debate)

    assert proposal.action == "BUY"
    assert proposal.requested_position_pct_nav == Decimal("5.0000")
    assert proposal.target_sizing_metadata["raw_new_entry_target_pct_nav"] == "9.0000"
    assert proposal.target_sizing_metadata["capped_new_entry_target_pct_nav"] == "5.0000"
    assert proposal.target_sizing_metadata["capped"] is True


def test_research_api_returns_trader_proposals(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_trader_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id=DEFAULT_ANALYST_RUN_ID,
        )
    with session_factory() as session:
        debate = ResearchDebateService(session, llm_provider=FakeLLMProvider()).run(
            symbol="INFY",
            rounds_requested=2,
        )
    with session_factory() as session:
        proposal = TraderAgent(
            session,
            settings,
            llm_provider=FakeLLMProvider(),
        ).run(symbol="INFY", debate=debate)

    client = TestClient(create_app(settings))
    response = client.get("/trader-proposals?symbol=INFY")

    assert response.status_code == 200
    proposals = response.json()
    assert len(proposals) == 1
    assert proposals[0]["proposal_id"] == proposal.proposal_id
    assert proposals[0]["debate_id"] == debate.debate_id
    assert proposals[0]["is_order"] is False
    assert proposals[0]["portfolio_id"] == settings.taurus_paper_portfolio_id
    assert proposals[0]["evaluation_mode"] == "after_close"


def test_trader_agent_holds_existing_stable_position(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_trader_db(settings)
    _seed_open_position(session_factory, settings, average_cost_multiplier=Decimal("1.0"))
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id="hold-run",
        )
    with session_factory() as session:
        debate = ResearchDebateService(session, llm_provider=FakeLLMProvider()).run(
            symbol="INFY",
            run_id="hold-run",
            rounds_requested=2,
        )
        neutral_summary = debate.manager_summary.model_copy(
            update={
                "consensus_label": "neutral",
                "consensus_score": Decimal("0.0000"),
            }
        )
        debate = debate.model_copy(update={"manager_summary": neutral_summary})

    with session_factory() as session:
        proposal = TraderAgent(
            session,
            settings,
            llm_provider=FakeLLMProvider(),
        ).run(symbol="INFY", run_id="hold-run", debate=debate)

    assert proposal.action == "HOLD"
    assert proposal.lifecycle_trigger == "hold_review"
    assert proposal.current_position_quantity == 10
    assert proposal.target_position_pct_nav == proposal.current_position_pct_nav
    assert proposal.order_type == "NONE"


def test_trader_agent_forces_exit_on_stop_loss(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_trader_db(settings)
    _seed_open_position(session_factory, settings, average_cost_multiplier=Decimal("1.12"))
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id="stop-run",
        )
    with session_factory() as session:
        debate = ResearchDebateService(session, llm_provider=FakeLLMProvider()).run(
            symbol="INFY",
            run_id="stop-run",
            rounds_requested=2,
        )

    with session_factory() as session:
        proposal = TraderAgent(
            session,
            settings,
            llm_provider=FakeLLMProvider(),
        ).run(symbol="INFY", run_id="stop-run", debate=debate)

    assert proposal.action == "EXIT"
    assert proposal.lifecycle_trigger == "stop_loss"
    assert proposal.target_position_pct_nav == Decimal("0.0000")


def test_trader_agent_falls_back_when_llm_recommends_outside_envelope(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_trader_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id="bad-llm-run",
        )
    with session_factory() as session:
        debate = ResearchDebateService(session, llm_provider=FakeLLMProvider()).run(
            symbol="INFY",
            run_id="bad-llm-run",
            rounds_requested=2,
        )

    with session_factory() as session:
        proposal = TraderAgent(
            session,
            settings,
            llm_provider=_BadTraderLLMProvider(),
        ).run(symbol="INFY", run_id="bad-llm-run", debate=debate)

    assert proposal.action == "BUY"
    assert proposal.lifecycle_trigger == "new_entry"
    assert "outside allowed actions" in proposal.position_management_summary


def test_trader_agent_normalizes_verbose_llm_model_version(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_trader_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id="verbose-model-version-run",
        )
    with session_factory() as session:
        debate = ResearchDebateService(session, llm_provider=FakeLLMProvider()).run(
            symbol="INFY",
            run_id="verbose-model-version-run",
            rounds_requested=2,
        )

    with session_factory() as session:
        proposal = TraderAgent(
            session,
            settings,
            llm_provider=_VerboseTraderModelVersionProvider(),
        ).run(
            symbol="INFY",
            run_id="verbose-model-version-run",
            debate=debate,
        )

    assert proposal.model_version == "trader_position_lifecycle_v1:test-trader-provider-v1"
    assert "GraphAnalyst inputs with debate synthesis" not in proposal.model_version


def _prepare_trader_db(settings: Settings):
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_test_market_data(session, candle_count=252)
        import_mock_news(session, MockNewsProvider())
    return session_factory


def _seed_open_position(session_factory, settings: Settings, *, average_cost_multiplier: Decimal) -> None:
    timestamp = datetime.now(timezone.utc)
    with session_factory() as session:
        latest_close = CandleRepository(session).get_by_symbol_and_date_range(symbol="INFY")[-1].close
        average_cost = (latest_close * average_cost_multiplier).quantize(Decimal("0.0001"))
        quantity = 10
        market_value = (latest_close * Decimal(quantity)).quantize(Decimal("0.0001"))
        account = PaperAccount(
            account_id=paper_account_id(
                portfolio_id=settings.taurus_paper_portfolio_id,
                run_id="prior-position-run",
            ),
            run_id="prior-position-run",
            portfolio_id=settings.taurus_paper_portfolio_id,
            starting_cash_inr=Decimal("1000000.0000"),
            available_cash_inr=Decimal("990000.0000"),
            reserved_cash_inr=Decimal("0.0000"),
            realized_pnl_inr=Decimal("0.0000"),
            unrealized_pnl_inr=Decimal("0.0000"),
            gross_exposure_inr=market_value,
            equity_inr=Decimal("1000000.0000"),
            updated_at=timestamp,
        )
        position = PaperPosition(
            run_id="prior-position-run",
            portfolio_id=settings.taurus_paper_portfolio_id,
            symbol="INFY",
            quantity=quantity,
            average_cost_inr=average_cost,
            last_price_inr=latest_close,
            market_value_inr=market_value,
            realized_pnl_inr=Decimal("0.0000"),
            unrealized_pnl_inr=(
                (latest_close - average_cost) * Decimal(quantity)
            ).quantize(Decimal("0.0001")),
            updated_at=timestamp,
        )
        ExecutionRepository(session).replace_account_state(
            run_id="prior-position-run",
            portfolio_id=settings.taurus_paper_portfolio_id,
            account=account,
            positions=[position],
        )
        session.commit()


class _BadTraderLLMProvider(FakeLLMProvider):
    def complete_trader_proposal(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMTraderOutput:
        return LLMTraderOutput(
            action="EXIT",
            confidence=Decimal("0.9900"),
            target_position_pct_nav=Decimal("0.0000"),
            stop_loss_pct=Decimal("6.0000"),
            take_profit_pct=Decimal("12.0000"),
            reason_summary="Bad test output tries to exit without a position.",
            invalid_if=["Bad test output invalidation."],
            position_management_summary="Bad test output outside action envelope.",
            model_version="bad-test-llm",
        )


class _VerboseTraderModelVersionProvider(FakeLLMProvider):
    def __init__(self) -> None:
        super().__init__(model_version="test-trader-provider-v1")

    def complete_trader_proposal(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMTraderOutput:
        fallback = context["deterministic_fallback"]
        assert isinstance(fallback, dict)
        return LLMTraderOutput(
            action=str(fallback["action"]),
            confidence=Decimal(str(fallback["confidence"])),
            target_position_pct_nav=Decimal(str(fallback["target_position_pct_nav"])),
            stop_loss_pct=Decimal("6.0000"),
            take_profit_pct=Decimal("12.0000"),
            reason_summary=str(fallback["reason_summary"]),
            invalid_if=["Risk committee rejects or resizes the proposal."],
            position_management_summary=str(fallback["position_management_summary"]),
            model_version=(
                "research_consensus_v1: TraderAgent processed GraphAnalyst inputs "
                "with debate synthesis."
            ),
        )


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings()
