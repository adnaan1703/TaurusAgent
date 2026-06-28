from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from experiments.parametric.errors import ExperimentSpecError


@dataclass(frozen=True, slots=True)
class MetricDefinition:
    metric_id: str
    namespace: str
    description: str


class MetricRegistry:
    def __init__(self, metrics: Mapping[str, MetricDefinition]) -> None:
        self._metrics = dict(metrics)

    def validate(self, metric_ids: tuple[str, ...]) -> tuple[MetricDefinition, ...]:
        unknown = [metric_id for metric_id in metric_ids if metric_id not in self._metrics]
        if unknown:
            known = ", ".join(sorted(self._metrics))
            raise ExperimentSpecError(
                f"Unknown metric id(s): {', '.join(unknown)}. Known metrics: {known}."
            )
        return tuple(self._metrics[metric_id] for metric_id in metric_ids)

    def ids(self) -> tuple[str, ...]:
        return tuple(sorted(self._metrics))


def default_metric_registry() -> MetricRegistry:
    metrics = [
        MetricDefinition("system.total_return", "system", "Full-system total return."),
        MetricDefinition("system.cagr", "system", "Full-system CAGR."),
        MetricDefinition("system.sharpe", "system", "Full-system Sharpe ratio."),
        MetricDefinition("system.sortino", "system", "Full-system Sortino ratio."),
        MetricDefinition("system.max_drawdown", "system", "Full-system max drawdown."),
        MetricDefinition("system.turnover", "system", "Full-system turnover."),
        MetricDefinition("system.win_rate", "system", "Full-system win rate."),
        MetricDefinition("system.profit_factor", "system", "Full-system profit factor."),
        MetricDefinition(
            "system.realized_pnl_inr",
            "system",
            "Closed-trade realized P&L in INR.",
        ),
        MetricDefinition(
            "system.unrealized_pnl_inr",
            "system",
            "Final open-position unrealized P&L in INR.",
        ),
        MetricDefinition(
            "system.closed_trade_count",
            "system",
            "Closed trade count.",
        ),
        MetricDefinition(
            "system.closed_win_count",
            "system",
            "Closed winning trade count.",
        ),
        MetricDefinition(
            "system.closed_loss_count",
            "system",
            "Closed losing trade count.",
        ),
        MetricDefinition(
            "system.gross_profit_inr",
            "system",
            "Gross closed-trade profit in INR.",
        ),
        MetricDefinition(
            "system.gross_loss_inr",
            "system",
            "Gross closed-trade loss magnitude in INR.",
        ),
        MetricDefinition(
            "system.average_closed_win_inr",
            "system",
            "Average closed winning trade profit in INR.",
        ),
        MetricDefinition(
            "system.average_closed_loss_inr",
            "system",
            "Average closed losing trade loss magnitude in INR.",
        ),
        MetricDefinition(
            "system.average_cash_utilization_pct",
            "system",
            "Average cash utilization percent.",
        ),
        MetricDefinition(
            "system.ranked_candidate_count",
            "system",
            "Ranked candidate count.",
        ),
        MetricDefinition(
            "system.eligible_candidate_count",
            "system",
            "Eligible candidate count.",
        ),
        MetricDefinition(
            "system.rejected_candidate_count",
            "system",
            "Rejected candidate count.",
        ),
        MetricDefinition(
            "system.trimmed_candidate_count",
            "system",
            "Trimmed candidate count.",
        ),
        MetricDefinition(
            "system.sizing_failure_count",
            "system",
            "Sizing failure count.",
        ),
        MetricDefinition(
            "rank.5d.rank_correlation",
            "rank",
            "5-day technical rank correlation.",
        ),
        MetricDefinition(
            "rank.5d.top_bottom_decile_spread",
            "rank",
            "5-day top-bottom decile spread.",
        ),
        MetricDefinition("rank.5d.hit_rate", "rank", "5-day hit rate."),
        MetricDefinition(
            "rank.21d.rank_correlation",
            "rank",
            "21-day technical rank correlation.",
        ),
        MetricDefinition(
            "rank.21d.top_bottom_decile_spread",
            "rank",
            "21-day top-bottom decile spread.",
        ),
        MetricDefinition("rank.21d.hit_rate", "rank", "21-day hit rate."),
        MetricDefinition(
            "rank.63d.rank_correlation",
            "rank",
            "63-day technical rank correlation.",
        ),
        MetricDefinition(
            "rank.63d.top_bottom_decile_spread",
            "rank",
            "63-day top-bottom decile spread.",
        ),
        MetricDefinition("rank.63d.hit_rate", "rank", "63-day hit rate."),
    ]
    return MetricRegistry({metric.metric_id: metric for metric in metrics})
