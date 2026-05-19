from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from taurus_core.execution.costs import RATE_DENOMINATOR
from taurus_core.execution.schemas import OrderSide

MONEY_QUANT = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class FixedBpsSlippageModel:
    slippage_bps: Decimal

    def fill_price(self, *, reference_price_inr: Decimal, side: OrderSide) -> Decimal:
        if reference_price_inr <= 0:
            raise ValueError("reference_price_inr must be positive")
        direction = Decimal("1") if side == "BUY" else Decimal("-1")
        multiplier = Decimal("1") + (direction * self.slippage_bps / RATE_DENOMINATOR)
        return _money(reference_price_inr * multiplier)

    def slippage_value(
        self,
        *,
        reference_price_inr: Decimal,
        fill_price_inr: Decimal,
        quantity: int,
    ) -> Decimal:
        return _money(abs(fill_price_inr - reference_price_inr) * Decimal(quantity))


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
