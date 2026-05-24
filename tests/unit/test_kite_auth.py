from __future__ import annotations

from pathlib import Path

import pytest

from scripts.kite_auth import build_login_url, exchange_request_token
from taurus_core.config import Settings
from taurus_core.domain.market_data import MarketDataProviderError


class FakeAuthClient:
    def __init__(self) -> None:
        self.request_token = ""
        self.api_secret = ""

    def login_url(self) -> str:
        return "https://kite.example/login?api_key=test-key"

    def generate_session(self, request_token: str, api_secret: str) -> dict[str, object]:
        self.request_token = request_token
        self.api_secret = api_secret
        return {"access_token": "generated-access-token"}


def test_kite_login_url_uses_configured_api_key() -> None:
    settings = Settings(kite_api_key="test-key")

    assert build_login_url(settings, client=FakeAuthClient()).endswith("api_key=test-key")


def test_kite_exchange_request_token_updates_env_file(tmp_path: Path) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "KITE_API_KEY=test-key\nKITE_API_SECRET=test-secret\nKITE_ACCESS_TOKEN=\n",
        encoding="utf-8",
    )
    client = FakeAuthClient()
    settings = Settings(kite_api_key="test-key", kite_api_secret="test-secret")

    token = exchange_request_token(
        "request-token",
        settings=settings,
        client=client,
        env_path=env_path,
    )

    assert token == "generated-access-token"
    assert client.request_token == "request-token"
    assert client.api_secret == "test-secret"
    assert "KITE_ACCESS_TOKEN=generated-access-token" in env_path.read_text(encoding="utf-8")


def test_kite_exchange_requires_api_secret(tmp_path: Path) -> None:
    with pytest.raises(MarketDataProviderError, match="KITE_API_KEY and KITE_API_SECRET"):
        exchange_request_token(
            "request-token",
            settings=Settings(kite_api_key="test-key", kite_api_secret=""),
            client=FakeAuthClient(),
            env_path=tmp_path / ".env",
        )
