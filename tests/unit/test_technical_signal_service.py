from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import date
from decimal import Decimal

import pytest

from taurus_core.features.store import FeatureSnapshot
from taurus_core.features.technical_context import (
    HIGHER_IS_BETTER,
    LOWER_IS_BETTER,
    build_universe_technical_context,
)
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


def test_score_ohlcv_v2_uses_full_ohlcv_suite_and_universe_context() -> None:
    service = TechnicalSignalService()
    snapshots = {
        "AAA": _feature_snapshot("AAA", values=_ohlcv_v2_values("strong")),
        "BBB": _feature_snapshot("BBB", values=_ohlcv_v2_values("neutral")),
        "CCC": _feature_snapshot("CCC", values=_ohlcv_v2_values("weak")),
    }
    context = build_universe_technical_context(snapshots)

    result = service.score_ohlcv_v2(
        snapshots["AAA"],
        universe_context=context,
        top_contributor_limit=5,
    )

    assert result.profile_name == "technical_ohlcv_v2"
    assert result.available is True
    assert result.score_source == "technical_ohlcv_v2"
    assert result.score == result.composite_score
    assert result.raw_score == result.composite_score
    assert result.source_ids == ("fs-AAA",)
    assert result.coverage == Decimal("1.0000")
    assert result.missing_features == ()
    assert result.alpha_score > Decimal("0.5000")
    assert result.risk_score > Decimal("0.5000")
    assert result.tradability_score > Decimal("0.5000")
    assert result.composite_score > Decimal("0.5000")
    assert result.confidence >= Decimal("0.9000")
    assert len(result.top_contributors) == 5
    assert all("contribution" in contributor for contributor in result.top_contributors)
    assert any(
        contributor["source"] == "universe_context"
        for contributor in result.top_contributors
    )
    assert result.components["alpha_score"] == result.alpha_score
    assert result.components["risk_score"] == result.risk_score
    assert result.components["tradability_score"] == result.tradability_score
    assert "alpha.vol_adjusted_return_126d.score" in result.components
    assert "risk.atr_percent_14.score" in result.components
    assert "tradability.avg_traded_value_20.score" in result.components
    assert result.metadata["family_weights"] == {
        "alpha": "0.65",
        "risk": "0.20",
        "tradability": "0.15",
    }
    assert result.metadata["universe_context_available"] is True
    assert result.metadata["symbol_context_available"] is True
    assert result.metadata["universe_size"] == 3
    assert result.metadata["missing_context_features"] == []


def test_score_ohlcv_v2_degrades_confidence_when_features_and_context_are_missing() -> None:
    service = TechnicalSignalService()
    snapshot = _feature_snapshot(
        "AAA",
        values={
            "return_20d": Decimal("0.05000000"),
            "ema_12": Decimal("105.00000000"),
            "ema_26": Decimal("100.00000000"),
            "rsi_14": Decimal("60.00000000"),
            "volatility_20": Decimal("0.03000000"),
        },
    )

    result = service.score_ohlcv_v2(snapshot)

    assert result.available is True
    assert result.coverage == Decimal("0.1667")
    assert result.confidence < Decimal("0.5000")
    assert result.composite_score > Decimal("0.0000")
    assert "return_252d" in result.missing_features
    assert "turnover" in result.missing_features
    assert result.metadata["universe_context_available"] is False
    assert result.metadata["symbol_context_available"] is False
    assert result.metadata["available_feature_count"] == 5
    assert "return_63d" in result.metadata["missing_context_features"]
    assert "turnover_z_score_20" in result.metadata["missing_context_features"]
    assert result.components["coverage"] == Decimal("0.1667")
    assert result.components["tradability_feature_quality"] == Decimal("0.0000")
    assert all(
        contributor["source"] != "universe_context"
        for contributor in result.top_contributors
    )


def test_score_ohlcv_v2_without_snapshot_is_unavailable() -> None:
    service = TechnicalSignalService()

    result = service.score_ohlcv_v2(None, symbol="WIPRO")

    assert result.profile_name == "technical_ohlcv_v2"
    assert result.available is False
    assert result.score == Decimal("0.0000")
    assert result.confidence == Decimal("0.0000")
    assert result.coverage == Decimal("0.0000")
    assert len(result.missing_features) == 30
    assert result.source_ids == ("technical:none",)
    assert result.metadata["symbol"] == "WIPRO"
    assert result.metadata["unavailable_reason"] == "missing_feature_snapshot"


def test_signal_results_are_immutable() -> None:
    service = TechnicalSignalService()
    result = service.score_analyst_rule(None, None, symbol="WIPRO")
    v2_result = service.score_ohlcv_v2(
        _feature_snapshot("AAA", values=_ohlcv_v2_values("strong")),
    )

    with pytest.raises(FrozenInstanceError):
        result.score = Decimal("1")  # type: ignore[misc]
    with pytest.raises(TypeError):
        result.components["raw"] = Decimal("1")  # type: ignore[index]
    with pytest.raises(FrozenInstanceError):
        v2_result.composite_score = Decimal("1")  # type: ignore[misc]
    with pytest.raises(TypeError):
        v2_result.components["raw"] = Decimal("1")  # type: ignore[index]
    with pytest.raises(TypeError):
        v2_result.top_contributors[0]["feature"] = "BBB"  # type: ignore[index]



def test_universe_technical_context_ranks_ties_and_missing_features() -> None:
    context = build_universe_technical_context(
        {
            "aaa": _feature_snapshot(
                "AAA",
                values={
                    "return_63d": Decimal("0.10000000"),
                    "volatility_20": Decimal("0.20000000"),
                },
            ),
            "BBB": _feature_snapshot(
                "BBB",
                values={
                    "return_63d": Decimal("0.05000000"),
                    "volatility_20": Decimal("0.10000000"),
                    "turnover_z_score_20": Decimal("1.00000000"),
                },
            ),
            "CCC": _feature_snapshot(
                "CCC",
                values={
                    "return_63d": Decimal("0.05000000"),
                    "turnover_z_score_20": Decimal("2.00000000"),
                },
            ),
            "DDD": _feature_snapshot(
                "DDD",
                values={
                    "volatility_20": Decimal("0.10000000"),
                    "turnover_z_score_20": Decimal("2.00000000"),
                },
            ),
        },
        feature_names=("return_63d", "volatility_20", "turnover_z_score_20"),
        rank_directions={
            "return_63d": HIGHER_IS_BETTER,
            "volatility_20": LOWER_IS_BETTER,
            "turnover_z_score_20": HIGHER_IS_BETTER,
        },
    )

    assert context.profile_name == "technical_ohlcv_v2"
    assert context.as_of_date == date(2024, 1, 12)
    assert context.universe_size == 4
    assert context.symbols == ("AAA", "BBB", "CCC", "DDD")
    assert context.symbols_by_feature["return_63d"] == ("AAA", "BBB", "CCC")
    assert context.missing_symbols_by_feature["return_63d"] == ("DDD",)
    assert context.missing_symbols_by_feature["volatility_20"] == ("CCC",)
    assert context.missing_symbols_by_feature["turnover_z_score_20"] == ("AAA",)
    assert context.for_symbol("ddd").missing_features == ("return_63d",)

    aaa_return = context.feature_for_symbol("AAA", "return_63d")
    bbb_return = context.feature_for_symbol("BBB", "return_63d")
    ccc_return = context.feature_for_symbol("CCC", "return_63d")
    assert aaa_return is not None
    assert bbb_return is not None
    assert ccc_return is not None
    assert aaa_return.rank == 1
    assert aaa_return.percentile == Decimal("1.00000000")
    assert aaa_return.directional_z_score == Decimal("1.41421356")
    assert bbb_return.rank == 2
    assert bbb_return.percentile == Decimal("0.25000000")
    assert bbb_return.directional_z_score == Decimal("-0.70710678")
    assert ccc_return.rank == 2
    assert ccc_return.percentile == Decimal("0.25000000")
    assert ccc_return.directional_z_score == Decimal("-0.70710678")

    bbb_volatility = context.feature_for_symbol("BBB", "volatility_20")
    ddd_volatility = context.feature_for_symbol("DDD", "volatility_20")
    aaa_volatility = context.feature_for_symbol("AAA", "volatility_20")
    assert bbb_volatility is not None
    assert ddd_volatility is not None
    assert aaa_volatility is not None
    assert bbb_volatility.rank == 1
    assert ddd_volatility.rank == 1
    assert aaa_volatility.rank == 3
    assert bbb_volatility.directional_z_score == Decimal("0.70710678")
    assert aaa_volatility.directional_z_score == Decimal("-1.41421356")
    assert context.metadata["eligible_symbol_count_by_feature"] == {
        "return_63d": 3,
        "volatility_20": 3,
        "turnover_z_score_20": 3,
    }
    assert context.metadata["rank_direction_by_feature"]["volatility_20"] == LOWER_IS_BETTER


def test_universe_technical_context_small_universe_is_neutral() -> None:
    context = build_universe_technical_context(
        {
            "AAA": _feature_snapshot(
                "AAA",
                values={"return_63d": Decimal("0.10000000")},
            )
        },
        feature_names=("return_63d",),
    )

    feature = context.feature_for_symbol("AAA", "return_63d")

    assert feature is not None
    assert feature.rank == 1
    assert feature.percentile == Decimal("0.50000000")
    assert feature.z_score == Decimal("0E-8")
    assert feature.directional_z_score == Decimal("0E-8")


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
        "neutral": {
            "return_20d": "0.01000000",
            "return_63d": "0.04000000",
            "return_126d": "0.08000000",
            "return_252d": "0.12000000",
            "vol_adjusted_return_63d": "0.60000000",
            "vol_adjusted_return_126d": "0.70000000",
            "vol_adjusted_return_252d": "0.80000000",
            "ema_12": "102.00000000",
            "ema_26": "100.00000000",
            "macd_histogram_12_26_9": "0.20000000",
            "adx_14": "22.00000000",
            "plus_di_14": "25.00000000",
            "minus_di_14": "20.00000000",
            "rsi_14": "52.00000000",
            "bollinger_percent_b_20": "0.52000000",
            "bollinger_bandwidth_20": "0.12000000",
            "breakout_high_distance_20d": "-0.01000000",
            "breakout_high_distance_50d": "-0.03000000",
            "breakout_high_distance_252d": "-0.08000000",
            "distance_from_52w_high": "-0.12000000",
            "atr_percent_14": "0.02500000",
            "volatility_20": "0.02500000",
            "volatility_63": "0.02800000",
            "volatility_126": "0.03000000",
            "volatility_252": "0.03200000",
            "volume_z_score_20": "0.20000000",
            "turnover": "5000000.00000000",
            "avg_traded_value_20": "5000000.00000000",
            "avg_traded_value_63": "4800000.00000000",
            "turnover_z_score_20": "0.10000000",
        },
        "weak": {
            "return_20d": "-0.04000000",
            "return_63d": "-0.08000000",
            "return_126d": "-0.12000000",
            "return_252d": "-0.20000000",
            "vol_adjusted_return_63d": "-0.80000000",
            "vol_adjusted_return_126d": "-1.00000000",
            "vol_adjusted_return_252d": "-1.20000000",
            "ema_12": "95.00000000",
            "ema_26": "100.00000000",
            "macd_histogram_12_26_9": "-0.80000000",
            "adx_14": "18.00000000",
            "plus_di_14": "15.00000000",
            "minus_di_14": "32.00000000",
            "rsi_14": "38.00000000",
            "bollinger_percent_b_20": "0.20000000",
            "bollinger_bandwidth_20": "0.22000000",
            "breakout_high_distance_20d": "-0.08000000",
            "breakout_high_distance_50d": "-0.12000000",
            "breakout_high_distance_252d": "-0.25000000",
            "distance_from_52w_high": "-0.35000000",
            "atr_percent_14": "0.04500000",
            "volatility_20": "0.05000000",
            "volatility_63": "0.05200000",
            "volatility_126": "0.05500000",
            "volatility_252": "0.06000000",
            "volume_z_score_20": "-1.00000000",
            "turnover": "1000000.00000000",
            "avg_traded_value_20": "1200000.00000000",
            "avg_traded_value_63": "1300000.00000000",
            "turnover_z_score_20": "-0.80000000",
        },
    }
    return {
        feature_name: Decimal(value)
        for feature_name, value in values_by_profile[profile].items()
    }
