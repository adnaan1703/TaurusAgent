from __future__ import annotations

from sqlalchemy.orm import Session

from taurus_core.alerts.adapters import DisabledAlertAdapter, MockAlertAdapter, TelegramAlertAdapter
from taurus_core.alerts.base import AlertAdapter
from taurus_core.alerts.schemas import AlertDeliveryResult, AlertEvent
from taurus_core.config import Settings, get_settings
from taurus_core.db.models import AuditLogModel
from taurus_core.logging import get_logger


def build_alert_adapter(settings: Settings | None = None, *, force_mock: bool = False) -> AlertAdapter:
    settings = settings or get_settings()
    if force_mock:
        return MockAlertAdapter()
    if settings.taurus_alert_provider == "disabled":
        return DisabledAlertAdapter()
    if settings.taurus_alert_provider == "telegram":
        return TelegramAlertAdapter(
            bot_token=settings.telegram_bot_token,
            chat_id=settings.telegram_chat_id,
        )
    return MockAlertAdapter()


class AlertService:
    def __init__(
        self,
        session: Session,
        settings: Settings | None = None,
        *,
        adapter: AlertAdapter | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.adapter = adapter or build_alert_adapter(self.settings)
        self.logger = get_logger(__name__)

    def send(self, event: AlertEvent, *, commit: bool = True) -> AlertDeliveryResult:
        try:
            result = self.adapter.send(event)
        except Exception as exc:
            result = AlertDeliveryResult(
                event_id=event.event_id,
                adapter=getattr(self.adapter, "name", self.adapter.__class__.__name__),
                delivered=False,
                error=str(exc),
            )
        self._audit(event, result)
        if commit:
            self.session.commit()
        self.logger.info(
            "alert.sent",
            event_type=event.event_type,
            event_id=event.event_id,
            adapter=result.adapter,
            delivered=result.delivered,
            symbol=event.symbol,
            run_id=event.run_id,
            decision_id=event.decision_id,
        )
        return result

    def send_many(
        self,
        events: list[AlertEvent],
        *,
        commit: bool = True,
    ) -> list[AlertDeliveryResult]:
        results = [self.send(event, commit=False) for event in events]
        if commit:
            self.session.commit()
        return results

    def _audit(self, event: AlertEvent, result: AlertDeliveryResult) -> None:
        self.session.add(
            AuditLogModel(
                event_type=f"alert.{event.event_type}",
                actor="alert_service",
                payload={
                    "event": event.model_dump(mode="json"),
                    "delivery": result.model_dump(mode="json"),
                },
                note=(
                    f"Alert {event.event_type} delivered by {result.adapter}."
                    if result.delivered
                    else f"Alert {event.event_type} not delivered by {result.adapter}."
                ),
            )
        )
