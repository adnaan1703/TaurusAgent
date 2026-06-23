from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from taurus_core.domain.market_data import DailyCandle


def simple_moving_average(
    values: Sequence[Decimal], window: int
) -> list[Decimal | None]:
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


def exponential_moving_average(
    values: Sequence[Decimal], window: int
) -> list[Decimal | None]:
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


def relative_strength_index(
    values: Sequence[Decimal], window: int = 14
) -> list[Decimal | None]:
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


def average_true_range(
    candles: Sequence[DailyCandle], window: int = 14
) -> list[Decimal | None]:
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


def volume_z_score(
    volumes: Sequence[int | Decimal], window: int
) -> list[Decimal | None]:
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


def moving_average_convergence_divergence(
    values: Sequence[Decimal],
    *,
    fast_window: int = 12,
    slow_window: int = 26,
    signal_window: int = 9,
) -> tuple[list[Decimal | None], list[Decimal | None], list[Decimal | None]]:
    _validate_window(fast_window)
    _validate_window(slow_window)
    _validate_window(signal_window)
    if fast_window >= slow_window:
        raise ValueError("fast_window must be smaller than slow_window")

    fast_ema = exponential_moving_average(values, fast_window)
    slow_ema = exponential_moving_average(values, slow_window)
    macd_line = [
        fast - slow if fast is not None and slow is not None else None
        for fast, slow in zip(fast_ema, slow_ema)
    ]
    signal_line = _ema_optional(macd_line, signal_window)
    histogram = [
        line - signal if line is not None and signal is not None else None
        for line, signal in zip(macd_line, signal_line)
    ]
    return macd_line, signal_line, histogram


def average_directional_index(
    candles: Sequence[DailyCandle],
    window: int = 14,
) -> tuple[list[Decimal | None], list[Decimal | None], list[Decimal | None]]:
    _validate_window(window)
    result_length = len(candles)
    adx: list[Decimal | None] = [None] * result_length
    plus_di: list[Decimal | None] = [None] * result_length
    minus_di: list[Decimal | None] = [None] * result_length
    if result_length <= window:
        return adx, plus_di, minus_di

    true_ranges = _true_ranges(candles)
    plus_dm: list[Decimal] = [Decimal("0")] * result_length
    minus_dm: list[Decimal] = [Decimal("0")] * result_length
    for index in range(1, result_length):
        up_move = candles[index].high - candles[index - 1].high
        down_move = candles[index - 1].low - candles[index].low
        if up_move > down_move and up_move > 0:
            plus_dm[index] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[index] = down_move

    smoothed_tr = sum(true_ranges[1 : window + 1], Decimal("0"))
    smoothed_plus_dm = sum(plus_dm[1 : window + 1], Decimal("0"))
    smoothed_minus_dm = sum(minus_dm[1 : window + 1], Decimal("0"))
    dx: list[Decimal | None] = [None] * result_length

    for index in range(window, result_length):
        if index > window:
            smoothed_tr = _wilder_smooth(smoothed_tr, true_ranges[index], window)
            smoothed_plus_dm = _wilder_smooth(smoothed_plus_dm, plus_dm[index], window)
            smoothed_minus_dm = _wilder_smooth(
                smoothed_minus_dm, minus_dm[index], window
            )

        if smoothed_tr == 0:
            plus = Decimal("0")
            minus = Decimal("0")
        else:
            plus = (smoothed_plus_dm / smoothed_tr) * Decimal("100")
            minus = (smoothed_minus_dm / smoothed_tr) * Decimal("100")
        plus_di[index] = plus
        minus_di[index] = minus
        denominator = plus + minus
        dx[index] = (
            Decimal("0")
            if denominator == 0
            else (abs(plus - minus) / denominator) * Decimal("100")
        )

        first_adx_index = (window * 2) - 1
        if index == first_adx_index:
            dx_window = [
                value for value in dx[window : first_adx_index + 1] if value is not None
            ]
            if len(dx_window) == window:
                adx[index] = sum(dx_window, Decimal("0")) / Decimal(window)
        elif (
            index > first_adx_index
            and adx[index - 1] is not None
            and dx[index] is not None
        ):
            adx[index] = ((adx[index - 1] * Decimal(window - 1)) + dx[index]) / Decimal(
                window
            )

    return adx, plus_di, minus_di


def bollinger_bands(
    values: Sequence[Decimal],
    *,
    window: int = 20,
    standard_deviations: Decimal | int = Decimal("2"),
) -> tuple[
    list[Decimal | None],
    list[Decimal | None],
    list[Decimal | None],
    list[Decimal | None],
    list[Decimal | None],
]:
    _validate_window(window)
    deviations = _to_decimal(standard_deviations)
    normalized = [_to_decimal(value) for value in values]
    middle_band: list[Decimal | None] = [None] * len(normalized)
    upper_band: list[Decimal | None] = [None] * len(normalized)
    lower_band: list[Decimal | None] = [None] * len(normalized)
    percent_b: list[Decimal | None] = [None] * len(normalized)
    bandwidth: list[Decimal | None] = [None] * len(normalized)

    for index in range(window - 1, len(normalized)):
        window_values = normalized[index - window + 1 : index + 1]
        middle = sum(window_values, Decimal("0")) / Decimal(window)
        stddev = _stddev(window_values)
        upper = middle + (stddev * deviations)
        lower = middle - (stddev * deviations)
        band_range = upper - lower
        middle_band[index] = middle
        upper_band[index] = upper
        lower_band[index] = lower
        percent_b[index] = (
            Decimal("0.5")
            if band_range == 0
            else (normalized[index] - lower) / band_range
        )
        if middle != 0:
            bandwidth[index] = band_range / middle

    return middle_band, upper_band, lower_band, percent_b, bandwidth


def rolling_breakout_distance(
    candles: Sequence[DailyCandle],
    window: int,
) -> tuple[list[Decimal | None], list[Decimal | None]]:
    _validate_window(window)
    high_distance: list[Decimal | None] = [None] * len(candles)
    low_distance: list[Decimal | None] = [None] * len(candles)

    for index in range(window, len(candles)):
        previous_candles = candles[index - window : index]
        rolling_high = max(candle.high for candle in previous_candles)
        rolling_low = min(candle.low for candle in previous_candles)
        close = candles[index].close
        if rolling_high != 0:
            high_distance[index] = (close / rolling_high) - Decimal("1")
        if rolling_low != 0:
            low_distance[index] = (close / rolling_low) - Decimal("1")

    return high_distance, low_distance


def distance_from_rolling_high(
    candles: Sequence[DailyCandle],
    window: int = 252,
) -> list[Decimal | None]:
    _validate_window(window)
    result: list[Decimal | None] = [None] * len(candles)

    for index in range(window - 1, len(candles)):
        window_candles = candles[index - window + 1 : index + 1]
        rolling_high = max(candle.high for candle in window_candles)
        if rolling_high != 0:
            result[index] = (candles[index].close / rolling_high) - Decimal("1")

    return result


def average_true_range_percent(
    candles: Sequence[DailyCandle],
    window: int = 14,
) -> list[Decimal | None]:
    atr_values = average_true_range(candles, window)
    result: list[Decimal | None] = [None] * len(candles)
    for index, atr in enumerate(atr_values):
        close = candles[index].close
        if atr is not None and close != 0:
            result[index] = atr / close
    return result


def traded_value(candles: Sequence[DailyCandle]) -> list[Decimal]:
    return [candle.close * _to_decimal(candle.volume) for candle in candles]


def rolling_average_traded_value(
    candles: Sequence[DailyCandle],
    window: int,
) -> list[Decimal | None]:
    return simple_moving_average(traded_value(candles), window)


def turnover_z_score(
    candles: Sequence[DailyCandle],
    window: int,
) -> list[Decimal | None]:
    return volume_z_score(traded_value(candles), window)


def volatility_adjusted_returns(
    values: Sequence[Decimal],
    *,
    window: int,
) -> list[Decimal | None]:
    _validate_window(window)
    returns = period_returns(values, period=window)
    volatility = rolling_volatility(daily_returns(values), window)
    result: list[Decimal | None] = [None] * len(values)
    for index, (period_return, realized_volatility) in enumerate(
        zip(returns, volatility)
    ):
        if period_return is not None and realized_volatility not in (
            None,
            Decimal("0"),
        ):
            result[index] = period_return / realized_volatility
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


def _ema_optional(
    values: Sequence[Decimal | None], window: int
) -> list[Decimal | None]:
    _validate_window(window)
    result: list[Decimal | None] = [None] * len(values)
    multiplier = Decimal("2") / Decimal(window + 1)
    seed_values: list[Decimal] = []
    previous: Decimal | None = None

    for index, value in enumerate(values):
        if value is None:
            continue
        if previous is None:
            seed_values.append(value)
            if len(seed_values) == window:
                previous = sum(seed_values, Decimal("0")) / Decimal(window)
                result[index] = previous
            continue
        previous = ((value - previous) * multiplier) + previous
        result[index] = previous

    return result


def _true_ranges(candles: Sequence[DailyCandle]) -> list[Decimal]:
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
    return true_ranges


def _wilder_smooth(previous: Decimal, current: Decimal, window: int) -> Decimal:
    return previous - (previous / Decimal(window)) + current


def _to_decimal(value: Decimal | int) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _validate_window(window: int) -> None:
    if window <= 0:
        raise ValueError("window must be positive")
