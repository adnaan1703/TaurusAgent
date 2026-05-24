from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api import routes_kite_auth
from apps.api.main import create_app
from taurus_core.config import Settings


def test_root_reports_kite_callback_ready() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/")

    assert response.status_code == 200
    assert "Kite login callback is ready" in response.text


def test_kite_callback_exchanges_request_token_without_echoing_it(monkeypatch) -> None:
    seen: dict[str, str] = {}

    def fake_exchange(request_token: str, **kwargs) -> str:
        seen["request_token"] = request_token
        return "generated-access-token"

    monkeypatch.setattr(routes_kite_auth, "exchange_request_token", fake_exchange)
    app = create_app(Settings(kite_api_key="test-key", kite_api_secret="test-secret"))
    client = TestClient(app)

    response = client.get("/?status=success&request_token=request-token")

    assert response.status_code == 200
    assert seen["request_token"] == "request-token"
    assert app.state.settings.kite_access_token == "generated-access-token"
    assert "Kite access token stored locally" in response.text
    assert "request-token" not in response.text
    assert "generated-access-token" not in response.text
