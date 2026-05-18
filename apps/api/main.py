from __future__ import annotations

import time

from fastapi import FastAPI, Request

from apps.api.routes_health import router as health_router
from taurus_core.config import Settings, get_settings
from taurus_core.logging import configure_logging, get_logger
from taurus_core.observability.metrics import configure_runtime_metrics, record_request


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    configure_runtime_metrics(settings)

    app = FastAPI(
        title="Taurus API",
        version=settings.service_version,
        description="M0 foundation API for Project Taurus.",
    )
    app.state.settings = settings
    app.include_router(health_router)

    logger = get_logger(__name__)
    logger.info(
        "api.configured",
        environment=settings.taurus_env,
        mode=settings.taurus_mode,
        broker_provider=settings.broker_provider,
        live_trading_enabled=settings.live_trading_enabled,
    )

    @app.middleware("http")
    async def metrics_middleware(request: Request, call_next):
        started_at = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            elapsed = time.perf_counter() - started_at
            record_request(
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_seconds=elapsed,
            )

    return app


app = create_app()
