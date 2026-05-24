from __future__ import annotations

import csv
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle, MarketDataProviderError, MarketPriceSnapshot


@dataclass(frozen=True, slots=True)
class CSVColumnMapping:
    symbol: str
    trade_date: str
    open: str
    high: str
    low: str
    close: str
    volume: str
    name: str | None = None
    exchange: str | None = None
    source: str | None = None
    data_available_time: str | None = None


class CSVMarketDataProvider:
    """Market data provider for user-supplied historical OHLCV CSV files."""

    def __init__(
        self,
        *,
        csv_path: str | Path | None = None,
        directory: str | Path | None = None,
        source_name: str | None = None,
    ) -> None:
        self._paths = _resolve_paths(csv_path=csv_path, directory=directory)
        self._source = source_name or "csv_market_data"
        self._instruments: dict[str, Instrument] = {}
        self._candles_by_symbol: dict[str, list[DailyCandle]] = defaultdict(list)
        self._load()

    @property
    def provider_name(self) -> str:
        return "csv"

    @property
    def source(self) -> str:
        return self._source

    def list_instruments(self) -> list[Instrument]:
        return [self._instruments[symbol] for symbol in sorted(self._instruments)]

    def get_daily_candles(self, symbol: str) -> list[DailyCandle]:
        return list(self._candles_by_symbol.get(symbol.upper(), []))

    def get_historical_candles(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyCandle]:
        candles = self.get_daily_candles(symbol)
        if start_date is not None:
            candles = [candle for candle in candles if candle.trade_date >= start_date]
        if end_date is not None:
            candles = [candle for candle in candles if candle.trade_date <= end_date]
        return candles

    def get_latest_candle(self, symbol: str) -> DailyCandle | None:
        candles = self.get_daily_candles(symbol)
        return candles[-1] if candles else None

    def get_latest_snapshots(self, symbols: list[str]) -> list[MarketPriceSnapshot]:
        snapshots: list[MarketPriceSnapshot] = []
        for symbol in symbols:
            normalized_symbol = symbol.upper()
            candle = self.get_latest_candle(normalized_symbol)
            instrument = self._instruments.get(normalized_symbol)
            if candle is None or instrument is None:
                continue
            snapshots.append(
                MarketPriceSnapshot(
                    symbol=normalized_symbol,
                    provider=self.provider_name,
                    exchange=instrument.exchange,
                    provider_symbol=normalized_symbol,
                    instrument_token=None,
                    last_price=candle.close,
                    open=candle.open,
                    high=candle.high,
                    low=candle.low,
                    close=candle.close,
                    volume=candle.volume,
                    fetched_at=candle.data_available_time
                    or datetime.combine(candle.trade_date, time(18, 0), tzinfo=timezone.utc),
                    source=f"{candle.source}:latest_candle",
                    raw=None,
                )
            )
        return snapshots

    def _load(self) -> None:
        for path in self._paths:
            self._load_file(path)

        for symbol, candles in self._candles_by_symbol.items():
            deduped = {
                (candle.timeframe, candle.trade_date): candle
                for candle in sorted(candles, key=lambda item: item.trade_date)
            }
            self._candles_by_symbol[symbol] = [
                deduped[key] for key in sorted(deduped, key=lambda item: item[1])
            ]

    def _load_file(self, path: Path) -> None:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if reader.fieldnames is None:
                raise MarketDataProviderError(f"Price CSV has no header row: {path}")

            mapping = _build_column_mapping(reader.fieldnames, path)
            for row_number, row in enumerate(reader, start=2):
                if not any((value or "").strip() for value in row.values()):
                    continue
                candle = _row_to_candle(row, mapping, path, row_number, self._source)
                instrument = _row_to_instrument(row, mapping, candle.symbol)
                self._instruments.setdefault(candle.symbol, instrument)
                self._candles_by_symbol[candle.symbol].append(candle)


class DisabledExternalMarketDataProvider:
    """Placeholder for future vendor or broker data integrations."""

    provider_name = "external"
    source = "external_market_data_disabled"

    def __init__(self, *, reason: str | None = None) -> None:
        self.reason = reason or (
            "External market data is disabled until a provider is selected and "
            "credentials are configured through environment variables."
        )

    def list_instruments(self) -> list[Instrument]:
        raise MarketDataProviderError(self.reason)

    def get_daily_candles(self, symbol: str) -> list[DailyCandle]:
        raise MarketDataProviderError(self.reason)

    def get_historical_candles(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyCandle]:
        raise MarketDataProviderError(self.reason)

    def get_latest_candle(self, symbol: str) -> DailyCandle | None:
        raise MarketDataProviderError(self.reason)


def _resolve_paths(
    *,
    csv_path: str | Path | None,
    directory: str | Path | None,
) -> list[Path]:
    if csv_path is None and directory is None:
        raise MarketDataProviderError("CSV price import requires CSV=/path/to/prices.csv or DIR=/path.")

    paths: list[Path] = []
    if csv_path is not None and str(csv_path).strip():
        path = Path(csv_path).expanduser()
        if not path.exists():
            raise MarketDataProviderError(f"Price CSV file not found: {path}")
        if not path.is_file():
            raise MarketDataProviderError(f"Price CSV path is not a file: {path}")
        paths.append(path)

    if directory is not None and str(directory).strip():
        folder = Path(directory).expanduser()
        if not folder.exists():
            raise MarketDataProviderError(f"Price CSV directory not found: {folder}")
        if not folder.is_dir():
            raise MarketDataProviderError(f"Price CSV DIR is not a directory: {folder}")
        paths.extend(sorted(folder.glob("*.csv")))

    if not paths:
        raise MarketDataProviderError("No price CSV files found.")
    return paths


def _build_column_mapping(fieldnames: Iterable[str], path: Path) -> CSVColumnMapping:
    normalized = {_normalize_column(name): name for name in fieldnames}

    def required(canonical: str, aliases: tuple[str, ...]) -> str:
        for alias in aliases:
            if alias in normalized:
                return normalized[alias]
        expected = ", ".join(sorted(aliases))
        raise MarketDataProviderError(
            f"Price CSV {path} is missing required column for {canonical}. "
            f"Accepted names include: {expected}"
        )

    def optional(aliases: tuple[str, ...]) -> str | None:
        for alias in aliases:
            if alias in normalized:
                return normalized[alias]
        return None

    return CSVColumnMapping(
        symbol=required("symbol", ("symbol", "ticker", "tradingsymbol", "instrument")),
        trade_date=required("date", ("date", "trade_date", "datetime", "timestamp")),
        open=required("open", ("open", "open_price", "openprice", "o")),
        high=required("high", ("high", "high_price", "highprice", "h")),
        low=required("low", ("low", "low_price", "lowprice", "l")),
        close=required("close", ("close", "close_price", "closeprice", "c", "adj_close")),
        volume=required("volume", ("volume", "vol", "traded_quantity", "qty")),
        name=optional(("name", "company", "company_name", "instrument_name")),
        exchange=optional(("exchange", "market")),
        source=optional(("source", "provider", "data_source")),
        data_available_time=optional(
            ("data_available_time", "available_at", "data_available_at", "as_of", "asof")
        ),
    )


def _row_to_instrument(
    row: dict[str, str],
    mapping: CSVColumnMapping,
    symbol: str,
) -> Instrument:
    name = _optional_value(row, mapping.name) or f"{symbol} Equity"
    exchange = _optional_value(row, mapping.exchange) or "NSE"
    return Instrument(symbol=symbol, name=name, exchange=exchange)


def _row_to_candle(
    row: dict[str, str],
    mapping: CSVColumnMapping,
    path: Path,
    row_number: int,
    default_source: str,
) -> DailyCandle:
    symbol = _required_value(row, mapping.symbol, path, row_number).upper()
    trade_date = _parse_date(_required_value(row, mapping.trade_date, path, row_number), path, row_number)
    open_price = _parse_decimal(row, mapping.open, path, row_number)
    high_price = _parse_decimal(row, mapping.high, path, row_number)
    low_price = _parse_decimal(row, mapping.low, path, row_number)
    close_price = _parse_decimal(row, mapping.close, path, row_number)
    volume = _parse_volume(row, mapping.volume, path, row_number)

    if low_price > min(open_price, close_price) or high_price < max(open_price, close_price):
        raise MarketDataProviderError(
            f"Invalid OHLC range in {path} row {row_number}: high/low do not contain open/close."
        )

    source = _optional_value(row, mapping.source) or f"{default_source}:{path.name}"
    available_value = _optional_value(row, mapping.data_available_time)
    data_available_time = (
        _parse_datetime(available_value, path, row_number)
        if available_value is not None
        else datetime.combine(trade_date, time(18, 0), tzinfo=timezone.utc)
    )

    return DailyCandle(
        symbol=symbol,
        trade_date=trade_date,
        open=open_price,
        high=high_price,
        low=low_price,
        close=close_price,
        volume=volume,
        source=source,
        data_available_time=data_available_time,
    )


def _required_value(
    row: dict[str, str],
    column: str,
    path: Path,
    row_number: int,
) -> str:
    value = (row.get(column) or "").strip()
    if not value:
        raise MarketDataProviderError(f"Price CSV {path} row {row_number} has empty {column}.")
    return value


def _optional_value(row: dict[str, str], column: str | None) -> str | None:
    if column is None:
        return None
    value = (row.get(column) or "").strip()
    return value or None


def _parse_date(value: str, path: Path, row_number: int) -> date:
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        raise MarketDataProviderError(
            f"Invalid date in {path} row {row_number}: {value!r}. Use YYYY-MM-DD."
        ) from exc


def _parse_datetime(value: str, path: Path, row_number: int) -> datetime:
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise MarketDataProviderError(
            f"Invalid data_available_time in {path} row {row_number}: {value!r}."
        ) from exc
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_decimal(
    row: dict[str, str],
    column: str,
    path: Path,
    row_number: int,
) -> Decimal:
    raw = _required_value(row, column, path, row_number).replace(",", "")
    try:
        return Decimal(raw)
    except InvalidOperation as exc:
        raise MarketDataProviderError(
            f"Invalid decimal in {path} row {row_number} column {column}: {raw!r}."
        ) from exc


def _parse_volume(
    row: dict[str, str],
    column: str,
    path: Path,
    row_number: int,
) -> int:
    raw = _required_value(row, column, path, row_number).replace(",", "")
    try:
        volume = int(Decimal(raw))
    except InvalidOperation as exc:
        raise MarketDataProviderError(
            f"Invalid volume in {path} row {row_number}: {raw!r}."
        ) from exc
    if volume < 0:
        raise MarketDataProviderError(f"Invalid negative volume in {path} row {row_number}.")
    return volume


def _normalize_column(value: str) -> str:
    return value.strip().lower().replace(" ", "_").replace("-", "_")
