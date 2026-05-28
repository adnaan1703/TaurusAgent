from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from decimal import Decimal

from taurus_core.agents.base import BaseAnalystAgent
from taurus_core.agents.schemas import AnalystReport, analyst_report_id, stance_from_score
from taurus_core.db.models import GraphEdgeModel, GraphEdgeStatsModel, GraphNodeModel
from taurus_core.db.repositories import CandleRepository, GraphRepository
from taurus_core.intelligence.documents import stable_id

GRAPH_ANALYST_MODEL_VERSION = "graph_rule_v1"
GRAPH_ANALYST_SOURCE_AGENT = "GraphAnalystAgent"
GRAPH_MOMENTUM_LOOKBACK_DAYS = 20
GRAPH_MAX_CONTRIBUTIONS = 10
REPORT_QUANT = Decimal("0.0001")
ZERO = Decimal("0")
ONE = Decimal("1")


@dataclass(frozen=True, slots=True)
class _GraphContribution:
    edge: GraphEdgeModel
    related_node: GraphNodeModel
    stat: GraphEdgeStatsModel
    related_symbol: str
    related_momentum_20d: Decimal
    relation_sign: Decimal
    score_contribution: Decimal
    weight: Decimal
    direction: str
    explanation: str
    metadata: dict[str, object]

    @property
    def source_ids(self) -> list[str]:
        return [
            f"graph_edge:{self.edge.edge_key}",
            (
                "graph_edge_stats:"
                f"{self.edge.edge_key}:{self.stat.stat_window}:{self.stat.as_of_date.isoformat()}"
            ),
        ]


class GraphAnalystAgent(BaseAnalystAgent):
    agent_name = GRAPH_ANALYST_SOURCE_AGENT

    def run(self, *, symbol: str, run_id: str) -> AnalystReport:
        symbol = symbol.upper()
        graph_repo = GraphRepository(self.session)
        center_node = self._company_node(graph_repo, symbol)
        contributions = self._contributions(graph_repo, center_node)
        as_of = self._as_of(symbol, contributions)
        score = _bounded_report_decimal(
            sum((item.score_contribution for item in contributions), ZERO)
        )
        confidence = self._confidence(contributions)
        source_ids = _source_ids(contributions)
        signal = graph_repo.upsert_signal(
            signal_id=self._signal_id(
                run_id=run_id,
                symbol=symbol,
                as_of=as_of,
                source_ids=source_ids,
            ),
            symbol=symbol,
            as_of=as_of,
            score=score,
            confidence=confidence,
            horizon="medium",
            explanation=self._signal_explanation(symbol, score, contributions),
            source_agent=self.agent_name,
            metadata={
                "run_id": run_id,
                "model_version": GRAPH_ANALYST_MODEL_VERSION,
                "contribution_count": len(contributions),
                "lookback_days": GRAPH_MOMENTUM_LOOKBACK_DAYS,
                "deterministic": True,
                "llm_override_allowed": False,
            },
        )
        for contribution in contributions:
            graph_repo.upsert_signal_contribution(
                contribution_id=stable_id(
                    "gsc",
                    signal.signal_id,
                    contribution.edge.edge_key,
                    contribution.stat.stat_window,
                    contribution.stat.as_of_date.isoformat(),
                ),
                signal_id=signal.signal_id,
                edge_key=contribution.edge.edge_key,
                contribution_type=contribution.edge.edge_type or "graph_relationship",
                direction=contribution.direction,
                score_contribution=contribution.score_contribution,
                weight=contribution.weight,
                explanation=contribution.explanation,
                metadata=contribution.metadata,
            )

        report_source_ids = [f"graph_signal:{signal.signal_id}", *source_ids]
        if len(report_source_ids) == 1:
            report_source_ids.append("graph:none")
        return AnalystReport(
            report_id=analyst_report_id(
                run_id=run_id,
                symbol=symbol,
                agent_name=self.agent_name,
                as_of=as_of,
                source_ids=report_source_ids,
            ),
            run_id=run_id,
            symbol=symbol,
            agent_name=self.agent_name,
            as_of=as_of,
            score=score,
            confidence=confidence,
            stance=stance_from_score(score),
            horizon="medium",
            key_points=self._key_points(symbol, contributions),
            risks=self._risks(contributions),
            source_ids=report_source_ids,
            model_version=GRAPH_ANALYST_MODEL_VERSION,
        )

    def _company_node(self, graph_repo: GraphRepository, symbol: str) -> GraphNodeModel | None:
        node = graph_repo.get_node_by_key(f"company:{symbol}")
        if node is not None:
            return node
        nodes = graph_repo.list_nodes(node_type="company", symbol=symbol, limit=1)
        return nodes[0] if nodes else None

    def _contributions(
        self,
        graph_repo: GraphRepository,
        center_node: GraphNodeModel | None,
    ) -> list[_GraphContribution]:
        if center_node is None:
            return []

        contributions: list[_GraphContribution] = []
        edges = graph_repo.list_edges_for_node(node_key=center_node.node_key, limit=250)
        for edge in edges:
            if edge.status not in {"active", "candidate"}:
                continue
            related_node = self._related_node(graph_repo, center_node, edge)
            if related_node is None or not related_node.symbol:
                continue
            stat = self._latest_valid_stat(graph_repo, edge.edge_key)
            if stat is None:
                continue
            momentum = self._related_momentum(
                symbol=related_node.symbol,
                end_date=stat.as_of_date,
            )
            if momentum is None:
                continue
            relation_sign = self._relation_sign(edge, stat)
            if relation_sign == ZERO:
                continue
            contribution = self._score_contribution(
                edge=edge,
                related_node=related_node,
                stat=stat,
                related_momentum_20d=momentum,
                relation_sign=relation_sign,
            )
            if contribution.score_contribution != ZERO:
                contributions.append(contribution)

        return sorted(
            contributions,
            key=lambda item: (abs(item.score_contribution), item.edge.edge_key),
            reverse=True,
        )[:GRAPH_MAX_CONTRIBUTIONS]

    def _related_node(
        self,
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
        return graph_repo.get_node_by_id(related_node_id)

    def _latest_valid_stat(
        self,
        graph_repo: GraphRepository,
        edge_key: str,
    ) -> GraphEdgeStatsModel | None:
        stats = graph_repo.list_edge_stats(edge_key=edge_key, limit=None)
        valid_stats = [
            stat
            for stat in stats
            if not stat.insufficient_data_reason
            and (
                stat.residual_correlation is not None
                or stat.raw_correlation is not None
                or stat.lead_lag_score is not None
            )
        ]
        if not valid_stats:
            return None
        return sorted(
            valid_stats,
            key=lambda item: (item.as_of_date, item.sample_size, item.stat_window),
            reverse=True,
        )[0]

    def _related_momentum(self, *, symbol: str, end_date: date) -> Decimal | None:
        candles = CandleRepository(self.session).get_by_symbol_and_date_range(
            symbol=symbol,
            end_date=end_date,
        )
        if len(candles) < 2:
            return None
        lookback = min(GRAPH_MOMENTUM_LOOKBACK_DAYS, len(candles) - 1)
        start = candles[-lookback - 1].close
        end = candles[-1].close
        if start == ZERO:
            return None
        return Decimal(end / start) - ONE

    def _relation_sign(self, edge: GraphEdgeModel, stat: GraphEdgeStatsModel) -> Decimal:
        if edge.expected_sign == "positive":
            return ONE
        if edge.expected_sign == "negative":
            return Decimal("-1")
        correlation = stat.residual_correlation or stat.raw_correlation
        if correlation is None:
            return ZERO
        if correlation > ZERO:
            return ONE
        if correlation < ZERO:
            return Decimal("-1")
        return ZERO

    def _score_contribution(
        self,
        *,
        edge: GraphEdgeModel,
        related_node: GraphNodeModel,
        stat: GraphEdgeStatsModel,
        related_momentum_20d: Decimal,
        relation_sign: Decimal,
    ) -> _GraphContribution:
        confidence = _clamp_decimal(Decimal(edge.confidence), ZERO, ONE)
        strength = _clamp_decimal(edge.strength or Decimal("0.50"), ZERO, ONE)
        status_weight = ONE if edge.status == "active" else Decimal("0.65")
        stats_weight = self._stats_weight(stat)
        momentum_signal = _clamp_decimal(
            related_momentum_20d / Decimal("0.10"),
            Decimal("-1"),
            ONE,
        )
        weight = _report_decimal(confidence * strength * status_weight * stats_weight)
        score_contribution = _bounded_report_decimal(relation_sign * momentum_signal * weight)
        direction = _direction_from_score(score_contribution)
        explanation = (
            f"{edge.edge_type} edge {edge.edge_key} links to {related_node.symbol}; "
            f"related 20-day momentum is {_pct(related_momentum_20d)} and "
            f"expected sign is {edge.expected_sign}, contributing {score_contribution}."
        )
        metadata = {
            "edge_key": edge.edge_key,
            "edge_status": edge.status,
            "edge_type": edge.edge_type,
            "expected_sign": edge.expected_sign,
            "related_node_key": related_node.node_key,
            "related_symbol": related_node.symbol,
            "related_momentum_20d": str(_report_decimal(related_momentum_20d)),
            "relation_sign": str(relation_sign),
            "stat_window": stat.stat_window,
            "stat_as_of_date": stat.as_of_date.isoformat(),
            "sample_size": stat.sample_size,
            "raw_correlation": _decimal_text(stat.raw_correlation),
            "residual_correlation": _decimal_text(stat.residual_correlation),
            "lead_lag_score": _decimal_text(stat.lead_lag_score),
            "stability_score": _decimal_text(stat.stability_score),
            "confidence": str(_report_decimal(confidence)),
            "strength": str(_report_decimal(strength)),
            "stats_weight": str(_report_decimal(stats_weight)),
            "status_weight": str(_report_decimal(status_weight)),
            "model_version": GRAPH_ANALYST_MODEL_VERSION,
        }
        return _GraphContribution(
            edge=edge,
            related_node=related_node,
            stat=stat,
            related_symbol=related_node.symbol,
            related_momentum_20d=related_momentum_20d,
            relation_sign=relation_sign,
            score_contribution=score_contribution,
            weight=weight,
            direction=direction,
            explanation=explanation,
            metadata=metadata,
        )

    def _stats_weight(self, stat: GraphEdgeStatsModel) -> Decimal:
        correlation = stat.residual_correlation or stat.raw_correlation or ZERO
        stability = stat.stability_score if stat.stability_score is not None else Decimal("0.50")
        lead_lag = abs(stat.lead_lag_score or ZERO)
        validation = max(abs(correlation), lead_lag)
        return _clamp_decimal(
            Decimal("0.35") + (validation * Decimal("0.45")) + (stability * Decimal("0.20")),
            Decimal("0.20"),
            ONE,
        )

    def _confidence(self, contributions: list[_GraphContribution]) -> Decimal:
        if not contributions:
            return Decimal("0.2500")
        total_weight = sum((item.weight for item in contributions), ZERO)
        average_weight = total_weight / Decimal(len(contributions))
        count_bonus = min(Decimal("0.15"), Decimal(len(contributions)) * Decimal("0.025"))
        return _report_decimal(
            _clamp_decimal(
                Decimal("0.35") + average_weight + count_bonus,
                ZERO,
                Decimal("0.90"),
            )
        )

    def _as_of(self, symbol: str, contributions: list[_GraphContribution]) -> datetime:
        if contributions:
            as_of_date = max(item.stat.as_of_date for item in contributions)
            return datetime.combine(as_of_date, time.min, tzinfo=timezone.utc)
        candles = CandleRepository(self.session).get_by_symbol_and_date_range(symbol=symbol)
        if candles:
            return datetime.combine(candles[-1].trade_date, time.min, tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    def _signal_id(
        self,
        *,
        run_id: str,
        symbol: str,
        as_of: datetime,
        source_ids: list[str],
    ) -> str:
        return stable_id(
            "gs",
            run_id,
            symbol,
            as_of.isoformat(),
            ",".join(sorted(source_ids)) or "graph:none",
            GRAPH_ANALYST_MODEL_VERSION,
        )

    def _signal_explanation(
        self,
        symbol: str,
        score: Decimal,
        contributions: list[_GraphContribution],
    ) -> str:
        if not contributions:
            return f"No validated graph relationship evidence produced a directional score for {symbol}."
        return (
            f"{stance_from_score(score).title()} graph score {score} for {symbol} "
            f"from {len(contributions)} validated graph contribution(s)."
        )

    def _key_points(
        self,
        symbol: str,
        contributions: list[_GraphContribution],
    ) -> list[str]:
        if not contributions:
            return [
                f"No validated graph edge stats and related momentum were available for {symbol}; neutral graph signal stored."
            ]
        points = [
            (
                f"{item.direction.title()} graph contribution from {item.related_symbol}: "
                f"{item.edge.edge_type} edge where expected sign is {item.edge.expected_sign}, "
                f"{_pct(item.related_momentum_20d)} related 20-day momentum, "
                f"score contribution {item.score_contribution}."
            )
            for item in contributions[:3]
        ]
        points.append(f"Stored {len(contributions)} graph signal contribution(s) for audit review.")
        return points

    def _risks(self, contributions: list[_GraphContribution]) -> list[str]:
        risks = [
            "Graph analysis is a deterministic research input and cannot create broker orders.",
            "Graph output still requires the debate, trader proposal, risk review, and final approval path.",
        ]
        if not contributions:
            risks.append(
                "Graph edge evidence is absent or not statistically validated for this symbol."
            )
        elif any(item.edge.status == "candidate" for item in contributions):
            risks.append("At least one graph contribution came from a candidate edge awaiting review.")
        return risks


def _source_ids(contributions: list[_GraphContribution]) -> list[str]:
    source_ids: list[str] = []
    for contribution in contributions:
        for source_id in contribution.source_ids:
            if source_id not in source_ids:
                source_ids.append(source_id)
    return source_ids


def _direction_from_score(score: Decimal) -> str:
    if score > ZERO:
        return "bullish"
    if score < ZERO:
        return "bearish"
    return "neutral"


def _bounded_report_decimal(value: Decimal) -> Decimal:
    return _report_decimal(_clamp_decimal(value, Decimal("-1"), ONE))


def _report_decimal(value: Decimal) -> Decimal:
    return value.quantize(REPORT_QUANT)


def _clamp_decimal(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(high, value))


def _pct(value: Decimal) -> str:
    return f"{_report_decimal(value * Decimal('100'))}%"


def _decimal_text(value: Decimal | None) -> str | None:
    return str(_report_decimal(value)) if value is not None else None
