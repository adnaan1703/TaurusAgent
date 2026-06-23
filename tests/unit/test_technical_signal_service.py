from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from taurus_core.features.store import FeatureSnapshot
from taurus_core.features.technical_signal import (
    TechnicalBacktestSignal,
    TechnicalSignalService,
)


def test_analyst_rule_uses_backtest_signal_override() -> None:
    service = TechnicalSignalService()
    snapshot = _feature_snapshot(
        "INFY",
        snapshot_id="snapshot-INFY-2024-01-12",
        values={
            "return_20d": Decimal("0.08000000"),
            "return_5d": Decimal("0.04000000"),
            "ema_12": Decimal("112.00000000"),
            "ema_26": Decimal("100.00000000"),
            "rsi_14": Decimal("64.00000000"),
            "volatility_20": Decimal("0.02000000"),
        },
    )
    result = service.score_analyst_rule(
        snapshot,
        TechnicalBacktestSignal(
            signal_id=123,
            action="SELL",
            score=Decimal("0.42000000"),
        ),
    )

    assert result.profile_name == "technical_rule_v1"
    assert result.available is True
    assert result.raw_score == Decimal("-0.42000000")
    assert result.score == Decimal("-0.4200")
    assert result.confidence == Decimal("0.6800")
    assert result.score_source == "technical_rule_v1"
    assert result.source_ids == ("snapshot-INFY-2024-01-12", "signal:123")
    assert result.key_points[0] == (
        "Latest strategy signal for INFY was SELL with score 0.42000000."
    )
    assert "20-day return feature is 0.08000000." in result.key_points
    assert result.components["signal_score"] == Decimal("0.42000000")
    assert result.components["signal_direction"] == Decimal("-1")
    assert result.metadata["snapshot_id"] == "snapshot-INFY-2024-01-12"
    assert result.metadata["symbol"] == "INFY"
    assert result.metadata["feature_time"] == "2024-01-11"
    assert result.metadata["as_of_date"] == "2024-01-12"
    assert result.metadata["signal_id"] == 123
    assert result.metadata["signal_action"] == "SELL"
    assert result.metadata["score_precision"] == Decimal("0.0001")


def test_analyst_rule_feature_formula_matches_existing_clamped_report_score() -> None:
    service = TechnicalSignalService()
    snapshot = _feature_snapshot(
        "TCS",
        snapshot_id="snapshot-TCS-2024-01-12",
        values={
            "return_20d": Decimal("0.60000000"),
            "return_5d": Decimal("0.20000000"),
            "ema_12": Decimal("120.00000000"),
            "ema_26": Decimal("100.00000000"),
            "rsi_14": Decimal("80.00000000"),
            "volatility_20": Decimal("0.01000000"),
        },
    )

    result = service.score_analyst_rule(snapshot, None)

    assert result.raw_score == Decimal("1.6525000000000")
    assert result.score == Decimal("1.0000")
    assert result.confidence == Decimal("0.6800")
    assert result.source_ids == ("snapshot-TCS-2024-01-12",)
    assert result.components["return_20d_component"] == Decimal("1.080000000")
    assert result.components["ema_trend_component"] == Decimal("0.240000000000")
    assert "RSI-14 feature is 80.00000000." in result.key_points
    assert "20-day volatility feature is 0.01000000." in result.key_points


def test_analyst_rule_empty_feature_fallback_matches_existing_report_behavior() -> None:
    service = TechnicalSignalService()

    result = service.score_analyst_rule(None, None, symbol="WIPRO")

    assert result.available is True
    assert result.raw_score == Decimal("0")
    assert result.score == Decimal("0.0000")
    assert result.confidence == Decimal("0.3500")
    assert result.source_ids == ("technical:none",)
    assert result.missing_features == (
        "return_20d",
        "return_5d",
        "ema_12",
        "ema_26",
        "rsi_14",
        "volatility_20",
    )
    assert result.key_points == (
        "No persisted technical features were available for WIPRO; neutral fallback used.",
    )


def test_sma_spread_requires_fast_and_slow_sma() -> None:
    service = TechnicalSignalService()

    missing_slow = service.score_sma_spread(
        _feature_snapshot("AAA", values={"sma_3": Decimal("101")}),
        fast_window=3,
        slow_window=5,
    )
    missing_fast = service.score_sma_spread(
        _feature_snapshot("AAA", values={"sma_5": Decimal("100")}),
        fast_window=3,
        slow_window=5,
    )
    zero_slow = service.score_sma_spread(
        _feature_snapshot(
            "AAA",
            values={
                "sma_3": Decimal("101"),
                "sma_5": Decimal("0"),
            },
        ),
        fast_window=3,
        slow_window=5,
    )

    assert missing_slow.available is False
    assert missing_slow.score is None
    assert missing_slow.missing_features == ("sma_5",)
    assert missing_slow.metadata["unavailable_reason"] == "missing_sma_feature"
    assert missing_slow.metadata["fast_feature"] == "sma_3"
    assert missing_slow.metadata["slow_feature"] == "sma_5"
    assert missing_slow.metadata["score_precision"] == Decimal("0.00000001")
    assert missing_fast.available is False
    assert missing_fast.score is None
    assert missing_fast.missing_features == ("sma_3",)
    assert zero_slow.available is False
    assert zero_slow.score is None
    assert zero_slow.metadata["unavailable_reason"] == "invalid_slow_sma"
    assert zero_slow.metadata["invalid_features"] == ["sma_5"]


def test_sma_spread_quantizes_like_graph_aware_strategy() -> None:
    service = TechnicalSignalService()

    result = service.score_sma_spread(
        _feature_snapshot(
            "AAA",
            values={
                "sma_3": Decimal("112.34567890"),
                "sma_5": Decimal("100.00000000"),
            },
        ),
        fast_window=3,
        slow_window=5,
    )

    assert result.profile_name == "sma_spread"
    assert result.available is True
    assert result.raw_score == Decimal("0.123456789")
    assert result.score == Decimal("0.12345679")
    assert result.confidence is None
    assert result.source_ids == ("fs-AAA",)
    assert result.components["fast_sma"] == Decimal("112.34567890")
    assert result.components["slow_sma"] == Decimal("100.00000000")
    assert result.metadata["fast_window"] == 3
    assert result.metadata["slow_window"] == 5
    assert result.metadata["fast_feature"] == "sma_3"
    assert result.metadata["slow_feature"] == "sma_5"
    assert result.metadata["score_precision"] == Decimal("0.00000001")


def test_signal_results_are_immutable() -> None:
    service = TechnicalSignalService()
    result = service.score_analyst_rule(None, None, symbol="WIPRO")

    with pytest.raises(FrozenInstanceError):
        result.score = Decimal("1")  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.components["raw"] = Decimal("1")  # type: ignore[index]


def _feature_snapshot(
    symbol: str,
    *,
    values: dict[str, Decimal],
    snapshot_id: str | None = None,
) -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=snapshot_id or f"fs-{symbol}",
        symbol=symbol,
        as_of_date=date(2024, 1, 12),
        feature_time=date(2024, 1, 11),
        values=values,
        rows=(),
    )
