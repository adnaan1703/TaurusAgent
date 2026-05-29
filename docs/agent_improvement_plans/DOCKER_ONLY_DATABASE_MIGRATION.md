# Docker-Only Database Migration Plan

Last inspected: 2026-05-30

## Goal

Remove local SQLite from Taurus completely. Going forward, development, runtime,
tests, graph data, and provided/imported data should use Docker-backed services:

- Postgres as the canonical source of truth.
- Neo4j as a disposable graph projection rebuilt from Postgres.
- No new local SQLite files for app runtime, development workflows, or tests.

## Current Findings

Docker was initially unavailable because Docker Desktop was not running. After
starting Docker Desktop, the Compose services were inspected directly.

Docker Postgres already contains the important local SQLite data and graph data:

| Dataset | Docker Postgres Count |
|---|---:|
| `instruments` | 205 |
| `daily_candles` | 2520 |
| `graph_nodes` | 1941 |
| `graph_edges` | 20576 |
| `graph_edge_evidence` | 988 |
| `graph_edge_stats` | 0 |
| `graph_signals` | 0 |
| `graph_signal_contributions` | 0 |
| `halal_stock_compliance` | 5310 |
| `paper_runs` | 10 |
| `paper_orders` | 8 |
| `paper_fills` | 16 |
| `analyst_reports` | 44 |
| `risk_reviews` | 11 |
| `final_decisions` | 11 |

Local SQLite files found:

| File | Relevant Contents |
|---|---|
| `./taurus.db` | 10 instruments, 2520 daily candles |
| `/private/tmp/taurus-graph-alignment-20260528.db` | 1941 graph nodes, 20576 graph edges, 988 graph evidence rows |

Comparison results:

- Docker Postgres has the same `2520` mock candles as `./taurus.db`, with dates
  from `2024-01-01` through `2024-12-17`.
- Docker Postgres contains all 10 instruments from `./taurus.db`.
- Docker Postgres matches the graph SQLite counts exactly:
  `1941` nodes, `20576` edges, and `988` evidence rows.
- Docker Postgres graph edge split is `4485 active` and `16091 candidate`.
- Docker Postgres graph edge source-file counts:
  - `company_dependencies.csv`: 792
  - `company_edges.csv`: 374
  - `company_industry_classifications.csv`: 1117
  - `company_products.csv`: 413
  - `company_risks.csv`: 397
  - `company_segments.csv`: 404
  - `edge_candidates.csv`: 16091
  - `source_evidence.csv`: 988

Neo4j findings:

- Neo4j was empty when started.
- Projection was rebuilt from Docker Postgres.
- After rebuild, Neo4j contained `1941` `TaurusGraphNode` nodes and `20576`
  `TAURUS_EDGE` relationships.
- Neo4j currently has no named data volume in `docker-compose.yml`; it should be
  treated as disposable and rebuilt from Postgres after recreation.

## Revised Migration Strategy

Do not copy local SQLite rows into Docker Postgres. The inspected Docker
Postgres database already contains the useful local SQLite data and the full
TaurusData graph import.

Use this strategy instead:

1. Keep the existing Docker Postgres volume as canonical.
2. Rebuild Neo4j from Postgres whenever needed.
3. Harden Taurus so SQLite cannot be recreated.
4. After hardening and verification pass, directly delete local SQLite database
   files.

Do not run `docker compose down -v` during this work, because that would delete
the canonical Docker Postgres volume.

## Implementation Plan

### 1. Enforce Docker Postgres in Configuration

- Change `Settings.database_url` default from `sqlite:///./taurus.db` to
  `postgresql+psycopg://taurus:taurus@localhost:5432/taurus`.
- Add validation that rejects any `DATABASE_URL` whose scheme starts with
  `sqlite`.
- Keep `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` unchanged.
- Update `tests/unit/test_config.py` to assert the new Postgres default and the
  SQLite rejection behavior.

### 2. Remove SQLite Runtime Paths

- Remove SQLite-specific `connect_args` from `create_engine_from_url`.
- Keep database code focused on SQLAlchemy/Postgres behavior.
- Update `scripts/README.md`, `README.md`, `docs/TAURUS_USAGE_GUIDE.md`, and
  active command examples so they no longer suggest SQLite workflows.
- Leave historical references only if clearly marked as obsolete history.

### 3. Refactor Tests Off SQLite

- Replace temp SQLite settings in tests with Docker Postgres-backed test
  databases.
- Add a shared pytest fixture that:
  - connects to an admin database from `TAURUS_TEST_DATABASE_URL` or the default
    local Docker Postgres URL,
  - creates a unique temporary test database per test or test module,
  - runs `run_migrations`,
  - yields a `Settings` object for that database,
  - drops the database after the test.
- Ensure tests do not write `.db`, `.sqlite`, or `.sqlite3` files anywhere.
- Preserve deterministic behavior by keeping mock providers and fixtures, only
  changing persistence from SQLite to Postgres.

### 4. Backup/Restore Behavior

- Remove or deprecate SQLite backup/restore round-trip behavior.
- Keep Postgres backup/restore behavior through `pg_dump`/`pg_restore` or
  Docker Compose fallback.
- Update backup tests to cover Postgres-only behavior.

### 5. Clean Command Approvals And Docs

- Remove Taurus-specific SQLite command approvals from
  `.codex/rules/default.rules`.
- Inspect `/Users/adnaan/.codex/rules/default.rules` at cleanup time. If any
  Taurus-specific approvals appear after `# END MY CUSTOM ADDITION`, move them
  into the project-local rules file only if still needed and non-SQLite.
- Update `docs/TAURUS_COMMANDS.md` with Docker/Postgres commands and remove
  active SQLite examples.

### 6. Verify Docker Data Before Cleanup

Run these checks before deleting any local SQLite file:

```bash
docker compose ps
docker compose exec -T postgres psql -U taurus -d taurus -Atc \
  "SELECT 'instruments', count(*) FROM instruments
   UNION ALL SELECT 'daily_candles', count(*) FROM daily_candles
   UNION ALL SELECT 'graph_nodes', count(*) FROM graph_nodes
   UNION ALL SELECT 'graph_edges', count(*) FROM graph_edges
   UNION ALL SELECT 'graph_edge_evidence', count(*) FROM graph_edge_evidence
   UNION ALL SELECT 'halal_stock_compliance', count(*) FROM halal_stock_compliance;"
docker compose exec -T neo4j cypher-shell -u neo4j -p taurus-neo4j-local \
  "MATCH (n:TaurusGraphNode) RETURN count(n) AS taurus_graph_nodes;"
docker compose exec -T neo4j cypher-shell -u neo4j -p taurus-neo4j-local \
  "MATCH ()-[r:TAURUS_EDGE]->() RETURN count(r) AS taurus_edges;"
```

Expected minimum counts:

- Postgres `daily_candles`: `2520`
- Postgres `graph_nodes`: `1941`
- Postgres `graph_edges`: `20576`
- Postgres `graph_edge_evidence`: `988`
- Neo4j `TaurusGraphNode`: `1941`
- Neo4j `TAURUS_EDGE`: `20576`

### 7. Delete Local SQLite Files

After all verification passes, directly delete the known local SQLite files:

```bash
rm ./taurus.db
rm /private/tmp/taurus-graph-alignment-20260528.db
find /private/tmp -maxdepth 2 -type f -name 'taurus*.db' -print
find . -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print
```

Only delete files confirmed to be Taurus SQLite databases.

## Verification Commands

Run the full backend checks after implementation:

```bash
make test
make lint
```

Run data/projection checks:

```bash
make migrate
TAURUS_NEO4J_ENABLED=true make project-neo4j-graph
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
```

Run repo scans:

```bash
rg -n "sqlite|sqlite3|taurus\\.db|DATABASE_URL=sqlite" .
find . -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print
find /private/tmp -maxdepth 2 -type f -name 'taurus*.db' -print
```

Acceptable remaining `sqlite` references after the cleanup should be limited to
clearly obsolete historical notes, if any are intentionally retained.

## Assumptions

- "Provided data" means the currently supported source/import paths: mock seed
  data, tracked market-data CSV fixtures, HalalStock sync output already present
  in Docker Postgres, and TaurusData graph CSV imports.
- TaurusData files that do not yet have importers, such as company profiles,
  annual report index, financial results, and quote snapshots, remain tracked
  source artifacts until a separate schema/import milestone is created.
- SQLite files should be deleted directly after verification, not archived.
- Neo4j remains disposable unless a future milestone adds a named Neo4j volume.
