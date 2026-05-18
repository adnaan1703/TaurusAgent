from __future__ import annotations

from fastapi.testclient import TestClient

from apps.api.main import create_app
from taurus_core.config import Settings


def test_health_endpoint_reports_safe_mode() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "service": "taurus-api",
        "environment": "local",
        "mode": "paper",
        "live_trading_enabled": False,
    }


def test_ready_endpoint_reports_config_checks() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["checks"]["config"] == "ok"
    assert payload["checks"]["broker_provider"] == "paper"
    assert payload["checks"]["live_trading"] == "disabled"
    assert payload["live_trading_enabled"] is False


def test_metrics_endpoint_returns_prometheus_text() -> None:
    client = TestClient(create_app(Settings()))

    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert b"taurus_app_info" in response.content
    assert b"taurus_live_trading_enabled" in response.content
