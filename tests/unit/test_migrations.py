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
