from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
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

FEATURE_VALUE = Decimal("0.00000001")
TECHNICAL_FEATURE_VERSION = "technical_v1"


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
        feature_version: str = TECHNICAL_FEATURE_VERSION,
    ) -> None:
        self.sma_windows = sma_windows or {5, 10, 20, 30, 50}
        self.ema_windows = ema_windows or {12, 26}
        self.return_windows = return_windows or {1, 5, 20}
        self.rsi_windows = rsi_windows or {14}
        self.atr_windows = atr_windows or {14}
        self.volatility_windows = volatility_windows or {20}
        self.volume_z_windows = volume_z_windows or {20}
        self.feature_version = feature_version

    @classmethod
    def from_strategy_parameters(
        cls,
        strategy_parameters: dict[str, object],
    ) -> TechnicalFeatureService:
        sma_windows = {5, 10, 20, 30, 50}
        for key in ("fast_window", "slow_window"):
            value = strategy_parameters.get(key)
            if isinstance(value, int):
                sma_windows.add(value)
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
            _add_latest(values, f"ema_{window}", exponential_moving_average(closes, window))
        for window in sorted(self.return_windows):
            series = returns_1d if window == 1 else period_returns(closes, period=window)
            _add_latest(values, f"return_{window}d", series)
        for window in sorted(self.rsi_windows):
            _add_latest(values, f"rsi_{window}", relative_strength_index(closes, window))
        for window in sorted(self.atr_windows):
            _add_latest(values, f"atr_{window}", average_true_range(ordered_history, window))
        for window in sorted(self.volatility_windows):
            _add_latest(values, f"volatility_{window}", rolling_volatility(returns_1d, window))
        for window in sorted(self.volume_z_windows):
            _add_latest(values, f"volume_z_score_{window}", volume_z_score(volumes, window))

        snapshot_id = _snapshot_id(
            symbol=symbol,
            as_of_date=as_of_date,
            feature_time=feature_time,
            feature_version=self.feature_version,
            values=values,
        )
        data_available_time = datetime.combine(as_of_date, time.min, tzinfo=timezone.utc)
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
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
    return f"fs-{digest[:16]}"
