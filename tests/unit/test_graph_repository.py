from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.db.models import Base, GraphEdgeModel, GraphNodeModel
from taurus_core.db.repositories import GraphRepository, InstrumentRepository
from taurus_core.db.session import build_session_factory, create_engine_from_url
from taurus_core.domain.instruments import Instrument


def test_migrations_create_graph_tables_on_sqlite(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)

    run_migrations(settings)

    inspector = inspect(create_engine_from_url(settings.database_url))
    tables = set(inspector.get_table_names())
    assert {
        "graph_nodes",
        "graph_edges",
        "graph_edge_evidence",
        "graph_edge_stats",
        "graph_signals",
        "graph_signal_contributions",
    }.issubset(tables)


def test_graph_tables_compile_with_postgres_dialect() -> None:
    ddl = "\n".join(
        str(CreateTable(Base.metadata.tables[table_name]).compile(dialect=postgresql.dialect()))
        for table_name in (
            "graph_nodes",
            "graph_edges",
            "graph_edge_evidence",
            "graph_edge_stats",
            "graph_signals",
            "graph_signal_contributions",
        )
    )

    assert "CREATE TABLE graph_nodes" in ddl
    assert "CREATE TABLE graph_signal_contributions" in ddl


def test_graph_node_and_edge_upserts_are_idempotent(tmp_path: Path) -> None:
    settings = _settings_for_temp_db(tmp_path)
    run_migrations(settings)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        instrument_repo = InstrumentRepository(session)
        instrument_repo.upsert(Instrument(symbol="INFY", name="Infosys Limited"))
        instrument_repo.upsert(Instrument(symbol="TCS", name="Tata Consultancy Services"))

        graph_repo = GraphRepository(session)
        source = graph_repo.upsert_node(
            node_key="company:INFY",
            node_type="company",
            display_name="Infosys Limited",
            symbol="infy",
            metadata={"batch": "m20.1"},
        )
        source_again = graph_repo.upsert_node(
            node_key="company:INFY",
            node_type="company",
            display_name="Infosys Ltd",
            symbol="INFY",
            metadata={"batch": "m20.1", "updated": True},
        )
        target = graph_repo.upsert_node(
            node_key="company:TCS",
            node_type="company",
            display_name="Tata Consultancy Services",
            symbol="TCS",
        )

        edge = graph_repo.upsert_edge(
            edge_key="peer:INFY:TCS",
            source_node_key=source.node_key,
            target_node_key=target.node_key,
            edge_type="peer",
            expected_sign="mixed",
            strength=Decimal("0.70"),
            evidence_type="curated",
            confidence=Decimal("0.65"),
            inferred=True,
            mechanism="Indian IT services peers share demand drivers.",
            tradability_relevance="watchlist",
            status="candidate",
            source_file="company_edges.csv",
            source_row_hash="hash-1",
            metadata={"relationship": "peer"},
        )
        edge_again = graph_repo.upsert_edge(
            edge_key="peer:INFY:TCS",
            source_node_key="company:INFY",
            target_node_key="company:TCS",
            edge_type="peer",
            expected_sign="positive",
            strength=Decimal("0.80"),
            evidence_type="curated",
            confidence=Decimal("0.75"),
            inferred=False,
            mechanism="Updated mechanism.",
            tradability_relevance="signal",
            status="active",
            source_file="company_edges.csv",
            source_row_hash="hash-2",
            metadata={"relationship": "peer", "updated": True},
        )

        evidence = graph_repo.upsert_edge_evidence(
            edge_key=edge.edge_key,
            evidence_id="evidence:INFY:TCS",
            claim_type="peer_mapping",
            claim_summary="Both companies are IT services peers.",
            confidence=Decimal("0.80"),
            source_file="source_evidence.csv",
            source_row_hash="evidence-hash",
        )
        evidence_again = graph_repo.upsert_edge_evidence(
            edge_key=edge.edge_key,
            evidence_id=evidence.evidence_id,
            claim_type="peer_mapping",
            claim_summary="Updated peer evidence.",
            confidence=Decimal("0.90"),
            source_file="source_evidence.csv",
            source_row_hash="evidence-hash-2",
        )
        stats = graph_repo.upsert_edge_stats(
            edge_key=edge.edge_key,
            window="90d",
            as_of_date=date(2026, 5, 27),
            sample_size=90,
            raw_correlation=Decimal("0.42"),
        )
        stats_again = graph_repo.upsert_edge_stats(
            edge_key=edge.edge_key,
            window="90d",
            as_of_date=date(2026, 5, 27),
            sample_size=91,
            raw_correlation=Decimal("0.43"),
        )
        signal = graph_repo.upsert_signal(
            signal_id="signal:INFY:2026-05-27",
            symbol="infy",
            as_of=datetime(2026, 5, 27, 9, 15, tzinfo=timezone.utc),
            score=Decimal("0.20"),
            confidence=Decimal("0.60"),
            horizon="swing",
            explanation="Peer graph signal.",
        )
        contribution = graph_repo.upsert_signal_contribution(
            contribution_id="contrib:signal:INFY:TCS",
            signal_id=signal.signal_id,
            edge_key=edge.edge_key,
            contribution_type="peer_momentum",
            score_contribution=Decimal("0.20"),
            weight=Decimal("1.00"),
        )
        contribution_again = graph_repo.upsert_signal_contribution(
            contribution_id=contribution.contribution_id,
            signal_id=signal.signal_id,
            edge_key=edge.edge_key,
            contribution_type="peer_momentum",
            score_contribution=Decimal("0.25"),
            weight=Decimal("1.00"),
        )

        assert source_again.id == source.id
        assert edge_again.id == edge.id
        assert evidence_again.evidence_id == evidence.evidence_id
        assert stats_again.id == stats.id
        assert contribution_again.contribution_id == contribution.contribution_id
        assert edge_again.status == "active"
        assert edge_again.confidence == Decimal("0.7500")
        assert graph_repo.list_edges_for_node(node_key="company:INFY") == [edge_again]
        assert graph_repo.list_edge_evidence(edge_key=edge.edge_key) == [evidence_again]
        assert graph_repo.list_edge_stats(edge_key=edge.edge_key) == [stats_again]
        assert graph_repo.list_signals(symbol="INFY") == [signal]
        assert graph_repo.list_signal_contributions(signal_id=signal.signal_id) == [
            contribution_again
        ]
        assert graph_repo.overview_counts() == {
            "nodes": 2,
            "edges": 1,
            "active_edges": 1,
            "candidate_edges": 0,
            "edge_evidence": 1,
            "edge_stats": 1,
            "signals": 1,
            "signal_contributions": 1,
        }

        node_count = session.scalar(select(func.count()).select_from(GraphNodeModel))
        edge_count = session.scalar(select(func.count()).select_from(GraphEdgeModel))

    assert node_count == 2
    assert edge_count == 1


def _settings_for_temp_db(tmp_path: Path) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp_path / 'taurus.db'}")
