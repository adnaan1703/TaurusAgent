from __future__ import annotations

from decimal import Decimal

import pytest
from pydantic import ValidationError

from taurus_core.config import Settings


def test_default_settings_are_safe() -> None:
    settings = Settings()

    assert settings.taurus_env == "local"
    assert settings.taurus_mode == "paper"
    assert settings.live_trading_enabled is False
    assert settings.broker_provider == "paper"
    assert settings.database_url == "sqlite:///./taurus.db"
    assert settings.taurus_graph_enabled is False
    assert settings.taurus_graph_risk_enabled is False
    assert settings.taurus_graph_auto_promote_edges is False
    assert settings.graph_stats_windows == (60, 120, 252)
    assert settings.taurus_graph_min_edge_sample_size == 30
    assert settings.taurus_graph_min_edge_confidence == Decimal("0.65")
    assert settings.taurus_graph_min_residual_corr == Decimal("0.35")
    assert settings.taurus_graph_min_lead_lag_score == Decimal("0.35")
    assert settings.taurus_graph_min_stability_score == Decimal("0.50")
    assert settings.taurus_graph_lead_lag_max_days == 5
    assert settings.taurus_graph_max_basic_industry_exposure_pct == Decimal("25.0")
    assert settings.taurus_graph_max_product_group_exposure_pct == Decimal("30.0")
    assert settings.taurus_graph_max_customer_industry_exposure_pct == Decimal("30.0")
    assert settings.taurus_graph_max_dependency_exposure_pct == Decimal("30.0")
    assert settings.taurus_graph_max_risk_category_exposure_pct == Decimal("25.0")
    assert settings.taurus_graph_max_correlated_cluster_exposure_pct == Decimal("35.0")
    assert settings.taurus_graph_concentration_warning_fraction == Decimal("0.80")
    assert settings.taurus_neo4j_enabled is False
    assert settings.taurus_neo4j_uri == "bolt://localhost:7687"
    assert settings.taurus_neo4j_user == "neo4j"
    assert settings.taurus_neo4j_password == "taurus-neo4j-local"
    assert settings.taurus_neo4j_database == "neo4j"
    assert settings.taurus_mock_seed == 42
    assert settings.taurus_mock_candle_count == 252
    assert settings.taurus_market_data_provider == "mock"
    assert settings.taurus_market_data_universe_path == "configs/market_data/kite_nse_cash.yaml"
    assert settings.taurus_market_data_lookback_days == 400
    assert settings.taurus_kite_exchange == "NSE"
    assert settings.taurus_llm_provider == "mock"
    assert settings.taurus_enabled_analysts == "technical"
    assert settings.enabled_analyst_keys == ("technical",)
    assert settings.taurus_initial_capital_inr == 1_000_000
    assert settings.taurus_max_position_pct == 5
    assert settings.taurus_max_open_positions == 8


def test_live_trading_cannot_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    with pytest.raises(ValidationError, match="Live trading is disabled"):
        Settings()


def test_non_paper_broker_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROKER_PROVIDER", "live")

    with pytest.raises(ValidationError, match="paper broker provider"):
        Settings()


def test_unknown_market_data_provider_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_MARKET_DATA_PROVIDER", "scraper")

    with pytest.raises(ValidationError, match="market data provider"):
        Settings()


def test_kite_market_data_provider_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_MARKET_DATA_PROVIDER", "kite")

    assert Settings().taurus_market_data_provider == "kite"


def test_graph_flags_can_be_enabled_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_GRAPH_ENABLED", "true")
    monkeypatch.setenv("TAURUS_GRAPH_RISK_ENABLED", "true")
    monkeypatch.setenv("TAURUS_GRAPH_AUTO_PROMOTE_EDGES", "true")
    monkeypatch.setenv("TAURUS_NEO4J_ENABLED", "true")

    settings = Settings()

    assert settings.taurus_graph_enabled is True
    assert settings.taurus_graph_risk_enabled is True
    assert settings.taurus_graph_auto_promote_edges is True
    assert settings.taurus_neo4j_enabled is True


def test_graph_analyst_key_can_be_enabled_explicitly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_ENABLED_ANALYSTS", "technical,graph")

    assert Settings().enabled_analyst_keys == ("technical", "graph")


def test_graph_stats_windows_are_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_GRAPH_STATS_WINDOWS", "20,not-a-window")

    with pytest.raises(ValidationError, match="GRAPH_STATS_WINDOWS"):
        Settings()


def test_unknown_enabled_analyst_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_ENABLED_ANALYSTS", "technical,macro")

    with pytest.raises(ValidationError, match="Unsupported analyst key"):
        Settings()


def test_empty_enabled_analyst_roster_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TAURUS_ENABLED_ANALYSTS", "")

    with pytest.raises(ValidationError, match="at least one analyst"):
        Settings()


def test_secret_values_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("KITE_API_KEY", "kite-key")
    monkeypatch.setenv("KITE_API_SECRET", "kite-secret")
    monkeypatch.setenv("KITE_ACCESS_TOKEN", "kite-token")
    monkeypatch.setenv("TAURUS_NEO4J_PASSWORD", "neo4j-secret")

    safe = Settings().safe_dict()
    assert safe["openai_api_key"] == "***REDACTED***"
    assert safe["kite_api_key"] == "***REDACTED***"
    assert safe["kite_api_secret"] == "***REDACTED***"
    assert safe["kite_access_token"] == "***REDACTED***"
    assert safe["taurus_neo4j_password"] == "***REDACTED***"


def test_database_url_password_is_redacted() -> None:
    settings = Settings(database_url="postgresql+psycopg://taurus:secret@localhost:5432/taurus")

    assert (
        settings.safe_dict()["database_url"]
        == "postgresql+psycopg://taurus:***REDACTED***@localhost:5432/taurus"
    )
