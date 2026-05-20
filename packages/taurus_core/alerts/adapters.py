from __future__ import annotations

import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from taurus_core.alerts.schemas import AlertDeliveryResult, AlertEvent


class MockAlertAdapter:
    name = "mock"

    def __init__(self) -> None:
        self.events: list[AlertEvent] = []

    def send(self, event: AlertEvent) -> AlertDeliveryResult:
        self.events.append(event)
        return AlertDeliveryResult(
            event_id=event.event_id,
            adapter=self.name,
            delivered=True,
            destination="mock",
            response_text="mock alert accepted",
        )


class DisabledAlertAdapter:
    name = "disabled"

    def send(self, event: AlertEvent) -> AlertDeliveryResult:
        return AlertDeliveryResult(
            event_id=event.event_id,
            adapter=self.name,
            delivered=False,
            response_text="alerts disabled",
        )


class TelegramAlertAdapter:
    name = "telegram"

    def __init__(self, *, bot_token: str, chat_id: str, timeout_seconds: float = 10.0) -> None:
        if not bot_token or not chat_id:
            raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are required.")
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.timeout_seconds = timeout_seconds

    def send(self, event: AlertEvent) -> AlertDeliveryResult:
        payload = {
            "chat_id": self.chat_id,
            "text": render_telegram_message(event),
            "disable_web_page_preview": True,
        }
        request = Request(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response.read()
                return AlertDeliveryResult(
                    event_id=event.event_id,
                    adapter=self.name,
                    delivered=200 <= response.status < 300,
                    destination="telegram",
                    status_code=response.status,
                    response_text="telegram sendMessage accepted",
                )
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            return AlertDeliveryResult(
                event_id=event.event_id,
                adapter=self.name,
                delivered=False,
                destination="telegram",
                status_code=exc.code,
                response_text=body[:500],
                error=str(exc),
            )
        except URLError as exc:
            return AlertDeliveryResult(
                event_id=event.event_id,
                adapter=self.name,
                delivered=False,
                destination="telegram",
                error=str(exc.reason),
            )


def render_telegram_message(event: AlertEvent) -> str:
    lines = [
        f"Taurus {event.severity.upper()}: {event.event_type}",
        event.message,
    ]
    if event.symbol:
        lines.append(f"symbol={event.symbol}")
    if event.run_id:
        lines.append(f"run_id={event.run_id}")
    if event.decision_id:
        lines.append(f"decision_id={event.decision_id}")
    if event.source_id:
        lines.append(f"source_id={event.source_id}")
    return "\n".join(lines)
