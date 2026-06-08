from __future__ import annotations

from sqlalchemy import inspect, text

from scripts.migrate import run_migrations
from taurus_core.config import Settings
from taurus_core.db.session import create_engine_from_url


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
