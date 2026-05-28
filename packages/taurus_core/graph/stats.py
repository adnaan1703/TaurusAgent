from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from taurus_core.config import Settings, get_settings
from taurus_core.db.models import DailyCandleModel, GraphEdgeModel, GraphNodeModel
from taurus_core.db.repositories import GraphRepository
from taurus_core.observability.metrics import record_graph_stats_summary

GRAPH_STATS_MODEL_VERSION = "graph_stats_v1"


@dataclass(frozen=True, slots=True)
class GraphEdgeStatResult:
    edge_key: str
    source_symbol: str | None
    target_symbol: str | None
    window: str
    as_of_date: date
    sample_size: int
    raw_correlation: Decimal | None
    residual_correlation: Decimal | None
    lead_lag_score: Decimal | None
    stability_score: Decimal | None
    insufficient_data_reason: str
    promoted: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "edge_key": self.edge_key,
            "source_symbol": self.source_symbol,
            "target_symbol": self.target_symbol,
            "window": self.window,
            "as_of_date": self.as_of_date.isoformat(),
            "sample_size": self.sample_size,
            "raw_correlation": _decimal_to_json(self.raw_correlation),
            "residual_correlation": _decimal_to_json(self.residual_correlation),
            "lead_lag_score": _decimal_to_json(self.lead_lag_score),
            "stability_score": _decimal_to_json(self.stability_score),
            "insufficient_data_reason": self.insufficient_data_reason,
            "promoted": self.promoted,
        }


@dataclass(frozen=True, slots=True)
class GraphStatsSummary:
    as_of_date: date
    windows: tuple[int, ...]
    model_version: str
    edges_seen: int
    stats_upserted: int
    insufficient_stats: int
    promoted_edges: tuple[str, ...]
    warnings: tuple[str, ...]
    results: tuple[GraphEdgeStatResult, ...]

    def to_dict(self, *, include_results: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "as_of_date": self.as_of_date.isoformat(),
            "windows": list(self.windows),
            "model_version": self.model_version,
            "edges_seen": self.edges_seen,
            "stats_upserted": self.stats_upserted,
            "insufficient_stats": self.insufficient_stats,
            "promoted_edges": list(self.promoted_edges),
            "warnings": list(self.warnings),
        }
        if include_results:
            payload["results"] = [result.to_dict() for result in self.results]
        return payload


@dataclass(frozen=True, slots=True)
class _WindowStats:
    sample_size: int
    raw_correlation: float | None
    residual_correlation: float | None
    lead_lag_score: float | None
    stability_score: float | None
    insufficient_data_reason: str
    metadata: dict[str, object]


def compute_graph_edge_stats(
    session: Session,
    *,
    settings: Settings | None = None,
    as_of_date: date | None = None,
    windows: Iterable[int] | None = None,
    edge_statuses: Iterable[str] = ("active", "candidate"),
    model_version: str = GRAPH_STATS_MODEL_VERSION,
) -> GraphStatsSummary:
    """Compute close-to-close statistical validation rows for graph edges."""

    settings = settings or get_settings()
    graph_repo = GraphRepository(session)
    resolved_as_of_date = as_of_date or _latest_candle_date(session) or date.today()
    resolved_windows = tuple(windows) if windows is not None else settings.graph_stats_windows
    _validate_windows(resolved_windows)

    symbol_returns = _load_symbol_returns(session, as_of_date=resolved_as_of_date)
    market_returns = _market_proxy_returns(symbol_returns)
    market_symbol_count = len(symbol_returns)
    edges = _list_edges(graph_repo, edge_statuses=edge_statuses)

    results: list[GraphEdgeStatResult] = []
    promoted_edges: set[str] = set()
    warnings: list[str] = []

    for edge in edges:
        source_node = graph_repo.get_node_by_id(edge.source_node_id)
        target_node = graph_repo.get_node_by_id(edge.target_node_id)
        source_symbol = _node_symbol(source_node)
        target_symbol = _node_symbol(target_node)

        for window in resolved_windows:
            stat_window = f"{window}d"
            stats = _compute_window_stats(
                source_symbol=source_symbol,
                target_symbol=target_symbol,
                source_returns=symbol_returns.get(source_symbol or "", {}),
                target_returns=symbol_returns.get(target_symbol or "", {}),
                market_returns=market_returns,
                window=window,
                min_sample_size=settings.taurus_graph_min_edge_sample_size,
                max_lag_days=settings.taurus_graph_lead_lag_max_days,
            )
            metadata = {
                **stats.metadata,
                "source_node_key": source_node.node_key if source_node is not None else "",
                "target_node_key": target_node.node_key if target_node is not None else "",
                "source_symbol": source_symbol,
                "target_symbol": target_symbol,
                "market_proxy_symbol_count": market_symbol_count,
                "edge_status_at_compute": edge.status,
                "auto_promote_edges": settings.taurus_graph_auto_promote_edges,
            }

            graph_repo.upsert_edge_stats(
                edge_key=edge.edge_key,
                window=stat_window,
                as_of_date=resolved_as_of_date,
                sample_size=stats.sample_size,
                raw_correlation=_decimal_from_float(stats.raw_correlation),
                residual_correlation=_decimal_from_float(stats.residual_correlation),
                lead_lag_score=_decimal_from_float(stats.lead_lag_score),
                stability_score=_decimal_from_float(stats.stability_score),
                p_value=None,
                insufficient_data_reason=stats.insufficient_data_reason,
                model_version=model_version,
                metadata=metadata,
            )

            promoted = False
            if not stats.insufficient_data_reason and edge.edge_key not in promoted_edges:
                promoted = _maybe_auto_promote_edge(
                    graph_repo,
                    edge=edge,
                    stats=stats,
                    settings=settings,
                    stat_window=stat_window,
                    as_of_date=resolved_as_of_date,
                )
                if promoted:
                    promoted_edges.add(edge.edge_key)
                    edge.status = "active"

            results.append(
                GraphEdgeStatResult(
                    edge_key=edge.edge_key,
                    source_symbol=source_symbol,
                    target_symbol=target_symbol,
                    window=stat_window,
                    as_of_date=resolved_as_of_date,
                    sample_size=stats.sample_size,
                    raw_correlation=_decimal_from_float(stats.raw_correlation),
                    residual_correlation=_decimal_from_float(stats.residual_correlation),
                    lead_lag_score=_decimal_from_float(stats.lead_lag_score),
                    stability_score=_decimal_from_float(stats.stability_score),
                    insufficient_data_reason=stats.insufficient_data_reason,
                    promoted=promoted,
                )
            )

    if not edges:
        warnings.append("No active or candidate graph edges found for statistics.")
    if not symbol_returns:
        warnings.append("No daily candle returns found for graph statistics.")

    session.commit()
    summary = GraphStatsSummary(
        as_of_date=resolved_as_of_date,
        windows=resolved_windows,
        model_version=model_version,
        edges_seen=len(edges),
        stats_upserted=len(results),
        insufficient_stats=sum(1 for result in results if result.insufficient_data_reason),
        promoted_edges=tuple(sorted(promoted_edges)),
        warnings=tuple(warnings),
        results=tuple(results),
    )
    record_graph_stats_summary(summary)
    return summary


def _compute_window_stats(
    *,
    source_symbol: str | None,
    target_symbol: str | None,
    source_returns: dict[date, float],
    target_returns: dict[date, float],
    market_returns: dict[date, float],
    window: int,
    min_sample_size: int,
    max_lag_days: int,
) -> _WindowStats:
    if source_symbol is None or target_symbol is None:
        return _insufficient_stats("source_or_target_missing_symbol")
    if source_symbol == target_symbol:
        return _insufficient_stats("source_target_same_symbol")
    missing_symbols = [
        symbol
        for symbol, returns in ((source_symbol, source_returns), (target_symbol, target_returns))
        if not returns
    ]
    if missing_symbols:
        return _insufficient_stats(f"missing_candles:{','.join(missing_symbols)}")

    common_dates = sorted(set(source_returns) & set(target_returns))
    window_dates = common_dates[-window:]
    xs = [source_returns[item] for item in window_dates]
    ys = [target_returns[item] for item in window_dates]
    sample_size = len(window_dates)
    metadata: dict[str, object] = {
        "return_start_date": window_dates[0].isoformat() if window_dates else "",
        "return_end_date": window_dates[-1].isoformat() if window_dates else "",
        "window_observations": window,
        "calculator": "close_to_close_return_pearson",
    }

    if sample_size < min_sample_size:
        return _WindowStats(
            sample_size=sample_size,
            raw_correlation=None,
            residual_correlation=None,
            lead_lag_score=None,
            stability_score=None,
            insufficient_data_reason=(
                f"insufficient_overlap:required={min_sample_size},found={sample_size}"
            ),
            metadata=metadata,
        )

    raw_correlation = _pearson(xs, ys)
    if raw_correlation is None:
        return _WindowStats(
            sample_size=sample_size,
            raw_correlation=None,
            residual_correlation=None,
            lead_lag_score=None,
            stability_score=None,
            insufficient_data_reason="zero_variance_returns",
            metadata=metadata,
        )

    residual_correlation, residual_reason = _residual_correlation(
        window_dates,
        xs,
        ys,
        market_returns,
        min_sample_size=min_sample_size,
    )
    lead_lag_score, lead_lag_days = _lead_lag_score(
        window_dates,
        source_returns,
        target_returns,
        min_sample_size=min_sample_size,
        max_lag_days=max_lag_days,
    )
    stability_score = _stability_score(xs, ys, min_sample_size=min_sample_size)
    metadata.update(
        {
            "lead_lag_days": lead_lag_days,
            "residual_reason": residual_reason,
            "residual_calculator": "market_proxy_beta_residual",
        }
    )

    return _WindowStats(
        sample_size=sample_size,
        raw_correlation=raw_correlation,
        residual_correlation=residual_correlation,
        lead_lag_score=lead_lag_score,
        stability_score=stability_score,
        insufficient_data_reason="",
        metadata=metadata,
    )


def _residual_correlation(
    dates: list[date],
    xs: list[float],
    ys: list[float],
    market_returns: dict[date, float],
    *,
    min_sample_size: int,
) -> tuple[float | None, str]:
    triples = [
        (x_value, y_value, market_returns[item])
        for item, x_value, y_value in zip(dates, xs, ys)
        if item in market_returns
    ]
    if len(triples) < min_sample_size:
        return None, f"insufficient_market_proxy:required={min_sample_size},found={len(triples)}"
    x_values = [item[0] for item in triples]
    y_values = [item[1] for item in triples]
    market_values = [item[2] for item in triples]
    x_beta = _beta(x_values, market_values)
    y_beta = _beta(y_values, market_values)
    if x_beta is None or y_beta is None:
        return None, "zero_variance_market_proxy"
    x_residuals = [
        x_value - (x_beta * market_value)
        for x_value, market_value in zip(x_values, market_values)
    ]
    y_residuals = [
        y_value - (y_beta * market_value)
        for y_value, market_value in zip(y_values, market_values)
    ]
    correlation = _pearson(x_residuals, y_residuals)
    if correlation is None:
        return None, "zero_variance_residual_returns"
    return correlation, ""


def _lead_lag_score(
    common_dates: list[date],
    source_returns: dict[date, float],
    target_returns: dict[date, float],
    *,
    min_sample_size: int,
    max_lag_days: int,
) -> tuple[float | None, int | None]:
    best_score: float | None = None
    best_lag: int | None = None
    max_lag = min(max_lag_days, max(len(common_dates) - min_sample_size, 0))
    for lag in range(1, max_lag + 1):
        xs = [
            source_returns[common_dates[index]]
            for index in range(0, len(common_dates) - lag)
        ]
        ys = [
            target_returns[common_dates[index + lag]]
            for index in range(0, len(common_dates) - lag)
        ]
        if len(xs) < min_sample_size:
            continue
        score = _pearson(xs, ys)
        if score is None:
            continue
        if best_score is None or abs(score) > abs(best_score):
            best_score = score
            best_lag = lag
    return best_score, best_lag


def _stability_score(
    xs: list[float],
    ys: list[float],
    *,
    min_sample_size: int,
) -> float | None:
    chunk_size = max(3, min_sample_size // 2)
    midpoint = len(xs) // 2
    if midpoint < chunk_size or len(xs) - midpoint < chunk_size:
        return None
    first = _pearson(xs[:midpoint], ys[:midpoint])
    second = _pearson(xs[midpoint:], ys[midpoint:])
    if first is None or second is None:
        return None
    if (first < 0 < second) or (second < 0 < first):
        return 0.0
    return _clamp(1.0 - min(abs(first - second) / 2.0, 1.0), 0.0, 1.0)


def _maybe_auto_promote_edge(
    graph_repo: GraphRepository,
    *,
    edge: GraphEdgeModel,
    stats: _WindowStats,
    settings: Settings,
    stat_window: str,
    as_of_date: date,
) -> bool:
    if not settings.taurus_graph_auto_promote_edges:
        return False
    if edge.status != "candidate":
        return False
    if Decimal(edge.confidence) < settings.taurus_graph_min_edge_confidence:
        return False
    if stats.sample_size < settings.taurus_graph_min_edge_sample_size:
        return False
    if stats.stability_score is None:
        return False
    if _decimal_from_float(stats.stability_score) < settings.taurus_graph_min_stability_score:
        return False

    residual_passes = (
        stats.residual_correlation is not None
        and abs(_decimal_from_float(stats.residual_correlation))
        >= settings.taurus_graph_min_residual_corr
    )
    lead_lag_passes = (
        stats.lead_lag_score is not None
        and abs(_decimal_from_float(stats.lead_lag_score))
        >= settings.taurus_graph_min_lead_lag_score
    )
    if not (residual_passes or lead_lag_passes):
        return False

    graph_repo.update_edge_status(
        edge_key=edge.edge_key,
        status="active",
        reviewed_by="graph_stats_job",
        review_note=(
            f"Auto-promoted from graph stats {stat_window} as of "
            f"{as_of_date.isoformat()}."
        ),
    )
    return True


def _load_symbol_returns(session: Session, *, as_of_date: date) -> dict[str, dict[date, float]]:
    statement = (
        select(DailyCandleModel)
        .where(
            DailyCandleModel.timeframe == "1d",
            DailyCandleModel.trade_date <= as_of_date,
        )
        .order_by(DailyCandleModel.symbol, DailyCandleModel.trade_date)
    )
    candles_by_symbol: dict[str, list[DailyCandleModel]] = defaultdict(list)
    for candle in session.scalars(statement):
        candles_by_symbol[candle.symbol.upper()].append(candle)

    returns_by_symbol: dict[str, dict[date, float]] = {}
    for symbol, candles in candles_by_symbol.items():
        previous_close: Decimal | None = None
        symbol_returns: dict[date, float] = {}
        for candle in candles:
            close = Decimal(candle.close)
            if previous_close is not None and previous_close != 0:
                symbol_returns[candle.trade_date] = float((close / previous_close) - Decimal("1"))
            previous_close = close
        if symbol_returns:
            returns_by_symbol[symbol] = symbol_returns
    return returns_by_symbol


def _market_proxy_returns(symbol_returns: dict[str, dict[date, float]]) -> dict[date, float]:
    returns_by_date: dict[date, list[float]] = defaultdict(list)
    for returns in symbol_returns.values():
        for return_date, return_value in returns.items():
            returns_by_date[return_date].append(return_value)
    return {
        return_date: sum(values) / len(values)
        for return_date, values in returns_by_date.items()
        if values
    }


def _latest_candle_date(session: Session) -> date | None:
    return session.scalar(select(func.max(DailyCandleModel.trade_date)))


def _list_edges(
    graph_repo: GraphRepository,
    *,
    edge_statuses: Iterable[str],
) -> list[GraphEdgeModel]:
    edges_by_id: dict[int, GraphEdgeModel] = {}
    for status in edge_statuses:
        for edge in graph_repo.list_edges(status=status, limit=None):
            edges_by_id[edge.id] = edge
    return sorted(edges_by_id.values(), key=lambda edge: edge.edge_key)


def _node_symbol(node: GraphNodeModel | None) -> str | None:
    if node is None or not node.symbol:
        return None
    return node.symbol.upper()


def _insufficient_stats(reason: str) -> _WindowStats:
    return _WindowStats(
        sample_size=0,
        raw_correlation=None,
        residual_correlation=None,
        lead_lag_score=None,
        stability_score=None,
        insufficient_data_reason=reason,
        metadata={"calculator": "close_to_close_return_pearson"},
    )


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    if len(xs) != len(ys) or len(xs) < 2:
        return None
    x_mean = sum(xs) / len(xs)
    y_mean = sum(ys) / len(ys)
    x_deltas = [value - x_mean for value in xs]
    y_deltas = [value - y_mean for value in ys]
    numerator = sum(x_value * y_value for x_value, y_value in zip(x_deltas, y_deltas))
    x_denominator = math.sqrt(sum(value * value for value in x_deltas))
    y_denominator = math.sqrt(sum(value * value for value in y_deltas))
    denominator = x_denominator * y_denominator
    if denominator == 0:
        return None
    return _clamp(numerator / denominator, -1.0, 1.0)


def _beta(xs: list[float], market_values: list[float]) -> float | None:
    market_mean = sum(market_values) / len(market_values)
    x_mean = sum(xs) / len(xs)
    market_deltas = [value - market_mean for value in market_values]
    variance = sum(value * value for value in market_deltas)
    if variance == 0:
        return None
    covariance = sum(
        (x_value - x_mean) * market_delta
        for x_value, market_delta in zip(xs, market_deltas)
    )
    return covariance / variance


def _decimal_from_float(value: float | None) -> Decimal | None:
    if value is None or math.isnan(value) or math.isinf(value):
        return None
    return Decimal(f"{value:.8f}")


def _decimal_to_json(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _validate_windows(windows: tuple[int, ...]) -> None:
    if not windows:
        raise ValueError("At least one graph stats window is required.")
    if any(window <= 0 for window in windows):
        raise ValueError("Graph stats windows must be positive integers.")


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(max(value, lower), upper)
