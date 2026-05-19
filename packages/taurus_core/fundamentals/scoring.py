from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

SCORE_QUANT = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class FundamentalScoreComponents:
    quality_score: Decimal | None
    valuation_score: Decimal | None
    leverage_risk_score: Decimal | None
    ownership_score: Decimal | None
    composite_score: Decimal

    def as_dict(self) -> dict[str, Decimal | None]:
        return {
            "quality_score": self.quality_score,
            "valuation_score": self.valuation_score,
            "leverage_risk_score": self.leverage_risk_score,
            "ownership_score": self.ownership_score,
            "composite_score": self.composite_score,
        }


def score_fundamentals(metrics: Mapping[str, Decimal]) -> FundamentalScoreComponents:
    quality_score = _average(
        [
            _scale(metrics.get("roce"), low=Decimal("5"), high=Decimal("25")),
            _scale(metrics.get("roe"), low=Decimal("5"), high=Decimal("22")),
            _eps_score(metrics.get("eps")),
            _scale(metrics.get("sales_growth"), low=Decimal("-5"), high=Decimal("20")),
            _scale(metrics.get("profit_growth"), low=Decimal("-5"), high=Decimal("20")),
        ]
    )
    valuation_score = _average(
        [
            _inverse_scale(metrics.get("stock_pe"), low=Decimal("12"), high=Decimal("45")),
            _price_to_book_score(
                current_price=metrics.get("current_price"),
                book_value=metrics.get("book_value"),
            ),
            _scale(metrics.get("dividend_yield"), low=Decimal("0"), high=Decimal("4")),
        ]
    )
    leverage_risk_score = _average(
        [
            _inverse_scale(metrics.get("debt_to_equity"), low=Decimal("0.2"), high=Decimal("2.0")),
            _inverse_scale(metrics.get("pledged_percentage"), low=Decimal("0"), high=Decimal("20")),
        ]
    )
    ownership_score = _average(
        [
            _scale(metrics.get("promoter_holding"), low=Decimal("25"), high=Decimal("60")),
            _scale(
                _sum_optional(metrics.get("fii_holding"), metrics.get("dii_holding")),
                low=Decimal("5"),
                high=Decimal("35"),
            ),
        ]
    )
    composite_score = _average(
        [quality_score, valuation_score, leverage_risk_score, ownership_score]
    ) or Decimal("0")
    return FundamentalScoreComponents(
        quality_score=quality_score,
        valuation_score=valuation_score,
        leverage_risk_score=leverage_risk_score,
        ownership_score=ownership_score,
        composite_score=_quantize(composite_score),
    )


def _scale(value: Decimal | None, *, low: Decimal, high: Decimal) -> Decimal | None:
    if value is None:
        return None
    if high <= low:
        raise ValueError("high must be greater than low")
    scaled = ((value - low) / (high - low) * Decimal("2")) - Decimal("1")
    return _quantize(scaled)


def _inverse_scale(value: Decimal | None, *, low: Decimal, high: Decimal) -> Decimal | None:
    score = _scale(value, low=low, high=high)
    return None if score is None else _quantize(-score)


def _eps_score(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if value < 0:
        return Decimal("-0.8000")
    if value == 0:
        return Decimal("-0.2000")
    return _scale(value, low=Decimal("0"), high=Decimal("100"))


def _price_to_book_score(
    *,
    current_price: Decimal | None,
    book_value: Decimal | None,
) -> Decimal | None:
    if current_price is None or book_value is None or book_value <= 0:
        return None
    return _inverse_scale(current_price / book_value, low=Decimal("1.5"), high=Decimal("8"))


def _average(values: list[Decimal | None]) -> Decimal | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return _quantize(sum(present, Decimal("0")) / Decimal(len(present)))


def _sum_optional(first: Decimal | None, second: Decimal | None) -> Decimal | None:
    if first is None and second is None:
        return None
    return (first or Decimal("0")) + (second or Decimal("0"))


def _quantize(value: Decimal) -> Decimal:
    return max(Decimal("-1"), min(Decimal("1"), value)).quantize(SCORE_QUANT)
