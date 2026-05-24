from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time as dt_time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from sqlalchemy.orm import Session

from taurus_core.config import Settings
from taurus_core.data.universe import MarketDataUniverse, UniverseSymbol, load_market_data_universe
from taurus_core.db.repositories import InstrumentProviderMappingRepository, InstrumentRepository
from taurus_core.domain.instruments import Instrument
from taurus_core.domain.market_data import DailyCandle, MarketDataProviderError, MarketPriceSnapshot


class KiteClientProtocol(Protocol):
    def instruments(self, exchange: str | None = None) -> list[dict[str, Any]]:
        ...

    def historical_data(
        self,
        instrument_token: int | str,
        from_date: date,
        to_date: date,
        interval: str,
        continuous: bool = False,
        oi: bool = False,
    ) -> list[dict[str, Any]]:
        ...

    def ohlc(self, *instruments: Any) -> dict[str, dict[str, Any]]:
        ...


@dataclass(frozen=True, slots=True)
class ResolvedKiteInstrument:
    universe_symbol: UniverseSymbol
    exchange: str
    tradingsymbol: str
    instrument_token: str
    name: str
    segment: str
    currency: str
    lot_size: int
    tick_size: Decimal
    raw: dict[str, Any]

    @property
    def provider_key(self) -> str:
        return f"{self.exchange}:{self.tradingsymbol}"

    def to_instrument(self) -> Instrument:
        return Instrument(
            symbol=self.universe_symbol.symbol,
            name=self.name,
            exchange=self.exchange,
            segment=self.universe_symbol.segment,
            currency=self.currency,
            lot_size=self.lot_size,
            tick_size=self.tick_size,
            active=True,
        )


@dataclass(frozen=True, slots=True)
class KiteInstrumentSyncSummary:
    provider_name: str
    universe_path: str
    instrument_count: int
    symbols: list[str]


class KiteMarketDataProvider:
    provider_name = "kite"

    def __init__(
        self,
        settings: Settings,
        *,
        client: KiteClientProtocol | None = None,
        universe: MarketDataUniverse | None = None,
        sleep_func: Callable[[float], None] = time.sleep,
        request_interval_seconds: float = 0.2,
        max_retries: int = 2,
        retry_delay_seconds: float = 0.5,
        quote_chunk_size: int = 1000,
    ) -> None:
        self.settings = settings
        self.universe = universe or load_market_data_universe(settings.taurus_market_data_universe_path)
        self.sleep_func = sleep_func
        self.request_interval_seconds = request_interval_seconds
        self.max_retries = max_retries
        self.retry_delay_seconds = retry_delay_seconds
        self.quote_chunk_size = quote_chunk_size
        self._client = client or _build_kite_client(settings)
        self._instrument_master: list[dict[str, Any]] | None = None
        self._resolved: dict[str, ResolvedKiteInstrument] | None = None

    @property
    def source(self) -> str:
        return f"kite_market_data:{self.universe.source_path}"

    def list_instruments(self) -> list[Instrument]:
        resolved = self._resolve_enabled_instruments()
        return [resolved[symbol].to_instrument() for symbol in sorted(resolved)]

    def get_daily_candles(self, symbol: str) -> list[DailyCandle]:
        return self.get_historical_candles(symbol)

    def get_historical_candles(
        self,
        symbol: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> list[DailyCandle]:
        instrument = self._resolve_symbol(symbol)
        to_date = end_date or datetime.now(timezone.utc).date()
        from_date = start_date or to_date - timedelta(days=self.settings.taurus_market_data_lookback_days)
        rows = self._call_with_retries(
            lambda: self._client.historical_data(
                instrument.instrument_token,
                from_date,
                to_date,
                "day",
            ),
            action=f"fetch Kite historical candles for {instrument.universe_symbol.symbol}",
        )
        if not rows:
            raise MarketDataProviderError(
                f"Kite returned no historical daily candles for {instrument.universe_symbol.symbol} "
                f"({instrument.provider_key}) from {from_date.isoformat()} to {to_date.isoformat()}."
            )
        candles = [
            _historical_row_to_candle(row, instrument)
            for row in rows
        ]
        return sorted(candles, key=lambda item: item.trade_date)

    def get_latest_candle(self, symbol: str) -> DailyCandle | None:
        candles = self.get_daily_candles(symbol)
        return candles[-1] if candles else None

    def get_latest_snapshots(self, symbols: list[str]) -> list[MarketPriceSnapshot]:
        normalized_symbols = _normalize_symbols(symbols)
        if not normalized_symbols:
            return []
        resolved = [self._resolve_symbol(symbol) for symbol in normalized_symbols]
        fetched_at = datetime.now(timezone.utc)
        snapshots: list[MarketPriceSnapshot] = []
        for chunk in _chunks(resolved, self.quote_chunk_size):
            keys = [instrument.provider_key for instrument in chunk]
            response = self._call_with_retries(
                lambda keys=keys: self._client.ohlc(keys),
                action=f"fetch Kite OHLC quotes for {len(keys)} instruments",
            )
            missing_keys = [key for key in keys if key not in response]
            if missing_keys:
                raise MarketDataProviderError(
                    "Kite OHLC response omitted requested instruments: "
                    f"{', '.join(missing_keys)}"
                )
            snapshots.extend(
                _ohlc_row_to_snapshot(
                    response[instrument.provider_key],
                    instrument,
                    fetched_at=fetched_at,
                )
                for instrument in chunk
            )
            self._pace_request()
        return snapshots

    def sync_instruments(self, session: Session) -> KiteInstrumentSyncSummary:
        instrument_repo = InstrumentRepository(session)
        mapping_repo = InstrumentProviderMappingRepository(session)
        resolved = self._resolve_enabled_instruments()
        synced_at = datetime.now(timezone.utc)
        for symbol in sorted(resolved):
            instrument = resolved[symbol]
            instrument_repo.upsert(instrument.to_instrument())
            mapping_repo.upsert(
                provider=self.provider_name,
                symbol=instrument.universe_symbol.symbol,
                exchange=instrument.exchange,
                provider_symbol=instrument.tradingsymbol,
                instrument_token=instrument.instrument_token,
                segment=instrument.segment,
                currency=instrument.currency,
                lot_size=instrument.lot_size,
                tick_size=instrument.tick_size,
                active=True,
                raw=instrument.raw,
                synced_at=synced_at,
            )
        session.commit()
        return KiteInstrumentSyncSummary(
            provider_name=self.provider_name,
            universe_path=str(self.universe.source_path),
            instrument_count=len(resolved),
            symbols=sorted(resolved),
        )

    def _resolve_symbol(self, symbol: str) -> ResolvedKiteInstrument:
        normalized_symbol = symbol.upper()
        resolved = self._resolve_enabled_instruments()
        if normalized_symbol not in resolved:
            raise MarketDataProviderError(
                f"Symbol {normalized_symbol} is not enabled in Kite universe "
                f"{self.universe.source_path}."
            )
        return resolved[normalized_symbol]

    def _resolve_enabled_instruments(self) -> dict[str, ResolvedKiteInstrument]:
        if self._resolved is not None:
            return self._resolved

        index = {
            (
                str(row.get("exchange") or "").upper(),
                str(row.get("tradingsymbol") or "").upper(),
            ): row
            for row in self._load_instrument_master()
        }
        resolved: dict[str, ResolvedKiteInstrument] = {}
        missing: list[str] = []
        for entry in self.universe.symbols:
            exchange = (
                entry.provider_value("kite", "exchange", entry.exchange)
                or self.settings.taurus_kite_exchange
            ).upper()
            tradingsymbol = entry.provider_value("kite", "tradingsymbol", entry.symbol) or entry.symbol
            record = index.get((exchange, tradingsymbol.upper()))
            if record is None:
                missing.append(f"{entry.symbol} ({exchange}:{tradingsymbol})")
                continue
            resolved[entry.symbol] = _record_to_resolved_instrument(
                entry=entry,
                exchange=exchange,
                tradingsymbol=tradingsymbol,
                record=record,
            )

        if missing:
            raise MarketDataProviderError(
                "Kite instrument master did not contain enabled universe symbols: "
                f"{', '.join(missing)}"
            )
        self._resolved = resolved
        return resolved

    def _load_instrument_master(self) -> list[dict[str, Any]]:
        if self._instrument_master is None:
            exchange = self.settings.taurus_kite_exchange.upper()
            self._instrument_master = self._call_with_retries(
                lambda: self._client.instruments(exchange),
                action=f"fetch Kite instrument master for {exchange}",
            )
            self._pace_request()
        return self._instrument_master

    def _call_with_retries(self, operation: Callable[[], Any], *, action: str) -> Any:
        attempts = max(self.max_retries, 0) + 1
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                return operation()
            except Exception as exc:  # noqa: BLE001 - vendor client raises typed runtime errors.
                if isinstance(exc, MarketDataProviderError):
                    raise
                last_error = exc
                if _is_permanent_kite_error(exc) or attempt >= attempts:
                    raise _kite_provider_error(action, exc) from exc
                self.sleep_func(self.retry_delay_seconds)
        assert last_error is not None
        raise _kite_provider_error(action, last_error)

    def _pace_request(self) -> None:
        if self.request_interval_seconds > 0:
            self.sleep_func(self.request_interval_seconds)


def _build_kite_client(settings: Settings) -> KiteClientProtocol:
    if not settings.kite_api_key or not settings.kite_access_token:
        raise MarketDataProviderError(
            "Kite market data requires KITE_API_KEY and KITE_ACCESS_TOKEN in local "
            "environment before use. Generate a fresh Kite access token locally and "
            "store it in .env; do not commit credentials."
        )
    try:
        from kiteconnect import KiteConnect
    except ImportError as exc:  # pragma: no cover - dependency is locked in pyproject.
        raise MarketDataProviderError("kiteconnect is not installed. Run `uv sync`.") from exc
    return KiteConnect(api_key=settings.kite_api_key, access_token=settings.kite_access_token)


def _record_to_resolved_instrument(
    *,
    entry: UniverseSymbol,
    exchange: str,
    tradingsymbol: str,
    record: dict[str, Any],
) -> ResolvedKiteInstrument:
    token = record.get("instrument_token")
    if token is None:
        raise MarketDataProviderError(f"Kite instrument {exchange}:{tradingsymbol} has no token.")
    name = str(record.get("name") or entry.name or f"{entry.symbol} Equity").strip()
    return ResolvedKiteInstrument(
        universe_symbol=entry,
        exchange=exchange.upper(),
        tradingsymbol=tradingsymbol,
        instrument_token=str(token),
        name=name,
        segment=str(record.get("segment") or entry.segment),
        currency=str(record.get("currency") or "INR"),
        lot_size=_to_int(record.get("lot_size"), default=1),
        tick_size=_to_decimal(record.get("tick_size"), field="tick_size", default=Decimal("0.05")),
        raw=dict(record),
    )


def _historical_row_to_candle(
    row: dict[str, Any],
    instrument: ResolvedKiteInstrument,
) -> DailyCandle:
    trade_date = _parse_trade_date(row.get("date"))
    return DailyCandle(
        symbol=instrument.universe_symbol.symbol,
        trade_date=trade_date,
        open=_to_decimal(row.get("open"), field="open"),
        high=_to_decimal(row.get("high"), field="high"),
        low=_to_decimal(row.get("low"), field="low"),
        close=_to_decimal(row.get("close"), field="close"),
        volume=_to_int(row.get("volume"), default=0),
        timeframe="1d",
        source=f"kite:historical:{instrument.exchange}",
        data_available_time=datetime.combine(trade_date, dt_time(18, 0), tzinfo=timezone.utc),
    )


def _ohlc_row_to_snapshot(
    row: dict[str, Any],
    instrument: ResolvedKiteInstrument,
    *,
    fetched_at: datetime,
) -> MarketPriceSnapshot:
    ohlc = row.get("ohlc")
    if not isinstance(ohlc, dict):
        raise MarketDataProviderError(f"Kite OHLC response for {instrument.provider_key} has no ohlc object.")
    return MarketPriceSnapshot(
        symbol=instrument.universe_symbol.symbol,
        provider="kite",
        exchange=instrument.exchange,
        provider_symbol=instrument.tradingsymbol,
        instrument_token=str(row.get("instrument_token") or instrument.instrument_token),
        last_price=_to_decimal(row.get("last_price"), field="last_price"),
        open=_to_decimal(ohlc.get("open"), field="ohlc.open"),
        high=_to_decimal(ohlc.get("high"), field="ohlc.high"),
        low=_to_decimal(ohlc.get("low"), field="ohlc.low"),
        close=_to_decimal(ohlc.get("close"), field="ohlc.close"),
        volume=_optional_int(row.get("volume")),
        fetched_at=fetched_at,
        source=f"kite:quote:{instrument.exchange}",
        raw={"provider_key": instrument.provider_key, "payload": dict(row)},
    )


def _parse_trade_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if value is None:
        raise MarketDataProviderError("Kite historical candle row is missing date.")
    text = str(value).strip()
    try:
        return date.fromisoformat(text[:10])
    except ValueError as exc:
        raise MarketDataProviderError(f"Invalid Kite historical candle date: {text}") from exc


def _to_decimal(value: object, *, field: str, default: Decimal | None = None) -> Decimal:
    if value is None:
        if default is not None:
            return default
        raise MarketDataProviderError(f"Kite response is missing {field}.")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise MarketDataProviderError(f"Invalid Kite decimal field {field}: {value}") from exc


def _to_int(value: object, *, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _normalize_symbols(symbols: Sequence[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        item = symbol.strip().upper()
        if item and item not in seen:
            seen.add(item)
            normalized.append(item)
    return normalized


def _chunks(items: Sequence[ResolvedKiteInstrument], size: int) -> list[Sequence[ResolvedKiteInstrument]]:
    chunk_size = max(size, 1)
    return [items[index : index + chunk_size] for index in range(0, len(items), chunk_size)]


def _is_permanent_kite_error(exc: Exception) -> bool:
    return exc.__class__.__name__ in {
        "InputException",
        "PermissionException",
        "TokenException",
    }


def _kite_provider_error(action: str, exc: Exception) -> MarketDataProviderError:
    name = exc.__class__.__name__
    if name == "TokenException":
        detail = "Kite access token is invalid or expired; generate a fresh access token and update .env."
    else:
        detail = str(exc) or name
    return MarketDataProviderError(f"Could not {action}: {detail}")
