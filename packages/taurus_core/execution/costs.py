from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

RATE_DENOMINATOR = Decimal("10000")
MONEY_QUANT = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class CostBreakdown:
    brokerage_inr: Decimal
    exchange_txn_charge_inr: Decimal
    tax_levy_inr: Decimal

    @property
    def total_inr(self) -> Decimal:
        return _money(
            self.brokerage_inr
            + self.exchange_txn_charge_inr
            + self.tax_levy_inr
        )


@dataclass(frozen=True, slots=True)
class IndiaPaperCostModel:
    """Simulation-only India cash-equity cost placeholders."""

    brokerage_bps: Decimal
    exchange_txn_charge_bps: Decimal
    tax_levy_bps: Decimal

    def calculate(self, gross_value_inr: Decimal) -> CostBreakdown:
        if gross_value_inr < 0:
            raise ValueError("gross_value_inr cannot be negative")
        return CostBreakdown(
            brokerage_inr=_money(gross_value_inr * self.brokerage_bps / RATE_DENOMINATOR),
            exchange_txn_charge_inr=_money(
                gross_value_inr * self.exchange_txn_charge_bps / RATE_DENOMINATOR
            ),
            tax_levy_inr=_money(gross_value_inr * self.tax_levy_bps / RATE_DENOMINATOR),
        )


def _money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP)
