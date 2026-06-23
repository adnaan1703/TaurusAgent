from __future__ import annotations

from decimal import Decimal

from taurus_core.backtesting import BacktestConfig


def test_backtest_config_uses_portfolio_breadth_cap() -> None:
    config = BacktestConfig(
        initial_capital_inr=Decimal("100000"),
        max_open_positions=3,
        portfolio_breadth=5,
    )

    assert config.effective_portfolio_breadth == 3
