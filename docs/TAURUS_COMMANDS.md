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

## Current Make Targets

```bash
make setup
make dev-up
make dev-down
make api
make migrate
make seed-mock
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
make paper-loop-start
make paper-loop-once
make replay-decision DECISION_ID=sample
make backup-local
make restore-local BACKUP=/path/to/backup
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
curl http://localhost:8000/debates
curl http://localhost:8000/trader-proposals
curl http://localhost:8000/risk-checks
curl http://localhost:8000/final-decisions
curl http://localhost:8000/paper/orders
curl http://localhost:8000/paper/fills
curl http://localhost:8000/paper/positions
curl http://localhost:8000/runs
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
prefix_rule(pattern=["make", "dashboard"], decision="allow")
prefix_rule(pattern=["make", "import-screener"], decision="allow")
prefix_rule(pattern=["make", "import-price-csv"], decision="allow")
prefix_rule(pattern=["make", "paper-loop-start"], decision="allow")
prefix_rule(pattern=["make", "paper-loop-once"], decision="allow")
prefix_rule(pattern=["make", "replay-decision"], decision="allow")
prefix_rule(pattern=["make", "backup-local"], decision="allow")
prefix_rule(pattern=["make", "restore-local"], decision="allow")
prefix_rule(pattern=["make", "alert-test-telegram"], decision="allow")
prefix_rule(pattern=["make", "broker-sandbox-smoke"], decision="allow")
prefix_rule(pattern=["make", "live-readiness-check"], decision="allow")
prefix_rule(pattern=["make", "taurus-smoke"], decision="allow")
prefix_rule(pattern=["docker", "info"], decision="allow")
prefix_rule(pattern=["docker", "compose"], decision="allow")
prefix_rule(pattern=["open", "-a", "Docker"], decision="allow")
prefix_rule(pattern=["pkill", "-f", "uvicorn apps.api.main:app"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/health"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/ready"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/metrics"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/data/instruments"], decision="allow")
prefix_rule(pattern=["curl", "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"], decision="allow")
```

Do not broadly allow `python`, `python3`, `uv`, `rm`, unconstrained shell commands, or bare `curl`. Keep destructive commands manually approved.

Codex prefix rules match argv tokens, not URL substrings. A rule such as `prefix_rule(pattern=["curl", "http://localhost:8000"], decision="allow")` does not cover `curl http://localhost:8000/health`, because the URL with its path is a different argv token. To avoid approving every endpoint one by one, prefer adding a project `make` smoke target for grouped API checks and allow that target. Use explicit `curl` rules only for stable one-off endpoints.

## Milestone Cleanup Rule

At the end of every milestone, inspect the global Codex rules file:

```text
/Users/adnaan/.codex/rules/default.rules
```

Only entries after the user's `# END MY CUSTOM ADDITION` marker should be treated as accidental approvals from Taurus work. Move any Taurus-specific allow prefixes from that section into `.codex/rules/default.rules` if they are missing, document them in this file, and remove them from the global rules file. Do not move unrelated global approvals into this project.
