from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

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
    _add_missing_backtest_signal_columns(engine)
    _add_missing_daily_candle_columns(engine)


def _add_missing_backtest_signal_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "backtest_signals" not in inspector.get_table_names():
        return

    existing_columns = {
        column["name"]
        for column in inspector.get_columns("backtest_signals")
    }
    statements: list[str] = []
    if "feature_snapshot_id" not in existing_columns:
        statements.append("ALTER TABLE backtest_signals ADD COLUMN feature_snapshot_id VARCHAR(128)")
    if "explanation" not in existing_columns:
        statements.append("ALTER TABLE backtest_signals ADD COLUMN explanation JSON")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


def _add_missing_daily_candle_columns(engine: Engine) -> None:
    inspector = inspect(engine)
    if "daily_candles" not in inspector.get_table_names():
        return

    existing_columns = {column["name"] for column in inspector.get_columns("daily_candles")}
    statements: list[str] = []
    source_added = False
    available_time_added = False
    if "source" not in existing_columns:
        statements.append("ALTER TABLE daily_candles ADD COLUMN source VARCHAR(128)")
        source_added = True
    if "data_available_time" not in existing_columns:
        statements.append("ALTER TABLE daily_candles ADD COLUMN data_available_time TIMESTAMP")
        available_time_added = True

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        if source_added:
            connection.execute(
                text(
                    "UPDATE daily_candles "
                    "SET source = 'mock_market_data' "
                    "WHERE source IS NULL OR source = ''"
                )
            )
        if available_time_added:
            if engine.dialect.name == "postgresql":
                connection.execute(
                    text(
                        "UPDATE daily_candles "
                        "SET data_available_time = trade_date::timestamp + interval '18 hours' "
                        "WHERE data_available_time IS NULL"
                    )
                )
            else:
                connection.execute(
                    text(
                        "UPDATE daily_candles "
                        "SET data_available_time = datetime(trade_date || ' 18:00:00') "
                        "WHERE data_available_time IS NULL"
                    )
                )


if __name__ == "__main__":
    run_migrations()
    print("Taurus database schema is up to date.")
