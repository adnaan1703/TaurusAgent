from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from taurus_core.domain.market_data import DailyCandle
from taurus_core.portfolio import (
    CoreBasketPosition,
    CoreBasketReviewInput,
    CoreShariahBasketStrategy,
    load_money_management_policy,
)
from taurus_core.portfolio.core_shariah_basket import (
    _CandidateScore,
    _inverse_vol_nav_weights,
)


def test_core_basket_selection_respects_shariah_universe_membership(tmp_path: Path) -> None:
    policy = load_money_management_policy(
        _write_policy(tmp_path, symbols=["INFY", "TCS"])
    )
    strategy = CoreShariahBasketStrategy(policy, max_stale_calendar_days=100)

    artifact = strategy.review(
        CoreBasketReviewInput(
            histories_by_symbol={
                "INFY": _candles("INFY", seed=1),
                "TCS": _candles("TCS", seed=2),
                "RELIANCE": _candles("RELIANCE", seed=3),
            },
            nav_inr=Decimal("1000000"),
            as_of_date=date(2024, 5, 20),
        )
    )

    assert set(artifact["selected_symbols"]).issubset({"INFY", "TCS"})
    rejected = {
        row["symbol"]: row["reasons"]
        for row in artifact["rejected_candidates"]
    }
    assert rejected["RELIANCE"] == ["shariah_universe_mismatch"]


def test_inverse_volatility_weights_respect_normal_and_hard_caps() -> None:
    weights = _inverse_vol_nav_weights(
        [
            _candidate("LOWVOL", "0.1000"),
            _candidate("MIDVOL", "0.2000"),
            _candidate("HIGHVOL", "0.4000"),
        ],
        sleeve_target_pct_nav=Decimal("30.0"),
        normal_cap_pct_nav=Decimal("15.0"),
        hard_cap_pct_nav=Decimal("15.0"),
    )

    assert weights["LOWVOL"] == Decimal("15.0000")
    assert weights["MIDVOL"] > weights["HIGHVOL"]
    assert all(weight <= Decimal("15.0000") for weight in weights.values())


def test_core_rebalance_gate_obeys_monthly_and_drift_thresholds(tmp_path: Path) -> None:
    policy = load_money_management_policy(_write_policy(tmp_path, symbols=["INFY", "TCS"]))
    strategy = CoreShariahBasketStrategy(policy, max_stale_calendar_days=100)
    first = strategy.review(
        CoreBasketReviewInput(
            histories_by_symbol={
                "INFY": _candles("INFY", seed=1),
                "TCS": _candles("TCS", seed=2),
            },
            nav_inr=Decimal("1000000"),
            as_of_date=date(2024, 5, 20),
        )
    )
    current_positions = tuple(
        CoreBasketPosition(
            symbol=symbol,
            market_value_inr=Decimal(str(weight)) * Decimal("10000"),
        )
        for symbol, weight in first["target_weights"].items()
    )

    unchanged = strategy.review(
        CoreBasketReviewInput(
            histories_by_symbol={
                "INFY": _candles("INFY", seed=1),
                "TCS": _candles("TCS", seed=2),
            },
            nav_inr=Decimal("1000000"),
            current_positions=current_positions,
            as_of_date=date(2024, 5, 25),
            last_core_rebalance_date=date(2024, 5, 20),
        )
    )
    drifted = strategy.review(
        CoreBasketReviewInput(
            histories_by_symbol={
                "INFY": _candles("INFY", seed=1),
                "TCS": _candles("TCS", seed=2),
            },
            nav_inr=Decimal("1000000"),
            as_of_date=date(2024, 5, 25),
            last_core_rebalance_date=date(2024, 5, 20),
        )
    )
    next_month = strategy.review(
        CoreBasketReviewInput(
            histories_by_symbol={
                "INFY": _candles("INFY", seed=1),
                "TCS": _candles("TCS", seed=2),
            },
            nav_inr=Decimal("1000000"),
            current_positions=current_positions,
            as_of_date=date(2024, 6, 1),
            last_core_rebalance_date=date(2024, 5, 20),
        )
    )

    assert unchanged["rebalance"]["should_rebalance"] is False
    assert "monthly_gate_not_due" in unchanged["rebalance"]["rationale"]
    assert drifted["rebalance"]["should_rebalance"] is True
    assert "drift_threshold_exceeded" in drifted["rebalance"]["rationale"]
    assert next_month["rebalance"]["should_rebalance"] is True
    assert "monthly_core_rebalance_due" in next_month["rebalance"]["rationale"]


def _candidate(symbol: str, volatility: str) -> _CandidateScore:
    return _CandidateScore(
        symbol=symbol,
        realized_volatility=Decimal(volatility),
        liquidity_inr=Decimal("10000000"),
        trend_quality=Decimal("0.1000"),
        diversification_score=Decimal("1.0000"),
        rank_score=Decimal("1.0000"),
    )


def _candles(symbol: str, *, seed: int) -> list[DailyCandle]:
    base = Decimal("100") + Decimal(seed)
    candles: list[DailyCandle] = []
    for offset in range(140):
        close = base + Decimal(offset) * Decimal("0.20") + Decimal(seed) * Decimal("0.01")
        candles.append(
            DailyCandle(
                symbol=symbol,
                trade_date=date.fromordinal(date(2024, 1, 1).toordinal() + offset),
                open=close - Decimal("0.05"),
                high=close + Decimal("0.15"),
                low=close - Decimal("0.15"),
                close=close,
                volume=1_000_000 + (seed * 10_000),
                source="test",
            )
        )
    return candles


def _write_policy(tmp_path: Path, *, symbols: list[str]) -> Path:
    universe_path = tmp_path / "shariah.yaml"
    universe_path.write_text(
        "universe_name: test_shariah\n"
        "default_exchange: NSE\n"
        "default_segment: EQUITY\n"
        "symbols:\n"
        + "".join(
            "  - symbol: {symbol}\n"
            "    name: {symbol} Ltd.\n"
            "    enabled: true\n"
            "    providers:\n"
            "      kite:\n"
            "        exchange: NSE\n"
            "        tradingsymbol: {symbol}\n".format(symbol=symbol)
            for symbol in symbols
        ),
        encoding="utf-8",
    )
    policy_path = tmp_path / "money_management.yaml"
    policy_path.write_text(
        "policy_version: test_policy\n"
        f"shariah_universe_path: {universe_path}\n"
        "sleeves:\n"
        "  - sleeve_id: core_shariah\n"
        "    name: Core\n"
        "    target_weight_pct: 40.0\n"
        "    role: Core sleeve\n"
        "  - sleeve_id: active_strategy\n"
        "    name: Active\n"
        "    target_weight_pct: 35.0\n"
        "    role: Active sleeve\n"
        "  - sleeve_id: diversifying_strategy\n"
        "    name: Diversifying\n"
        "    target_weight_pct: 15.0\n"
        "    role: Diversifying sleeve\n"
        "  - sleeve_id: experimental_models\n"
        "    name: Experimental\n"
        "    target_weight_pct: 5.0\n"
        "    role: Experimental sleeve\n"
        "  - sleeve_id: cash_buffer\n"
        "    name: Cash\n"
        "    target_weight_pct: 5.0\n"
        "    role: Cash buffer\n"
        "strategy_mappings:\n"
        "  - strategy_name: core_shariah_basket_v1\n"
        "    sleeve_id: core_shariah\n"
        "limits:\n"
        "  max_stock_pct_nav: 5.0\n"
        "  max_stock_hard_cap_pct_nav: 7.5\n"
        "  max_sector_pct_nav: 25.0\n"
        "  max_graph_cluster_pct_nav: 35.0\n"
        "  max_open_positions: 20\n"
        "trade_risk:\n"
        "  normal_trade_risk_pct_nav: 0.50\n"
        "  strong_trade_risk_pct_nav: 0.75\n"
        "  max_single_trade_risk_pct_nav: 1.00\n"
        "  max_total_open_trade_risk_pct_nav: 5.00\n"
        "rebalance:\n"
        "  sleeve_drift_threshold_pct: 20.0\n"
        "  min_rebalance_notional_inr: 5000\n"
        "  review_frequency: daily_after_close\n"
        "  core_rebalance_frequency: monthly\n",
        encoding="utf-8",
    )
    return policy_path
