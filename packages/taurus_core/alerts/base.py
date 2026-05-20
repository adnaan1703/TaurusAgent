from __future__ import annotations

from typing import Protocol

from taurus_core.alerts.schemas import AlertDeliveryResult, AlertEvent


class AlertAdapter(Protocol):
    name: str

    def send(self, event: AlertEvent) -> AlertDeliveryResult:
        """Send one alert event and return delivery metadata."""
