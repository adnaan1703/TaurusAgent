from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

SCORE_QUANT = Decimal("0.0001")
NEUTRAL_ALLOCATION_COMPONENT = Decimal("50.0000")


@dataclass(frozen=True, slots=True)
class StrategyScoreCalibration:
    raw_strategy_score: Decimal | None
    calibrated_strategy_score: Decimal
    allocation_score_component: Decimal
    strategy_rank: int | None = None
    method: str = "strategy_score_linear_v1"

    def score_parts(self) -> dict[str, Decimal]:
        parts = {
            "strategy_score": self.allocation_score_component,
            "calibrated_strategy_score": self.calibrated_strategy_score,
        }
        if self.raw_strategy_score is not None:
            parts["raw_strategy_score"] = self.raw_strategy_score.quantize(SCORE_QUANT)
        return parts

    def rationale(self) -> str:
        if self.raw_strategy_score is None:
            return "Strategy score calibration used the neutral missing-score component 50.0000."
        rank_text = f", strategy_rank={self.strategy_rank}" if self.strategy_rank is not None else ""
        return (
            "Strategy score calibration "
            f"raw_strategy_score={self.raw_strategy_score.quantize(SCORE_QUANT)}, "
            f"calibrated_strategy_score={self.calibrated_strategy_score}, "
            f"allocation_component={self.allocation_score_component}{rank_text}."
        )


def calibrate_strategy_score(
    raw_strategy_score: Decimal | int | float | str | None,
    *,
    strategy_rank: int | None = None,
) -> StrategyScoreCalibration:
    """Map natural strategy scores to an allocation component without early saturation."""

    if raw_strategy_score is None:
        return StrategyScoreCalibration(
            raw_strategy_score=None,
            calibrated_strategy_score=NEUTRAL_ALLOCATION_COMPONENT,
            allocation_score_component=NEUTRAL_ALLOCATION_COMPONENT,
            strategy_rank=strategy_rank,
            method="missing_score_default_v1",
        )

    raw = Decimal(str(raw_strategy_score))
    if raw >= 0:
        calibrated = Decimal("60") + (raw * Decimal("100"))
    else:
        calibrated = Decimal("60") + (raw * Decimal("300"))
    component = _clamp(calibrated, Decimal("0"), Decimal("100")).quantize(SCORE_QUANT)
    return StrategyScoreCalibration(
        raw_strategy_score=raw,
        calibrated_strategy_score=component,
        allocation_score_component=component,
        strategy_rank=strategy_rank,
    )


def _clamp(value: Decimal, lower: Decimal, upper: Decimal) -> Decimal:
    return max(lower, min(upper, value))
