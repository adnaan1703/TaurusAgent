from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.technical import (
    average_true_range,
    daily_returns,
    exponential_moving_average,
    period_returns,
    relative_strength_index,
    rolling_volatility,
    simple_moving_average,
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
    assert rolling_volatility([None, Decimal("0.1"), Decimal("0.2"), Decimal("0.3")], 2) == [
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

    assert relative_strength_index(closes, window=3) == [None, None, None, Decimal("100")]
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
        )
        for index, (open_price, high, low, close, volume) in enumerate(rows)
    ]
