from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from taurus_core import __version__


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
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

    taurus_universe: str = Field(default="NIFTY_100", validation_alias="TAURUS_UNIVERSE")
    taurus_timeframe: str = Field(default="1d", validation_alias="TAURUS_TIMEFRAME")
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

    taurus_llm_provider: str = Field(default="mock", validation_alias="TAURUS_LLM_PROVIDER")
    taurus_llm_base_url: str = Field(default="", validation_alias="TAURUS_LLM_BASE_URL")
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    telegram_bot_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")
    upstox_client_id: str = Field(default="", validation_alias="UPSTOX_CLIENT_ID")
    upstox_client_secret: str = Field(default="", validation_alias="UPSTOX_CLIENT_SECRET")
    upstox_redirect_uri: str = Field(default="", validation_alias="UPSTOX_REDIRECT_URI")

    @model_validator(mode="after")
    def enforce_m0_safety(self) -> Settings:
        if self.taurus_mode not in {"paper", "backtest"}:
            raise ValueError("M0 supports only paper or backtest modes.")
        if self.live_trading_enabled:
            raise ValueError("Live trading is disabled in M0 and cannot be enabled.")
        if self.broker_provider != "paper":
            raise ValueError("M0 supports only the paper broker provider.")
        if self.taurus_llm_provider not in {"mock", "lmstudio", "openai"}:
            raise ValueError("Unsupported Taurus LLM provider.")
        return self

    def safe_dict(self) -> dict[str, Any]:
        redacted = self.model_dump()
        for key in (
            "openai_api_key",
            "telegram_bot_token",
            "telegram_chat_id",
            "upstox_client_id",
            "upstox_client_secret",
            "upstox_redirect_uri",
        ):
            if redacted.get(key):
                redacted[key] = "***REDACTED***"
        return redacted


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError:
        raise
