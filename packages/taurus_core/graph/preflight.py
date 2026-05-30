from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from taurus_core.backtesting.graph import GraphBacktestSignalLoader
from taurus_core.config import Settings
from taurus_core.db.models import DailyCandleModel, GraphEdgeModel, GraphEdgeStatsModel, GraphNodeModel


class GraphReadinessError(RuntimeError):
    """Raised when graph-enabled paper trading lacks reviewed graph inputs."""


@dataclass(frozen=True, slots=True)
class GraphReadinessSummary:
    selected_symbol_count: int
    company_node_count: int
    active_edge_count: int
    latest_candle_date: str
    latest_edge_stat_count: int
    usable_signal_count: int
    symbols_with_usable_signals: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "selected_symbol_count": self.selected_symbol_count,
            "company_node_count": self.company_node_count,
            "active_edge_count": self.active_edge_count,
            "latest_candle_date": self.latest_candle_date,
            "latest_edge_stat_count": self.latest_edge_stat_count,
            "usable_signal_count": self.usable_signal_count,
            "symbols_with_usable_signals": list(self.symbols_with_usable_signals),
        }


def assert_graph_ready_for_paper(
    session: Session,
    *,
    settings: Settings,
    symbols: list[str],
) -> GraphReadinessSummary:
    normalized_symbols = sorted({symbol.upper() for symbol in symbols if symbol.strip()})
    if not normalized_symbols:
        raise GraphReadinessError("Graph readiness requires at least one selected symbol.")
    if not settings.taurus_graph_enabled:
        raise GraphReadinessError(
            "Graph-enabled paper execution requires TAURUS_GRAPH_ENABLED=true."
        )
    if not settings.taurus_graph_risk_enabled:
        raise GraphReadinessError(
            "Graph-enabled paper execution requires TAURUS_GRAPH_RISK_ENABLED=true so "
            "graph concentration checks participate in risk review."
        )

    _assert_graph_risk_limits(settings)
    latest_candle_date = session.scalar(
        select(func.max(DailyCandleModel.trade_date)).where(
            DailyCandleModel.symbol.in_(normalized_symbols)
        )
    )
    if latest_candle_date is None:
        raise GraphReadinessError(
            "Graph-enabled Kite paper run found no Kite daily candles for the selected "
            "universe. Run make import-market-data before make paper-loop-kite."
        )

    company_nodes = list(
        session.scalars(
            select(GraphNodeModel)
            .where(
                GraphNodeModel.node_type == "company",
                GraphNodeModel.symbol.in_(normalized_symbols),
            )
            .order_by(GraphNodeModel.symbol)
        )
    )
    if not company_nodes:
        raise GraphReadinessError(
            "Graph-enabled Kite paper run found no graph company nodes for the selected "
            "universe. Run make import-taurus-graph, then make compute-graph-stats."
        )

    company_node_ids = [node.id for node in company_nodes]
    active_edges = list(
        session.scalars(
            select(GraphEdgeModel)
            .where(
                GraphEdgeModel.status == "active",
                or_(
                    GraphEdgeModel.source_node_id.in_(company_node_ids),
                    GraphEdgeModel.target_node_id.in_(company_node_ids),
                ),
            )
            .order_by(GraphEdgeModel.edge_key)
        )
    )
    if not active_edges:
        raise GraphReadinessError(
            "Graph-enabled Kite paper run found graph company nodes but no active graph "
            "edges for the selected universe. Review and promote real candidate edges, "
            "then rerun make compute-graph-stats."
        )

    active_edge_ids = [edge.id for edge in active_edges]
    latest_stat_count = int(
        session.scalar(
            select(func.count())
            .select_from(GraphEdgeStatsModel)
            .where(
                GraphEdgeStatsModel.edge_id.in_(active_edge_ids),
                GraphEdgeStatsModel.as_of_date == latest_candle_date,
                GraphEdgeStatsModel.insufficient_data_reason == "",
                or_(
                    GraphEdgeStatsModel.residual_correlation.is_not(None),
                    GraphEdgeStatsModel.raw_correlation.is_not(None),
                    GraphEdgeStatsModel.lead_lag_score.is_not(None),
                ),
            )
        )
        or 0
    )
    if latest_stat_count == 0:
        raise GraphReadinessError(
            "Graph-enabled Kite paper run found active graph edges, but no usable edge "
            f"stats for latest candle date {latest_candle_date.isoformat()}. Run "
            "make compute-graph-stats after importing the latest Kite candles."
        )

    graph_signals = GraphBacktestSignalLoader(session, edge_statuses=("active",)).load_by_as_of_date(
        as_of_date=latest_candle_date + timedelta(days=1),
        symbols=normalized_symbols,
    )
    if not graph_signals:
        raise GraphReadinessError(
            "Graph-enabled Kite paper run found active graph rows and latest stats, but "
            "no selected symbol has usable validated graph evidence for strategy scoring. "
            "Review graph coverage, run make import-taurus-graph, and rerun make compute-graph-stats."
        )

    return GraphReadinessSummary(
        selected_symbol_count=len(normalized_symbols),
        company_node_count=len(company_nodes),
        active_edge_count=len(active_edges),
        latest_candle_date=latest_candle_date.isoformat(),
        latest_edge_stat_count=latest_stat_count,
        usable_signal_count=len(graph_signals),
        symbols_with_usable_signals=tuple(sorted(graph_signals)),
    )


def _assert_graph_risk_limits(settings: Settings) -> None:
    limits = {
        "TAURUS_GRAPH_MAX_BASIC_INDUSTRY_EXPOSURE_PCT": settings.taurus_graph_max_basic_industry_exposure_pct,
        "TAURUS_GRAPH_MAX_PRODUCT_GROUP_EXPOSURE_PCT": settings.taurus_graph_max_product_group_exposure_pct,
        "TAURUS_GRAPH_MAX_CUSTOMER_INDUSTRY_EXPOSURE_PCT": settings.taurus_graph_max_customer_industry_exposure_pct,
        "TAURUS_GRAPH_MAX_DEPENDENCY_EXPOSURE_PCT": settings.taurus_graph_max_dependency_exposure_pct,
        "TAURUS_GRAPH_MAX_RISK_CATEGORY_EXPOSURE_PCT": settings.taurus_graph_max_risk_category_exposure_pct,
        "TAURUS_GRAPH_MAX_CORRELATED_CLUSTER_EXPOSURE_PCT": settings.taurus_graph_max_correlated_cluster_exposure_pct,
    }
    bad_limits = [name for name, value in limits.items() if value <= 0]
    if bad_limits:
        raise GraphReadinessError(
            "Graph risk config must set positive concentration limits before graph-enabled "
            f"paper execution. Check: {', '.join(sorted(bad_limits))}."
        )
