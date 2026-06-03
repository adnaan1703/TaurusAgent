from __future__ import annotations

from datetime import timezone
from decimal import Decimal
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from taurus_core.allocation_schemas import AllocationDecision
from taurus_core.agents.portfolio_manager import PortfolioManagerAgent
from taurus_core.agents.runner import DEFAULT_ANALYST_RUN_ID, run_analyst_suite
from taurus_core.agents.trader_agent import TraderAgent
from taurus_core.config import Settings
from taurus_core.db.models import BacktestOrderModel, FinalDecisionModel, RiskReviewModel
from taurus_core.db.repositories import IntelligenceRepository, ResearchRepository
from taurus_core.llm.base import LLMProviderError
from taurus_core.db.session import build_session_factory
from taurus_core.intelligence.documents import NewsEvent, RawDocument, document_checksum, stable_id
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from tests.llm_fakes import FakeLLMProvider
from taurus_core.research.debate_service import ResearchDebateService
from taurus_core.research.schemas import TraderProposal
from taurus_core.risk.engine import RiskEngine
from taurus_core.risk.review_service import RiskReviewService
from taurus_core.risk.schemas import decision_id_for_proposal, risk_review_id
from tests.market_data_fixtures import seed_test_market_data


def test_risk_review_is_deterministic_stores_rules_and_does_not_create_orders(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory)

    with session_factory() as session:
        first = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    with session_factory() as session:
        second = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)

    with session_factory() as session:
        review_count = session.scalar(select(func.count()).select_from(RiskReviewModel))
        order_count = session.scalar(select(func.count()).select_from(BacktestOrderModel))

    rule_names = {result.rule for result in first.hard_rule_results}
    persona_names = {review.agent_name for review in first.persona_reviews}

    assert first.model_dump(mode="json") == second.model_dump(mode="json")
    assert first.status in {"APPROVED", "APPROVED_WITH_REDUCTION"}
    assert {"RiskyRiskAgent", "NeutralRiskAgent", "SafeRiskAgent"} == persona_names
    assert {
        "live_trading_disabled",
        "max_position_pct",
        "kill_switch",
        "severe_event_block",
        "required_trace_ids",
    }.issubset(rule_names)
    assert first.is_order is False
    assert first.can_send_to_broker is False
    assert review_count == 1
    assert order_count == 0


def test_risk_engine_reduces_oversized_positions(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory).model_copy(
        update={
            "action": "BUY",
            "requested_position_pct_nav": Decimal("12.0000"),
            "target_position_pct_nav": Decimal("12.0000"),
        }
    )

    with session_factory() as session:
        result = RiskEngine(session, settings).evaluate(
            proposal=proposal,
            decision_id=_decision_id(proposal),
            risk_check_id=_risk_check_id(proposal),
        )

    assert result.status == "APPROVED_WITH_REDUCTION"
    assert result.approved_position_pct_nav == Decimal("5.0000")
    assert any(
        rule.rule == "max_position_pct" and rule.status == "reduced"
        for rule in result.hard_rule_results
    )


def test_risk_engine_uses_money_management_position_limits_when_enabled(
    tmp_path: Path,
) -> None:
    policy_path = _write_money_management_policy(
        tmp_path,
        max_stock_pct=Decimal("3.0"),
        max_open_positions=1,
    )
    settings = Settings(
        taurus_money_management_enabled=True,
        taurus_money_management_config_path=str(policy_path),
        taurus_max_position_pct=9,
        taurus_max_open_positions=99,
    )
    session_factory = _prepare_approval_db(settings)
    oversized = _build_trader_proposal(session_factory).model_copy(
        update={
            "action": "BUY",
            "requested_position_pct_nav": Decimal("6.0000"),
            "target_position_pct_nav": Decimal("6.0000"),
        }
    )
    new_position = oversized.model_copy(
        update={
            "requested_position_pct_nav": Decimal("2.0000"),
            "target_position_pct_nav": Decimal("2.0000"),
        }
    )

    with session_factory() as session:
        reduced = RiskEngine(session, settings).evaluate(
            proposal=oversized,
            decision_id=_decision_id(oversized),
            risk_check_id=_risk_check_id(oversized),
        )
    with session_factory() as session:
        rejected = RiskEngine(
            session,
            settings,
            current_open_positions=1,
        ).evaluate(
            proposal=new_position,
            decision_id=_decision_id(new_position),
            risk_check_id=_risk_check_id(new_position),
        )

    assert reduced.status == "APPROVED_WITH_REDUCTION"
    assert reduced.approved_position_pct_nav == Decimal("3.0000")
    assert rejected.status == "REJECTED"
    assert any(
        rule.rule == "max_open_positions" and rule.status == "rejected"
        for rule in rejected.hard_rule_results
    )


def test_kill_switch_blocks_risk_approval(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory)

    with session_factory() as session:
        result = RiskEngine(session, settings, kill_switch_enabled=True).evaluate(
            proposal=proposal,
            decision_id=_decision_id(proposal),
            risk_check_id=_risk_check_id(proposal),
        )

    assert result.status == "BLOCKED"
    assert result.approved_position_pct_nav == Decimal("0.0000")
    assert any(
        rule.rule == "kill_switch" and rule.status == "blocked"
        for rule in result.hard_rule_results
    )


def test_severe_negative_event_blocks_long_entry(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory).model_copy(
        update={
            "action": "BUY",
            "requested_position_pct_nav": Decimal("3.0000"),
            "target_position_pct_nav": Decimal("3.0000"),
        }
    )

    with session_factory() as session:
        _insert_severe_negative_event(session, proposal)
        result = RiskEngine(session, settings).evaluate(
            proposal=proposal,
            decision_id=_decision_id(proposal),
            risk_check_id=_risk_check_id(proposal),
        )

    assert result.status == "BLOCKED"
    assert any(
        rule.rule == "severe_event_block" and rule.status == "blocked"
        for rule in result.hard_rule_results
    )


def test_portfolio_manager_stores_final_paper_decision_and_api_returns_m6_artifacts(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory)
    with session_factory() as session:
        review = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    with session_factory() as session:
        decision = PortfolioManagerAgent(
            session,
            settings,
            llm_provider=FakeLLMProvider(),
        ).run(
            symbol="INFY",
            risk_review=review,
        )

    with session_factory() as session:
        decision_count = session.scalar(select(func.count()).select_from(FinalDecisionModel))
        order_count = session.scalar(select(func.count()).select_from(BacktestOrderModel))

    client = TestClient(create_app(settings))
    risk_response = client.get("/risk-checks?symbol=INFY")
    final_response = client.get("/final-decisions?symbol=INFY")

    assert decision.status == "APPROVED_FOR_PAPER"
    assert decision.final_action == "BUY"
    assert decision.approved_quantity > 0
    assert decision.is_order is False
    assert decision.can_send_to_broker is True
    assert "Test-only explanation confirms APPROVED_FOR_PAPER" in decision.reason
    assert decision.model_version == "portfolio_manager_lifecycle_rules_v1+llm_explainer"
    assert decision_count == 1
    assert order_count == 0
    assert risk_response.status_code == 200
    assert final_response.status_code == 200
    assert risk_response.json()[0]["risk_check_id"] == review.risk_check_id
    assert final_response.json()[0]["final_decision_id"] == decision.final_decision_id
    assert "Test-only explanation confirms APPROVED_FOR_PAPER" in final_response.json()[0]["reason"]


def test_hold_proposal_becomes_no_action_final_decision(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory).model_copy(
        update={
            "action": "HOLD",
            "requested_position_pct_nav": Decimal("2.0000"),
            "current_position_quantity": 10,
            "current_position_pct_nav": Decimal("2.0000"),
            "target_position_pct_nav": Decimal("2.0000"),
            "lifecycle_trigger": "hold_review",
        }
    )
    with session_factory() as session:
        ResearchRepository(session).replace_trader_proposal_for_run_symbol(proposal)
        session.commit()

    with session_factory() as session:
        review = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    with session_factory() as session:
        decision = PortfolioManagerAgent(
            session,
            settings,
            enable_llm_explanation=False,
        ).run(
            symbol="INFY",
            risk_review=review,
        )

    assert review.status == "APPROVED"
    assert decision.status == "NO_ACTION"
    assert decision.final_action == "HOLD"
    assert decision.approved_quantity == 0
    assert decision.can_send_to_broker is False


def test_allocation_rejected_buy_final_decision_keeps_binding_reason(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory).model_copy(
        update={
            "action": "NO_TRADE",
            "requested_position_pct_nav": Decimal("0.0000"),
            "target_position_pct_nav": Decimal("0.0000"),
            "order_type": "NONE",
            "entry_rule": (
                "not_selected_by_run_allocation: Run-level allocation rejected this BUY."
            ),
            "allocation_decision": AllocationDecision(
                symbol="INFY",
                action="BUY",
                strategy_name="moving_average_crossover_v1",
                sleeve_id="settings_fallback",
                sleeve_name="Settings fallback",
                status="allocation_rejected",
                requested_position_pct_nav=Decimal("3.0000"),
                approved_position_pct_nav=Decimal("0.0000"),
                requested_notional_inr=Decimal("30000.00"),
                approved_notional_inr=Decimal("0.00"),
                approved_quantity=0,
                binding_constraint="candidate_score_below_fallback_floor",
                rationale=("Run-level allocation rejected the BUY candidate.",),
            ),
        }
    )
    with session_factory() as session:
        ResearchRepository(session).replace_trader_proposal_for_run_symbol(proposal)
        session.commit()
    with session_factory() as session:
        review = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    with session_factory() as session:
        decision = PortfolioManagerAgent(
            session,
            settings,
            enable_llm_explanation=False,
        ).run(symbol="INFY", risk_review=review)

    assert review.status == "APPROVED"
    assert decision.status == "NO_ACTION"
    assert decision.final_action == "NO_TRADE"
    assert decision.can_send_to_broker is False
    assert "allocation_rejected_by_run_allocation" in decision.reason
    assert "candidate_score_below_fallback_floor" in decision.reason


def test_portfolio_manager_falls_back_to_deterministic_reason_on_llm_failure(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory)
    with session_factory() as session:
        review = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    with session_factory() as session:
        decision = PortfolioManagerAgent(
            session,
            settings,
            llm_provider=_FailingFinalDecisionLLMProvider(),
        ).run(symbol="INFY", risk_review=review)

    deterministic_reason = (
        "Approved BUY for PaperBroker execution after stored risk review and "
        "paper-safe configuration checks."
    )
    assert decision.status == "APPROVED_FOR_PAPER"
    assert decision.reason == deterministic_reason
    assert decision.model_version == "portfolio_manager_lifecycle_rules_v1"
    with session_factory() as session:
        stored = session.scalars(select(FinalDecisionModel)).one()
    assert stored.payload["reason"] == deterministic_reason


def test_portfolio_manager_disabled_explanation_does_not_call_provider(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory)
    with session_factory() as session:
        review = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    provider = _ExplodingFinalDecisionLLMProvider()

    with session_factory() as session:
        decision = PortfolioManagerAgent(
            session,
            settings,
            llm_provider=provider,
            enable_llm_explanation=False,
        ).run(symbol="INFY", risk_review=review)

    assert decision.status == "APPROVED_FOR_PAPER"
    assert "LLM explainer" not in decision.reason
    assert provider.called is False


def test_portfolio_manager_llm_explains_blocked_without_changing_status(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory)

    with session_factory() as session:
        _insert_severe_negative_event(session, proposal)
        review = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    with session_factory() as session:
        decision = PortfolioManagerAgent(
            session,
            settings,
            llm_provider=FakeLLMProvider(),
        ).run(symbol="INFY", risk_review=review)

    assert review.status == "BLOCKED"
    assert decision.status == "BLOCKED"
    assert decision.final_action == "NO_TRADE"
    assert decision.approved_quantity == 0
    assert decision.can_send_to_broker is False
    assert "Test-only explanation confirms BLOCKED" in decision.reason


def test_portfolio_manager_llm_explains_rejected_without_changing_status(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory).model_copy(
        update={
            "action": "BUY",
            "requested_position_pct_nav": Decimal("2.0000"),
            "current_position_quantity": 10,
            "current_position_pct_nav": Decimal("2.0000"),
            "target_position_pct_nav": Decimal("2.0000"),
        }
    )
    with session_factory() as session:
        ResearchRepository(session).replace_trader_proposal_for_run_symbol(proposal)
        session.commit()
    with session_factory() as session:
        review = RiskReviewService(session, settings).run(symbol="INFY", proposal=proposal)
    with session_factory() as session:
        decision = PortfolioManagerAgent(
            session,
            settings,
            llm_provider=FakeLLMProvider(),
        ).run(symbol="INFY", risk_review=review)

    assert review.status == "REJECTED"
    assert decision.status == "REJECTED"
    assert decision.final_action == "NO_TRADE"
    assert decision.approved_quantity == 0
    assert decision.can_send_to_broker is False
    assert "Test-only explanation confirms REJECTED" in decision.reason


def test_severe_negative_event_does_not_block_exit(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_approval_db(settings)
    proposal = _build_trader_proposal(session_factory).model_copy(
        update={
            "action": "EXIT",
            "requested_position_pct_nav": Decimal("0.0000"),
            "current_position_quantity": 10,
            "current_position_pct_nav": Decimal("2.0000"),
            "target_position_pct_nav": Decimal("0.0000"),
            "lifecycle_trigger": "thesis_invalidated",
        }
    )

    with session_factory() as session:
        _insert_severe_negative_event(session, proposal)
        result = RiskEngine(session, settings).evaluate(
            proposal=proposal,
            decision_id=_decision_id(proposal),
            risk_check_id=_risk_check_id(proposal),
        )

    assert result.status == "APPROVED"
    assert any(
        rule.rule == "severe_event_block" and rule.status == "passed"
        for rule in result.hard_rule_results
    )


def _prepare_approval_db(settings: Settings):
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_test_market_data(session, candle_count=252)
        import_mock_news(session, MockNewsProvider())
    return session_factory


def _build_trader_proposal(session_factory) -> TraderProposal:
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
        return TraderAgent(
            session,
            Settings(),
            llm_provider=FakeLLMProvider(),
        ).run(symbol="INFY", debate=debate)


def _insert_severe_negative_event(session, proposal: TraderProposal) -> None:
    published_at = proposal.as_of
    if published_at.tzinfo is None:
        published_at = published_at.replace(tzinfo=timezone.utc)
    checksum = document_checksum("risk_test", proposal.symbol, published_at.isoformat())
    document = RawDocument(
        document_id=stable_id("raw", checksum),
        source="risk_test",
        source_url="mock://risk-test/severe-negative",
        title="Infosys faces severe regulatory probe",
        body="A severe regulatory probe creates direct event risk for the long setup.",
        published_at=published_at,
        symbols=[proposal.symbol],
        entities=["Infosys Ltd"],
        checksum=checksum,
        metadata={"provider": "risk_test"},
    )
    event = NewsEvent(
        event_id=stable_id("evt", document.document_id, proposal.symbol, "regulatory_probe"),
        document_id=document.document_id,
        symbol=proposal.symbol,
        event_type="regulatory_probe",
        event_time=published_at,
        headline=document.title,
        summary=document.body,
        severity=Decimal("0.9500"),
        horizon="short",
        source_confidence=Decimal("0.9500"),
        metadata={"provider": "risk_test"},
    )
    repo = IntelligenceRepository(session)
    repo.upsert_raw_document(document)
    repo.upsert_event(event)
    session.commit()


def _decision_id(proposal: TraderProposal) -> str:
    return decision_id_for_proposal(
        run_id=proposal.run_id,
        symbol=proposal.symbol,
        proposal_id=proposal.proposal_id,
    )


def _risk_check_id(proposal: TraderProposal) -> str:
    return risk_review_id(
        run_id=proposal.run_id,
        symbol=proposal.symbol,
        proposal_id=proposal.proposal_id,
        source_report_ids=proposal.source_report_ids,
    )


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings()


def _write_money_management_policy(
    tmp_path: Path,
    *,
    max_stock_pct: Decimal,
    max_open_positions: int,
) -> Path:
    universe_path = tmp_path / "risk_shariah.yaml"
    universe_path.write_text(
        "universe_name: risk_test_shariah\n"
        "default_exchange: NSE\n"
        "default_segment: EQUITY\n"
        "symbols:\n"
        "  - symbol: INFY\n"
        "    name: Infosys Ltd.\n"
        "    enabled: true\n"
        "    providers:\n"
        "      kite:\n"
        "        exchange: NSE\n"
        "        tradingsymbol: INFY\n",
        encoding="utf-8",
    )
    policy_path = tmp_path / "money_management_risk.yaml"
    policy_path.write_text(
        "policy_version: risk_test_policy\n"
        f"shariah_universe_path: {universe_path}\n"
        "sleeves:\n"
        "  - sleeve_id: core_shariah\n"
        "    name: Core\n"
        "    target_weight_pct: 40.0\n"
        "    role: Core sleeve\n"
        "  - sleeve_id: active_strategy\n"
        "    name: Active\n"
        "    target_weight_pct: 55.0\n"
        "    role: Active sleeve\n"
        "  - sleeve_id: cash_buffer\n"
        "    name: Cash\n"
        "    target_weight_pct: 5.0\n"
        "    role: Cash buffer\n"
        "strategy_mappings:\n"
        "  - strategy_name: graph_aware_score_v1\n"
        "    sleeve_id: active_strategy\n"
        "limits:\n"
        f"  max_stock_pct_nav: {max_stock_pct}\n"
        f"  max_stock_hard_cap_pct_nav: {max_stock_pct}\n"
        "  max_sector_pct_nav: 25.0\n"
        "  max_graph_cluster_pct_nav: 35.0\n"
        f"  max_open_positions: {max_open_positions}\n"
        "trade_risk:\n"
        "  normal_trade_risk_pct_nav: 0.50\n"
        "  strong_trade_risk_pct_nav: 0.75\n"
        "  max_single_trade_risk_pct_nav: 1.00\n"
        "  max_total_open_trade_risk_pct_nav: 5.00\n"
        "allocation_scoring:\n"
        "  weights:\n"
        "    strategy_score: 0.30\n"
        "    trader_confidence: 0.25\n"
        "    liquidity: 0.15\n"
        "    volatility: 0.15\n"
        "    diversification: 0.10\n"
        "    recent_sleeve_performance: 0.05\n"
        "  score_bands:\n"
        "    reject_below: 60.0\n"
        "    half_normal_below: 75.0\n"
        "    normal_below: 85.0\n"
        "rebalance:\n"
        "  sleeve_drift_threshold_pct: 20.0\n"
        "  min_rebalance_notional_inr: 5000\n"
        "  review_frequency: daily_after_close\n"
        "  core_rebalance_frequency: monthly\n",
        encoding="utf-8",
    )
    return policy_path


class _FailingFinalDecisionLLMProvider(FakeLLMProvider):
    def complete_final_decision_explanation(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ):
        raise LLMProviderError("provider unavailable")


class _ExplodingFinalDecisionLLMProvider(FakeLLMProvider):
    def __init__(self) -> None:
        super().__init__()
        self.called = False

    def complete_final_decision_explanation(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ):
        self.called = True
        raise AssertionError("LLM provider should not be called")
