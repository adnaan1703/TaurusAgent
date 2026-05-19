from __future__ import annotations

from abc import ABC, abstractmethod

from taurus_core.execution.schemas import PaperAccount, PaperOrder, PaperPosition
from taurus_core.risk.schemas import FinalDecision


class BrokerAdapter(ABC):
    @abstractmethod
    def place_order(self, decision: FinalDecision) -> PaperOrder:
        raise NotImplementedError

    @abstractmethod
    def cancel_order(self, order_id: str) -> PaperOrder:
        raise NotImplementedError

    @abstractmethod
    def get_order(self, order_id: str) -> PaperOrder | None:
        raise NotImplementedError

    @abstractmethod
    def list_orders(self, *, symbol: str | None = None, limit: int | None = 100) -> list[PaperOrder]:
        raise NotImplementedError

    @abstractmethod
    def positions(self, *, symbol: str | None = None) -> list[PaperPosition]:
        raise NotImplementedError

    @abstractmethod
    def cash(self, *, run_id: str | None = None) -> PaperAccount | None:
        raise NotImplementedError
