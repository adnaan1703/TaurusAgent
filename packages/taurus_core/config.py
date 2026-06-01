from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from pydantic import Field, ValidationError, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from taurus_core import __version__
from taurus_core.agents.roster import DEFAULT_ENABLED_ANALYSTS, parse_enabled_analysts


DEFAULT_DATABASE_URL = "postgresql+psycopg://taurus:taurus@localhost:5432/taurus"
DEFAULT_LMSTUDIO_BASE_URL = "http://localhost:1234/v1"
DEFAULT_LMSTUDIO_MODEL = "local-model"
DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5-mini"
DEFAULT_GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"
SUPPORTED_LLM_PROVIDERS = ("lmstudio", "openai", "gemini")
SUPPORTED_MARKET_DATA_PROVIDERS = ("kite",)


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
        default=DEFAULT_DATABASE_URL,
        validation_alias="DATABASE_URL",
    )
    taurus_graph_enabled: bool = Field(
        default=False,
        validation_alias="TAURUS_GRAPH_ENABLED",
    )
    taurus_graph_risk_enabled: bool = Field(
        default=False,
        validation_alias="TAURUS_GRAPH_RISK_ENABLED",
    )
    taurus_graph_auto_promote_edges: bool = Field(
        default=False,
        validation_alias="TAURUS_GRAPH_AUTO_PROMOTE_EDGES",
    )
    taurus_graph_stats_windows: str = Field(
        default="60,120,252",
        validation_alias="TAURUS_GRAPH_STATS_WINDOWS",
    )
    taurus_graph_min_edge_sample_size: int = Field(
        default=30,
        ge=2,
        validation_alias="TAURUS_GRAPH_MIN_EDGE_SAMPLE_SIZE",
    )
    taurus_graph_min_edge_confidence: Decimal = Field(
        default=Decimal("0.65"),
        ge=Decimal("0"),
        le=Decimal("1"),
        validation_alias="TAURUS_GRAPH_MIN_EDGE_CONFIDENCE",
    )
    taurus_graph_min_residual_corr: Decimal = Field(
        default=Decimal("0.35"),
        ge=Decimal("0"),
        le=Decimal("1"),
        validation_alias="TAURUS_GRAPH_MIN_RESIDUAL_CORR",
    )
    taurus_graph_min_lead_lag_score: Decimal = Field(
        default=Decimal("0.35"),
        ge=Decimal("0"),
        le=Decimal("1"),
        validation_alias="TAURUS_GRAPH_MIN_LEAD_LAG_SCORE",
    )
    taurus_graph_min_stability_score: Decimal = Field(
        default=Decimal("0.50"),
        ge=Decimal("0"),
        le=Decimal("1"),
        validation_alias="TAURUS_GRAPH_MIN_STABILITY_SCORE",
    )
    taurus_graph_lead_lag_max_days: int = Field(
        default=5,
        ge=1,
        validation_alias="TAURUS_GRAPH_LEAD_LAG_MAX_DAYS",
    )
    taurus_graph_max_basic_industry_exposure_pct: Decimal = Field(
        default=Decimal("25.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
        validation_alias="TAURUS_GRAPH_MAX_BASIC_INDUSTRY_EXPOSURE_PCT",
    )
    taurus_graph_max_product_group_exposure_pct: Decimal = Field(
        default=Decimal("30.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
        validation_alias="TAURUS_GRAPH_MAX_PRODUCT_GROUP_EXPOSURE_PCT",
    )
    taurus_graph_max_customer_industry_exposure_pct: Decimal = Field(
        default=Decimal("30.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
        validation_alias="TAURUS_GRAPH_MAX_CUSTOMER_INDUSTRY_EXPOSURE_PCT",
    )
    taurus_graph_max_dependency_exposure_pct: Decimal = Field(
        default=Decimal("30.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
        validation_alias="TAURUS_GRAPH_MAX_DEPENDENCY_EXPOSURE_PCT",
    )
    taurus_graph_max_risk_category_exposure_pct: Decimal = Field(
        default=Decimal("25.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
        validation_alias="TAURUS_GRAPH_MAX_RISK_CATEGORY_EXPOSURE_PCT",
    )
    taurus_graph_max_correlated_cluster_exposure_pct: Decimal = Field(
        default=Decimal("35.0"),
        ge=Decimal("0"),
        le=Decimal("100"),
        validation_alias="TAURUS_GRAPH_MAX_CORRELATED_CLUSTER_EXPOSURE_PCT",
    )
    taurus_graph_concentration_warning_fraction: Decimal = Field(
        default=Decimal("0.80"),
        ge=Decimal("0"),
        le=Decimal("1"),
        validation_alias="TAURUS_GRAPH_CONCENTRATION_WARNING_FRACTION",
    )
    taurus_neo4j_enabled: bool = Field(
        default=False,
        validation_alias="TAURUS_NEO4J_ENABLED",
    )
    taurus_neo4j_uri: str = Field(
        default="bolt://localhost:7687",
        validation_alias="TAURUS_NEO4J_URI",
    )
    taurus_neo4j_user: str = Field(
        default="neo4j",
        validation_alias="TAURUS_NEO4J_USER",
    )
    taurus_neo4j_password: str = Field(
        default="taurus-neo4j-local",
        validation_alias="TAURUS_NEO4J_PASSWORD",
    )
    taurus_neo4j_database: str = Field(
        default="neo4j",
        validation_alias="TAURUS_NEO4J_DATABASE",
    )

    taurus_universe: str = Field(
        default="NIFTY_500_SHARIAH",
        validation_alias="TAURUS_UNIVERSE",
    )
    taurus_timeframe: str = Field(default="1d", validation_alias="TAURUS_TIMEFRAME")
    taurus_market_data_provider: str = Field(
        default="kite",
        validation_alias="TAURUS_MARKET_DATA_PROVIDER",
    )
    taurus_market_data_universe_path: str = Field(
        default="configs/market_data/nifty_500_shariah.yaml",
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
    taurus_initial_capital_inr: int = Field(
        default=1_000_000,
        gt=0,
        validation_alias="TAURUS_INITIAL_CAPITAL_INR",
    )
    taurus_paper_portfolio_id: str = Field(
        default="local-paper",
        min_length=1,
        validation_alias="TAURUS_PAPER_PORTFOLIO_ID",
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
    taurus_money_management_enabled: bool = Field(
        default=False,
        validation_alias="TAURUS_MONEY_MANAGEMENT_ENABLED",
    )
    taurus_money_management_config_path: str = Field(
        default="configs/portfolio/money_management_v1.yaml",
        validation_alias="TAURUS_MONEY_MANAGEMENT_CONFIG_PATH",
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
    taurus_position_monitor_enabled: bool = Field(
        default=False,
        validation_alias="TAURUS_POSITION_MONITOR_ENABLED",
    )
    taurus_position_monitor_interval_seconds: int = Field(
        default=30,
        ge=1,
        validation_alias="TAURUS_POSITION_MONITOR_INTERVAL_SECONDS",
    )
    taurus_position_monitor_provider: str = Field(
        default="kite",
        validation_alias="TAURUS_POSITION_MONITOR_PROVIDER",
    )
    taurus_position_monitor_market_hours_only: bool = Field(
        default=True,
        validation_alias="TAURUS_POSITION_MONITOR_MARKET_HOURS_ONLY",
    )
    taurus_position_monitor_max_iterations: int = Field(
        default=0,
        ge=0,
        validation_alias="TAURUS_POSITION_MONITOR_MAX_ITERATIONS",
    )

    taurus_llm_provider: str = Field(default="lmstudio", validation_alias="TAURUS_LLM_PROVIDER")
    taurus_llm_base_url: str = Field(default="", validation_alias="TAURUS_LLM_BASE_URL")
    taurus_llm_model: str = Field(default="", validation_alias="TAURUS_LLM_MODEL")
    taurus_llm_timeout_seconds: int = Field(
        default=20,
        gt=0,
        validation_alias="TAURUS_LLM_TIMEOUT_SECONDS",
    )
    taurus_alert_provider: str = Field(default="mock", validation_alias="TAURUS_ALERT_PROVIDER")
    taurus_enabled_analysts: str = Field(
        default=DEFAULT_ENABLED_ANALYSTS,
        validation_alias="TAURUS_ENABLED_ANALYSTS",
    )
    openai_api_key: str = Field(default="", validation_alias="OPENAI_API_KEY")
    gemini_api_key: str = Field(default="", validation_alias="GEMINI_API_KEY")
    telegram_bot_token: str = Field(default="", validation_alias="TELEGRAM_BOT_TOKEN")
    telegram_chat_id: str = Field(default="", validation_alias="TELEGRAM_CHAT_ID")
    kite_api_key: str = Field(default="", validation_alias="KITE_API_KEY")
    kite_api_secret: str = Field(default="", validation_alias="KITE_API_SECRET")
    kite_access_token: str = Field(default="", validation_alias="KITE_ACCESS_TOKEN")
    taurus_kite_exchange: str = Field(default="NSE", validation_alias="TAURUS_KITE_EXCHANGE")

    @model_validator(mode="after")
    def enforce_trading_safety(self) -> Settings:
        if self.taurus_mode not in {"paper", "backtest"}:
            raise ValueError("Taurus currently supports only paper or backtest modes.")
        if self.live_trading_enabled:
            raise ValueError("Live trading is disabled and cannot be enabled.")
        if self.broker_provider != "paper":
            raise ValueError("Taurus currently supports only the paper broker provider.")
        if urlsplit(self.database_url).scheme.lower().startswith("sqlite"):
            raise ValueError("SQLite database URLs are no longer supported; use Docker Postgres.")
        if self.taurus_market_data_provider not in set(SUPPORTED_MARKET_DATA_PROVIDERS):
            raise ValueError(
                "Unsupported Taurus market data provider. Supported values: "
                f"{', '.join(SUPPORTED_MARKET_DATA_PROVIDERS)}."
            )
        if self.taurus_position_monitor_provider not in set(SUPPORTED_MARKET_DATA_PROVIDERS):
            raise ValueError(
                "Unsupported Taurus position monitor provider. Supported values: "
                f"{', '.join(SUPPORTED_MARKET_DATA_PROVIDERS)}."
            )
        if self.taurus_llm_provider not in set(SUPPORTED_LLM_PROVIDERS):
            raise ValueError(
                "Unsupported Taurus LLM provider. Supported values: "
                f"{', '.join(SUPPORTED_LLM_PROVIDERS)}."
            )
        if self.taurus_alert_provider not in {"mock", "telegram", "disabled"}:
            raise ValueError("Unsupported Taurus alert provider.")
        parse_enabled_analysts(self.taurus_enabled_analysts)
        _parse_graph_stats_windows(self.taurus_graph_stats_windows)
        return self

    @property
    def enabled_analyst_keys(self) -> tuple[str, ...]:
        return parse_enabled_analysts(self.taurus_enabled_analysts)

    @property
    def graph_stats_windows(self) -> tuple[int, ...]:
        return _parse_graph_stats_windows(self.taurus_graph_stats_windows)

    @property
    def configured_llm_model(self) -> str:
        if self.taurus_llm_model:
            return self.taurus_llm_model
        if self.taurus_llm_provider == "openai":
            return DEFAULT_OPENAI_MODEL
        if self.taurus_llm_provider == "gemini":
            return DEFAULT_GEMINI_MODEL
        return DEFAULT_LMSTUDIO_MODEL

    @property
    def configured_llm_model_version(self) -> str:
        return f"{self.taurus_llm_provider}:{self.configured_llm_model}"

    def safe_dict(self) -> dict[str, Any]:
        redacted = self.model_dump()
        for key in (
            "openai_api_key",
            "gemini_api_key",
            "telegram_bot_token",
            "telegram_chat_id",
            "kite_api_key",
            "kite_api_secret",
            "kite_access_token",
            "taurus_neo4j_password",
        ):
            if redacted.get(key):
                redacted[key] = "***REDACTED***"
        redacted["database_url"] = _redact_url_password(self.database_url)
        redacted["taurus_neo4j_uri"] = _redact_url_password(self.taurus_neo4j_uri)
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


def _parse_graph_stats_windows(value: str) -> tuple[int, ...]:
    windows: list[int] = []
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        try:
            window = int(item)
        except ValueError as exc:
            raise ValueError("TAURUS_GRAPH_STATS_WINDOWS must contain positive integers.") from exc
        if window <= 0:
            raise ValueError("TAURUS_GRAPH_STATS_WINDOWS must contain positive integers.")
        windows.append(window)
    if not windows:
        raise ValueError("TAURUS_GRAPH_STATS_WINDOWS must contain at least one window.")
    return tuple(windows)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    try:
        return Settings()
    except ValidationError:
        raise
