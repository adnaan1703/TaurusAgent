# Taurus Command Reference

This file lists commands used during M0 and commands expected across later Taurus milestones.

## M0 Commands Used

```bash
make setup
make test
make lint
make dev-up
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
make dev-down
make api
pkill -f "uvicorn apps.api.main:app"
docker info
docker compose ps
docker compose logs --no-color api
open -a Docker
```

## M1 Commands Used

```bash
make setup
make dev-up
make migrate
make seed-mock
make lint
make test
curl http://localhost:8000/ready
curl http://localhost:8000/data/instruments
curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"
```

## M2 Commands Used

```bash
make dev-up
make backtest-mock
make lint
make test
```

## M3 Commands Used

```bash
make test
make lint
make dev-up
make backtest-mock STRATEGY=configs/strategies/moving_average_crossover_v1.yaml
make backtest-mock STRATEGY=configs/strategies/blended_score_v1.yaml
make dev-down
```

## M4 Commands Used

```bash
make test
make lint
DATABASE_URL=sqlite:////private/tmp/taurus-m4.db make import-mock-news
DATABASE_URL=sqlite:////private/tmp/taurus-m4.db make run-analysts-mock SYMBOL=INFY
DATABASE_URL=sqlite:////private/tmp/taurus-m4.db make api
curl http://localhost:8000/events
curl "http://localhost:8000/agent-reports?symbol=INFY"
```

## M6 Commands Used

```bash
make test
make lint
DATABASE_URL=sqlite:////private/tmp/taurus-m6.db make risk-review-mock SYMBOL=INFY
DATABASE_URL=sqlite:////private/tmp/taurus-m6.db make final-approval-mock SYMBOL=INFY
```

## M7 Commands Used

```bash
make test
make lint
DATABASE_URL=sqlite:////private/tmp/taurus-m7-deterministic-20260519.db make paper-once-mock SYMBOL=INFY
DATABASE_URL=sqlite:////private/tmp/taurus-m7-verify-20260519.db make api
curl http://127.0.0.1:8000/paper/orders
curl http://127.0.0.1:8000/paper/fills
curl http://127.0.0.1:8000/paper/positions
curl http://127.0.0.1:8000/paper/account
pkill -f "uvicorn apps.api.main:app"
```

## M8 Commands Used

```bash
make test
make lint
make dev-up
make backtest-mock
make paper-once-mock SYMBOL=INFY
make dashboard
curl http://127.0.0.1:8000/metrics
curl http://127.0.0.1:8501/_stcore/health
curl http://127.0.0.1:3000/api/health
docker compose ps
uv run python -m json.tool infra/grafana/dashboards/taurus-system.json
uv run python -m json.tool infra/grafana/dashboards/taurus-trading.json
pkill -f "streamlit run apps/dashboard/main.py"
```

## M10 Commands Used

```bash
make test
make lint
DATABASE_URL=sqlite:////private/tmp/taurus-m10-verify-20260519.db make import-price-csv
DATABASE_URL=sqlite:////private/tmp/taurus-m10-verify-20260519.db make backtest-real-data
DATABASE_URL=sqlite:////private/tmp/taurus-m10-mock-verify-20260519.db make backtest-mock
DATABASE_URL=sqlite:////private/tmp/taurus-m10-verify-20260519.db make api
curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"
pkill -f "uvicorn apps.api.main:app"
```

## M11 Commands Used

```bash
make test
make lint
DATABASE_URL=sqlite:////private/tmp/taurus-m11-verify-20260520.db make paper-loop-mock
DATABASE_URL=sqlite:////private/tmp/taurus-m11-verify-20260520.db make api
curl http://localhost:8000/runs
curl http://localhost:8000/runs/pr-edecbedf6614c240
DATABASE_URL=sqlite:////private/tmp/taurus-m11-verify-20260520.db make dashboard
curl http://127.0.0.1:8501/_stcore/health
```

## M12 Commands Used

```bash
make test
make lint
DATABASE_URL=sqlite:////private/tmp/taurus-m12-verify-20260520.db make alert-smoke
DATABASE_URL=sqlite:////private/tmp/taurus-m12-verify-20260520.db make replay-decision DECISION_ID=sample
DATABASE_URL=sqlite:////private/tmp/taurus-m12-verify-20260520.db BACKUP_DIR=/private/tmp/taurus-m12-backups make backup-local
DATABASE_URL=sqlite:////private/tmp/taurus-m12-verify-20260520.db BACKUP_DIR=/private/tmp/taurus-m12-backups make backup-db
DATABASE_URL=sqlite:////private/tmp/taurus-m12-verify-20260520.db BACKUP=/private/tmp/taurus-m12-backups/taurus-20260520T105647138364Z make restore-local
```

## Current Make Targets

```bash
make setup
make dev-up
make dev-down
make api
make migrate
make seed-mock
make backtest-mock
make backtest-real-data
make import-mock-news
make import-screener CSV=/path/to/screener.csv
make import-price-csv CSV=mock/market_data/prices_sample.csv
make run-analysts-mock SYMBOL=INFY
make debate-mock SYMBOL=INFY
make trader-proposal-mock SYMBOL=INFY
make risk-review-mock SYMBOL=INFY
make final-approval-mock SYMBOL=INFY
make paper-once-mock SYMBOL=INFY
make paper-loop-mock
make paper-loop-once
make paper-loop-start
make alert-smoke
make alert-test-telegram
make replay-decision DECISION_ID=sample
make backup-local
make backup-db
make restore-local BACKUP=/path/to/backup
make llm-smoke
make test
make lint
```

## Expected Project Commands By Milestone

```bash
make migrate
make seed-mock
make backtest-mock
make import-mock-news
make run-analysts-mock SYMBOL=INFY
make llm-smoke
make debate-mock SYMBOL=INFY
make trader-proposal-mock SYMBOL=INFY
make risk-review-mock SYMBOL=INFY
make final-approval-mock SYMBOL=INFY
make paper-once-mock SYMBOL=INFY
make dashboard
make import-screener CSV=/path/to/screener.csv
make import-price-csv CSV=/path/to/prices.csv
make import-price-csv DIR=/path/to/price_csvs
make backtest-real-data
make paper-loop-mock
make paper-loop-start
make paper-loop-once
make replay-decision DECISION_ID=sample
make backup-local
make backup-db
make restore-local BACKUP=/path/to/backup
make alert-smoke
make alert-test-telegram
make broker-sandbox-smoke
make live-readiness-check
make taurus-smoke
```

## API Smoke Checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
curl http://localhost:8000/data/instruments
curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"
curl http://localhost:8000/backtests
curl http://localhost:8000/events
curl "http://localhost:8000/agent-reports?symbol=INFY"
curl "http://localhost:8000/fundamentals?symbol=INFY"
curl http://localhost:8000/fundamentals/imports
curl http://localhost:8000/debates
curl http://localhost:8000/trader-proposals
curl http://localhost:8000/risk-checks
curl http://localhost:8000/final-decisions
curl http://localhost:8000/paper/orders
curl http://localhost:8000/paper/fills
curl http://localhost:8000/paper/positions
curl http://localhost:8000/paper/account
curl http://localhost:8000/runs
curl http://localhost:8000/runs/{run_id}
curl -X POST http://localhost:8000/alerts/test
curl http://localhost:8000/replay/{decision_id}
curl http://localhost:8000/live-readiness
```

## Codex Project-Local Prefix Allowlist

Taurus command approvals are stored in the project-local file:

```text
.codex/rules/default.rules
```

Codex loads project-local rules only when the project is trusted. This repo is trusted in the local user config:

```toml
[projects."/Users/adnaan/Workbench/TaurusAgent"]
trust_level = "trusted"
```

The rules file uses this format:

```text
prefix_rule(pattern=["make", "test"], decision="allow")
```

Current Taurus allowlist prefixes:

```text
prefix_rule(pattern=["make", "setup"], decision="allow")
prefix_rule(pattern=["make", "test"], decision="allow")
prefix_rule(pattern=["make", "lint"], decision="allow")
prefix_rule(pattern=["make", "dev-up"], decision="allow")
prefix_rule(pattern=["make", "dev-down"], decision="allow")
prefix_rule(pattern=["make", "api"], decision="allow")
prefix_rule(pattern=["uv", "run"], decision="allow")
prefix_rule(pattern=["graphify", "update", "."], decision="allow")
prefix_rule(pattern=["make", "migrate"], decision="allow")
prefix_rule(pattern=["make", "seed-mock"], decision="allow")
prefix_rule(pattern=["make", "backtest-mock"], decision="allow")
prefix_rule(pattern=["make", "import-mock-news"], decision="allow")
prefix_rule(pattern=["make", "run-analysts-mock"], decision="allow")
prefix_rule(pattern=["make", "llm-smoke"], decision="allow")
prefix_rule(pattern=["make", "debate-mock"], decision="allow")
prefix_rule(pattern=["make", "trader-proposal-mock"], decision="allow")
prefix_rule(pattern=["make", "risk-review-mock"], decision="allow")
prefix_rule(pattern=["make", "final-approval-mock"], decision="allow")
prefix_rule(pattern=["make", "paper-once-mock"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m7-verify-20260519.db make paper-once-mock SYMBOL=INFY"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m7-verify-20260519.db make api"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m7-deterministic-20260519.db TAURUS_LLM_PROVIDER=mock SYMBOL=INFY PYTHONPATH=packages:. uv run python scripts/run_paper_once.py"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m7-deterministic-20260519.db make paper-once-mock SYMBOL=INFY"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m9-verify-20260519.db make import-screener CSV=tests/fixtures/screener_sample.csv"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m9-verify-20260519.db make run-analysts-mock SYMBOL=INFY"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m9-verify-20260519.db make api"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m10-verify-20260519.db make import-price-csv"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m10-verify-20260519.db make backtest-real-data"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m10-mock-verify-20260519.db make backtest-mock"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m10-verify-20260519.db make api"], decision="allow")
prefix_rule(pattern=["make", "dashboard"], decision="allow")
prefix_rule(pattern=["make", "import-screener"], decision="allow")
prefix_rule(pattern=["make", "import-price-csv"], decision="allow")
prefix_rule(pattern=["make", "paper-loop-start"], decision="allow")
prefix_rule(pattern=["make", "paper-loop-once"], decision="allow")
prefix_rule(pattern=["make", "paper-loop-mock"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m11-verify-20260520.db make paper-loop-mock"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m11-verify-20260520.db make api"], decision="allow")
prefix_rule(pattern=["/bin/zsh", "-lc", "DATABASE_URL=sqlite:////private/tmp/taurus-m11-verify-20260520.db make dashboard"], decision="allow")
prefix_rule(pattern=["make", "alert-smoke"], decision="allow")
prefix_rule(pattern=["make", "replay-decision"], decision="allow")
prefix_rule(pattern=["make", "backup-local"], decision="allow")
prefix_rule(pattern=["make", "backup-db"], decision="allow")
prefix_rule(pattern=["make", "restore-local"], decision="allow")
prefix_rule(pattern=["make", "alert-test-telegram"], decision="allow")
prefix_rule(pattern=["make", "broker-sandbox-smoke"], decision="allow")
prefix_rule(pattern=["make", "live-readiness-check"], decision="allow")
prefix_rule(pattern=["make", "taurus-smoke"], decision="allow")
prefix_rule(pattern=["docker", "info"], decision="allow")
prefix_rule(pattern=["docker", "compose"], decision="allow")
prefix_rule(pattern=["open", "-a", "Docker"], decision="allow")
prefix_rule(pattern=["pkill", "-f", "uvicorn apps.api.main:app"], decision="allow")
prefix_rule(pattern=["pkill", "-f", "streamlit run apps/dashboard/main.py"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/health"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/ready"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/metrics"], decision="allow")
prefix_rule(pattern=["curl", "http://127.0.0.1:8000/metrics"], decision="allow")
prefix_rule(pattern=["curl", "http://127.0.0.1:8501/_stcore/health"], decision="allow")
prefix_rule(pattern=["curl", "http://127.0.0.1:3000/api/health"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/data/instruments"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/events"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/agent-reports?symbol=INFY"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/fundamentals?symbol=INFY"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/fundamentals/imports"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/debates"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/trader-proposals"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/paper/orders"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/paper/fills"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/paper/positions"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/paper/account"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/runs"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/runs/pr-edecbedf6614c240"], decision="allow")
prefix_rule(pattern=["curl", "http://127.0.0.1:8000/paper/orders"], decision="allow")
prefix_rule(pattern=["curl", "http://127.0.0.1:8000/paper/fills"], decision="allow")
prefix_rule(pattern=["curl", "http://127.0.0.1:8000/paper/positions"], decision="allow")
prefix_rule(pattern=["curl", "http://127.0.0.1:8000/paper/account"], decision="allow")
```

Do not broadly allow `python`, `python3`, `uv`, `rm`, unconstrained shell commands, or bare `curl`. Keep destructive commands manually approved.

Codex prefix rules match argv tokens, not URL substrings. A rule such as `prefix_rule(pattern=["curl", "http://localhost:8000"], decision="allow")` does not cover `curl http://localhost:8000/health`, because the URL with its path is a different argv token. To avoid approving every endpoint one by one, prefer adding a project `make` smoke target for grouped API checks and allow that target. Use explicit `curl` rules only for stable one-off endpoints.

## Milestone Cleanup Rule

At the end of every milestone, inspect the global Codex rules file:

```text
/Users/adnaan/.codex/rules/default.rules
```

Only entries after the user's `# END MY CUSTOM ADDITION` marker should be treated as accidental approvals from Taurus work. Move any Taurus-specific allow prefixes from that section into `.codex/rules/default.rules` if they are missing, document them in this file, and remove them from the global rules file. Do not move unrelated global approvals into this project.
