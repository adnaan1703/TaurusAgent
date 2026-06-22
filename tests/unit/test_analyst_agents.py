from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from apps.api.main import create_app
from scripts.import_mock_news import import_mock_news
from scripts.migrate import run_migrations
from taurus_core.agents.runner import run_analyst_suite
from taurus_core.agents.roster import ANALYST_KEYS
from taurus_core.agents.schemas import LLMAnalystOutput, stance_from_score
from taurus_core.agents.technical_analyst import TechnicalAnalystAgent
from taurus_core.config import Settings
from taurus_core.db.models import (
    AnalystReportModel,
    BacktestOrderModel,
    BacktestRunModel,
    BacktestSignalModel,
    FeatureValueModel,
)
from taurus_core.db.session import build_session_factory
from taurus_core.intelligence.mock_news_provider import MockNewsProvider
from taurus_core.llm.base import LLMProviderError
from tests.llm_fakes import FakeLLMProvider
from tests.market_data_fixtures import seed_test_market_data

FULL_ANALYST_ROSTER = ANALYST_KEYS


def test_analyst_suite_stores_full_roster_without_creating_orders(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)

    with session_factory() as session:
        reports = run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id="test-run",
            enabled_analysts=FULL_ANALYST_ROSTER,
        )

    with session_factory() as session:
        report_count = session.scalar(select(func.count()).select_from(AnalystReportModel))
        order_count = session.scalar(select(func.count()).select_from(BacktestOrderModel))

    assert {report.agent_name for report in reports} == {
        "TechnicalAnalystAgent",
        "NewsAnalystAgent",
        "SentimentAnalystAgent",
        "FundamentalsAnalystAgent",
        "GraphAnalystAgent",
    }
    assert all(report.symbol == "INFY" for report in reports)
    assert all(report.key_points for report in reports)
    assert all(report.risks for report in reports)
    assert report_count == 5
    assert order_count == 0


def test_analyst_suite_raises_when_llm_provider_fails(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)

    with session_factory() as session:
        with pytest.raises(LLMProviderError, match="TechnicalAnalystAgent LLM provider failed"):
            run_analyst_suite(
                session,
                symbol="INFY",
                llm_provider=FailingLLMProvider(),
                run_id="provider-failure-run",
                enabled_analysts=FULL_ANALYST_ROSTER,
            )

    with session_factory() as session:
        report_count = session.scalar(select(func.count()).select_from(AnalystReportModel))

    assert report_count == 0


def test_analyst_suite_can_skip_fundamentals(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)

    with session_factory() as session:
        reports = run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id="no-fundamentals-run",
            enabled_analysts=("technical", "news", "sentiment"),
        )

    assert {report.agent_name for report in reports} == {
        "TechnicalAnalystAgent",
        "NewsAnalystAgent",
        "SentimentAnalystAgent",
    }
    assert all(report.agent_name != "FundamentalsAnalystAgent" for report in reports)


def test_analyst_suite_allows_technical_only_roster(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)

    with session_factory() as session:
        reports = run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id="technical-only-run",
            enabled_analysts=("technical",),
        )

    assert len(reports) == 1
    assert reports[0].agent_name == "TechnicalAnalystAgent"


def test_technical_analyst_keeps_bounded_score_with_raw_metadata(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)

    with session_factory() as session:
        report = run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id="technical-score-metadata-run",
            enabled_analysts=("technical",),
        )[0]

    assert Decimal("-1") <= report.score <= Decimal("1")
    assert report.stance == stance_from_score(report.score)
    assert report.score_metadata is not None
    assert report.score_metadata.bounded_report_score == report.score
    assert report.score_metadata.raw_signal_score is not None
    assert report.score_metadata.score_source == "technical_rule_v1"


def test_technical_analyst_characterizes_backtest_signal_override(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_empty_db(settings)

    with session_factory() as session:
        _seed_backtest_run(session, run_id="baseline-backtest")
        _seed_feature_snapshot(
            session,
            run_id="baseline-backtest",
            snapshot_id="snapshot-INFY-2024-01-12",
            symbol="INFY",
            values={
                "return_20d": Decimal("0.08000000"),
                "return_5d": Decimal("0.04000000"),
                "ema_12": Decimal("112.00000000"),
                "ema_26": Decimal("100.00000000"),
                "rsi_14": Decimal("64.00000000"),
                "volatility_20": Decimal("0.02000000"),
            },
        )
        signal = BacktestSignalModel(
            run_id="baseline-backtest",
            trade_date=date(2024, 1, 12),
            symbol="INFY",
            action="SELL",
            score=Decimal("0.42000000"),
            reason="Characterization signal override.",
            feature_snapshot_id="snapshot-INFY-2024-01-12",
            explanation={"source": "characterization"},
        )
        session.add(signal)
        session.commit()
        session.refresh(signal)

        report = TechnicalAnalystAgent(session, FakeLLMProvider()).run(
            symbol="infy",
            run_id="technical-signal-override-run",
        )

    assert report.score == Decimal("-0.4200")
    assert report.confidence == Decimal("0.6800")
    assert report.source_ids == [
        "snapshot-INFY-2024-01-12",
        f"signal:{signal.id}",
    ]
    assert report.score_metadata is not None
    assert report.score_metadata.raw_signal_score == Decimal("-0.42000000")
    assert report.score_metadata.bounded_report_score == report.score
    assert report.score_metadata.score_source == "technical_rule_v1"
    assert report.key_points[0] == (
        "Latest strategy signal for INFY was SELL with score 0.42000000."
    )
    assert "20-day return feature is 0.08000000." in report.key_points


def test_technical_analyst_characterizes_feature_formula_and_report_clamp(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_empty_db(settings)

    with session_factory() as session:
        _seed_backtest_run(session, run_id="feature-formula-backtest")
        _seed_feature_snapshot(
            session,
            run_id="feature-formula-backtest",
            snapshot_id="snapshot-TCS-2024-01-12",
            symbol="TCS",
            values={
                "return_20d": Decimal("0.60000000"),
                "return_5d": Decimal("0.20000000"),
                "ema_12": Decimal("120.00000000"),
                "ema_26": Decimal("100.00000000"),
                "rsi_14": Decimal("80.00000000"),
                "volatility_20": Decimal("0.01000000"),
            },
        )
        report = TechnicalAnalystAgent(session, FakeLLMProvider()).run(
            symbol="TCS",
            run_id="technical-feature-formula-run",
        )

    assert report.score == Decimal("1.0000")
    assert report.confidence == Decimal("0.6800")
    assert report.source_ids == ["snapshot-TCS-2024-01-12"]
    assert report.score_metadata is not None
    assert report.score_metadata.raw_signal_score == Decimal("1.6525000000000")
    assert report.score_metadata.bounded_report_score == Decimal("1.0000")
    assert "20-day return feature is 0.60000000." in report.key_points
    assert "RSI-14 feature is 80.00000000." in report.key_points
    assert "20-day volatility feature is 0.01000000." in report.key_points


def test_technical_analyst_characterizes_empty_feature_fallback(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_empty_db(settings)

    with session_factory() as session:
        report = TechnicalAnalystAgent(session, FakeLLMProvider()).run(
            symbol="WIPRO",
            run_id="technical-empty-fallback-run",
        )

    assert report.score == Decimal("0.0000")
    assert report.confidence == Decimal("0.3500")
    assert report.source_ids == ["technical:none"]
    assert report.score_metadata is not None
    assert report.score_metadata.raw_signal_score == Decimal("0")
    assert report.score_metadata.bounded_report_score == Decimal("0.0000")
    assert report.key_points == [
        "No persisted technical features were available for WIPRO; neutral fallback used."
    ]


def test_intelligence_api_returns_events_and_agent_reports(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_intelligence_db(settings)
    with session_factory() as session:
        run_analyst_suite(
            session,
            symbol="INFY",
            llm_provider=FakeLLMProvider(),
            run_id="api-run",
            enabled_analysts=FULL_ANALYST_ROSTER,
        )
    client = TestClient(create_app(settings))

    events_response = client.get("/events?symbol=INFY")
    reports_response = client.get("/agent-reports?symbol=INFY")

    assert events_response.status_code == 200
    assert reports_response.status_code == 200
    events = events_response.json()
    reports = reports_response.json()
    assert len(events) >= 1
    assert events[0]["symbol"] == "INFY"
    assert events[0]["event_score"] is not None
    assert len(reports) == 5
    assert {report["agent_name"] for report in reports} == {
        "TechnicalAnalystAgent",
        "NewsAnalystAgent",
        "SentimentAnalystAgent",
        "FundamentalsAnalystAgent",
        "GraphAnalystAgent",
    }


class FailingLLMProvider:
    @property
    def model_version(self) -> str:
        return "failing"

    def complete_analyst_report(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMAnalystOutput:
        raise RuntimeError("simulated provider failure")


def _prepare_intelligence_db(settings: Settings):
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        seed_test_market_data(session, candle_count=252)
        import_mock_news(session, MockNewsProvider())
    return session_factory


def _prepare_empty_db(settings: Settings):
    run_migrations(settings)
    return build_session_factory(settings)


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings()


def _seed_backtest_run(session, *, run_id: str) -> None:
    session.add(
        BacktestRunModel(
            run_id=run_id,
            strategy_name="characterization",
            seed=7,
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 12),
            initial_capital_inr=Decimal("100000.0000"),
            final_equity_inr=Decimal("100000.0000"),
            metrics={},
            parameters={},
        )
    )


def _seed_feature_snapshot(
    session,
    *,
    run_id: str,
    snapshot_id: str,
    symbol: str,
    values: dict[str, Decimal],
) -> None:
    feature_time = date(2024, 1, 11)
    data_available_time = datetime(2024, 1, 12, tzinfo=timezone.utc)
    session.add_all(
        FeatureValueModel(
            run_id=run_id,
            snapshot_id=snapshot_id,
            symbol=symbol,
            feature_name=name,
            feature_value=value,
            feature_time=feature_time,
            data_available_time=data_available_time,
            source="characterization",
            feature_version="technical_v1",
        )
        for name, value in values.items()
    )
    session.flush()
