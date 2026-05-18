from __future__ import annotations

from prometheus_client import CONTENT_TYPE_LATEST, REGISTRY, Counter, Gauge, Histogram, generate_latest

from taurus_core.config import Settings

APP_INFO = Gauge(
    "taurus_app_info",
    "Static Taurus API metadata.",
    ["service", "version", "environment", "mode"],
)

LIVE_TRADING_ENABLED = Gauge(
    "taurus_live_trading_enabled",
    "Whether live trading is enabled. M0 must always report 0.",
)

HTTP_REQUESTS = Counter(
    "taurus_http_requests_total",
    "Total HTTP requests served by the Taurus API.",
    ["method", "path", "status_code"],
)

HTTP_REQUEST_SECONDS = Histogram(
    "taurus_http_request_duration_seconds",
    "HTTP request duration in seconds for the Taurus API.",
    ["method", "path"],
)


def configure_runtime_metrics(settings: Settings) -> None:
    APP_INFO.labels(
        service=settings.service_name,
        version=settings.service_version,
        environment=settings.taurus_env,
        mode=settings.taurus_mode,
    ).set(1)
    LIVE_TRADING_ENABLED.set(1 if settings.live_trading_enabled else 0)


def record_request(
    *,
    method: str,
    path: str,
    status_code: int,
    duration_seconds: float,
) -> None:
    HTTP_REQUESTS.labels(
        method=method,
        path=path,
        status_code=str(status_code),
    ).inc()
    HTTP_REQUEST_SECONDS.labels(method=method, path=path).observe(duration_seconds)


def metrics_response_body() -> bytes:
    return generate_latest(REGISTRY)


def metrics_response_type() -> str:
    return CONTENT_TYPE_LATEST
