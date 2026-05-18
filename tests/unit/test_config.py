from __future__ import annotations

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
    assert settings.taurus_mock_seed == 42
    assert settings.taurus_mock_candle_count == 252
    assert settings.taurus_llm_provider == "mock"
    assert settings.taurus_initial_capital_inr == 1_000_000
    assert settings.taurus_max_position_pct == 5
    assert settings.taurus_max_open_positions == 8


def test_live_trading_cannot_be_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LIVE_TRADING_ENABLED", "true")

    with pytest.raises(ValidationError, match="Live trading is disabled"):
        Settings()


def test_non_paper_broker_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BROKER_PROVIDER", "upstox")

    with pytest.raises(ValidationError, match="paper broker provider"):
        Settings()


def test_secret_values_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")

    assert Settings().safe_dict()["openai_api_key"] == "***REDACTED***"


def test_database_url_password_is_redacted() -> None:
    settings = Settings(database_url="postgresql+psycopg://taurus:secret@localhost:5432/taurus")

    assert (
        settings.safe_dict()["database_url"]
        == "postgresql+psycopg://taurus:***REDACTED***@localhost:5432/taurus"
    )
