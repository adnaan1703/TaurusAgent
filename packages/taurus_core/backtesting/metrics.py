from __future__ import annotations

import math
from decimal import Decimal


def calculate_backtest_metrics(
    equity_values: list[Decimal],
    *,
    periods_per_year: int = 252,
    winning_pnl: list[Decimal] | None = None,
    losing_pnl: list[Decimal] | None = None,
) -> dict[str, float]:
    if len(equity_values) < 2:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
        }

    returns = [
        float((equity_values[index] / equity_values[index - 1]) - Decimal("1"))
        for index in range(1, len(equity_values))
        if equity_values[index - 1] > 0
    ]
    total_return = float((equity_values[-1] / equity_values[0]) - Decimal("1"))
    years = max((len(equity_values) - 1) / periods_per_year, 1 / periods_per_year)
    cagr = (1 + total_return) ** (1 / years) - 1 if total_return > -1 else -1.0

    average_return = _mean(returns)
    std_return = _sample_std(returns)
    downside_returns = [value for value in returns if value < 0]
    downside_std = _sample_std(downside_returns)

    drawdowns: list[float] = []
    peak = equity_values[0]
    for equity in equity_values:
        peak = max(peak, equity)
        drawdown = float((equity / peak) - Decimal("1")) if peak > 0 else 0.0
        drawdowns.append(drawdown)

    winning_pnl = winning_pnl or []
    losing_pnl = losing_pnl or []
    trade_count = len(winning_pnl) + len(losing_pnl)
    gross_profit = sum(winning_pnl, Decimal("0"))
    gross_loss = abs(sum(losing_pnl, Decimal("0")))

    return {
        "total_return": round(total_return, 8),
        "cagr": round(cagr, 8),
        "sharpe": round((average_return / std_return) * math.sqrt(periods_per_year), 8)
        if std_return
        else 0.0,
        "sortino": round((average_return / downside_std) * math.sqrt(periods_per_year), 8)
        if downside_std
        else 0.0,
        "max_drawdown": round(min(drawdowns), 8),
        "win_rate": round(len(winning_pnl) / trade_count, 8) if trade_count else 0.0,
        "profit_factor": round(float(gross_profit / gross_loss), 8) if gross_loss else float(len(winning_pnl) > 0),
    }


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    average = _mean(values)
    variance = sum((value - average) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)
