from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from taurus_core.domain.market_data import DailyCandle


def simple_moving_average(values: Sequence[Decimal], window: int) -> list[Decimal | None]:
    _validate_window(window)
    normalized = [_to_decimal(value) for value in values]
    result: list[Decimal | None] = [None] * len(normalized)
    rolling_sum = Decimal("0")

    for index, value in enumerate(normalized):
        rolling_sum += value
        if index >= window:
            rolling_sum -= normalized[index - window]
        if index >= window - 1:
            result[index] = rolling_sum / Decimal(window)

    return result


def exponential_moving_average(values: Sequence[Decimal], window: int) -> list[Decimal | None]:
    _validate_window(window)
    normalized = [_to_decimal(value) for value in values]
    result: list[Decimal | None] = [None] * len(normalized)
    if len(normalized) < window:
        return result

    multiplier = Decimal("2") / Decimal(window + 1)
    seed = sum(normalized[:window], Decimal("0")) / Decimal(window)
    result[window - 1] = seed
    previous = seed

    for index in range(window, len(normalized)):
        previous = ((normalized[index] - previous) * multiplier) + previous
        result[index] = previous

    return result


def daily_returns(values: Sequence[Decimal]) -> list[Decimal | None]:
    return period_returns(values, period=1)


def period_returns(values: Sequence[Decimal], *, period: int) -> list[Decimal | None]:
    _validate_window(period)
    normalized = [_to_decimal(value) for value in values]
    result: list[Decimal | None] = [None] * len(normalized)

    for index in range(period, len(normalized)):
        previous = normalized[index - period]
        if previous == 0:
            continue
        result[index] = (normalized[index] / previous) - Decimal("1")

    return result


def relative_strength_index(values: Sequence[Decimal], window: int = 14) -> list[Decimal | None]:
    _validate_window(window)
    normalized = [_to_decimal(value) for value in values]
    result: list[Decimal | None] = [None] * len(normalized)
    if len(normalized) <= window:
        return result

    gains: list[Decimal] = []
    losses: list[Decimal] = []
    for index in range(1, window + 1):
        change = normalized[index] - normalized[index - 1]
        gains.append(max(change, Decimal("0")))
        losses.append(abs(min(change, Decimal("0"))))

    average_gain = sum(gains, Decimal("0")) / Decimal(window)
    average_loss = sum(losses, Decimal("0")) / Decimal(window)
    result[window] = _rsi_from_averages(average_gain, average_loss)

    for index in range(window + 1, len(normalized)):
        change = normalized[index] - normalized[index - 1]
        gain = max(change, Decimal("0"))
        loss = abs(min(change, Decimal("0")))
        average_gain = ((average_gain * Decimal(window - 1)) + gain) / Decimal(window)
        average_loss = ((average_loss * Decimal(window - 1)) + loss) / Decimal(window)
        result[index] = _rsi_from_averages(average_gain, average_loss)

    return result


def average_true_range(candles: Sequence[DailyCandle], window: int = 14) -> list[Decimal | None]:
    _validate_window(window)
    if not candles:
        return []

    true_ranges: list[Decimal] = []
    for index, candle in enumerate(candles):
        high_low = candle.high - candle.low
        if index == 0:
            true_ranges.append(high_low)
            continue
        previous_close = candles[index - 1].close
        true_ranges.append(
            max(
                high_low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )

    result: list[Decimal | None] = [None] * len(candles)
    if len(true_ranges) < window:
        return result

    atr = sum(true_ranges[:window], Decimal("0")) / Decimal(window)
    result[window - 1] = atr
    for index in range(window, len(true_ranges)):
        atr = ((atr * Decimal(window - 1)) + true_ranges[index]) / Decimal(window)
        result[index] = atr

    return result


def rolling_volatility(
    returns: Sequence[Decimal | None],
    window: int,
) -> list[Decimal | None]:
    _validate_window(window)
    result: list[Decimal | None] = [None] * len(returns)

    for index in range(window - 1, len(returns)):
        window_values = returns[index - window + 1 : index + 1]
        if any(value is None for value in window_values):
            continue
        result[index] = _stddev([value for value in window_values if value is not None])

    return result


def volume_z_score(volumes: Sequence[int | Decimal], window: int) -> list[Decimal | None]:
    _validate_window(window)
    normalized = [_to_decimal(value) for value in volumes]
    result: list[Decimal | None] = [None] * len(normalized)

    for index in range(window, len(normalized)):
        previous_values = normalized[index - window : index]
        stddev = _stddev(previous_values)
        if stddev == 0:
            result[index] = Decimal("0")
        else:
            mean = sum(previous_values, Decimal("0")) / Decimal(window)
            result[index] = (normalized[index] - mean) / stddev

    return result


def _rsi_from_averages(average_gain: Decimal, average_loss: Decimal) -> Decimal:
    if average_loss == 0:
        return Decimal("100")
    if average_gain == 0:
        return Decimal("0")
    relative_strength = average_gain / average_loss
    return Decimal("100") - (Decimal("100") / (Decimal("1") + relative_strength))


def _stddev(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values))
    return variance.sqrt()


def _to_decimal(value: Decimal | int) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _validate_window(window: int) -> None:
    if window <= 0:
        raise ValueError("window must be positive")
