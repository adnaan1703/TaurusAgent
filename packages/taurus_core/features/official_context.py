from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.db.models import (
    OfficialIndexCandleModel,
    OfficialSecurityMicrostructureModel,
)
from taurus_core.db.repositories import (
    OfficialIndexCandleRepository,
    OfficialSecurityMicrostructureRepository,
)
from taurus_core.features.technical_context import (
    DEFAULT_OFFICIAL_BENCHMARK_INDEX_SYMBOL,
    DEFAULT_OFFICIAL_VOLATILITY_INDEX_SYMBOL,
    OfficialIndexFeature,
    OfficialMicrostructureFeature,
    OfficialTechnicalContext,
    OfficialTechnicalSymbolContext,
    TECHNICAL_OFFICIAL_V2B_PROFILE,
)

INDEX_RETURN_WINDOW_SHORT = 20
INDEX_RETURN_WINDOW_LONG = 63
DELIVERY_Z_WINDOW = 20


def build_official_technical_context(
    session: Session,
    *,
    symbols: Sequence[str],
    as_of: date | datetime,
    benchmark_index_symbol: str = DEFAULT_OFFICIAL_BENCHMARK_INDEX_SYMBOL,
    volatility_index_symbol: str = DEFAULT_OFFICIAL_VOLATILITY_INDEX_SYMBOL,
    sector_index_by_symbol: Mapping[str, str] | None = None,
    index_timeframe: str = "1d",
    microstructure_timeframe: str = "1d",
) -> OfficialTechnicalContext:
    normalized_symbols = tuple(sorted({symbol.upper() for symbol in symbols}))
    as_of_date = as_of.date() if isinstance(as_of, datetime) else as_of
    sector_map = {
        symbol.upper(): index_symbol.upper()
        for symbol, index_symbol in (sector_index_by_symbol or {}).items()
        if index_symbol
    }
    index_repo = OfficialIndexCandleRepository(session)
    micro_repo = OfficialSecurityMicrostructureRepository(session)

    benchmark_history = index_repo.history_as_of(
        index_symbol=benchmark_index_symbol,
        as_of=as_of,
        end_date=as_of_date,
        timeframe=index_timeframe,
    )
    volatility_history = index_repo.history_as_of(
        index_symbol=volatility_index_symbol,
        as_of=as_of,
        end_date=as_of_date,
        timeframe=index_timeframe,
    )
    benchmark = _index_feature(benchmark_history, index_family="benchmark")
    volatility = _volatility_feature(volatility_history)

    sector_features = {
        index_symbol: _index_feature(
            index_repo.history_as_of(
                index_symbol=index_symbol,
                as_of=as_of,
                end_date=as_of_date,
                timeframe=index_timeframe,
            ),
            index_family="sector",
        )
        for index_symbol in sorted(set(sector_map.values()))
    }

    symbol_contexts: dict[str, OfficialTechnicalSymbolContext] = {}
    for symbol in normalized_symbols:
        sector_index_symbol = sector_map.get(symbol)
        sector = (
            sector_features.get(sector_index_symbol)
            if sector_index_symbol is not None
            else None
        )
        micro_history = micro_repo.history_as_of(
            symbol=symbol,
            as_of=as_of,
            end_date=as_of_date,
            timeframe=microstructure_timeframe,
        )
        microstructure = _microstructure_feature(micro_history)
        symbol_contexts[symbol] = _symbol_context(
            symbol=symbol,
            as_of_date=as_of_date,
            benchmark=benchmark,
            sector=sector,
            volatility=volatility,
            microstructure=microstructure,
            sector_index_required=sector_index_symbol is not None,
        )

    return OfficialTechnicalContext(
        profile_name=TECHNICAL_OFFICIAL_V2B_PROFILE,
        as_of_date=as_of_date,
        benchmark_index_symbol=benchmark_index_symbol.upper(),
        volatility_index_symbol=volatility_index_symbol.upper(),
        sector_index_by_symbol=sector_map,
        symbols=normalized_symbols,
        symbol_contexts=symbol_contexts,
        metadata={
            "profile_name": TECHNICAL_OFFICIAL_V2B_PROFILE,
            "as_of_date": as_of_date.isoformat(),
            "benchmark_index_symbol": benchmark_index_symbol.upper(),
            "volatility_index_symbol": volatility_index_symbol.upper(),
            "sector_index_by_symbol": dict(sector_map),
            "symbol_count": len(normalized_symbols),
            "index_timeframe": index_timeframe,
            "microstructure_timeframe": microstructure_timeframe,
        },
    )


def _symbol_context(
    *,
    symbol: str,
    as_of_date: date,
    benchmark: OfficialIndexFeature | None,
    sector: OfficialIndexFeature | None,
    volatility: OfficialIndexFeature | None,
    microstructure: OfficialMicrostructureFeature | None,
    sector_index_required: bool,
) -> OfficialTechnicalSymbolContext:
    source_coverage = {
        "benchmark": benchmark is not None and benchmark.return_20d is not None,
        "volatility": volatility is not None and volatility.close is not None,
        "delivery": _has_delivery(microstructure),
        "circuit": _has_circuit(microstructure),
        "tradability": _has_tradability(microstructure),
    }
    if sector_index_required:
        source_coverage["sector"] = sector is not None and sector.return_20d is not None
    missing = tuple(
        feature for feature, available in source_coverage.items() if not available
    )
    return OfficialTechnicalSymbolContext(
        symbol=symbol,
        as_of_date=as_of_date,
        benchmark_index=benchmark,
        sector_index=sector,
        volatility_index=volatility,
        microstructure=microstructure,
        market_relative_return_20d=None,
        sector_relative_return_20d=None,
        source_coverage=source_coverage,
        missing_features=missing,
        metadata={
            "sector_index_required": sector_index_required,
            "coverage_ratio": str(
                (
                    Decimal(sum(1 for available in source_coverage.values() if available))
                    / Decimal(len(source_coverage))
                ).quantize(Decimal("0.0001"))
            ),
            "missing_features": list(missing),
        },
    )


def official_context_with_snapshot_returns(
    context: OfficialTechnicalContext,
    returns_by_symbol: Mapping[str, Decimal | None],
) -> OfficialTechnicalContext:
    symbol_contexts: dict[str, OfficialTechnicalSymbolContext] = {}
    for symbol, symbol_context in context.symbol_contexts.items():
        symbol_return = returns_by_symbol.get(symbol)
        benchmark = symbol_context.benchmark_index
        sector = symbol_context.sector_index
        market_relative = (
            symbol_return - benchmark.return_20d
            if symbol_return is not None
            and benchmark is not None
            and benchmark.return_20d is not None
            else None
        )
        sector_relative = (
            symbol_return - sector.return_20d
            if symbol_return is not None
            and sector is not None
            and sector.return_20d is not None
            else None
        )
        symbol_contexts[symbol] = OfficialTechnicalSymbolContext(
            symbol=symbol_context.symbol,
            as_of_date=symbol_context.as_of_date,
            benchmark_index=symbol_context.benchmark_index,
            sector_index=symbol_context.sector_index,
            volatility_index=symbol_context.volatility_index,
            microstructure=symbol_context.microstructure,
            market_relative_return_20d=market_relative,
            sector_relative_return_20d=sector_relative,
            source_coverage=symbol_context.source_coverage,
            missing_features=symbol_context.missing_features,
            metadata={
                **dict(symbol_context.metadata),
                "symbol_return_20d": str(symbol_return)
                if symbol_return is not None
                else None,
                "market_relative_return_20d": str(market_relative)
                if market_relative is not None
                else None,
                "sector_relative_return_20d": str(sector_relative)
                if sector_relative is not None
                else None,
            },
        )
    return OfficialTechnicalContext(
        profile_name=context.profile_name,
        as_of_date=context.as_of_date,
        benchmark_index_symbol=context.benchmark_index_symbol,
        volatility_index_symbol=context.volatility_index_symbol,
        sector_index_by_symbol=context.sector_index_by_symbol,
        symbols=context.symbols,
        symbol_contexts=symbol_contexts,
        metadata=context.metadata,
    )


def _index_feature(
    rows: Sequence[OfficialIndexCandleModel],
    *,
    index_family: str,
) -> OfficialIndexFeature | None:
    if not rows:
        return None
    ordered = sorted(rows, key=lambda row: (row.trade_date, row.data_available_time))
    latest = ordered[-1]
    return_20d = _period_return(ordered, INDEX_RETURN_WINDOW_SHORT)
    return_63d = _period_return(ordered, INDEX_RETURN_WINDOW_LONG)
    regime_value = return_20d if return_20d is not None else return_63d
    return OfficialIndexFeature(
        index_symbol=latest.index_symbol,
        index_family=index_family,
        trade_date=latest.trade_date,
        close=latest.close,
        return_20d=return_20d,
        return_63d=return_63d,
        regime_state=_index_regime(regime_value),
        source=latest.source,
        source_url=latest.source_url,
        data_available_time=latest.data_available_time,
    )


def _volatility_feature(
    rows: Sequence[OfficialIndexCandleModel],
) -> OfficialIndexFeature | None:
    feature = _index_feature(rows, index_family="volatility")
    if feature is None:
        return None
    change = feature.return_20d
    return OfficialIndexFeature(
        index_symbol=feature.index_symbol,
        index_family=feature.index_family,
        trade_date=feature.trade_date,
        close=feature.close,
        return_20d=change,
        return_63d=feature.return_63d,
        regime_state=_vix_regime(feature.close, change),
        source=feature.source,
        source_url=feature.source_url,
        data_available_time=feature.data_available_time,
    )


def _microstructure_feature(
    rows: Sequence[OfficialSecurityMicrostructureModel],
) -> OfficialMicrostructureFeature | None:
    if not rows:
        return None
    ordered = sorted(rows, key=lambda row: (row.trade_date, row.data_available_time))
    latest = ordered[-1]
    delivery_z = _delivery_z_score(ordered)
    delivery_state = _delivery_state(latest.delivery_percentage, delivery_z)
    score, label = _implementability_score(latest)
    circuit_status = latest.circuit_status
    near_circuit = circuit_status in {"near_upper", "near_lower"}
    return OfficialMicrostructureFeature(
        symbol=latest.symbol,
        trade_date=latest.trade_date,
        delivery_percentage=latest.delivery_percentage,
        delivery_z_score=delivery_z,
        delivery_state=delivery_state,
        circuit_status=circuit_status,
        circuit_hit=latest.circuit_hit,
        near_circuit=near_circuit,
        impact_cost_bps=latest.impact_cost_bps,
        impact_cost_source_kind=latest.impact_cost_source_kind,
        impact_cost_proxy_name=latest.impact_cost_proxy_name,
        implementability_score=score,
        implementability_label=label,
        source=latest.source,
        source_url=latest.source_url,
        data_available_time=latest.data_available_time,
    )


def _period_return(
    rows: Sequence[OfficialIndexCandleModel],
    window: int,
) -> Decimal | None:
    if len(rows) <= window:
        return None
    current = rows[-1].close
    previous = rows[-window - 1].close
    if previous == 0:
        return None
    return ((current / previous) - Decimal("1")).quantize(Decimal("0.00000001"))


def _index_regime(value: Decimal | None) -> str:
    if value is None:
        return "unknown"
    if value >= Decimal("0.03000000"):
        return "bullish"
    if value <= Decimal("-0.03000000"):
        return "bearish"
    return "neutral"


def _vix_regime(level: Decimal, change: Decimal | None) -> str:
    if level >= Decimal("22"):
        return "stress"
    if level <= Decimal("15") and (change is None or change <= Decimal("0.10")):
        return "calm"
    return "normal"


def _delivery_z_score(
    rows: Sequence[OfficialSecurityMicrostructureModel],
) -> Decimal | None:
    latest = rows[-1]
    if latest.delivery_percentage is None:
        return None
    previous_values = [
        row.delivery_percentage
        for row in rows[-DELIVERY_Z_WINDOW - 1 : -1]
        if row.delivery_percentage is not None
    ]
    if len(previous_values) < 2:
        return None
    stddev = _stddev(previous_values)
    if stddev == 0:
        return Decimal("0.00000000")
    mean = sum(previous_values, Decimal("0")) / Decimal(len(previous_values))
    return ((latest.delivery_percentage - mean) / stddev).quantize(
        Decimal("0.00000001")
    )


def _delivery_state(
    delivery_percentage: Decimal | None,
    delivery_z_score: Decimal | None,
) -> str:
    if delivery_z_score is not None:
        if delivery_z_score >= Decimal("1"):
            return "high_participation"
        if delivery_z_score <= Decimal("-1"):
            return "low_participation"
    if delivery_percentage is None:
        return "unknown"
    if delivery_percentage >= Decimal("50"):
        return "high_participation"
    if delivery_percentage <= Decimal("20"):
        return "low_participation"
    return "normal"


def _implementability_score(
    row: OfficialSecurityMicrostructureModel,
) -> tuple[Decimal | None, str]:
    if row.impact_cost_bps is not None:
        score = _bounded(Decimal("1") - ((row.impact_cost_bps / Decimal("50")) * 2))
        label = (
            "impact_cost_official"
            if row.impact_cost_source_kind == "official"
            else f"impact_cost_{row.impact_cost_source_kind}"
        )
        if row.impact_cost_proxy_name:
            label = f"{label}:{row.impact_cost_proxy_name}"
        return score.quantize(Decimal("0.0001")), label

    proxy_value = row.average_trade_value or row.turnover
    if proxy_value is None:
        return None, "impact_cost_unavailable"
    if proxy_value >= Decimal("50000000"):
        score = Decimal("0.8000")
    elif proxy_value >= Decimal("10000000"):
        score = Decimal("0.3000")
    else:
        score = Decimal("-0.4000")
    proxy_name = "average_trade_value_proxy" if row.average_trade_value else "turnover_proxy"
    return score, proxy_name


def _has_delivery(row: OfficialMicrostructureFeature | None) -> bool:
    return row is not None and (
        row.delivery_percentage is not None or row.delivery_z_score is not None
    )


def _has_circuit(row: OfficialMicrostructureFeature | None) -> bool:
    return row is not None and (
        row.circuit_status is not None or row.circuit_hit is not None
    )


def _has_tradability(row: OfficialMicrostructureFeature | None) -> bool:
    return row is not None and row.implementability_score is not None


def _stddev(values: Sequence[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    mean = sum(values, Decimal("0")) / Decimal(len(values))
    variance = sum((value - mean) ** 2 for value in values) / Decimal(len(values))
    return variance.sqrt()


def _bounded(value: Decimal) -> Decimal:
    return max(Decimal("-1"), min(Decimal("1"), value))
