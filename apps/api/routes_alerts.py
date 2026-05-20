from __future__ import annotations

from collections.abc import Iterator

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from taurus_core.alerts.adapters import MockAlertAdapter
from taurus_core.alerts.schemas import AlertDeliveryResult
from taurus_core.alerts.service import AlertService
from taurus_core.alerts.templates import alert_smoke_test_event

router = APIRouter(prefix="/alerts", tags=["alerts"])


def get_db_session(request: Request) -> Iterator[Session]:
    session_factory: sessionmaker[Session] = request.app.state.session_factory
    with session_factory() as session:
        yield session


@router.post("/test", response_model=AlertDeliveryResult)
def test_alert(session: Session = Depends(get_db_session)) -> AlertDeliveryResult:
    event = alert_smoke_test_event(run_id="api-alert-test")
    return AlertService(session, adapter=MockAlertAdapter()).send(event)
