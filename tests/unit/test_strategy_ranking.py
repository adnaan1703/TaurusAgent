from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from taurus_core.domain.market_data import DailyCandle
from taurus_core.features.store import (
    TECHNICAL_OHLCV_V2_FEATURE_VERSION,
    FeatureSnapshot,
    TechnicalFeatureService,
)
from taurus_core.features.technical_context import build_universe_technical_context
from taurus_core.features.technical_context import (
    OfficialIndexFeature,
    OfficialMicrostructureFeature,
    OfficialTechnicalContext,
    OfficialTechnicalSymbolContext,
)
from taurus_core.features.technical_signal import (
    OFFICIAL_V2B_PROFILE,
    OHLCV_V2_PROFILE,
    TechnicalSignalService,
)
from taurus_core.strategies.blended_score import BlendedScoreStrategy
from taurus_core.strategies.config import load_strategy_config
from taurus_core.strategies.graph_aware import GraphAwareScoreStrategy
from taurus_core.strategies.mock_momentum import MockMomentumStrategy
from taurus_core.strategies.moving_average_crossover import (
    MovingAverageCrossoverStrategy,
)


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


def test_moving_average_ranks_all_eligible_symbols_and_caps_only_when_requested() -> (
    None
):
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

    assert [ranking.symbol for ranking in rankings if ranking.is_eligible] == [
        "AAA",
        "BBB",
    ]
    assert {ranking.symbol for ranking in rankings if not ranking.is_eligible} == {
        "CCC"
    }
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

    assert [ranking.symbol for ranking in rankings if ranking.is_eligible] == [
        "AAA",
        "BBB",
    ]
    assert {ranking.symbol for ranking in rankings if not ranking.is_eligible} == {
        "CCC"
    }


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


def test_graph_aware_v2_config_selects_ohlcv_profile_and_feature_version() -> None:
    config = load_strategy_config("configs/strategies/graph_aware_score_v2.yaml")
    feature_service = TechnicalFeatureService.from_strategy_parameters(
        config.parameters
    )
    strategy = GraphAwareScoreStrategy(
        name=config.strategy_name,
        parameters=config.parameters,
    )

    assert config.strategy_name == "graph_aware_score_v2"
    assert config.strategy_type == "graph_aware_score"
    assert config.lookback_days == 756
    assert config.parameters["technical_analyst_profile"] == OHLCV_V2_PROFILE
    assert config.parameters["technical_profile"] == OHLCV_V2_PROFILE
    assert (
        config.parameters["technical_feature_version"]
        == TECHNICAL_OHLCV_V2_FEATURE_VERSION
    )
    assert feature_service.feature_version == TECHNICAL_OHLCV_V2_FEATURE_VERSION
    assert strategy.technical_profile == OHLCV_V2_PROFILE


def test_graph_aware_v2b_config_selects_official_profile_without_changing_v2a() -> None:
    v2_config = load_strategy_config("configs/strategies/graph_aware_score_v2.yaml")
    v2b_config = load_strategy_config("configs/strategies/graph_aware_score_v2b.yaml")
    feature_service = TechnicalFeatureService.from_strategy_parameters(
        v2b_config.parameters
    )
    strategy = GraphAwareScoreStrategy(
        name=v2b_config.strategy_name,
        parameters=v2b_config.parameters,
    )

    assert v2_config.parameters["technical_profile"] == OHLCV_V2_PROFILE
    assert v2b_config.strategy_name == "graph_aware_score_v2b"
    assert v2b_config.strategy_type == "graph_aware_score"
    assert v2b_config.lookback_days == 756
    assert v2b_config.parameters["technical_analyst_profile"] == OFFICIAL_V2B_PROFILE
    assert v2b_config.parameters["technical_profile"] == OFFICIAL_V2B_PROFILE
    assert (
        v2b_config.parameters["technical_feature_version"]
        == TECHNICAL_OHLCV_V2_FEATURE_VERSION
    )
    assert v2b_config.parameters["official_data"]["benchmark_index_symbol"] == "NIFTY_50"
    assert feature_service.feature_version == TECHNICAL_OHLCV_V2_FEATURE_VERSION
    assert strategy.technical_profile == OFFICIAL_V2B_PROFILE


def test_graph_aware_v2_ranking_uses_ohlcv_signal_and_nested_metadata() -> None:
    strategy = GraphAwareScoreStrategy(
        name="graph_aware_v2_context_test",
        parameters={
            "technical_profile": OHLCV_V2_PROFILE,
            "technical_weight": "1",
            "graph_weight": "0",
            "min_combined_score": "-1",
        },
    )
    features = {
        "AAA": _feature_snapshot("AAA", _ohlcv_v2_values(momentum="strong")),
        "BBB": _feature_snapshot("BBB", _ohlcv_v2_values(momentum="weak")),
    }
    context = build_universe_technical_context(features)
    expected_aaa = TechnicalSignalService().score_ohlcv_v2(
        features["AAA"],
        universe_context=context,
    )

    rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
        universe_technical_context=context,
    )
    targets, signals = strategy.select_targets_with_graph(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
        graph_signals_by_symbol={},
        target_limit=1,
    )

    assert [ranking.symbol for ranking in rankings if ranking.is_eligible] == [
        "AAA",
        "BBB",
    ]
    assert rankings[0].raw_strategy_score == expected_aaa.score
    assert rankings[0].metadata["technical_score"] == str(expected_aaa.composite_score)
    technical_v2 = rankings[0].metadata["technical_v2"]
    assert technical_v2["profile_name"] == OHLCV_V2_PROFILE
    assert technical_v2["alpha_score"] == str(expected_aaa.alpha_score)
    assert technical_v2["risk_score"] == str(expected_aaa.risk_score)
    assert technical_v2["tradability_score"] == str(expected_aaa.tradability_score)
    assert technical_v2["confidence"] == str(expected_aaa.confidence)
    assert technical_v2["composite_score"] == str(expected_aaa.composite_score)
    assert technical_v2["coverage"] == str(expected_aaa.coverage)
    assert technical_v2["missing_features"] == []
    assert technical_v2["top_contributors"]
    assert targets == {"AAA"}
    assert (
        signals[0].explanation.metadata["technical_v2"]["profile_name"]
        == OHLCV_V2_PROFILE
    )


def test_graph_aware_v2_scoring_params_are_profile_gated() -> None:
    v1_strategy = GraphAwareScoreStrategy(
        name="graph_aware_v1_ignores_v2_params",
        parameters={
            "fast_window": 3,
            "slow_window": 5,
            "min_combined_score": "-1",
            "technical_ohlcv_v2_params": {"alpha_weights": {"not_real": "1"}},
        },
    )
    v2_strategy = GraphAwareScoreStrategy(
        name="graph_aware_v2_compressed",
        parameters={
            "technical_profile": OHLCV_V2_PROFILE,
            "technical_weight": "1",
            "graph_weight": "0",
            "min_combined_score": "-1",
            "technical_ohlcv_v2_params": {
                "score_compression": {
                    "mode": "linear",
                    "lower_bound": "0",
                    "upper_bound": "0.20",
                }
            },
        },
    )
    features = {
        "AAA": _feature_snapshot("AAA", _ohlcv_v2_values(momentum="strong")),
        "BBB": _feature_snapshot("BBB", _ohlcv_v2_values(momentum="weak")),
    }

    assert v1_strategy._technical_score(
        _feature_snapshot(
            "AAA",
            {
                "sma_3": Decimal("110"),
                "sma_5": Decimal("100"),
            },
        )
    ) == Decimal("0.10000000")
    rankings = v2_strategy.rank_universe(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
        target_limit=1,
    )

    assert rankings[0].raw_strategy_score <= Decimal("0.20000000")
    assert (
        rankings[0].metadata["technical_v2"]["metadata"]["score_compression"]["mode"]
        == "linear"
    )
    with pytest.raises(ValueError, match="Unknown v2A scoring parameter"):
        GraphAwareScoreStrategy(
            name="graph_aware_v2_bad_params",
            parameters={
                "technical_profile": OHLCV_V2_PROFILE,
                "technical_ohlcv_v2_params": {"alpha_weights": {"not_real": "1"}},
            },
        )


def test_graph_aware_v2_risk_gate_blocks_new_buys_only_when_configured() -> None:
    strategy = GraphAwareScoreStrategy(
        name="graph_aware_v2_risk_gate",
        parameters={
            "technical_profile": OHLCV_V2_PROFILE,
            "technical_weight": "1",
            "graph_weight": "0",
            "min_combined_score": "-1",
            "technical_ohlcv_v2_params": {
                "eligibility": {"min_risk_score_for_new_buys": "0.95"}
            },
        },
    )
    features = {
        "AAA": _feature_snapshot("AAA", _ohlcv_v2_values(momentum="strong")),
    }

    new_buy_rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
        target_limit=1,
    )
    existing_position_rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions={"AAA"},
        target_limit=1,
    )

    assert new_buy_rankings[0].is_eligible is False
    assert new_buy_rankings[0].raw_strategy_score is None
    assert (
        new_buy_rankings[0].metadata["technical_v2"]["metadata"]["guardrail"][
            "blocked"
        ]
        is True
    )
    assert existing_position_rankings[0].is_eligible is True
    assert existing_position_rankings[0].action_intent == "HOLD"


def test_graph_aware_v2b_ranking_uses_official_context_and_metadata() -> None:
    strategy = GraphAwareScoreStrategy(
        name="graph_aware_v2b_context_test",
        parameters={
            "technical_profile": OFFICIAL_V2B_PROFILE,
            "technical_weight": "1",
            "graph_weight": "0",
            "min_combined_score": "-1",
        },
    )
    features = {
        "AAA": _feature_snapshot("AAA", _ohlcv_v2_values(momentum="strong")),
        "BBB": _feature_snapshot("BBB", _ohlcv_v2_values(momentum="weak")),
    }
    universe_context = build_universe_technical_context(features)
    official_context = _official_context()
    expected_aaa = TechnicalSignalService().score_official_v2b(
        features["AAA"],
        universe_context=universe_context,
        official_context=official_context,
    )

    rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
        universe_technical_context=universe_context,
        official_technical_context=official_context,
    )
    targets, signals = strategy.select_targets_with_graph(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
        graph_signals_by_symbol={},
        target_limit=1,
        universe_technical_context=universe_context,
        official_technical_context=official_context,
    )

    assert rankings[0].symbol == "AAA"
    assert rankings[0].raw_strategy_score == expected_aaa.score
    technical_v2 = rankings[0].metadata["technical_v2"]
    assert technical_v2["profile_name"] == OFFICIAL_V2B_PROFILE
    assert technical_v2["score_source"] == OFFICIAL_V2B_PROFILE
    assert technical_v2["metadata"]["official_coverage"] == "1.0000"
    assert targets == {"AAA"}
    assert (
        signals[0].explanation.metadata["technical_v2"]["profile_name"]
        == OFFICIAL_V2B_PROFILE
    )


def test_graph_aware_v2b_missing_official_context_is_ineligible() -> None:
    strategy = GraphAwareScoreStrategy(
        name="graph_aware_v2b_missing_official_context_test",
        parameters={
            "technical_profile": OFFICIAL_V2B_PROFILE,
            "technical_weight": "1",
            "graph_weight": "0",
            "min_combined_score": "-1",
        },
    )
    features = {"AAA": _feature_snapshot("AAA", _ohlcv_v2_values(momentum="strong"))}

    rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
    )

    assert rankings[0].symbol == "AAA"
    assert rankings[0].is_eligible is False
    assert rankings[0].metadata["technical_v2"]["profile_name"] == OFFICIAL_V2B_PROFILE
    assert (
        rankings[0].metadata["technical_v2"]["metadata"]["unavailable_reason"]
        == "missing_official_context"
    )


def test_graph_aware_v1_ranking_stays_sma_spread_driven_with_universe_context() -> None:
    strategy = GraphAwareScoreStrategy(
        name="graph_aware_v1_context_guard",
        parameters={"fast_window": 3, "slow_window": 5, "min_combined_score": "-1"},
    )
    features = {
        "AAA": _feature_snapshot(
            "AAA",
            {
                "sma_3": Decimal("115"),
                "sma_5": Decimal("100"),
                "return_20d": Decimal("0.01"),
                "return_63d": Decimal("0.01"),
            },
        ),
        "BBB": _feature_snapshot(
            "BBB",
            {
                "sma_3": Decimal("110"),
                "sma_5": Decimal("100"),
                "return_20d": Decimal("0.01"),
                "return_63d": Decimal("0.20"),
            },
        ),
    }

    context = build_universe_technical_context(features, feature_names=("return_63d",))
    rankings = strategy.rank_universe(
        trade_date=date(2024, 1, 10),
        features_by_symbol=features,
        current_positions=set(),
    )

    assert context.feature_for_symbol("BBB", "return_63d").rank == 1
    assert [ranking.symbol for ranking in rankings if ranking.is_eligible] == [
        "AAA",
        "BBB",
    ]
    assert [
        ranking.raw_strategy_score for ranking in rankings if ranking.is_eligible
    ] == [
        Decimal("0.15000000"),
        Decimal("0.10000000"),
    ]
    assert rankings[0].metadata["technical_score"] == "0.15000000"


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

    assert [ranking.symbol for ranking in rankings if ranking.is_eligible] == [
        "AAA",
        "BBB",
    ]
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


def _ohlcv_v2_values(*, momentum: str) -> dict[str, Decimal]:
    if momentum == "strong":
        return {
            "return_20d": Decimal("0.06000000"),
            "return_63d": Decimal("0.18000000"),
            "return_126d": Decimal("0.32000000"),
            "return_252d": Decimal("0.52000000"),
            "vol_adjusted_return_63d": Decimal("3.10000000"),
            "vol_adjusted_return_126d": Decimal("3.60000000"),
            "vol_adjusted_return_252d": Decimal("3.80000000"),
            "ema_12": Decimal("124.00000000"),
            "ema_26": Decimal("110.00000000"),
            "macd_histogram_12_26_9": Decimal("0.35000000"),
            "adx_14": Decimal("34.00000000"),
            "plus_di_14": Decimal("38.00000000"),
            "minus_di_14": Decimal("14.00000000"),
            "rsi_14": Decimal("64.00000000"),
            "bollinger_percent_b_20": Decimal("0.68000000"),
            "bollinger_bandwidth_20": Decimal("0.07000000"),
            "breakout_high_distance_20d": Decimal("0.03000000"),
            "breakout_high_distance_50d": Decimal("0.05000000"),
            "breakout_high_distance_252d": Decimal("-0.01000000"),
            "distance_from_52w_high": Decimal("-0.02000000"),
            "atr_percent_14": Decimal("0.01800000"),
            "volatility_20": Decimal("0.01800000"),
            "volatility_63": Decimal("0.02100000"),
            "volatility_126": Decimal("0.02400000"),
            "volatility_252": Decimal("0.02600000"),
            "volume_z_score_20": Decimal("1.60000000"),
            "turnover": Decimal("125000000.00000000"),
            "avg_traded_value_20": Decimal("112000000.00000000"),
            "avg_traded_value_63": Decimal("98000000.00000000"),
            "turnover_z_score_20": Decimal("1.40000000"),
        }
    return {
        "return_20d": Decimal("-0.01000000"),
        "return_63d": Decimal("0.02000000"),
        "return_126d": Decimal("0.04000000"),
        "return_252d": Decimal("0.06000000"),
        "vol_adjusted_return_63d": Decimal("0.50000000"),
        "vol_adjusted_return_126d": Decimal("0.60000000"),
        "vol_adjusted_return_252d": Decimal("0.70000000"),
        "ema_12": Decimal("101.00000000"),
        "ema_26": Decimal("100.00000000"),
        "macd_histogram_12_26_9": Decimal("-0.05000000"),
        "adx_14": Decimal("18.00000000"),
        "plus_di_14": Decimal("20.00000000"),
        "minus_di_14": Decimal("22.00000000"),
        "rsi_14": Decimal("47.00000000"),
        "bollinger_percent_b_20": Decimal("0.43000000"),
        "bollinger_bandwidth_20": Decimal("0.17000000"),
        "breakout_high_distance_20d": Decimal("-0.06000000"),
        "breakout_high_distance_50d": Decimal("-0.09000000"),
        "breakout_high_distance_252d": Decimal("-0.22000000"),
        "distance_from_52w_high": Decimal("-0.24000000"),
        "atr_percent_14": Decimal("0.04700000"),
        "volatility_20": Decimal("0.05200000"),
        "volatility_63": Decimal("0.04900000"),
        "volatility_126": Decimal("0.04700000"),
        "volatility_252": Decimal("0.04500000"),
        "volume_z_score_20": Decimal("-0.30000000"),
        "turnover": Decimal("24000000.00000000"),
        "avg_traded_value_20": Decimal("26000000.00000000"),
        "avg_traded_value_63": Decimal("28000000.00000000"),
        "turnover_z_score_20": Decimal("-0.40000000"),
    }


def _official_context() -> OfficialTechnicalContext:
    benchmark = OfficialIndexFeature(
        index_symbol="NIFTY_50",
        index_family="benchmark",
        trade_date=date(2024, 1, 9),
        close=Decimal("100"),
        return_20d=Decimal("0.03000000"),
        return_63d=Decimal("0.08000000"),
        regime_state="bullish",
        source="nse",
    )
    volatility = OfficialIndexFeature(
        index_symbol="INDIA_VIX",
        index_family="volatility",
        trade_date=date(2024, 1, 9),
        close=Decimal("13"),
        return_20d=Decimal("-0.05000000"),
        return_63d=Decimal("-0.10000000"),
        regime_state="calm",
        source="nse",
    )
    contexts = {
        "AAA": _official_symbol_context(
            "AAA",
            benchmark=benchmark,
            volatility=volatility,
            market_relative_return_20d=Decimal("0.03000000"),
            delivery_state="high_participation",
            delivery_z_score=Decimal("1.50000000"),
            implementability_score=Decimal("0.8000"),
        ),
        "BBB": _official_symbol_context(
            "BBB",
            benchmark=benchmark,
            volatility=volatility,
            market_relative_return_20d=Decimal("-0.05000000"),
            delivery_state="low_participation",
            delivery_z_score=Decimal("-1.20000000"),
            implementability_score=Decimal("-0.4000"),
        ),
    }
    return OfficialTechnicalContext(
        profile_name=OFFICIAL_V2B_PROFILE,
        as_of_date=date(2024, 1, 10),
        benchmark_index_symbol="NIFTY_50",
        volatility_index_symbol="INDIA_VIX",
        symbols=tuple(contexts),
        symbol_contexts=contexts,
    )


def _official_symbol_context(
    symbol: str,
    *,
    benchmark: OfficialIndexFeature,
    volatility: OfficialIndexFeature,
    market_relative_return_20d: Decimal,
    delivery_state: str,
    delivery_z_score: Decimal,
    implementability_score: Decimal,
) -> OfficialTechnicalSymbolContext:
    microstructure = OfficialMicrostructureFeature(
        symbol=symbol,
        trade_date=date(2024, 1, 9),
        delivery_percentage=Decimal("55"),
        delivery_z_score=delivery_z_score,
        delivery_state=delivery_state,
        circuit_status="none",
        circuit_hit=False,
        near_circuit=False,
        impact_cost_bps=Decimal("12"),
        impact_cost_source_kind="proxy",
        impact_cost_proxy_name="avg_trade_value_proxy",
        implementability_score=implementability_score,
        implementability_label="impact_cost_proxy:avg_trade_value_proxy",
        source="nse",
    )
    return OfficialTechnicalSymbolContext(
        symbol=symbol,
        as_of_date=date(2024, 1, 10),
        benchmark_index=benchmark,
        sector_index=None,
        volatility_index=volatility,
        microstructure=microstructure,
        market_relative_return_20d=market_relative_return_20d,
        sector_relative_return_20d=None,
        source_coverage={
            "benchmark": True,
            "volatility": True,
            "delivery": True,
            "circuit": True,
            "tradability": True,
        },
    )


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
