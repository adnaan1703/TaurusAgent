from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import BaseModel

from taurus_core.config import Settings
from taurus_core.observability.metrics import (
    metrics_response_body,
    metrics_response_type,
    refresh_database_metrics,
)

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: Literal["healthy"]
    service: str
    environment: str
    mode: str
    live_trading_enabled: bool


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    checks: dict[str, str]
    live_trading_enabled: bool


def _settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    settings = _settings(request)
    return HealthResponse(
        status="healthy",
        service=settings.service_name,
        environment=settings.taurus_env,
        mode=settings.taurus_mode,
        live_trading_enabled=settings.live_trading_enabled,
    )


@router.get("/ready", response_model=ReadinessResponse)
def ready(request: Request) -> ReadinessResponse:
    settings = _settings(request)
    return ReadinessResponse(
        status="ready",
        checks={
            "config": "ok",
            "broker_provider": settings.broker_provider,
            "live_trading": "disabled",
        },
        live_trading_enabled=settings.live_trading_enabled,
    )


@router.get("/metrics")
def metrics(request: Request) -> Response:
    session_factory = request.app.state.session_factory
    with session_factory() as session:
        refresh_database_metrics(session)
    return Response(content=metrics_response_body(), media_type=metrics_response_type())
