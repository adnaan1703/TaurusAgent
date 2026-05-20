# Taurus Operations Runbook

## M13 Release Flow

Run the complete paper MVP smoke check:

```bash
make taurus-smoke
```

Run the full local release sequence when validating a fresh environment:

```bash
make setup
make dev-up
make migrate
make seed-mock
make import-mock-news
make backtest-mock
make run-analysts-mock SYMBOL=INFY
make debate-mock SYMBOL=INFY
make trader-proposal-mock SYMBOL=INFY
make risk-review-mock SYMBOL=INFY
make final-approval-mock SYMBOL=INFY
make paper-once-mock SYMBOL=INFY
make paper-loop-mock
make replay-decision DECISION_ID=sample
make backup-local
make dashboard
make test
```

The M13 release assumptions, optional inputs, and known limitations are in `docs/TAURUS_MVP_RELEASE.md`.

## Safety Defaults

Taurus remains paper-only in M13:

- `LIVE_TRADING_ENABLED=false`
- `BROKER_PROVIDER=paper`
- `TAURUS_MODE=paper`

Do not commit real API keys, broker credentials, Telegram tokens, or exported user data.

Broker sandbox and production broker work are deferred to `docs/UPSTOX_INTEGRATION_PLAN.md`.

## Alerts

Default local alerting uses the mock adapter:

```bash
make alert-smoke
```

For a real Telegram smoke test, add these values locally in `.env` and keep them uncommitted:

```text
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

Then run:

```bash
make alert-test-telegram
```

Operational alerts are emitted for paper fills, paper order rejections, kill-switch blocks, severe-event blocks, stale-data blocks, risk rejections/blocks, and scheduled paper-run failures.

The API exposes a safe mock-only test endpoint:

```bash
curl -X POST http://localhost:8000/alerts/test
```

## Decision Replay

Replay reconstructs the stored decision path. It does not rerun agents or mutate trading state.

```bash
make replay-decision DECISION_ID=<decision_id>
```

For smoke checks, `DECISION_ID=sample` replays the latest stored final decision, or creates a deterministic mock paper decision if none exists:

```bash
make replay-decision DECISION_ID=sample
```

The API endpoint is:

```bash
curl http://localhost:8000/replay/<decision_id>
```

Replay includes analyst reports, company events, debate report, trader proposal, risk review, final decision, paper order/fills, and relevant audit rows when available.

## Backup

Create a local backup:

```bash
make backup-local
```

`make backup-db` is an alias for `make backup-local`.

For SQLite, the database file is copied into `backups/taurus-<timestamp>/taurus.sqlite3` with a `manifest.json`.

For Postgres, the command uses local `pg_dump --format=custom` when available. If `pg_dump` is not installed, Taurus falls back to `docker compose exec -T postgres pg_dump` for the local Docker Compose stack. Ensure the configured `DATABASE_URL` is reachable.

## Restore

Restore from a backup directory:

```bash
make restore-local BACKUP=backups/taurus-<timestamp>
```

For SQLite, Taurus copies the current database to a `*.pre-restore-<timestamp>` file before replacing it.

For Postgres, restore is destructive and requires explicit confirmation:

```bash
RESTORE_CONFIRM=I_UNDERSTAND make restore-local BACKUP=backups/taurus-<timestamp>
```

Postgres restore uses local `pg_restore --clean --if-exists` when available, or the local Docker Compose `postgres` service fallback. Confirm the target `DATABASE_URL` before running it.
