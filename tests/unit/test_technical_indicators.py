from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.store import (
    TECHNICAL_OHLCV_V2_FEATURE_VERSION,
    TECHNICAL_FEATURE_VERSION,
    TechnicalFeatureService,
)
from taurus_core.features.technical import (
    average_directional_index,
    average_true_range,
    average_true_range_percent,
    bollinger_bands,
    daily_returns,
    distance_from_rolling_high,
    exponential_moving_average,
    moving_average_convergence_divergence,
    period_returns,
    relative_strength_index,
    rolling_average_traded_value,
    rolling_breakout_distance,
    rolling_volatility,
    simple_moving_average,
    traded_value,
    turnover_z_score,
    volatility_adjusted_returns,
    volume_z_score,
)


def test_sma_and_ema_are_aligned_to_input_series() -> None:
    values = [Decimal(value) for value in ("1", "2", "3", "4", "5")]

    assert simple_moving_average(values, 3) == [
        None,
        None,
        Decimal("2"),
        Decimal("3"),
        Decimal("4"),
    ]
    assert exponential_moving_average(values, 3) == [
        None,
        None,
        Decimal("2"),
        Decimal("3.0"),
        Decimal("4.00"),
    ]


def test_returns_and_rolling_volatility_use_past_windows() -> None:
    closes = [Decimal("100"), Decimal("110"), Decimal("121"), Decimal("133.1")]
    returns = daily_returns(closes)

    assert returns == [None, Decimal("0.1"), Decimal("0.1"), Decimal("0.1")]
    assert period_returns(closes, period=2) == [
        None,
        None,
        Decimal("0.21"),
        Decimal("0.21"),
    ]
    assert rolling_volatility(
        [None, Decimal("0.1"), Decimal("0.2"), Decimal("0.3")], 2
    ) == [
        None,
        None,
        Decimal("0.05"),
        Decimal("0.05"),
    ]


def test_rsi_atr_and_volume_z_score_on_fixed_data() -> None:
    closes = [Decimal(value) for value in ("1", "2", "3", "4")]
    candles = _candles(
        [
            (Decimal("10"), Decimal("12"), Decimal("10"), Decimal("11"), 10),
            (Decimal("11"), Decimal("15"), Decimal("11"), Decimal("14"), 20),
            (Decimal("14"), Decimal("18"), Decimal("14"), Decimal("17"), 30),
        ]
    )

    assert relative_strength_index(closes, window=3) == [
        None,
        None,
        None,
        Decimal("100"),
    ]
    assert average_true_range(candles, window=2) == [
        None,
        Decimal("3"),
        Decimal("3.5"),
    ]
    assert volume_z_score([10, 20, 30, 40], window=2) == [
        None,
        None,
        Decimal("3"),
        Decimal("3"),
    ]


def test_macd_is_aligned_and_waits_for_signal_history() -> None:
    values = [Decimal(value) for value in ("1", "2", "3", "4", "5", "6")]

    macd_line, signal_line, histogram = moving_average_convergence_divergence(
        values,
        fast_window=2,
        slow_window=3,
        signal_window=2,
    )

    assert macd_line == [
        None,
        None,
        Decimal("0.5"),
        Decimal("0.5"),
        Decimal("0.5"),
        Decimal("0.5"),
    ]
    assert signal_line == [
        None,
        None,
        None,
        Decimal("0.5"),
        Decimal("0.5"),
        Decimal("0.5"),
    ]
    assert histogram == [
        None,
        None,
        None,
        Decimal("0.0"),
        Decimal("0.0"),
        Decimal("0.0"),
    ]


def test_adx_plus_di_and_minus_di_use_wilder_smoothing() -> None:
    candles = _candles(
        [
            (Decimal("9.5"), Decimal("10"), Decimal("9"), Decimal("9.5"), 100),
            (Decimal("10.5"), Decimal("11"), Decimal("10"), Decimal("10.5"), 100),
            (Decimal("11.5"), Decimal("12"), Decimal("11"), Decimal("11.5"), 100),
            (Decimal("12.5"), Decimal("13"), Decimal("12"), Decimal("12.5"), 100),
            (Decimal("13.5"), Decimal("14"), Decimal("13"), Decimal("13.5"), 100),
        ]
    )

    adx, plus_di, minus_di = average_directional_index(candles, window=2)

    assert plus_di[:2] == [None, None]
    assert plus_di[2].quantize(Decimal("0.0001")) == Decimal("66.6667")
    assert minus_di[2] == Decimal("0")
    assert adx[:3] == [None, None, None]
    assert adx[3] == Decimal("100")
    assert adx[4] == Decimal("100")


def test_bollinger_bands_emit_neutral_percent_b_for_flat_bands() -> None:
    middle, upper, lower, percent_b, bandwidth = bollinger_bands(
        [Decimal("2"), Decimal("2"), Decimal("2")],
        window=3,
    )

    assert middle == [None, None, Decimal("2")]
    assert upper == [None, None, Decimal("2")]
    assert lower == [None, None, Decimal("2")]
    assert percent_b == [None, None, Decimal("0.5")]
    assert bandwidth == [None, None, Decimal("0")]


def test_breakout_and_rolling_high_distances_are_history_only() -> None:
    candles = _candles(
        [
            (Decimal("10"), Decimal("11"), Decimal("9"), Decimal("10"), 100),
            (Decimal("12"), Decimal("13"), Decimal("10"), Decimal("12"), 100),
            (Decimal("15"), Decimal("16"), Decimal("12"), Decimal("15"), 100),
        ]
    )

    high_distance, low_distance = rolling_breakout_distance(candles, window=2)
    distance_from_high = distance_from_rolling_high(candles, window=3)

    assert high_distance[:2] == [None, None]
    assert high_distance[2].quantize(Decimal("0.0001")) == Decimal("0.1538")
    assert low_distance[2].quantize(Decimal("0.0001")) == Decimal("0.6667")
    assert distance_from_high == [None, None, Decimal("-0.0625")]


def test_atr_percent_turnover_and_volatility_adjusted_returns() -> None:
    candles = _candles(
        [
            (Decimal("10"), Decimal("12"), Decimal("10"), Decimal("11"), 10),
            (Decimal("11"), Decimal("15"), Decimal("11"), Decimal("14"), 20),
            (Decimal("14"), Decimal("18"), Decimal("14"), Decimal("17"), 30),
        ]
    )

    atr_percent = average_true_range_percent(candles, window=2)
    assert atr_percent[0] is None
    assert atr_percent[1].quantize(Decimal("0.0001")) == Decimal("0.2143")
    assert atr_percent[2].quantize(Decimal("0.0001")) == Decimal("0.2059")
    assert traded_value(candles) == [Decimal("110"), Decimal("280"), Decimal("510")]
    assert rolling_average_traded_value(candles, window=2) == [
        None,
        Decimal("195"),
        Decimal("395"),
    ]
    assert turnover_z_score(candles, window=2) == [
        None,
        None,
        Decimal("3.705882352941176470588235294"),
    ]

    adjusted = volatility_adjusted_returns(
        [Decimal("100"), Decimal("110"), Decimal("99")],
        window=2,
    )
    assert adjusted == [None, None, Decimal("-0.1")]
    assert volatility_adjusted_returns(
        [Decimal("100"), Decimal("110"), Decimal("121")],
        window=2,
    ) == [None, None, None]


def test_feature_service_v1_defaults_remain_unchanged_with_strategy_windows() -> None:
    service = TechnicalFeatureService.from_strategy_parameters(
        {"fast_window": 7, "slow_window": 9}
    )
    snapshot = service.build_snapshot(
        symbol="AAA",
        as_of_date=date(2024, 10, 1),
        history=_long_history(260),
    )

    assert snapshot is not None
    assert snapshot.rows[0].feature_version == TECHNICAL_FEATURE_VERSION
    assert {"sma_5", "sma_7", "sma_9", "sma_10", "return_20d"}.issubset(snapshot.values)
    assert "macd_line_12_26_9" not in snapshot.values
    assert "breakout_high_distance_252d" not in snapshot.values
    assert "vol_adjusted_return_252d" not in snapshot.values


def test_feature_service_technical_ohlcv_v2_outputs_full_opt_in_suite() -> None:
    service = TechnicalFeatureService.from_strategy_parameters(
        {
            "technical_feature_version": TECHNICAL_OHLCV_V2_FEATURE_VERSION,
            "fast_window": 7,
            "slow_window": 9,
        }
    )
    snapshot = service.build_snapshot(
        symbol="AAA",
        as_of_date=date(2024, 10, 1),
        history=_long_history(260),
    )

    assert snapshot is not None
    assert snapshot.rows[0].feature_version == TECHNICAL_OHLCV_V2_FEATURE_VERSION
    expected_features = {
        "sma_7",
        "sma_9",
        "return_63d",
        "return_126d",
        "return_252d",
        "macd_line_12_26_9",
        "macd_signal_12_26_9",
        "macd_histogram_12_26_9",
        "adx_14",
        "plus_di_14",
        "minus_di_14",
        "bollinger_ma_20",
        "bollinger_upper_20",
        "bollinger_lower_20",
        "bollinger_percent_b_20",
        "bollinger_bandwidth_20",
        "breakout_high_distance_20d",
        "breakout_low_distance_20d",
        "breakout_high_distance_50d",
        "breakout_low_distance_50d",
        "breakout_high_distance_252d",
        "breakout_low_distance_252d",
        "distance_from_52w_high",
        "atr_percent_14",
        "turnover",
        "avg_traded_value_20",
        "avg_traded_value_63",
        "turnover_z_score_20",
        "vol_adjusted_return_63d",
        "vol_adjusted_return_126d",
        "vol_adjusted_return_252d",
    }
    assert expected_features.issubset(snapshot.values)
    assert all(
        value == value.quantize(Decimal("0.00000001"))
        for value in snapshot.values.values()
    )

    short_snapshot = service.build_snapshot(
        symbol="AAA",
        as_of_date=date(2024, 3, 1),
        history=_long_history(30),
    )
    assert short_snapshot is not None
    assert "distance_from_52w_high" not in short_snapshot.values
    assert "breakout_high_distance_252d" not in short_snapshot.values
    assert "vol_adjusted_return_252d" not in short_snapshot.values


def _candles(
    rows: list[tuple[Decimal, Decimal, Decimal, Decimal, int]],
) -> list[DailyCandle]:
    start = date(2024, 1, 1)
    return [
        DailyCandle(
            symbol="AAA",
            trade_date=start + timedelta(days=index),
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
            source="test_fixture",
        )
        for index, (open_price, high, low, close, volume) in enumerate(rows)
    ]


def _long_history(count: int) -> list[DailyCandle]:
    start = date(2024, 1, 1)
    candles: list[DailyCandle] = []
    for index in range(count):
        drift = Decimal(index)
        cycle = Decimal(index % 7) / Decimal("10")
        close = Decimal("100") + drift + cycle
        candles.append(
            DailyCandle(
                symbol="AAA",
                trade_date=start + timedelta(days=index),
                open=close - Decimal("0.5"),
                high=close + Decimal("1.5"),
                low=close - Decimal("1.5"),
                close=close,
                volume=1_000 + (index * 10) + ((index % 5) * 100),
                source="test_fixture",
            )
        )
    return candles
