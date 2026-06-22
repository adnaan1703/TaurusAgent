from __future__ import annotations

from sqlalchemy import inspect, text

from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.db.repositories import GraphRepository
from taurus_core.db.session import build_session_factory, create_engine_from_url


def test_migration_widens_agent_model_version_columns(
    postgres_test_settings: Settings,
) -> None:
    settings = postgres_test_settings
    engine = create_engine_from_url(settings.database_url)

    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE trader_proposals "
                "ALTER COLUMN model_version TYPE VARCHAR(128)"
            )
        )

    run_migrations(settings)

    inspector = inspect(engine)
    columns = {
        column["name"]: column
        for column in inspector.get_columns("trader_proposals")
    }
    assert str(columns["model_version"]["type"]).lower() == "text"


def test_migration_creates_and_seeds_default_profile(
    postgres_test_settings: Settings,
) -> None:
    settings = postgres_test_settings
    engine = create_engine_from_url(settings.database_url)

    run_migrations(settings)

    inspector = inspect(engine)
    assert "taurus_profiles" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("taurus_profiles")}
    assert {
        "profile_id",
        "display_name",
        "starting_corpus_inr",
        "currency",
        "status",
        "description",
        "profile_metadata",
        "created_at",
        "updated_at",
    } <= columns
    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT profile_id, display_name, starting_corpus_inr, currency, status "
                "FROM taurus_profiles WHERE profile_id = 'local-paper'"
            )
        ).one()
    assert row.profile_id == "local-paper"
    assert row.display_name == "Local Paper"
    assert row.starting_corpus_inr == 10000
    assert row.currency == "INR"
    assert row.status == "ACTIVE"


def test_migration_replaces_legacy_graph_edge_inferred_column(
    postgres_test_settings: Settings,
) -> None:
    settings = postgres_test_settings
    engine = create_engine_from_url(settings.database_url)
    session_factory = build_session_factory(settings)

    with session_factory() as session:
        graph_repo = GraphRepository(session)
        graph_repo.upsert_node(
            node_key="company:INFY",
            node_type="company",
            display_name="Infosys Limited",
        )
        graph_repo.upsert_node(
            node_key="company:TCS",
            node_type="company",
            display_name="Tata Consultancy Services",
        )
        graph_repo.upsert_edge(
            edge_key="peer:INFY:TCS",
            source_node_key="company:INFY",
            target_node_key="company:TCS",
            edge_type="peer",
            provenance_type="inferred",
            status="candidate",
        )
        session.commit()

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE graph_edges DROP CONSTRAINT ck_graph_edges_provenance_type")
        )
        connection.execute(
            text("ALTER TABLE graph_edges ADD COLUMN inferred BOOLEAN NOT NULL DEFAULT false")
        )
        connection.execute(text("UPDATE graph_edges SET inferred = true"))
        connection.execute(text("ALTER TABLE graph_edges DROP COLUMN provenance_type"))

    run_migrations(settings)

    inspector = inspect(engine)
    columns = {column["name"] for column in inspector.get_columns("graph_edges")}
    constraints = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("graph_edges")
    }
    with engine.begin() as connection:
        row = connection.execute(
            text("SELECT provenance_type FROM graph_edges WHERE edge_key = 'peer:INFY:TCS'")
        ).one()

    assert "provenance_type" in columns
    assert "inferred" not in columns
    assert "ck_graph_edges_provenance_type" in constraints
    assert row.provenance_type == "inferred"
