from __future__ import annotations

import os
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.db.repositories import GraphRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory
from taurus_core.domain.instruments import Instrument
from taurus_core.graph.neo4j_projection import build_neo4j_driver, rebuild_neo4j_projection


def test_neo4j_projection_is_skipped_when_disabled(tmp_path: Path) -> None:
    settings = Settings(
        database_url=f"sqlite:///{tmp_path / 'taurus.db'}",
        taurus_neo4j_enabled=False,
        taurus_neo4j_uri="bolt://neo4j:secret@localhost:7687",
    )
    run_migrations(settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        summary = rebuild_neo4j_projection(
            session,
            settings=settings,
            driver=_FakeNeo4jDriver(),
        )

    assert summary.enabled is False
    assert summary.skipped_reason == "TAURUS_NEO4J_ENABLED is false"
    assert summary.neo4j_uri == "bolt://neo4j:***REDACTED***@localhost:7687"
    assert summary.nodes_projected == 0
    assert summary.edges_projected == 0


def test_neo4j_projection_rebuild_uses_stable_keys_and_is_idempotent(
    tmp_path: Path,
) -> None:
    settings = _settings_for_temp_db(tmp_path, neo4j_enabled=True)
    _seed_projection_graph(settings)
    driver = _FakeNeo4jDriver()
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        source_counts_before = GraphRepository(session).overview_counts()
        first = rebuild_neo4j_projection(
            session,
            settings=settings,
            driver=driver,
        )
        first_nodes = dict(driver.nodes)
        first_edges = dict(driver.edges)
        second = rebuild_neo4j_projection(
            session,
            settings=settings,
            driver=driver,
        )
        source_counts_after = GraphRepository(session).overview_counts()

    assert driver.connectivity_checks == 2
    assert first.source_counts == source_counts_before
    assert source_counts_after == source_counts_before
    assert first.nodes_projected == 2
    assert first.edges_projected == 1
    assert second.nodes_projected == first.nodes_projected
    assert second.edges_projected == first.edges_projected
    assert driver.nodes == first_nodes
    assert driver.edges == first_edges
    assert set(driver.nodes) == {"company:INFY", "company:TCS"}
    assert set(driver.edges) == {"peer:INFY:TCS"}
    assert driver.edges["peer:INFY:TCS"]["source_node_key"] == "company:INFY"
    assert driver.edges["peer:INFY:TCS"]["target_node_key"] == "company:TCS"
    assert driver.edges["peer:INFY:TCS"]["properties"]["status"] == "active"


def test_live_neo4j_projection_skips_cleanly_when_service_is_absent(
    tmp_path: Path,
) -> None:
    if os.environ.get("TAURUS_NEO4J_INTEGRATION") != "1":
        pytest.skip("Set TAURUS_NEO4J_INTEGRATION=1 to exercise a live Neo4j service.")

    settings = _settings_for_temp_db(tmp_path, neo4j_enabled=True)
    _seed_projection_graph(settings)
    driver = build_neo4j_driver(settings)
    try:
        driver.verify_connectivity()
    except Exception as exc:
        pytest.skip(f"Neo4j service is not available: {exc}")

    session_factory = build_session_factory(settings)
    try:
        with session_factory() as session:
            first = rebuild_neo4j_projection(session, settings=settings, driver=driver)
            second = rebuild_neo4j_projection(session, settings=settings, driver=driver)
    finally:
        driver.close()

    assert second.nodes_projected == first.nodes_projected == 2
    assert second.edges_projected == first.edges_projected == 1


def _settings_for_temp_db(tmp_path: Path, *, neo4j_enabled: bool) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'taurus.db'}",
        taurus_neo4j_enabled=neo4j_enabled,
    )


def _seed_projection_graph(settings: Settings) -> None:
    run_migrations(settings)
    session_factory = build_session_factory(settings)
    with session_factory() as session:
        instruments = InstrumentRepository(session)
        instruments.upsert(Instrument(symbol="INFY", name="Infosys Limited"))
        instruments.upsert(Instrument(symbol="TCS", name="Tata Consultancy Services"))

        graph_repo = GraphRepository(session)
        graph_repo.upsert_node(
            node_key="company:INFY",
            node_type="company",
            display_name="Infosys Limited",
            symbol="INFY",
            metadata={"fixture": True},
        )
        graph_repo.upsert_node(
            node_key="company:TCS",
            node_type="company",
            display_name="Tata Consultancy Services",
            symbol="TCS",
            metadata={"fixture": True},
        )
        graph_repo.upsert_edge(
            edge_key="peer:INFY:TCS",
            source_node_key="company:INFY",
            target_node_key="company:TCS",
            edge_type="peer",
            direction="bidirectional",
            expected_sign="positive",
            strength=Decimal("0.80"),
            evidence_type="fixture",
            confidence=Decimal("0.75"),
            inferred=True,
            mechanism="Fixture peer relationship.",
            tradability_relevance="signal",
            status="active",
            valid_from=date(2026, 5, 27),
            source_file="fixture.csv",
            source_row_hash="row-1",
            metadata={"fixture": True},
        )
        session.commit()


class _FakeNeo4jDriver:
    def __init__(self) -> None:
        self.connectivity_checks = 0
        self.closed = False
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}

    def verify_connectivity(self) -> None:
        self.connectivity_checks += 1

    def execute_query(
        self,
        query_: str,
        parameters_: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> tuple[list[object], None, list[object]]:
        query = " ".join(query_.split())
        parameters = parameters_ or {}
        if "MATCH ()-[edge:TAURUS_EDGE]->() DELETE edge" in query:
            self.edges.clear()
        elif "MATCH (node:TaurusGraphNode) DETACH DELETE node" in query:
            self.nodes.clear()
        elif "MERGE (node:TaurusGraphNode" in query:
            self.nodes[parameters["node_key"]] = dict(parameters)
        elif "MERGE (source)-[edge:TAURUS_EDGE" in query:
            self.edges[parameters["edge_key"]] = {
                "source_node_key": parameters["source_node_key"],
                "target_node_key": parameters["target_node_key"],
                "properties": dict(parameters),
            }
        return [], None, []

    def close(self) -> None:
        self.closed = True
