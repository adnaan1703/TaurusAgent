from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from taurus_core.config import Settings
from taurus_core.db.repositories import (
    OfficialIndexCandleRepository,
    OfficialSecurityMicrostructureRepository,
)
from taurus_core.db.session import build_session_factory
from taurus_core.domain.official_market_data import (
    OfficialIndexCandle,
    OfficialSecurityMicrostructure,
)
from taurus_core.features.official_context import (
    build_official_technical_context,
    official_context_with_snapshot_returns,
)
from taurus_core.features.store import FeatureSnapshot
from taurus_core.features.technical_context import build_universe_technical_context
from taurus_core.features.technical_signal import (
    OFFICIAL_V2B_PROFILE,
    OHLCV_V2_PROFILE,
    TechnicalSignalService,
)


def test_official_technical_context_joins_as_of_without_lookahead(
    postgres_test_settings: Settings,
) -> None:
    session_factory = build_session_factory(postgres_test_settings)
    with session_factory() as session:
        OfficialIndexCandleRepository(session).upsert(
            [
                *_index_history("NIFTY_50", "benchmark", start_close=Decimal("100")),
                *_index_history("NIFTY_IT", "sector", start_close=Decimal("200")),
                *_index_history("INDIA_VIX", "volatility", start_close=Decimal("12")),
            ]
        )
        OfficialSecurityMicrostructureRepository(session).upsert(_micro_history())
        session.commit()

    with session_factory() as session:
        context = build_official_technical_context(
            session,
            symbols=("INFY",),
            as_of=datetime(2024, 1, 27, tzinfo=timezone.utc),
            sector_index_by_symbol={"INFY": "NIFTY_IT"},
        )
        enriched = official_context_with_snapshot_returns(
            context,
            {"INFY": Decimal("0.25000000")},
        )

    symbol_context = enriched.for_symbol("INFY")

    assert symbol_context is not None
    assert symbol_context.benchmark_index is not None
    assert symbol_context.sector_index is not None
    assert symbol_context.volatility_index is not None
    assert symbol_context.microstructure is not None
    assert symbol_context.benchmark_index.trade_date == date(2024, 1, 25)
    assert symbol_context.sector_index.trade_date == date(2024, 1, 25)
    assert symbol_context.microstructure.trade_date == date(2024, 1, 25)
    assert symbol_context.market_relative_return_20d is not None
    assert symbol_context.sector_relative_return_20d is not None
    assert symbol_context.source_coverage == {
        "benchmark": True,
        "volatility": True,
        "delivery": True,
        "circuit": True,
        "tradability": True,
        "sector": True,
    }
    assert symbol_context.missing_features == ()


def test_score_official_v2b_uses_official_context_and_marks_missing_data(
    postgres_test_settings: Settings,
) -> None:
    session_factory = build_session_factory(postgres_test_settings)
    snapshots = {
        "INFY": _feature_snapshot("INFY", _ohlcv_values("strong")),
        "TCS": _feature_snapshot("TCS", _ohlcv_values("weak")),
    }
    universe_context = build_universe_technical_context(snapshots)
    with session_factory() as session:
        OfficialIndexCandleRepository(session).upsert(
            [
                *_index_history("NIFTY_50", "benchmark", start_close=Decimal("100")),
                *_index_history("INDIA_VIX", "volatility", start_close=Decimal("12")),
            ]
        )
        OfficialSecurityMicrostructureRepository(session).upsert(_micro_history())
        session.commit()

    with session_factory() as session:
        official_context = official_context_with_snapshot_returns(
            build_official_technical_context(
                session,
                symbols=tuple(snapshots),
                as_of=date(2024, 1, 27),
            ),
            {
                symbol: snapshot.get("return_20d")
                for symbol, snapshot in snapshots.items()
            },
        )

    service = TechnicalSignalService()
    v2a_result = service.score_ohlcv_v2(
        snapshots["INFY"],
        universe_context=universe_context,
    )
    v2b_result = service.score_official_v2b(
        snapshots["INFY"],
        universe_context=universe_context,
        official_context=official_context,
    )
    missing_result = service.score_official_v2b(
        snapshots["INFY"],
        universe_context=universe_context,
    )

    assert v2a_result.profile_name == OHLCV_V2_PROFILE
    assert v2b_result.profile_name == OFFICIAL_V2B_PROFILE
    assert v2b_result.available is True
    assert v2b_result.score_source == OFFICIAL_V2B_PROFILE
    assert v2b_result.metadata["base_profile_name"] == OHLCV_V2_PROFILE
    assert v2b_result.metadata["source_coverage"] == {
        "benchmark": True,
        "volatility": True,
        "delivery": True,
        "circuit": True,
        "tradability": True,
    }
    assert v2b_result.metadata["official_coverage"] == "1.0000"
    assert any(
        contributor["source"] == "official_data"
        for contributor in v2b_result.top_contributors
    )
    assert any(source.startswith("official_index:benchmark") for source in v2b_result.source_ids)
    assert any(
        source.startswith("official_microstructure:INFY")
        for source in v2b_result.source_ids
    )
    assert missing_result.available is False
    assert missing_result.metadata["unavailable_reason"] == "missing_official_context"
    assert missing_result.confidence == Decimal("0.0000")


def _index_history(
    index_symbol: str,
    index_family: str,
    *,
    start_close: Decimal,
) -> list[OfficialIndexCandle]:
    rows = [
        OfficialIndexCandle(
            index_symbol=index_symbol,
            index_name=index_symbol.replace("_", " ").title(),
            index_family=index_family,
            trade_date=date(2024, 1, day),
            open=start_close + Decimal(day),
            high=start_close + Decimal(day),
            low=start_close + Decimal(day),
            close=start_close + Decimal(day),
            source="nse",
            data_available_time=datetime(
                2024,
                1,
                day,
                18,
                tzinfo=timezone.utc,
            )
            + timedelta(days=1),
        )
        for day in range(1, 26)
    ]
    rows.append(
        OfficialIndexCandle(
            index_symbol=index_symbol,
            index_name=index_symbol.replace("_", " ").title(),
            index_family=index_family,
            trade_date=date(2024, 1, 26),
            open=start_close + Decimal("1000"),
            high=start_close + Decimal("1000"),
            low=start_close + Decimal("1000"),
            close=start_close + Decimal("1000"),
            source="nse",
            data_available_time=datetime(2024, 2, 1, 9, tzinfo=timezone.utc),
        )
    )
    return rows


def _micro_history() -> list[OfficialSecurityMicrostructure]:
    rows = [
        OfficialSecurityMicrostructure(
            symbol="INFY",
            trade_date=date(2024, 1, day),
            source="nse_security_wise_csv",
            data_available_time=datetime(2024, 1, day, 18, tzinfo=timezone.utc)
            + timedelta(days=1),
            delivery_quantity=10_000 + day,
            delivery_percentage=Decimal("45") + Decimal(day) / Decimal("10"),
            price_band_percent=Decimal("20"),
            circuit_status="none",
            circuit_hit=False,
            impact_cost_bps=Decimal("12"),
            impact_cost_source_kind="proxy",
            impact_cost_proxy_name="avg_trade_value_proxy",
            average_trade_value=Decimal("75000000"),
            turnover=Decimal("100000000"),
        )
        for day in range(1, 26)
    ]
    rows.append(
        OfficialSecurityMicrostructure(
            symbol="INFY",
            trade_date=date(2024, 1, 26),
            source="nse_security_wise_csv",
            data_available_time=datetime(2024, 2, 1, 9, tzinfo=timezone.utc),
            delivery_quantity=999_999,
            delivery_percentage=Decimal("1"),
            price_band_percent=Decimal("20"),
            circuit_status="upper_circuit",
            circuit_hit=True,
            impact_cost_bps=Decimal("90"),
            impact_cost_source_kind="proxy",
            impact_cost_proxy_name="avg_trade_value_proxy",
        )
    )
    return rows


def _feature_snapshot(symbol: str, values: dict[str, Decimal]) -> FeatureSnapshot:
    return FeatureSnapshot(
        snapshot_id=f"fs-{symbol}",
        symbol=symbol,
        as_of_date=date(2024, 1, 27),
        feature_time=date(2024, 1, 25),
        values=values,
        rows=(),
    )


def _ohlcv_values(profile: str) -> dict[str, Decimal]:
    base = {
        "return_20d": "0.05000000",
        "return_63d": "0.14000000",
        "return_126d": "0.22000000",
        "return_252d": "0.34000000",
        "vol_adjusted_return_63d": "2.00000000",
        "vol_adjusted_return_126d": "2.50000000",
        "vol_adjusted_return_252d": "3.00000000",
        "ema_12": "110.00000000",
        "ema_26": "100.00000000",
        "macd_histogram_12_26_9": "1.50000000",
        "adx_14": "35.00000000",
        "plus_di_14": "35.00000000",
        "minus_di_14": "12.00000000",
        "rsi_14": "62.00000000",
        "bollinger_percent_b_20": "0.65000000",
        "bollinger_bandwidth_20": "0.08000000",
        "breakout_high_distance_20d": "0.02000000",
        "breakout_high_distance_50d": "0.04000000",
        "breakout_high_distance_252d": "0.03000000",
        "distance_from_52w_high": "-0.03000000",
        "atr_percent_14": "0.01500000",
        "volatility_20": "0.01500000",
        "volatility_63": "0.01800000",
        "volatility_126": "0.02000000",
        "volatility_252": "0.02200000",
        "volume_z_score_20": "1.50000000",
        "turnover": "10000000.00000000",
        "avg_traded_value_20": "9000000.00000000",
        "avg_traded_value_63": "8000000.00000000",
        "turnover_z_score_20": "1.20000000",
    }
    if profile == "weak":
        base.update(
            {
                "return_20d": "-0.04000000",
                "return_63d": "-0.08000000",
                "return_126d": "-0.12000000",
                "return_252d": "-0.20000000",
                "vol_adjusted_return_63d": "-0.80000000",
                "vol_adjusted_return_126d": "-1.00000000",
                "vol_adjusted_return_252d": "-1.20000000",
                "ema_12": "95.00000000",
                "macd_histogram_12_26_9": "-0.80000000",
                "plus_di_14": "15.00000000",
                "minus_di_14": "32.00000000",
                "rsi_14": "38.00000000",
                "volatility_20": "0.05000000",
                "volume_z_score_20": "-1.00000000",
                "turnover": "1000000.00000000",
                "turnover_z_score_20": "-0.80000000",
            }
        )
    return {name: Decimal(value) for name, value in base.items()}
