from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse

from scripts.kite_auth import exchange_request_token
from taurus_core.config import get_settings
from taurus_core.domain.market_data import MarketDataProviderError

router = APIRouter(tags=["kite-auth"])


@router.get("/", response_class=HTMLResponse)
def kite_login_callback(
    request: Request,
    request_token: Annotated[str | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
) -> HTMLResponse:
    if request_token is None:
        return HTMLResponse(
            "<!doctype html><title>Taurus API</title><h1>Taurus API</h1>"
            "<p>Paper trading mode. Kite login callback is ready.</p>"
        )
    if not _is_local_request(request):
        raise HTTPException(status_code=403, detail="Kite login callback accepts only local requests.")
    if status not in {None, "success"}:
        raise HTTPException(status_code=400, detail="Kite login did not complete successfully.")

    settings = request.app.state.settings
    try:
        token = exchange_request_token(request_token, settings=settings)
    except MarketDataProviderError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.app.state.settings = settings.model_copy(update={"kite_access_token": token})
    get_settings.cache_clear()
    return HTMLResponse(
        "<!doctype html><title>Kite Connected</title><h1>Kite Connected</h1>"
        f"<p>Kite access token stored locally in .env ({len(token)} characters).</p>"
        "<p>You can close this tab and run Kite market-data commands.</p>"
    )


def _is_local_request(request: Request) -> bool:
    host = request.client.host if request.client is not None else ""
    return host in {"127.0.0.1", "::1", "localhost", "testclient"}
