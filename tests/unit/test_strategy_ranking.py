from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.store import FeatureSnapshot
from taurus_core.strategies.blended_score import BlendedScoreStrategy
from taurus_core.strategies.config import load_strategy_config
from taurus_core.strategies.graph_aware import GraphAwareScoreStrategy
from taurus_core.strategies.mock_momentum import MockMomentumStrategy
from taurus_core.strategies.moving_average_crossover import MovingAverageCrossoverStrategy


def test_missing_target_positions_stays_unset(tmp_path: Path) -> None:
    path = tmp_path / "strategy.yaml"
    path.write_text(
        "strategy_name: ranking_test\n"
        "strategy_type: moving_average_crossover\n"
        "lookback_days: 60\n"
        "rebalance_every_days: 21\n"
        "parameters:\n"
        "  fast_window: 1\n"
        "  slow_window: 2\n",
        encoding="utf-8",
    )

    config = load_strategy_config(path)

    assert config.target_positions is None


def test_moving_average_ranks_all_eligible_symbols_and_caps_only_when_requested() -> None:
    strategy = MovingAverageCrossoverStrategy(
        name="ma_test",
        parameters={"fast_window": 1, "slow_window": 2, "min_return_20d": -1},
    )
    features = {
        "AAA": _feature_snapshot(
            "AAA",
            {
                "sma_1": Decimal("120"),
                "sma_2": Decimal("100"),
                "return_20d": Decimal("0.01"),
            },
        ),
        "BBB": _feature_snapshot(
            "BBB",
            {
                "sma_1": Decimal("110"),
                "sma_2": Decimal("100"),
                "return_20d": Decimal("0.01"),
            },
        ),
        "CCC": _feature_snapshot(
            "CCC",
            {
                "sma_1": Decimal("90"),
                "sma_2": Decimal("100"),
                "return_20d": Decimal("0.01"),
            },
        ),
    }

    rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
    )
    uncapped_targets, _signals = strategy.select_targets(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
    )
    capped_targets, capped_signals = strategy.select_targets(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
        target_limit=1,
    )

    assert [ranking.symbol for ranking in rankings if ranking.is_eligible] == ["AAA", "BBB"]
    assert {ranking.symbol for ranking in rankings if not ranking.is_eligible} == {"CCC"}
    assert uncapped_targets == {"AAA", "BBB"}
    assert capped_targets == {"AAA"}
    assert [signal.symbol for signal in capped_signals] == ["AAA"]


def test_blended_score_ranks_all_eligible_symbols() -> None:
    strategy = BlendedScoreStrategy(
        name="blend_test",
        parameters={"min_score": "-1", "min_return_20d": "-1"},
    )
    features = {
        "AAA": _feature_snapshot("AAA", _blended_values(return_20d=Decimal("0.08"))),
        "BBB": _feature_snapshot("BBB", _blended_values(return_20d=Decimal("0.04"))),
        "CCC": _feature_snapshot("CCC", {"return_20d": Decimal("0.02")}),
    }

    rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
    )

    assert [ranking.symbol for ranking in rankings if ranking.is_eligible] == ["AAA", "BBB"]
    assert {ranking.symbol for ranking in rankings if not ranking.is_eligible} == {"CCC"}


def test_graph_aware_technical_score_requires_fast_and_slow_sma() -> None:
    strategy = GraphAwareScoreStrategy(
        name="graph_aware_missing_sma_test",
        parameters={"fast_window": 3, "slow_window": 5},
    )

    assert (
        strategy._technical_score(_feature_snapshot("AAA", {"sma_3": Decimal("101")}))
        is None
    )
    assert (
        strategy._technical_score(_feature_snapshot("AAA", {"sma_5": Decimal("100")}))
        is None
    )
    assert (
        strategy._technical_score(
            _feature_snapshot(
                "AAA",
                {
                    "sma_3": Decimal("101"),
                    "sma_5": Decimal("0"),
                },
            )
        )
        is None
    )


def test_graph_aware_technical_score_quantizes_sma_spread() -> None:
    strategy = GraphAwareScoreStrategy(
        name="graph_aware_sma_spread_test",
        parameters={"fast_window": 3, "slow_window": 5},
    )

    score = strategy._technical_score(
        _feature_snapshot(
            "AAA",
            {
                "sma_3": Decimal("112.34567890"),
                "sma_5": Decimal("100.00000000"),
            },
        )
    )

    assert score == Decimal("0.12345679")


def test_mock_momentum_legacy_selection_uses_explicit_cap_only() -> None:
    strategy = MockMomentumStrategy(lookback_days=2, target_positions=1)
    history = {
        "AAA": _candles("AAA", "100", "105", "120"),
        "BBB": _candles("BBB", "100", "104", "110"),
        "CCC": _candles("CCC", "100", "99", "98"),
    }

    rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 10),
        history_by_symbol=history,
        current_positions=set(),
    )
    uncapped_targets, _signals = strategy.select_targets(
        trade_date=date(2024, 1, 10),
        history_by_symbol=history,
        current_positions=set(),
    )
    capped_targets, _signals = strategy.select_targets(
        trade_date=date(2024, 1, 10),
        history_by_symbol=history,
        current_positions=set(),
        target_limit=1,
    )

    assert [ranking.symbol for ranking in rankings if ranking.is_eligible] == ["AAA", "BBB"]
    assert uncapped_targets == {"AAA", "BBB"}
    assert capped_targets == {"AAA"}


def _feature_snapshot(symbol: str, values: dict[str, Decimal]) -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=f"fs-{symbol}",
        symbol=symbol,
        as_of_date=date(2024, 1, 10),
        feature_time=date(2024, 1, 9),
        values=values,
        rows=(),
    )


def _blended_values(*, return_20d: Decimal) -> dict[str, Decimal]:
    return {
        "return_20d": return_20d,
        "return_5d": Decimal("0.01"),
        "ema_12": Decimal("110"),
        "ema_26": Decimal("100"),
        "rsi_14": Decimal("55"),
        "volatility_20": Decimal("0.01"),
        "volume_z_score_20": Decimal("0.5"),
    }


def _candles(symbol: str, *closes: str) -> list[DailyCandle]:
    return [
        DailyCandle(
            symbol=symbol,
            trade_date=date(2024, 1, index + 1),
            open=Decimal(close),
            high=Decimal(close),
            low=Decimal(close),
            close=Decimal(close),
            volume=1_000,
            source="test_fixture",
        )
        for index, close in enumerate(closes)
    ]
