from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Instrument:
    symbol: str
    name: str
    exchange: str = "NSE"
    segment: str = "EQUITY"
    currency: str = "INR"
    lot_size: int = 1
    tick_size: Decimal = Decimal("0.05")
    active: bool = True
