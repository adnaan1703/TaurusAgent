from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

from neo4j import GraphDatabase
from sqlalchemy.orm import Session

from taurus_core.config import Settings, get_settings
from taurus_core.db.models import GraphEdgeModel, GraphNodeModel
from taurus_core.db.repositories import GraphRepository
from taurus_core.observability.metrics import (
    record_graph_job_failure,
    record_graph_projection_summary,
)


class Neo4jDriver(Protocol):
    def verify_connectivity(self) -> None:
        ...

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> Any:
        ...

    def close(self) -> None:
        ...


@dataclass(frozen=True, slots=True)
class Neo4jProjectionSummary:
    enabled: bool
    skipped_reason: str
    neo4j_uri: str
    neo4j_database: str
    source_counts: dict[str, int]
    nodes_projected: int
    edges_projected: int
    started_at: datetime
    finished_at: datetime

    def to_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "skipped_reason": self.skipped_reason,
            "neo4j_uri": self.neo4j_uri,
            "neo4j_database": self.neo4j_database,
            "source_counts": dict(self.source_counts),
            "nodes_projected": self.nodes_projected,
            "edges_projected": self.edges_projected,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
        }


def build_neo4j_driver(settings: Settings | None = None) -> Neo4jDriver:
    settings = settings or get_settings()
    return GraphDatabase.driver(
        settings.taurus_neo4j_uri,
        auth=(settings.taurus_neo4j_user, settings.taurus_neo4j_password),
    )


def rebuild_neo4j_projection(
    session: Session,
    *,
    settings: Settings | None = None,
    driver: Neo4jDriver | None = None,
    verify_connectivity: bool = True,
) -> Neo4jProjectionSummary:
    settings = settings or get_settings()
    started_at = _utc_now()
    if not settings.taurus_neo4j_enabled:
        summary = Neo4jProjectionSummary(
            enabled=False,
            skipped_reason="TAURUS_NEO4J_ENABLED is false",
            neo4j_uri=_redact_url_password(settings.taurus_neo4j_uri),
            neo4j_database=settings.taurus_neo4j_database,
            source_counts={},
            nodes_projected=0,
            edges_projected=0,
            started_at=started_at,
            finished_at=_utc_now(),
        )
        record_graph_projection_summary(summary)
        return summary

    driver_was_created = driver is None
    driver = driver or build_neo4j_driver(settings)
    try:
        if verify_connectivity:
            driver.verify_connectivity()
        summary = Neo4jProjectionRebuilder(
            session=session,
            driver=driver,
            database=settings.taurus_neo4j_database,
            uri=_redact_url_password(settings.taurus_neo4j_uri),
        ).rebuild(started_at=started_at)
        record_graph_projection_summary(summary)
        return summary
    except Exception as exc:
        record_graph_job_failure(job="projection", error_type=exc.__class__.__name__)
        raise
    finally:
        if driver_was_created:
            driver.close()


class Neo4jProjectionRebuilder:
    def __init__(
        self,
        *,
        session: Session,
        driver: Neo4jDriver,
        database: str,
        uri: str,
    ) -> None:
        self.graph_repo = GraphRepository(session)
        self.driver = driver
        self.database = database
        self.uri = uri

    def rebuild(self, *, started_at: datetime | None = None) -> Neo4jProjectionSummary:
        started_at = started_at or _utc_now()
        source_counts = self.graph_repo.overview_counts()
        nodes = self.graph_repo.list_nodes(limit=None)
        edges = self.graph_repo.list_edges(limit=None)
        node_lookup = {node.id: node for node in nodes}

        self._ensure_constraints()
        self._clear_projection()
        for node in nodes:
            self._project_node(node)
        for edge in edges:
            source = node_lookup.get(edge.source_node_id)
            target = node_lookup.get(edge.target_node_id)
            if source is None or target is None:
                raise ValueError(f"Graph edge {edge.edge_key} references missing graph nodes.")
            self._project_edge(edge=edge, source=source, target=target)

        return Neo4jProjectionSummary(
            enabled=True,
            skipped_reason="",
            neo4j_uri=self.uri,
            neo4j_database=self.database,
            source_counts=source_counts,
            nodes_projected=len(nodes),
            edges_projected=len(edges),
            started_at=started_at,
            finished_at=_utc_now(),
        )

    def _ensure_constraints(self) -> None:
        self._execute(
            """
            CREATE CONSTRAINT taurus_graph_node_key IF NOT EXISTS
            FOR (node:TaurusGraphNode)
            REQUIRE node.node_key IS UNIQUE
            """,
        )

    def _clear_projection(self) -> None:
        self._execute("MATCH ()-[edge:TAURUS_EDGE]->() DELETE edge")
        self._execute("MATCH (node:TaurusGraphNode) DETACH DELETE node")

    def _project_node(self, node: GraphNodeModel) -> None:
        self._execute(
            """
            MERGE (node:TaurusGraphNode {node_key: $node_key})
            SET node.node_type = $node_type,
                node.display_name = $display_name,
                node.symbol = $symbol,
                node.isin = $isin,
                node.metadata_json = $metadata_json,
                node.created_at = $created_at,
                node.updated_at = $updated_at
            """,
            {
                "node_key": node.node_key,
                "node_type": node.node_type,
                "display_name": node.display_name,
                "symbol": node.symbol,
                "isin": node.isin,
                "metadata_json": _json_dumps(node.node_metadata),
                "created_at": _iso_or_none(node.created_at),
                "updated_at": _iso_or_none(node.updated_at),
            },
        )

    def _project_edge(
        self,
        *,
        edge: GraphEdgeModel,
        source: GraphNodeModel,
        target: GraphNodeModel,
    ) -> None:
        self._execute(
            """
            MATCH (source:TaurusGraphNode {node_key: $source_node_key})
            MATCH (target:TaurusGraphNode {node_key: $target_node_key})
            MERGE (source)-[edge:TAURUS_EDGE {edge_key: $edge_key}]->(target)
            SET edge.edge_type = $edge_type,
                edge.direction = $direction,
                edge.expected_sign = $expected_sign,
                edge.strength = $strength,
                edge.evidence_type = $evidence_type,
                edge.confidence = $confidence,
                edge.inferred = $inferred,
                edge.mechanism = $mechanism,
                edge.tradability_relevance = $tradability_relevance,
                edge.status = $status,
                edge.valid_from = $valid_from,
                edge.valid_to = $valid_to,
                edge.source_file = $source_file,
                edge.source_row_hash = $source_row_hash,
                edge.metadata_json = $metadata_json,
                edge.created_at = $created_at,
                edge.updated_at = $updated_at
            """,
            {
                "source_node_key": source.node_key,
                "target_node_key": target.node_key,
                "edge_key": edge.edge_key,
                "edge_type": edge.edge_type,
                "direction": edge.direction,
                "expected_sign": edge.expected_sign,
                "strength": _decimal_to_float(edge.strength),
                "evidence_type": edge.evidence_type,
                "confidence": _decimal_to_float(edge.confidence),
                "inferred": edge.inferred,
                "mechanism": edge.mechanism,
                "tradability_relevance": edge.tradability_relevance,
                "status": edge.status,
                "valid_from": _iso_or_none(edge.valid_from),
                "valid_to": _iso_or_none(edge.valid_to),
                "source_file": edge.source_file,
                "source_row_hash": edge.source_row_hash,
                "metadata_json": _json_dumps(edge.edge_metadata),
                "created_at": _iso_or_none(edge.created_at),
                "updated_at": _iso_or_none(edge.updated_at),
            },
        )

    def _execute(self, query: str, parameters: dict[str, Any] | None = None) -> Any:
        return self.driver.execute_query(
            query,
            parameters_=parameters or {},
            database_=self.database,
        )


def _decimal_to_float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def _iso_or_none(value: date | datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _json_dumps(value: Any) -> str:
    return json.dumps(value or {}, default=str, sort_keys=True, separators=(",", ":"))


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _redact_url_password(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.password is None:
        return value
    username = parsed.username or ""
    hostname = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    userinfo = f"{username}:***REDACTED***@" if username else ""
    return urlunsplit(
        (
            parsed.scheme,
            f"{userinfo}{hostname}{port}",
            parsed.path,
            parsed.query,
            parsed.fragment,
        )
    )
