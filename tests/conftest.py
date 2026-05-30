from __future__ import annotations

import os
import re
from collections.abc import Iterator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from scripts.migrate import run_migrations
from taurus_core.config import DEFAULT_DATABASE_URL, Settings


@pytest.fixture(autouse=True)
def postgres_test_settings(
    monkeypatch: pytest.MonkeyPatch,
    request: pytest.FixtureRequest,
) -> Iterator[Settings | None]:
    if request.node.path.name == "test_config.py":
        yield None
        return

    base_url = os.environ.get("TAURUS_TEST_DATABASE_URL", DEFAULT_DATABASE_URL)
    admin_url = make_url(base_url).set(database="postgres")
    test_database = _test_database_name(request.node.name)
    test_url = make_url(base_url).set(database=test_database).render_as_string(
        hide_password=False
    )

    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
    with admin_engine.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{test_database}"'))
    admin_engine.dispose()

    monkeypatch.setenv("DATABASE_URL", test_url)
    settings = Settings(database_url=test_url)
    run_migrations(settings)

    try:
        yield settings
    finally:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
        with admin_engine.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) "
                    "FROM pg_stat_activity "
                    "WHERE datname = :database AND pid <> pg_backend_pid()"
                ),
                {"database": test_database},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{test_database}"'))
        admin_engine.dispose()


def _test_database_name(test_name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", test_name).strip("_").lower()
    return f"taurus_test_{slug[:32]}_{uuid4().hex[:12]}"
