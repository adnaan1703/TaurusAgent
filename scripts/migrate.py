from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from taurus_core.config import Settings, get_settings
from taurus_core.db.graph_contracts import GRAPH_EDGE_PROVENANCE_SQL_LIST
from taurus_core.db.models import Base, TaurusProfileModel
from taurus_core.db.session import create_engine_from_url
from taurus_core.profiles.schemas import (
    DEFAULT_PROFILE_CURRENCY,
    DEFAULT_PROFILE_DISPLAY_NAME,
    DEFAULT_PROFILE_ID,
    DEFAULT_PROFILE_STARTING_CORPUS_INR,
)


def run_migrations(settings: Settings | None = None) -> None:
    """Use SQLAlchemy metadata as the migration source of truth.

    This is intentionally small until schema history is needed. The command is
    idempotent and creates missing tables without dropping existing data.
    """
    settings = settings or get_settings()
    engine = create_engine_from_url(settings.database_url)
    Base.metadata.create_all(bind=engine)
    _migrate_graph_edge_provenance(engine)
    _seed_default_profile(engine)
    _add_missing_backtest_signal_columns(engine)
    _add_missing_daily_candle_columns(engine)
    _widen_graph_edge_columns(engine)
    _add_missing_m28_position_lifecycle_columns(engine)
    _add_missing_m52_profile_lineage_columns(engine)
    _widen_agent_model_version_columns(engine)


def _seed_default_profile(engine: Engine) -> None:
    inspector = inspect(engine)
    if "taurus_profiles" not in inspector.get_table_names():
        return

    with engine.begin() as connection:
        existing = connection.execute(
            text("SELECT profile_id FROM taurus_profiles WHERE profile_id = :profile_id"),
            {"profile_id": DEFAULT_PROFILE_ID},
        ).first()
        if existing is not None:
            return
        connection.execute(
            TaurusProfileModel.__table__.insert().values(
                profile_id=DEFAULT_PROFILE_ID,
                display_name=DEFAULT_PROFILE_DISPLAY_NAME,
                starting_corpus_inr=DEFAULT_PROFILE_STARTING_CORPUS_INR,
                currency=DEFAULT_PROFILE_CURRENCY,
                status="ACTIVE",
                description="",
                profile_metadata={},
            )
        )


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


def _widen_graph_edge_columns(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    inspector = inspect(engine)
    if "graph_edges" not in inspector.get_table_names():
        return

    columns = {
        column["name"]: column
        for column in inspector.get_columns("graph_edges")
    }
    tradability_relevance = columns.get("tradability_relevance")
    if tradability_relevance is None:
        return

    column_type = str(tradability_relevance["type"]).lower()
    if column_type == "text":
        return

    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE graph_edges ALTER COLUMN tradability_relevance TYPE TEXT")
        )


def _migrate_graph_edge_provenance(engine: Engine) -> None:
    inspector = inspect(engine)
    if "graph_edges" not in inspector.get_table_names():
        return

    columns = {
        column["name"]
        for column in inspector.get_columns("graph_edges")
    }
    has_provenance_type = "provenance_type" in columns
    has_inferred = "inferred" in columns

    statements: list[str] = []
    if not has_provenance_type:
        statements.append("ALTER TABLE graph_edges ADD COLUMN provenance_type VARCHAR(32)")
    if has_inferred:
        statements.append(
            "UPDATE graph_edges "
            "SET provenance_type = CASE "
            "WHEN inferred IS TRUE THEN 'inferred' "
            "ELSE 'deterministic' END "
            "WHERE provenance_type IS NULL OR provenance_type = ''"
        )
    else:
        statements.append(
            "UPDATE graph_edges "
            "SET provenance_type = 'deterministic' "
            "WHERE provenance_type IS NULL OR provenance_type = ''"
        )

    if engine.dialect.name == "postgresql":
        statements.extend(
            [
                "ALTER TABLE graph_edges "
                "ALTER COLUMN provenance_type SET DEFAULT 'deterministic'",
                "ALTER TABLE graph_edges ALTER COLUMN provenance_type SET NOT NULL",
            ]
        )
        if has_inferred:
            statements.append("ALTER TABLE graph_edges DROP COLUMN inferred")
    elif has_inferred:
        # Taurus runtime rejects SQLite URLs, but keep non-Postgres test/dev
        # migrations data-safe by leaving the legacy column in place.
        pass

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))

        if engine.dialect.name == "postgresql":
            constraints = {
                constraint["name"]
                for constraint in inspect(connection).get_check_constraints("graph_edges")
            }
            if "ck_graph_edges_provenance_type" not in constraints:
                connection.execute(
                    text(
                        "ALTER TABLE graph_edges ADD CONSTRAINT "
                        "ck_graph_edges_provenance_type CHECK "
                        f"(provenance_type IN ({GRAPH_EDGE_PROVENANCE_SQL_LIST}))"
                    )
                )


def _add_missing_m28_position_lifecycle_columns(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    statements: list[str] = []

    for table in ("paper_accounts", "paper_orders", "paper_fills", "paper_positions"):
        if table not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "portfolio_id" not in columns:
            statements.append(
                f"ALTER TABLE {table} "
                "ADD COLUMN portfolio_id VARCHAR(128) NOT NULL DEFAULT 'local-paper'"
            )

    if "trader_proposals" in table_names:
        columns = {column["name"] for column in inspector.get_columns("trader_proposals")}
        if "portfolio_id" not in columns:
            statements.append(
                "ALTER TABLE trader_proposals "
                "ADD COLUMN portfolio_id VARCHAR(128) NOT NULL DEFAULT 'local-paper'"
            )
        if "current_position_quantity" not in columns:
            statements.append(
                "ALTER TABLE trader_proposals "
                "ADD COLUMN current_position_quantity INTEGER NOT NULL DEFAULT 0"
            )
        if "current_position_pct_nav" not in columns:
            statements.append(
                "ALTER TABLE trader_proposals "
                "ADD COLUMN current_position_pct_nav NUMERIC(8, 4) NOT NULL DEFAULT 0"
            )
        if "target_position_pct_nav" not in columns:
            statements.append(
                "ALTER TABLE trader_proposals "
                "ADD COLUMN target_position_pct_nav NUMERIC(8, 4) NOT NULL DEFAULT 0"
            )
        if "lifecycle_trigger" not in columns:
            statements.append(
                "ALTER TABLE trader_proposals "
                "ADD COLUMN lifecycle_trigger VARCHAR(32) NOT NULL DEFAULT 'new_entry'"
            )
        if "evaluation_mode" not in columns:
            statements.append(
                "ALTER TABLE trader_proposals "
                "ADD COLUMN evaluation_mode VARCHAR(32) NOT NULL DEFAULT 'after_close'"
            )
        if "position_management_summary" not in columns:
            statements.append(
                "ALTER TABLE trader_proposals "
                "ADD COLUMN position_management_summary TEXT NOT NULL DEFAULT "
                "'Legacy proposal before position-aware TraderAgent.'"
            )

    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_paper_accounts_portfolio_updated_at "
        "ON paper_accounts (portfolio_id, updated_at)",
        "CREATE INDEX IF NOT EXISTS ix_paper_orders_portfolio_symbol_time "
        "ON paper_orders (portfolio_id, symbol, submitted_at)",
        "CREATE INDEX IF NOT EXISTS ix_paper_fills_portfolio_symbol_time "
        "ON paper_fills (portfolio_id, symbol, filled_at)",
        "CREATE INDEX IF NOT EXISTS ix_paper_positions_portfolio_symbol "
        "ON paper_positions (portfolio_id, symbol)",
    ]

    if not statements and not any(table in table_names for table in ("paper_accounts", "paper_orders", "paper_fills", "paper_positions")):
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        for statement in index_statements:
            table_name = statement.split(" ON ", 1)[1].split(" ", 1)[0]
            if table_name in table_names:
                connection.execute(text(statement))


def _add_missing_m52_profile_lineage_columns(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    lineage_tables = (
        "paper_runs",
        "analyst_reports",
        "debate_reports",
        "risk_reviews",
        "final_decisions",
    )
    statements: list[str] = []
    for table in lineage_tables:
        if table not in table_names:
            continue
        columns = {column["name"] for column in inspector.get_columns(table)}
        if "portfolio_id" not in columns:
            statements.append(
                f"ALTER TABLE {table} "
                "ADD COLUMN portfolio_id VARCHAR(128) NOT NULL DEFAULT 'local-paper'"
            )

    index_statements = [
        "CREATE INDEX IF NOT EXISTS ix_paper_runs_portfolio_started_at "
        "ON paper_runs (portfolio_id, started_at)",
        "CREATE INDEX IF NOT EXISTS ix_paper_runs_portfolio_status "
        "ON paper_runs (portfolio_id, status)",
        "CREATE INDEX IF NOT EXISTS ix_analyst_reports_portfolio_as_of "
        "ON analyst_reports (portfolio_id, as_of)",
        "CREATE INDEX IF NOT EXISTS ix_debate_reports_portfolio_as_of "
        "ON debate_reports (portfolio_id, as_of)",
        "CREATE INDEX IF NOT EXISTS ix_risk_reviews_portfolio_as_of "
        "ON risk_reviews (portfolio_id, as_of)",
        "CREATE INDEX IF NOT EXISTS ix_final_decisions_portfolio_as_of "
        "ON final_decisions (portfolio_id, as_of)",
    ]

    payload_backfills = [
        f"UPDATE {table} "
        "SET payload = (COALESCE(payload::jsonb, '{}'::jsonb) "
        "|| jsonb_build_object('portfolio_id', portfolio_id))::json "
        "WHERE payload IS NULL OR NOT (payload::jsonb ? 'portfolio_id')"
        for table in lineage_tables
        if table in table_names
    ]

    if not statements and not any(table in table_names for table in lineage_tables):
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
        for statement in index_statements:
            table_name = statement.split(" ON ", 1)[1].split(" ", 1)[0]
            if table_name in table_names:
                connection.execute(text(statement))
        for statement in payload_backfills:
            connection.execute(text(statement))


def _widen_agent_model_version_columns(engine: Engine) -> None:
    if engine.dialect.name != "postgresql":
        return

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    agent_tables = (
        "analyst_reports",
        "debate_reports",
        "trader_proposals",
        "risk_reviews",
        "final_decisions",
    )
    statements: list[str] = []
    for table in agent_tables:
        if table not in table_names:
            continue
        columns = {
            column["name"]: column
            for column in inspector.get_columns(table)
        }
        model_version = columns.get("model_version")
        if model_version is None:
            continue
        if str(model_version["type"]).lower() == "text":
            continue
        statements.append(f"ALTER TABLE {table} ALTER COLUMN model_version TYPE TEXT")

    if not statements:
        return

    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))


if __name__ == "__main__":
    run_migrations()
    print("Taurus database schema is up to date.")
