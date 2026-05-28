from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from taurus_core.db.models import (
    GraphEdgeEvidenceModel,
    GraphEdgeModel,
    GraphEdgeStatsModel,
    GraphNodeModel,
)
from taurus_core.db.repositories import GraphRepository

SCORE_QUANT = Decimal("0.00000001")
SUMMARY_QUANT = Decimal("0.00000001")
ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class GraphBacktestContribution:
    edge_key: str
    edge_type: str
    edge_status: str
    related_symbol: str
    stat_window: str
    stat_as_of_date: date
    evidence_count: int
    score: Decimal
    confidence: Decimal
    direction: str
    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "edge_key": self.edge_key,
            "edge_type": self.edge_type,
            "edge_status": self.edge_status,
            "related_symbol": self.related_symbol,
            "stat_window": self.stat_window,
            "stat_as_of_date": self.stat_as_of_date.isoformat(),
            "evidence_count": self.evidence_count,
            "score": str(self.score),
            "confidence": str(self.confidence),
            "direction": self.direction,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class GraphBacktestSignal:
    symbol: str
    as_of_date: date
    score: Decimal
    confidence: Decimal
    contributions: tuple[GraphBacktestContribution, ...]

    @property
    def edge_types(self) -> tuple[str, ...]:
        return tuple(sorted({item.edge_type for item in self.contributions if item.edge_type}))

    @property
    def edge_keys(self) -> tuple[str, ...]:
        return tuple(sorted({item.edge_key for item in self.contributions if item.edge_key}))

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "as_of_date": self.as_of_date.isoformat(),
            "score": str(self.score),
            "confidence": str(self.confidence),
            "edge_types": list(self.edge_types),
            "edge_keys": list(self.edge_keys),
            "contributions": [item.to_dict() for item in self.contributions],
        }


@dataclass(frozen=True, slots=True)
class GraphBacktestTrade:
    symbol: str
    entry_date: date
    exit_date: date
    return_pct: Decimal
    signal_score: Decimal
    signal_confidence: Decimal
    edge_types: tuple[str, ...]
    edge_keys: tuple[str, ...]


class GraphBacktestSignalLoader:
    """Build point-in-time graph scores from graph rows available by a date."""

    def __init__(
        self,
        session: Session,
        *,
        edge_statuses: Iterable[str] = ("active", "candidate"),
    ) -> None:
        self.session = session
        self.graph_repo = GraphRepository(session)
        self.edge_statuses = {status.strip().lower() for status in edge_statuses}

    def load_by_as_of_date(
        self,
        *,
        as_of_date: date,
        symbols: Iterable[str],
    ) -> dict[str, GraphBacktestSignal]:
        signals: dict[str, GraphBacktestSignal] = {}
        for symbol in sorted({item.upper() for item in symbols}):
            signal = self.load_symbol(as_of_date=as_of_date, symbol=symbol)
            if signal is not None:
                signals[symbol] = signal
        return signals

    def load_symbol(self, *, as_of_date: date, symbol: str) -> GraphBacktestSignal | None:
        normalized_symbol = symbol.upper()
        center_node = _company_node(self.graph_repo, normalized_symbol)
        if center_node is None:
            return None

        contributions = self._contributions(center_node=center_node, as_of_date=as_of_date)
        if not contributions:
            return None

        score = _bounded_score(sum((item.score for item in contributions), ZERO))
        confidence = _average_decimal(item.confidence for item in contributions)
        return GraphBacktestSignal(
            symbol=normalized_symbol,
            as_of_date=as_of_date,
            score=score,
            confidence=confidence,
            contributions=tuple(
                sorted(
                    contributions,
                    key=lambda item: (abs(item.score), item.edge_key),
                    reverse=True,
                )
            ),
        )

    def _contributions(
        self,
        *,
        center_node: GraphNodeModel,
        as_of_date: date,
    ) -> list[GraphBacktestContribution]:
        contributions: list[GraphBacktestContribution] = []
        edges = self.graph_repo.list_edges_for_node(node_key=center_node.node_key, limit=None)
        for edge in edges:
            if not self._edge_available(edge=edge, as_of_date=as_of_date):
                continue
            related_node = _related_company_node(self.graph_repo, center_node, edge)
            if related_node is None or not related_node.symbol:
                continue
            evidence = self._available_evidence(edge=edge, as_of_date=as_of_date)
            if evidence is None:
                continue
            stat = self._latest_available_stat(edge=edge, as_of_date=as_of_date)
            if stat is None:
                continue

            contribution = _score_contribution(
                edge=edge,
                related_node=related_node,
                stat=stat,
                evidence=evidence,
            )
            if contribution.score != ZERO:
                contributions.append(contribution)
        return contributions

    def _edge_available(self, *, edge: GraphEdgeModel, as_of_date: date) -> bool:
        if edge.status not in self.edge_statuses:
            return False
        if edge.valid_from is not None and edge.valid_from > as_of_date:
            return False
        if edge.valid_to is not None and edge.valid_to < as_of_date:
            return False
        return True

    def _available_evidence(
        self,
        *,
        edge: GraphEdgeModel,
        as_of_date: date,
    ) -> tuple[GraphEdgeEvidenceModel, ...] | None:
        evidence_rows = self.graph_repo.list_edge_evidence(edge_key=edge.edge_key, limit=None)
        if not evidence_rows:
            return ()
        available = tuple(
            row
            for row in evidence_rows
            if row.source_date is None or row.source_date <= as_of_date
        )
        return available or None

    def _latest_available_stat(
        self,
        *,
        edge: GraphEdgeModel,
        as_of_date: date,
    ) -> GraphEdgeStatsModel | None:
        stats = self.graph_repo.list_edge_stats(edge_key=edge.edge_key, limit=None)
        available = [
            stat
            for stat in stats
            if stat.as_of_date <= as_of_date
            and not stat.insufficient_data_reason
            and (
                stat.residual_correlation is not None
                or stat.raw_correlation is not None
                or stat.lead_lag_score is not None
            )
        ]
        if not available:
            return None
        return sorted(
            available,
            key=lambda item: (item.as_of_date, item.sample_size, item.stat_window),
            reverse=True,
        )[0]


def summarize_graph_performance(trades: Iterable[GraphBacktestTrade]) -> dict[str, object]:
    rows = list(trades)
    grouped: dict[str, list[GraphBacktestTrade]] = defaultdict(list)
    for trade in rows:
        edge_types = trade.edge_types or ("ungrouped",)
        for edge_type in edge_types:
            grouped[edge_type].append(trade)

    return {
        "graph_trade_count": len(rows),
        "graph_hit_rate": _hit_rate(rows),
        "graph_average_return": _average_return(rows),
        "graph_max_drawdown": _trade_drawdown(rows),
        "graph_performance_by_edge_type": {
            edge_type: {
                "trade_count": len(edge_trades),
                "hit_rate": _hit_rate(edge_trades),
                "average_return": _average_return(edge_trades),
                "max_drawdown": _trade_drawdown(edge_trades),
                "average_signal_score": _average_float(
                    trade.signal_score for trade in edge_trades
                ),
            }
            for edge_type, edge_trades in sorted(grouped.items())
        },
    }


def _company_node(graph_repo: GraphRepository, symbol: str) -> GraphNodeModel | None:
    node = graph_repo.get_node_by_key(f"company:{symbol}")
    if node is not None:
        return node
    nodes = graph_repo.list_nodes(node_type="company", symbol=symbol, limit=1)
    return nodes[0] if nodes else None


def _related_company_node(
    graph_repo: GraphRepository,
    center_node: GraphNodeModel,
    edge: GraphEdgeModel,
) -> GraphNodeModel | None:
    if edge.direction == "directed" and edge.target_node_id != center_node.id:
        return None
    related_node_id = (
        edge.target_node_id
        if edge.source_node_id == center_node.id
        else edge.source_node_id
    )
    related_node = graph_repo.get_node_by_id(related_node_id)
    if related_node is None or related_node.node_type != "company":
        return None
    return related_node


def _score_contribution(
    *,
    edge: GraphEdgeModel,
    related_node: GraphNodeModel,
    stat: GraphEdgeStatsModel,
    evidence: tuple[GraphEdgeEvidenceModel, ...],
) -> GraphBacktestContribution:
    confidence = _clamp_decimal(Decimal(edge.confidence), ZERO, ONE)
    strength = _clamp_decimal(edge.strength or Decimal("0.50"), ZERO, ONE)
    status_weight = ONE if edge.status == "active" else Decimal("0.65")
    stats_weight = _stats_weight(stat)
    evidence_weight = _evidence_weight(evidence)
    directional_score = _directional_score(edge=edge, stat=stat)
    score = _bounded_score(
        directional_score * confidence * strength * status_weight * stats_weight * evidence_weight
    )
    contribution_confidence = _score_decimal(
        _clamp_decimal(confidence * stats_weight * evidence_weight, ZERO, ONE)
    )
    return GraphBacktestContribution(
        edge_key=edge.edge_key,
        edge_type=edge.edge_type,
        edge_status=edge.status,
        related_symbol=related_node.symbol or "",
        stat_window=stat.stat_window,
        stat_as_of_date=stat.as_of_date,
        evidence_count=len(evidence),
        score=score,
        confidence=contribution_confidence,
        direction=_direction_from_score(score),
        metadata={
            "expected_sign": edge.expected_sign,
            "sample_size": stat.sample_size,
            "raw_correlation": _decimal_text(stat.raw_correlation),
            "residual_correlation": _decimal_text(stat.residual_correlation),
            "lead_lag_score": _decimal_text(stat.lead_lag_score),
            "stability_score": _decimal_text(stat.stability_score),
            "stats_weight": str(_score_decimal(stats_weight)),
            "status_weight": str(_score_decimal(status_weight)),
            "evidence_weight": str(_score_decimal(evidence_weight)),
        },
    )


def _directional_score(edge: GraphEdgeModel, stat: GraphEdgeStatsModel) -> Decimal:
    relation_sign = _relation_sign(edge=edge, stat=stat)
    stat_sign = _sign(stat.lead_lag_score or stat.residual_correlation or stat.raw_correlation)
    if relation_sign == ZERO or stat_sign == ZERO:
        return ZERO
    return relation_sign * stat_sign


def _relation_sign(edge: GraphEdgeModel, stat: GraphEdgeStatsModel) -> Decimal:
    if edge.expected_sign == "positive":
        return ONE
    if edge.expected_sign == "negative":
        return Decimal("-1")
    return _sign(stat.residual_correlation or stat.raw_correlation)


def _stats_weight(stat: GraphEdgeStatsModel) -> Decimal:
    correlation = stat.residual_correlation or stat.raw_correlation or ZERO
    stability = stat.stability_score if stat.stability_score is not None else Decimal("0.50")
    lead_lag = abs(stat.lead_lag_score or ZERO)
    validation = max(abs(correlation), lead_lag)
    return _clamp_decimal(
        Decimal("0.35") + (validation * Decimal("0.45")) + (stability * Decimal("0.20")),
        Decimal("0.20"),
        ONE,
    )


def _evidence_weight(evidence: tuple[GraphEdgeEvidenceModel, ...]) -> Decimal:
    if not evidence:
        return Decimal("0.85")
    average_confidence = _average_decimal(Decimal(row.confidence) for row in evidence)
    return _clamp_decimal(Decimal("0.70") + (average_confidence * Decimal("0.30")), ZERO, ONE)


def _hit_rate(trades: list[GraphBacktestTrade]) -> float:
    if not trades:
        return 0.0
    wins = Decimal(sum(1 for trade in trades if trade.return_pct > ZERO))
    return _decimal_float(wins / Decimal(len(trades)))


def _average_return(trades: list[GraphBacktestTrade]) -> float:
    if not trades:
        return 0.0
    return _decimal_float(sum((trade.return_pct for trade in trades), ZERO) / Decimal(len(trades)))


def _trade_drawdown(trades: list[GraphBacktestTrade]) -> float:
    ordered = sorted(trades, key=lambda item: (item.exit_date, item.symbol, item.entry_date))
    if not ordered:
        return 0.0
    equity = ONE
    peak = ONE
    max_drawdown = ZERO
    for trade in ordered:
        equity = equity * (ONE + trade.return_pct)
        peak = max(peak, equity)
        drawdown = (equity / peak) - ONE if peak > ZERO else ZERO
        max_drawdown = min(max_drawdown, drawdown)
    return _decimal_float(max_drawdown)


def _average_float(values: Iterable[Decimal]) -> float:
    rows = list(values)
    if not rows:
        return 0.0
    return _decimal_float(sum(rows, ZERO) / Decimal(len(rows)))


def _average_decimal(values: Iterable[Decimal]) -> Decimal:
    rows = list(values)
    if not rows:
        return ZERO
    return _score_decimal(sum(rows, ZERO) / Decimal(len(rows)))


def _bounded_score(value: Decimal) -> Decimal:
    return _score_decimal(_clamp_decimal(value, Decimal("-1"), ONE))


def _score_decimal(value: Decimal) -> Decimal:
    return value.quantize(SCORE_QUANT)


def _decimal_float(value: Decimal) -> float:
    return float(value.quantize(SUMMARY_QUANT))


def _clamp_decimal(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(high, value))


def _sign(value: Decimal | None) -> Decimal:
    if value is None:
        return ZERO
    if value > ZERO:
        return ONE
    if value < ZERO:
        return Decimal("-1")
    return ZERO


def _direction_from_score(score: Decimal) -> str:
    if score > ZERO:
        return "bullish"
    if score < ZERO:
        return "bearish"
    return "neutral"


def _decimal_text(value: Decimal | None) -> str | None:
    return str(_score_decimal(value)) if value is not None else None
