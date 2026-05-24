from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from taurus_core import __version__
from taurus_core.agents.roster import DEFAULT_ENABLED_ANALYSTS, parse_enabled_analysts


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    service_name: str = "taurus-api"
    service_version: str = __version__

    taurus_env: str = Field(default="local", validation_alias="TAURUS_ENV")
    taurus_mode: str = Field(default="paper", validation_alias="TAURUS_MODE")
    live_trading_enabled: bool = Field(
        default=False,
        validation_alias="LIVE_TRADING_ENABLED",
    )
    broker_provider: str = Field(default="paper", validation_alias="BROKER_PROVIDER")
    database_url: str = Field(
        default="sqlite:///./taurus.db",
        validation_alias="DATABASE_URL",
    )

    taurus_universe: str = Field(default="NIFTY_100", validation_alias="TAURUS_UNIVERSE")
    taurus_timeframe: str = Field(default="1d", validation_alias="TAURUS_TIMEFRAME")
    taurus_market_data_provider: str = Field(
        default="mock",
        validation_alias="TAURUS_MARKET_DATA_PROVIDER",
    )
    taurus_market_data_universe_path: str = Field(
        default="configs/market_data/kite_nse_cash.yaml",
        validation_alias="TAURUS_MARKET_DATA_UNIVERSE_PATH",
    )
    taurus_halal_stock_source_url: str = Field(
        default="https://halalstock.in/halal-shariah-compliant-shares-list/",
        validation_alias="TAURUS_HALAL_STOCK_SOURCE_URL",
    )
    taurus_halal_stock_table_id: str = Field(
        default="tablepress-24",
        validation_alias="TAURUS_HALAL_STOCK_TABLE_ID",
    )
    taurus_halal_stock_universe_path: str = Field(
        default="configs/market_data/halal_nse_cash.yaml",
        validation_alias="TAURUS_HALAL_STOCK_UNIVERSE_PATH",
    )
    taurus_halal_stock_min_rows: int = Field(
        default=5000,
        ge=1,
        validation_alias="TAURUS_HALAL_STOCK_MIN_ROWS",
    )
    taurus_market_data_lookback_days: int = Field(
        default=400,
        ge=1,
        validation_alias="TAURUS_MARKET_DATA_LOOKBACK_DAYS",
    )
    taurus_price_csv_path: str = Field(default="", validation_alias="TAURUS_PRICE_CSV_PATH")
    taurus_price_csv_dir: str = Field(default="", validation_alias="TAURUS_PRICE_CSV_DIR")
    taurus_mock_seed: int = Field(default=42, validation_alias="TAURUS_MOCK_SEED")
    taurus_mock_candle_count: int = Field(
        default=252,
        ge=252,
        validation_alias="TAURUS_MOCK_CANDLE_COUNT",
    )
    taurus_initial_capital_inr: int = Field(
        default=1_000_000,
        gt=0,
        validation_alias="TAURUS_INITIAL_CAPITAL_INR",
    )
    taurus_max_position_pct: int = Field(
        default=5,
        gt=0,
        le=100,
        validation_alias="TAURUS_MAX_POSITION_PCT",
    )
    taurus_max_open_positions: int = Field(
        default=8,
        gt=0,
        validation_alias="TAURUS_MAX_OPEN_POSITIONS",
    )
    taurus_kill_switch_enabled: bool = Field(
        default=False,
        validation_alias="TAURUS_KILL_SWITCH_ENABLED",
    )
    taurus_max_daily_loss_pct: Decimal = Field(
        default=Decimal("3.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
        validation_alias="TAURUS_MAX_DAILY_LOSS_PCT",
    )
    taurus_paper_slippage_bps: Decimal = Field(
        default=Decimal("5.0"),
        ge=Decimal("0"),
        validation_alias="TAURUS_PAPER_SLIPPAGE_BPS",
    )
    taurus_paper_brokerage_bps: Decimal = Field(
        default=Decimal("3.0"),
        ge=Decimal("0"),
        validation_alias="TAURUS_PAPER_BROKERAGE_BPS",
    )
    taurus_paper_exchange_txn_charge_bps: Decimal = Field(
        default=Decimal("0.35"),
        ge=Decimal("0"),
        validation_alias="TAURUS_PAPER_EXCHANGE_TXN_CHARGE_BPS",
    )
    taurus_paper_tax_levy_bps: Decimal = Field(
        default=Decimal("1.0"),
        ge=Decimal("0"),
        validation_alias="TAURUS_PAPER_TAX_LEVY_BPS",
    )
    taurus_paper_partial_fill_threshold: int = Field(
        default=50,
        ge=1,
        validation_alias="TAURUS_PAPER_PARTIAL_FILL_THRESHOLD",
    )
    taurus_paper_first_fill_pct: Decimal = Field(
        default=Decimal("0.60"),
        gt=Decimal("0"),
        lt=Decimal("1"),
        validation_alias="TAURUS_PAPER_FIRST_FILL_PCT",
    )
    taurus_paper_timezone: str = Field(
        default="Asia/Kolkata",
        validation_alias="TAURUS_PAPER_TIMEZONE",
    )
    taurus_paper_after_market_close: bool = Field(
        default=True,
        validation_alias="TAURUS_PAPER_AFTER_MARKET_CLOSE",
    )
    taurus_paper_schedule: str = Field(
        default="daily_after_close",
        validation_alias="TAURUS_PAPER_SCHEDULE",
    )

    taurus_llm_provider: str = Field(default="mock", validation_alias="TAURUS_LLM_PROVIDER")
    taurus_llm_base_url: str = Field(default="", validation_alias="TAURUS_LLM_BASE_URL")
    taurus_alert_provider: str = Field(default="mock", validation_alias="TAURUS_ALERT_PROVIDER")
    taurus_enabled_analysts: str = Field(
        default=DEFAULT_ENABLED_ANALYSTS,
        validation_alias="TAURUS_ENABLED_ANALYSTS",
    )
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    telegram_bot_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")
    kite_api_key: str = Field(default="", validation_alias="KITE_API_KEY")
    kite_api_secret: str = Field(default="", validation_alias="KITE_API_SECRET")
    kite_access_token: str = Field(default="", validation_alias="KITE_ACCESS_TOKEN")
    taurus_kite_exchange: str = Field(default="NSE", validation_alias="TAURUS_KITE_EXCHANGE")
    upstox_client_id: str = Field(default="", validation_alias="UPSTOX_CLIENT_ID")
    upstox_client_secret: str = Field(default="", validation_alias="UPSTOX_CLIENT_SECRET")
    upstox_redirect_uri: str = Field(default="", validation_alias="UPSTOX_REDIRECT_URI")

    @model_validator(mode="after")
    def enforce_trading_safety(self) -> Settings:
        if self.taurus_mode not in {"paper", "backtest"}:
            raise ValueError("Taurus currently supports only paper or backtest modes.")
        if self.live_trading_enabled:
            raise ValueError("Live trading is disabled and cannot be enabled.")
        if self.broker_provider != "paper":
            raise ValueError("Taurus currently supports only the paper broker provider.")
        if self.taurus_market_data_provider not in {"mock", "csv", "kite", "external"}:
            raise ValueError("Unsupported Taurus market data provider.")
        if self.taurus_llm_provider not in {"mock", "lmstudio", "openai"}:
            raise ValueError("Unsupported Taurus LLM provider.")
        if self.taurus_alert_provider not in {"mock", "telegram", "disabled"}:
            raise ValueError("Unsupported Taurus alert provider.")
        parse_enabled_analysts(self.taurus_enabled_analysts)
        return self

    @property
    def enabled_analyst_keys(self) -> tuple[str, ...]:
        return parse_enabled_analysts(self.taurus_enabled_analysts)

    def safe_dict(self) -> dict[str, Any]:
        redacted = self.model_dump()
        for key in (
            "openai_api_key",
            "telegram_bot_token",
            "telegram_chat_id",
            "kite_api_key",
            "kite_api_secret",
            "kite_access_token",
            "upstox_client_id",
            "upstox_client_secret",
            "upstox_redirect_uri",
        ):
            if redacted.get(key):
                redacted[key] = "***REDACTED***"
        redacted["database_url"] = _redact_url_password(self.database_url)
        return redacted


def _redact_url_password(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.password is None:
        return value
    username = parsed.username or ""
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    userinfo = f"{username}:***REDACTED***@" if username else ""
    return urlunsplit(
        (
            parsed.scheme,
            f"{userinfo}{hostname}{port}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError:
        raise
