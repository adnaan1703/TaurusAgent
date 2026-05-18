from __future__ import annotations

from taurus_core.config import Settings, get_settings
from taurus_core.db.models import Base
from taurus_core.db.session import create_engine_from_url


def run_migrations(settings: Settings | None = None) -> None:
    """M1 uses SQLAlchemy metadata as the migration source of truth.

    This is intentionally small until schema history is needed. The command is
    idempotent and creates missing M1 tables without dropping existing data.
    """
    settings = settings or get_settings()
    engine = create_engine_from_url(settings.database_url)
    Base.metadata.create_all(bind=engine)


if __name__ == "__main__":
    run_migrations()
    print("M1 database schema is up to date.")
