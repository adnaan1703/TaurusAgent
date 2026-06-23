from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal

from taurus_core.domain.market_data import DailyCandle
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

FEATURE_VALUE = Decimal("0.00000001")
TECHNICAL_FEATURE_VERSION = "technical_v1"
TECHNICAL_OHLCV_V2_FEATURE_VERSION = "technical_ohlcv_v2"


@dataclass(frozen=True, slots=True)
class FeatureValue:
    snapshot_id: str
    symbol: str
    feature_name: str
    feature_value: Decimal
    feature_time: date
    data_available_time: datetime
    source: str = "daily_candles"
    feature_version: str = TECHNICAL_FEATURE_VERSION


@dataclass(frozen=True, slots=True)
class FeatureSnapshot:
    snapshot_id: str
    symbol: str
    as_of_date: date
    feature_time: date
    values: dict[str, Decimal]
    rows: tuple[FeatureValue, ...]

    def get(self, feature_name: str) -> Decimal | None:
        return self.values.get(feature_name)


class TechnicalFeatureService:
    def __init__(
        self,
        *,
        sma_windows: set[int] | None = None,
        ema_windows: set[int] | None = None,
        return_windows: set[int] | None = None,
        rsi_windows: set[int] | None = None,
        atr_windows: set[int] | None = None,
        volatility_windows: set[int] | None = None,
        volume_z_windows: set[int] | None = None,
        macd_windows: set[tuple[int, int, int]] | None = None,
        adx_windows: set[int] | None = None,
        bollinger_windows: set[int] | None = None,
        breakout_windows: set[int] | None = None,
        distance_from_high_windows: set[int] | None = None,
        atr_percent_windows: set[int] | None = None,
        average_traded_value_windows: set[int] | None = None,
        turnover_z_windows: set[int] | None = None,
        volatility_adjusted_return_windows: set[int] | None = None,
        include_turnover: bool = False,
        feature_version: str = TECHNICAL_FEATURE_VERSION,
    ) -> None:
        self.sma_windows = _window_set(sma_windows, default={5, 10, 20, 30, 50})
        self.ema_windows = _window_set(ema_windows, default={12, 26})
        self.return_windows = _window_set(return_windows, default={1, 5, 20})
        self.rsi_windows = _window_set(rsi_windows, default={14})
        self.atr_windows = _window_set(atr_windows, default={14})
        self.volatility_windows = _window_set(volatility_windows, default={20})
        self.volume_z_windows = _window_set(volume_z_windows, default={20})
        self.macd_windows = set(macd_windows or set())
        self.adx_windows = _window_set(adx_windows, default=set())
        self.bollinger_windows = _window_set(bollinger_windows, default=set())
        self.breakout_windows = _window_set(breakout_windows, default=set())
        self.distance_from_high_windows = _window_set(
            distance_from_high_windows,
            default=set(),
        )
        self.atr_percent_windows = _window_set(atr_percent_windows, default=set())
        self.average_traded_value_windows = _window_set(
            average_traded_value_windows,
            default=set(),
        )
        self.turnover_z_windows = _window_set(turnover_z_windows, default=set())
        self.volatility_adjusted_return_windows = _window_set(
            volatility_adjusted_return_windows,
            default=set(),
        )
        self.include_turnover = include_turnover
        self.feature_version = feature_version

    @classmethod
    def ohlcv_v2(cls) -> TechnicalFeatureService:
        return cls(
            sma_windows={5, 10, 20, 30, 50},
            ema_windows={12, 26},
            return_windows={1, 5, 20, 63, 126, 252},
            rsi_windows={14},
            atr_windows={14},
            volatility_windows={20, 63, 126, 252},
            volume_z_windows={20},
            macd_windows={(12, 26, 9)},
            adx_windows={14},
            bollinger_windows={20},
            breakout_windows={20, 50, 252},
            distance_from_high_windows={252},
            atr_percent_windows={14},
            average_traded_value_windows={20, 63},
            turnover_z_windows={20},
            volatility_adjusted_return_windows={63, 126, 252},
            include_turnover=True,
            feature_version=TECHNICAL_OHLCV_V2_FEATURE_VERSION,
        )

    @classmethod
    def from_strategy_parameters(
        cls,
        strategy_parameters: dict[str, object],
    ) -> TechnicalFeatureService:
        feature_version = _technical_feature_version(strategy_parameters)
        if feature_version == TECHNICAL_OHLCV_V2_FEATURE_VERSION:
            service = cls.ohlcv_v2()
            _add_strategy_sma_windows(service.sma_windows, strategy_parameters)
            return service

        sma_windows = {5, 10, 20, 30, 50}
        _add_strategy_sma_windows(sma_windows, strategy_parameters)
        return cls(sma_windows=sma_windows)

    def build_snapshot(
        self,
        *,
        symbol: str,
        as_of_date: date,
        history: list[DailyCandle],
    ) -> FeatureSnapshot | None:
        if not history:
            return None

        ordered_history = sorted(history, key=lambda candle: candle.trade_date)
        feature_time = ordered_history[-1].trade_date
        if feature_time >= as_of_date:
            raise ValueError("Feature history must end before the backtest trade date.")

        closes = [candle.close for candle in ordered_history]
        volumes = [candle.volume for candle in ordered_history]
        returns_1d = daily_returns(closes)
        values: dict[str, Decimal] = {}

        for window in sorted(self.sma_windows):
            _add_latest(values, f"sma_{window}", simple_moving_average(closes, window))
        for window in sorted(self.ema_windows):
            _add_latest(
                values, f"ema_{window}", exponential_moving_average(closes, window)
            )
        for window in sorted(self.return_windows):
            series = (
                returns_1d if window == 1 else period_returns(closes, period=window)
            )
            _add_latest(values, f"return_{window}d", series)
        for window in sorted(self.rsi_windows):
            _add_latest(
                values, f"rsi_{window}", relative_strength_index(closes, window)
            )
        for window in sorted(self.atr_windows):
            _add_latest(
                values, f"atr_{window}", average_true_range(ordered_history, window)
            )
        for window in sorted(self.volatility_windows):
            _add_latest(
                values, f"volatility_{window}", rolling_volatility(returns_1d, window)
            )
        for window in sorted(self.volume_z_windows):
            _add_latest(
                values, f"volume_z_score_{window}", volume_z_score(volumes, window)
            )
        for fast_window, slow_window, signal_window in sorted(self.macd_windows):
            macd_line, signal_line, histogram = moving_average_convergence_divergence(
                closes,
                fast_window=fast_window,
                slow_window=slow_window,
                signal_window=signal_window,
            )
            suffix = f"{fast_window}_{slow_window}_{signal_window}"
            _add_latest(values, f"macd_line_{suffix}", macd_line)
            _add_latest(values, f"macd_signal_{suffix}", signal_line)
            _add_latest(values, f"macd_histogram_{suffix}", histogram)
        for window in sorted(self.adx_windows):
            adx, plus_di, minus_di = average_directional_index(ordered_history, window)
            _add_latest(values, f"adx_{window}", adx)
            _add_latest(values, f"plus_di_{window}", plus_di)
            _add_latest(values, f"minus_di_{window}", minus_di)
        for window in sorted(self.bollinger_windows):
            middle, upper, lower, percent_b, bandwidth = bollinger_bands(
                closes,
                window=window,
            )
            _add_latest(values, f"bollinger_ma_{window}", middle)
            _add_latest(values, f"bollinger_upper_{window}", upper)
            _add_latest(values, f"bollinger_lower_{window}", lower)
            _add_latest(values, f"bollinger_percent_b_{window}", percent_b)
            _add_latest(values, f"bollinger_bandwidth_{window}", bandwidth)
        for window in sorted(self.breakout_windows):
            high_distance, low_distance = rolling_breakout_distance(
                ordered_history, window
            )
            _add_latest(values, f"breakout_high_distance_{window}d", high_distance)
            _add_latest(values, f"breakout_low_distance_{window}d", low_distance)
        for window in sorted(self.distance_from_high_windows):
            feature_name = (
                "distance_from_52w_high"
                if window == 252
                else f"distance_from_{window}d_high"
            )
            _add_latest(
                values,
                feature_name,
                distance_from_rolling_high(ordered_history, window),
            )
        for window in sorted(self.atr_percent_windows):
            _add_latest(
                values,
                f"atr_percent_{window}",
                average_true_range_percent(ordered_history, window),
            )
        if self.include_turnover:
            _add_latest(values, "turnover", traded_value(ordered_history))
        for window in sorted(self.average_traded_value_windows):
            _add_latest(
                values,
                f"avg_traded_value_{window}",
                rolling_average_traded_value(ordered_history, window),
            )
        for window in sorted(self.turnover_z_windows):
            _add_latest(
                values,
                f"turnover_z_score_{window}",
                turnover_z_score(ordered_history, window),
            )
        for window in sorted(self.volatility_adjusted_return_windows):
            _add_latest(
                values,
                f"vol_adjusted_return_{window}d",
                volatility_adjusted_returns(closes, window=window),
            )

        snapshot_id = _snapshot_id(
            symbol=symbol,
            as_of_date=as_of_date,
            feature_time=feature_time,
            feature_version=self.feature_version,
            values=values,
        )
        data_available_time = datetime.combine(
            as_of_date, time.min, tzinfo=timezone.utc
        )
        rows = tuple(
            FeatureValue(
                snapshot_id=snapshot_id,
                symbol=symbol.upper(),
                feature_name=feature_name,
                feature_value=feature_value,
                feature_time=feature_time,
                data_available_time=data_available_time,
                feature_version=self.feature_version,
            )
            for feature_name, feature_value in sorted(values.items())
        )
        return FeatureSnapshot(
            snapshot_id=snapshot_id,
            symbol=symbol.upper(),
            as_of_date=as_of_date,
            feature_time=feature_time,
            values=values,
            rows=rows,
        )


def _add_latest(
    values: dict[str, Decimal],
    feature_name: str,
    series: list[Decimal | None],
) -> None:
    if not series:
        return
    value = series[-1]
    if value is not None:
        values[feature_name] = value.quantize(FEATURE_VALUE)


def _window_set(values: set[int] | None, *, default: set[int]) -> set[int]:
    return set(default if values is None else values)


def _technical_feature_version(strategy_parameters: dict[str, object]) -> str:
    nested = strategy_parameters.get("technical_features")
    if isinstance(nested, dict):
        value = nested.get("feature_version") or nested.get("technical_feature_version")
        if isinstance(value, str) and value:
            return value
    value = strategy_parameters.get(
        "technical_feature_version"
    ) or strategy_parameters.get("feature_version")
    if isinstance(value, str) and value:
        return value
    return TECHNICAL_FEATURE_VERSION


def _add_strategy_sma_windows(
    sma_windows: set[int],
    strategy_parameters: dict[str, object],
) -> None:
    for key in ("fast_window", "slow_window"):
        value = strategy_parameters.get(key)
        if isinstance(value, int):
            sma_windows.add(value)


def _snapshot_id(
    *,
    symbol: str,
    as_of_date: date,
    feature_time: date,
    feature_version: str,
    values: dict[str, Decimal],
) -> str:
    payload = {
        "symbol": symbol.upper(),
        "as_of_date": as_of_date.isoformat(),
        "feature_time": feature_time.isoformat(),
        "feature_version": feature_version,
        "values": {name: str(value) for name, value in sorted(values.items())},
    }
    digest = hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return f"fs-{digest[:16]}"
