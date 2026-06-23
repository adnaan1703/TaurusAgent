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
from taurus_core.agents.base import BaseAnalystAgent
from taurus_core.agents.schemas import (
    AnalystScoreMetadata,
    LLMAnalystOutput,
    stance_from_score,
)
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
from taurus_core.features.store import FeatureSnapshot
from taurus_core.features.technical_context import build_universe_technical_context
from taurus_core.features.technical_signal import OHLCV_V2_PROFILE, TechnicalSignalService
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
    assert report.model_version == "technical_rule_v1"


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


def test_technical_analyst_v2_owns_score_confidence_and_audits_signal(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_empty_db(settings)
    snapshots = {
        "INFY": _v2_feature_snapshot("INFY", _ohlcv_v2_values("strong")),
        "TCS": _v2_feature_snapshot("TCS", _ohlcv_v2_values("weak")),
    }
    context = build_universe_technical_context(snapshots)
    expected = TechnicalSignalService().score_ohlcv_v2(
        snapshots["INFY"],
        universe_context=context,
        symbol="INFY",
    )

    with session_factory() as session:
        _seed_backtest_run(session, run_id="v2-backtest-audit")
        signal = BacktestSignalModel(
            run_id="v2-backtest-audit",
            trade_date=date(2024, 1, 12),
            symbol="INFY",
            action="SELL",
            score=Decimal("0.99000000"),
            reason="V2 must keep this as audit context only.",
            feature_snapshot_id="fs-INFY-v2",
            explanation={"source": "v2-audit"},
        )
        session.add(signal)
        session.commit()
        session.refresh(signal)

        report = TechnicalAnalystAgent(session, NumericOwningLLMProvider()).run(
            symbol="infy",
            run_id="technical-v2-run",
            technical_profile=OHLCV_V2_PROFILE,
            feature_snapshot=snapshots["INFY"],
            universe_technical_context=context,
        )

    assert report.model_version == OHLCV_V2_PROFILE
    assert report.score == expected.score
    assert report.confidence == expected.confidence
    assert report.score != Decimal("0.7777")
    assert report.confidence != Decimal("0.4444")
    assert report.stance == stance_from_score(expected.score)
    assert report.source_ids == ["fs-INFY-v2"]
    assert report.score_metadata is not None
    assert report.score_metadata.raw_signal_score == expected.raw_score
    assert report.score_metadata.bounded_report_score == expected.score
    assert report.score_metadata.score_source == OHLCV_V2_PROFILE
    technical_v2 = report.score_metadata.technical_v2
    assert technical_v2["profile_name"] == OHLCV_V2_PROFILE
    assert technical_v2["alpha_score"] == str(expected.alpha_score)
    assert technical_v2["risk_score"] == str(expected.risk_score)
    assert technical_v2["tradability_score"] == str(expected.tradability_score)
    assert technical_v2["confidence"] == str(expected.confidence)
    assert technical_v2["composite_score"] == str(expected.composite_score)
    assert technical_v2["metadata"]["universe_context_available"] is True
    assert technical_v2["latest_backtest_signal_audit"] == {
        "signal_id": signal.id,
        "action": "SELL",
        "score": "0.99000000",
        "score_override_applied": False,
    }


def test_technical_analyst_v2_symbol_local_fallback_marks_missing_context(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path)
    session_factory = _prepare_empty_db(settings)
    snapshot = _v2_feature_snapshot("INFY", _ohlcv_v2_values("strong"))
    context = build_universe_technical_context(
        {
            "INFY": snapshot,
            "TCS": _v2_feature_snapshot("TCS", _ohlcv_v2_values("weak")),
        }
    )
    with_context = TechnicalSignalService().score_ohlcv_v2(
        snapshot,
        universe_context=context,
        symbol="INFY",
    )
    symbol_local = TechnicalSignalService().score_ohlcv_v2(snapshot, symbol="INFY")

    with session_factory() as session:
        report = TechnicalAnalystAgent(session, FakeLLMProvider()).run(
            symbol="INFY",
            run_id="technical-v2-symbol-local-run",
            technical_profile=OHLCV_V2_PROFILE,
            feature_snapshot=snapshot,
        )

    assert report.score == symbol_local.score
    assert report.confidence == symbol_local.confidence
    assert report.confidence < with_context.confidence
    assert report.score_metadata is not None
    technical_v2 = report.score_metadata.technical_v2
    assert technical_v2["metadata"]["universe_context_available"] is False
    assert technical_v2["metadata"]["symbol_context_available"] is False
    assert any("Universe technical context was unavailable" in point for point in report.key_points)
    assert any("result is symbol-local" in note for note in report.score_metadata.notes)


def test_base_analyst_report_currently_uses_llm_owned_numeric_output() -> None:
    provider = NumericOwningLLMProvider()
    agent = DraftOwningAnalyst(None, provider)  # type: ignore[arg-type]
    fallback = LLMAnalystOutput(
        score=Decimal("-0.2500"),
        confidence=Decimal("0.3000"),
        stance="bearish",
        horizon="medium",
        key_points=["Deterministic fallback key point."],
        risks=["Deterministic fallback risk."],
        model_version="deterministic-fallback",
    )

    report = agent._build_report(
        symbol="infy",
        run_id="llm-numeric-ownership-run",
        as_of=datetime(2024, 1, 12, tzinfo=timezone.utc),
        fallback=fallback,
        context={
            "score": "-0.2500",
            "confidence": "0.3000",
            "horizon": "medium",
            "key_points": ["Deterministic context key point."],
            "risks": ["Deterministic context risk."],
        },
        source_ids=["deterministic-context"],
        score_metadata=AnalystScoreMetadata(
            raw_signal_score=Decimal("-0.2500"),
            bounded_report_score=Decimal("-0.2500"),
            score_source="deterministic_context",
        ),
    )

    assert report.symbol == "INFY"
    assert report.score == Decimal("0.7777")
    assert report.confidence == Decimal("0.4444")
    assert report.stance == "bullish"
    assert report.horizon == "long"
    assert report.key_points == ["LLM draft owns the report text and score."]
    assert report.risks == ["LLM draft risk text."]
    assert report.model_version == "llm-owning-test"
    assert report.score_metadata is not None
    assert report.score_metadata.raw_signal_score == Decimal("-0.2500")
    assert report.score_metadata.bounded_report_score == Decimal("0.7777")
    assert report.score_metadata.score_source == "deterministic_context"


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


class DraftOwningAnalyst(BaseAnalystAgent):
    agent_name = "DraftOwningAnalyst"


class NumericOwningLLMProvider:
    @property
    def model_version(self) -> str:
        return "llm-owning-test"

    def complete_analyst_report(
        self,
        *,
        agent_name: str,
        symbol: str,
        context: dict[str, object],
    ) -> LLMAnalystOutput:
        score = Decimal("0.7777")
        return LLMAnalystOutput(
            score=score,
            confidence=Decimal("0.4444"),
            stance=stance_from_score(score),
            horizon="long",
            key_points=["LLM draft owns the report text and score."],
            risks=["LLM draft risk text."],
            model_version=self.model_version,
        )


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


def _v2_feature_snapshot(symbol: str, values: dict[str, Decimal]) -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=f"fs-{symbol}-v2",
        symbol=symbol,
        as_of_date=date(2024, 1, 12),
        feature_time=date(2024, 1, 11),
        values=values,
        rows=(),
    )


def _ohlcv_v2_values(profile: str) -> dict[str, Decimal]:
    values_by_profile = {
        "strong": {
            "return_20d": "0.05000000",
            "return_63d": "0.14000000",
            "return_126d": "0.22000000",
            "return_252d": "0.34000000",
            "vol_adjusted_return_63d": "2.00000000",
            "vol_adjusted_return_126d": "2.50000000",
            "vol_adjusted_return_252d": "3.00000000",
            "ema_12": "110.00000000",
            "ema_26": "100.00000000",
            "macd_histogram_12_26_9": "1.50000000",
            "adx_14": "35.00000000",
            "plus_di_14": "35.00000000",
            "minus_di_14": "12.00000000",
            "rsi_14": "62.00000000",
            "bollinger_percent_b_20": "0.65000000",
            "bollinger_bandwidth_20": "0.08000000",
            "breakout_high_distance_20d": "0.02000000",
            "breakout_high_distance_50d": "0.04000000",
            "breakout_high_distance_252d": "0.03000000",
            "distance_from_52w_high": "-0.03000000",
            "atr_percent_14": "0.01500000",
            "volatility_20": "0.01500000",
            "volatility_63": "0.01800000",
            "volatility_126": "0.02000000",
            "volatility_252": "0.02200000",
            "volume_z_score_20": "1.50000000",
            "turnover": "10000000.00000000",
            "avg_traded_value_20": "9000000.00000000",
            "avg_traded_value_63": "8000000.00000000",
            "turnover_z_score_20": "1.20000000",
        },
        "weak": {
            "return_20d": "-0.05000000",
            "return_63d": "-0.12000000",
            "return_126d": "-0.18000000",
            "return_252d": "-0.30000000",
            "vol_adjusted_return_63d": "-1.80000000",
            "vol_adjusted_return_126d": "-2.20000000",
            "vol_adjusted_return_252d": "-2.60000000",
            "ema_12": "94.00000000",
            "ema_26": "100.00000000",
            "macd_histogram_12_26_9": "-1.20000000",
            "adx_14": "32.00000000",
            "plus_di_14": "12.00000000",
            "minus_di_14": "35.00000000",
            "rsi_14": "38.00000000",
            "bollinger_percent_b_20": "0.25000000",
            "bollinger_bandwidth_20": "0.22000000",
            "breakout_high_distance_20d": "-0.08000000",
            "breakout_high_distance_50d": "-0.12000000",
            "breakout_high_distance_252d": "-0.25000000",
            "distance_from_52w_high": "-0.25000000",
            "atr_percent_14": "0.06000000",
            "volatility_20": "0.06500000",
            "volatility_63": "0.07000000",
            "volatility_126": "0.07500000",
            "volatility_252": "0.08000000",
            "volume_z_score_20": "-1.00000000",
            "turnover": "1000000.00000000",
            "avg_traded_value_20": "900000.00000000",
            "avg_traded_value_63": "800000.00000000",
            "turnover_z_score_20": "-1.10000000",
        },
    }
    return {
        feature_name: Decimal(value)
        for feature_name, value in values_by_profile[profile].items()
    }


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
