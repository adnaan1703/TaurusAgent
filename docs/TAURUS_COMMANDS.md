# Taurus Command Reference

This file lists commands used during M0 and commands expected across later Taurus milestones.
M21 made Docker Postgres the canonical database; command examples should use
the default Postgres URL or an explicit Postgres `DATABASE_URL`, not SQLite.
M23 retired runtime mock/CSV market-data entry points. Historical sections may
still show the commands that were used at the time, but current workflows should
use Kite commands and `make import-market-data`.

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
make import-mock-news
make run-analysts-mock SYMBOL=INFY
make api
curl http://localhost:8000/events
curl "http://localhost:8000/agent-reports?symbol=INFY"
```

## M6 Commands Used

```bash
make test
make lint
make risk-review-mock SYMBOL=INFY
make final-approval-mock SYMBOL=INFY
```

## M7 Commands Used

```bash
make test
make lint
make paper-once-mock SYMBOL=INFY
make api
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
make import-price-csv
make backtest-real-data
make backtest-mock
make api
curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"
pkill -f "uvicorn apps.api.main:app"
```

## M11 Commands Used

```bash
make test
make lint
make paper-loop-mock
make api
curl http://localhost:8000/runs
curl http://localhost:8000/runs/pr-edecbedf6614c240
make dashboard
curl http://127.0.0.1:8501/_stcore/health
```

## M12 Commands Used

```bash
make test
make lint
make alert-smoke
make replay-decision DECISION_ID=sample
BACKUP_DIR=/private/tmp/taurus-m12-backups make backup-local
BACKUP_DIR=/private/tmp/taurus-m12-backups make backup-db
BACKUP=/private/tmp/taurus-m12-backups/taurus-20260520T105647138364Z make restore-local
```

## M13 Commands Used

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
make taurus-smoke
make dashboard
make test
make lint
```

## M16.1 Commands Used

```bash
git status --short
find docs/stitch/paper-trade-event-monitor -maxdepth 1 -type f | sort
find docs/stitch/paper-trade-event-monitor/assets -maxdepth 1 -type f | sort
curl -L '<stitch-screenshot-url>' -o docs/stitch/paper-trade-event-monitor/assets/<screen>.png
curl -L '<stitch-html-url>' -o docs/stitch/paper-trade-event-monitor/assets/<screen>.html
```

## M16.2 Commands Used

```bash
make test
make lint
make paper-loop-mock
make api
curl -sS -o /private/tmp/taurus-m16-ui-overview.json -w '%{http_code}' http://127.0.0.1:8000/ui/overview
curl -sS -o /private/tmp/taurus-m16-ui-history.json -w '%{http_code}' http://127.0.0.1:8000/ui/history
curl -sS -o /private/tmp/taurus-m16-ui-run.json -w '%{http_code}' http://127.0.0.1:8000/ui/runs/pr-75fdbb0381152d57
curl -sS -o /private/tmp/taurus-m16-ui-trail.json -w '%{http_code}' http://127.0.0.1:8000/ui/runs/pr-75fdbb0381152d57/symbols/INFY/decision-trail
curl -sS -o /private/tmp/taurus-m16-ui-replay.json -w '%{http_code}' http://127.0.0.1:8000/ui/replay/dec-1d59184394a64b42
curl -sS -o /private/tmp/taurus-m16-ui-risk.json -w '%{http_code}' http://127.0.0.1:8000/ui/risk
curl -sS -o /private/tmp/taurus-m16-ui-portfolio.json -w '%{http_code}' http://127.0.0.1:8000/ui/portfolio
pkill -f "uvicorn apps.api.main:app"
```

## M16.3 Commands Used

```bash
make setup-ui
make test-ui
make build-ui
make ui
curl -sS -o /private/tmp/taurus-m16-ui-vite.html -w '%{http_code}' http://127.0.0.1:5173/
make test
make lint
```

## M16.4 Commands Used

```bash
make test-ui
make build-ui
make test
make lint
make paper-loop-mock
make api
make ui
curl -sS -o /private/tmp/taurus-m16-ui-overview-smoke.json -w '%{http_code}' http://127.0.0.1:8000/ui/overview
curl -sS -o /private/tmp/taurus-m16-ui-run-smoke.json -w '%{http_code}' http://127.0.0.1:8000/ui/runs/pr-03c57d458f851eaf
curl -sS -o /private/tmp/taurus-m16-ui-trail-smoke.json -w '%{http_code}' http://127.0.0.1:8000/ui/runs/pr-03c57d458f851eaf/symbols/INFY/decision-trail
curl -sS -o /private/tmp/taurus-m16-ui-vite-smoke.html -w '%{http_code}' http://127.0.0.1:5173/
lsof -iTCP:8000 -sTCP:LISTEN -n -P
lsof -iTCP:5173 -sTCP:LISTEN -n -P
```

## M16.5 Commands Used

```bash
make test
make lint
make test-ui
make build-ui
make taurus-smoke
make dev-up
docker compose ps
docker compose up -d postgres redis
make taurus-smoke
BACKUP_DIR=/private/tmp/taurus-m16-final-backups make taurus-smoke
make api
make ui
curl -sS -o /private/tmp/taurus-m16-final-ui-overview.json -w '%{http_code}' http://127.0.0.1:8000/ui/overview
curl -sS -o /private/tmp/taurus-m16-final-ui-run.json -w '%{http_code}' http://127.0.0.1:8000/ui/runs/pr-16216828cc03acfe
curl -sS -o /private/tmp/taurus-m16-final-ui-trail.json -w '%{http_code}' http://127.0.0.1:8000/ui/runs/pr-16216828cc03acfe/symbols/INFY/decision-trail
curl -sS -o /private/tmp/taurus-m16-final-vite.html -w '%{http_code}' http://127.0.0.1:5173/
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1000 --virtual-time-budget=5000 --screenshot=/private/tmp/taurus-m16-overview-desktop.png http://127.0.0.1:5173/
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=390,844 --virtual-time-budget=5000 --screenshot=/private/tmp/taurus-m16-overview-mobile.png http://127.0.0.1:5173/
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1000 --virtual-time-budget=5000 --screenshot=/private/tmp/taurus-m16-trail-desktop.png http://127.0.0.1:5173/runs/pr-16216828cc03acfe/symbols/INFY
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=390,844 --virtual-time-budget=5000 --screenshot=/private/tmp/taurus-m16-trail-mobile.png http://127.0.0.1:5173/runs/pr-16216828cc03acfe/symbols/INFY
lsof -iTCP:8000 -sTCP:LISTEN -n -P
lsof -iTCP:5173 -sTCP:LISTEN -n -P
make dev-down
```

## M16.5 Retest Commands Used

```bash
make test
make lint
make test-ui
make build-ui
docker compose up -d postgres redis
make taurus-smoke
make api
make ui
curl -sS -o /private/tmp/taurus-retry-ui-overview-final.json -w '%{http_code}' http://127.0.0.1:8000/ui/overview
curl -sS -o /private/tmp/taurus-retry-ui-run-final.json -w '%{http_code}' http://127.0.0.1:8000/ui/runs/pr-e65310164943cf50
curl -sS -o /private/tmp/taurus-retry-ui-trail-final.json -w '%{http_code}' http://127.0.0.1:8000/ui/runs/pr-e65310164943cf50/symbols/INFY/decision-trail
curl -sS -o /private/tmp/taurus-retry-vite-final.html -w '%{http_code}' http://127.0.0.1:5173/
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1000 --virtual-time-budget=5000 --screenshot=/private/tmp/taurus-retry-overview-desktop.png http://127.0.0.1:5173/
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=390,844 --virtual-time-budget=5000 --screenshot=/private/tmp/taurus-retry-overview-mobile.png http://127.0.0.1:5173/
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1000 --virtual-time-budget=5000 --screenshot=/private/tmp/taurus-retry-trail-desktop.png http://127.0.0.1:5173/runs/pr-e65310164943cf50/symbols/INFY
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=390,844 --virtual-time-budget=5000 --screenshot=/private/tmp/taurus-retry-trail-mobile.png http://127.0.0.1:5173/runs/pr-e65310164943cf50/symbols/INFY
pkill -f "uvicorn apps.api.main:app"
make dev-down
```

## M17 Commands Used

```bash
uv add 'kiteconnect>=5,<6' 'PyYAML>=6,<7'
make kite-login-url
uv run pytest tests/unit/test_kite_auth.py
uv run pytest tests/unit/test_kite_market_data.py tests/unit/test_config.py
uv run pytest tests/unit/test_kite_market_data.py
make test
make lint
make kite-sync-instruments
make import-kite-candles
make import-market-data
make kite-ltp-smoke
make paper-loop-kite
date '+%Y-%m-%d %H:%M %Z'
```

## M23 Commands Used

```bash
uv run pytest tests/unit/test_kite_market_data.py tests/unit/test_config.py
uv run pytest
make test-ui
make lint
git diff --check
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
```

Manual real-credential Kite commands, after a fresh local `KITE_ACCESS_TOKEN` is added to ignored `.env`:

```bash
make api
make kite-login-url
# Browser redirects to http://127.0.0.1:8000/ and Taurus stores KITE_ACCESS_TOKEN.
# Fallback if the API was not running:
# make kite-exchange-token REQUEST_TOKEN=<request_token_from_redirect_url>
make kite-sync-instruments
make import-kite-candles
make kite-ltp-smoke
make import-taurus-graph
make compute-graph-stats
make paper-loop-kite
curl "http://localhost:8000/data/quotes/latest?symbol=INFY"
```

## M24 Commands Used

```bash
uv run pytest tests/unit/test_graph_analyst.py tests/unit/test_graph_risk.py tests/unit/test_graph_stats.py tests/unit/test_graph_backtesting.py tests/unit/test_paper_runs.py
make test
make lint
make test-ui
make build-ui
rg -n "mock|Mock" packages/taurus_core/agents/graph_analyst.py packages/taurus_core/risk/graph_concentration.py packages/taurus_core/strategies/graph_aware.py packages/taurus_core/graph
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
```

`make paper-loop-kite` is now the canonical graph-enabled real-data paper
profile. It sets:

```bash
TAURUS_ENABLED_ANALYSTS=technical,graph
TAURUS_GRAPH_ENABLED=true
TAURUS_GRAPH_RISK_ENABLED=true
STRATEGY=configs/strategies/graph_aware_score_v1.yaml
```

Before running it on a fresh database, import Kite candles, import reviewed
graph rows, and compute stats:

```bash
make import-market-data
make import-taurus-graph
make compute-graph-stats
make paper-loop-kite
```

The graph readiness preflight fails before paper execution if company nodes,
active edges, latest edge stats, usable active-edge graph signals, or graph risk
limits are missing.

## M29 Commands Used

```bash
uv run pytest tests/unit/test_risk_approval.py tests/unit/test_llm_provider.py tests/unit/test_paper_broker.py
uv run pytest tests/unit/test_paper_runs.py tests/unit/test_ui_aggregate_api.py tests/unit/test_dashboard_observability.py
make test
make lint
rg -n "MockLLMProvider|mock LLM|mock_llm|LLM mock" packages apps scripts
git diff --check
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,260p' .codex/rules/default.rules
```

`PortfolioManagerAgent` now accepts an optional real LLM provider and can enrich
`FinalDecision.reason` after deterministic final approval fields are fixed. The
LLM explanation path is allowed to update only the stored reason and bounded
model metadata; status, final action, approved quantity, exposure, order flags,
broker routing, IDs, and persistence behavior remain rule-owned.

Production paper-run and final-approval script paths build the configured real
provider with `build_llm_provider(settings)` when explanation is enabled. Tests
use test-only fake providers; runtime mock LLM providers remain unsupported.

## M30 Commands Used

```bash
make position-monitor POSITION_MONITOR_ENABLED=true POSITION_MONITOR_ITERATIONS=1
uv run pytest tests/unit/test_position_monitor.py -q
make test-ui
make test
make lint
rg -n "MockLLMProvider|mock LLM|mock_llm|LLM mock" packages apps scripts
rg -n "MockMarketDataProvider|mock market|mock_market|CSVMarketDataProvider|market-data mock|quote mock" packages apps scripts
git diff --check
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,260p' .codex/rules/default.rules
```

`make position-monitor` respects the disabled default
`POSITION_MONITOR_ENABLED=false`, keeps provider `kite`, and runs
`scripts/run_position_monitor.py`. To opt in later, pass
`POSITION_MONITOR_ENABLED=true`; use `POSITION_MONITOR_ITERATIONS=1` for one
local/dev pass, or set it to `0` for continuous polling until stopped. The
monitor is paper-only and creates `market_hours` stop-loss/take-profit lifecycle
proposals from persisted Kite quote snapshots before routing through
TraderAgent, RiskReview, PortfolioManagerAgent, and PaperBroker.

## M31 Commands Used

```bash
env TAURUS_GRAPH_ENABLED=false TAURUS_GRAPH_RISK_ENABLED=false TAURUS_GRAPH_AUTO_PROMOTE_EDGES=false TAURUS_NEO4J_ENABLED=false TAURUS_LLM_BASE_URL= TAURUS_LLM_MODEL= TAURUS_LLM_TIMEOUT_SECONDS=20 TAURUS_ENABLED_ANALYSTS=technical uv run pytest tests/unit/test_config.py tests/unit/test_ui_aggregate_api.py -q
make lint
git diff --check
env TAURUS_GRAPH_ENABLED=false TAURUS_GRAPH_RISK_ENABLED=false TAURUS_GRAPH_AUTO_PROMOTE_EDGES=false TAURUS_NEO4J_ENABLED=false TAURUS_LLM_BASE_URL= TAURUS_LLM_MODEL= TAURUS_LLM_TIMEOUT_SECONDS=20 TAURUS_ENABLED_ANALYSTS=technical make test
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,260p' .codex/rules/default.rules
```

Money-management defaults remain disabled:
`TAURUS_MONEY_MANAGEMENT_ENABLED=false` and
`TAURUS_MONEY_MANAGEMENT_CONFIG_PATH=configs/portfolio/money_management_v1.yaml`.
When enabled, `/ui/risk` and `/ui/portfolio` include read-only
`money_management` metadata loaded from that policy file. M31 does not change
paper order sizing.

## M32 Commands Used

```bash
uv run pytest tests/unit/test_core_shariah_basket.py tests/unit/test_paper_runs.py::test_money_management_paper_run_creates_shariah_equity_core_decisions -q
cd apps/web && pnpm test -- --run RunDetailPage
make test-ui
make lint
make test
git diff --check
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,260p' .codex/rules/default.rules
```

To include M32 core basket artifacts in a local paper run, keep execution paper
only and enable the existing policy flag:

```bash
TAURUS_MONEY_MANAGEMENT_ENABLED=true make paper-loop-kite
```

The core Shariah basket writes decisions to the paper-run
`money_management.core_shariah_basket` artifact. It does not route core basket
orders; runtime market data remains Kite-backed and broker routing remains
PaperBroker-only.

## M33 Commands Used

```bash
uv run pytest tests/unit/test_active_allocation.py tests/unit/test_paper_runs.py::test_graph_enabled_money_management_run_adds_active_allocation_metadata tests/unit/test_paper_runs.py::test_money_management_paper_run_creates_shariah_equity_core_decisions tests/unit/test_paper_runs.py::test_graph_enabled_kite_paper_run_uses_graph_roster_strategy_and_risk tests/unit/test_risk_approval.py::test_portfolio_manager_stores_final_paper_decision_and_api_returns_m6_artifacts -q
uv run pytest tests/unit/test_ui_aggregate_api.py::test_disabled_money_management_does_not_change_paper_run_artifacts tests/unit/test_active_allocation.py tests/unit/test_paper_runs.py::test_graph_enabled_money_management_run_adds_active_allocation_metadata -q
make lint
make test
git diff --check
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,260p' .codex/rules/default.rules
```

M33 active allocation runs only when
`TAURUS_MONEY_MANAGEMENT_ENABLED=true`. It resizes or rejects active-sleeve
paper BUY/increase proposals before risk review, then stores the allocation
rationale in proposal, risk review, final decision, and run-symbol payloads.
It does not add live broker routing and leaves REDUCE/EXIT lifecycle actions
unblocked by new-risk sizing.

The full `make test` pass was blocked in the local environment by existing
configuration/LLM expectation failures unrelated to M33: `.env`/environment
values set graph enabled and override default LLM model/base URLs, LM Studio
tests expect `response_format={"type":"json_object"}` while the current
provider emits JSON schema format, and the smoke test fails graph readiness
when graph is enabled without imported graph nodes.

## M28 Commands Used

```bash
uv run pytest tests/unit/test_trader_agent.py tests/unit/test_risk_approval.py tests/unit/test_paper_broker.py tests/unit/test_paper_runs.py tests/unit/test_ui_aggregate_api.py tests/unit/test_dashboard_observability.py tests/unit/test_llm_provider.py
uv run pytest tests/unit/test_graph_risk.py
make test-ui
make build-ui
make test
make lint
rg -n "MockLLMProvider|mock LLM|mock_llm|LLM mock" packages apps scripts
rg -n "MockMarketDataProvider|mock market data|mock_market_data|CSVMarketDataProvider|csv market" packages apps scripts
git diff --check
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,260p' .codex/rules/default.rules
```

`TAURUS_PAPER_PORTFOLIO_ID=local-paper` is now the default paper portfolio
boundary. Paper orders, fills, positions, and account snapshots retain `run_id`
for audit, but PaperBroker reconstructs portfolio state from all prior fills for
the configured portfolio. `TraderAgent` calls the configured real LLM provider
for advisory after-close lifecycle reasoning, then deterministic guardrails
validate BUY/HOLD/NO_TRADE/REDUCE/EXIT action, target exposure, stop/take-profit
defaults, and summaries before persistence.

## M18 Commands Used

```bash
uv add 'beautifulsoup4>=4,<5'
uv run pytest tests/unit/test_halal_stock_compliance.py
make test
make lint
make sync-halal-stocks
uv run python - <<'PY'
from taurus_core.data.universe import load_market_data_universe
u = load_market_data_universe('configs/market_data/halal_nse_cash.yaml')
print(u.universe_name, len(u.symbols), u.enabled_symbols()[:5], u.enabled_symbols()[-5:])
PY
PYTHONPATH=packages:. uv run python - <<'PY'
from sqlalchemy import func, select
from taurus_core.config import Settings
from taurus_core.db.models import HalalStockComplianceModel, HalalStockImportModel
from taurus_core.db.session import build_session_factory
s = Settings()
f = build_session_factory(s)
with f() as session:
    print('imports', session.scalar(select(func.count()).select_from(HalalStockImportModel)))
    print('active', session.scalar(select(func.count()).select_from(HalalStockComplianceModel).where(HalalStockComplianceModel.active.is_(True))))
    print('halal active', session.scalar(select(func.count()).select_from(HalalStockComplianceModel).where(HalalStockComplianceModel.active.is_(True), HalalStockComplianceModel.compliance_status == 'halal')))
PY
date '+%Y-%m-%d %H:%M %Z'
```

## M20.0 Commands Used

```bash
git status --short
sed -n '1,260p' docs/TAURUS_DATA_INTEGRATION.md
sed -n '1,220p' docs/TAURUS_MILESTONE_TODO.md
find packages/taurus_core -maxdepth 3 -type f | sort
find apps -maxdepth 4 -type f | sort
find scripts tests/unit configs infra -maxdepth 3 -type f | sort
sed -n '1,280p' packages/taurus_core/config.py
sed -n '1,220p' apps/api/main.py
sed -n '1,180p' scripts/migrate.py
sed -n '1,220p' apps/web/src/app/routes.tsx
sed -n '1,220p' apps/web/src/api/client.ts
sed -n '1,260p' /Users/adnaan/.codex/rules/default.rules
make test
make lint
```

## M20.1 Commands Used

```bash
git status --short
sed -n '1,240p' docs/TAURUS_MILESTONE_TODO.md
sed -n '1,260p' docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
rg --files
sed -n '1,260p' packages/taurus_core/config.py
sed -n '1,1320p' packages/taurus_core/db/models.py
sed -n '1,1800p' packages/taurus_core/db/repositories.py
sed -n '1,220p' scripts/migrate.py
sed -n '1,220p' tests/unit/test_config.py
uv run pytest tests/unit/test_config.py tests/unit/test_graph_repository.py
make test
make lint
sed -n '1,260p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,260p' .codex/rules/default.rules
```

## M20.2 Commands Used

```bash
git status --short
sed -n '1,260p' docs/TAURUS_MILESTONE_TODO.md
sed -n '1,300p' docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
rg --files
sed -n '1334,1845p' packages/taurus_core/db/repositories.py
head -n 1 configs/taurus_data/company_edges.csv
head -n 1 configs/taurus_data/edge_candidates.csv
head -n 1 configs/taurus_data/source_evidence.csv
uv run pytest tests/unit/test_graph_importer.py
make import-taurus-graph
make import-taurus-graph
uv run pytest tests/unit/test_graph_repository.py tests/unit/test_graph_importer.py
make test
make lint
sed -n '1,320p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,320p' .codex/rules/default.rules
```

## M20.3 Commands Used

```bash
git status --short
sed -n '1,260p' docs/TAURUS_MILESTONE_TODO.md
sed -n '1,260p' docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
rg --files
sed -n '320,580p' packages/taurus_core/db/models.py
sed -n '1330,1845p' packages/taurus_core/db/repositories.py
sed -n '1,220p' apps/api/main.py
sed -n '1,260p' apps/api/routes_data.py
sed -n '1,260p' apps/api/routes_ui.py
sed -n '1,240p' tests/unit/test_graph_repository.py
sed -n '1,240p' tests/unit/test_graph_importer.py
uv run pytest tests/unit/test_graph_api.py
uv run pytest tests/unit/test_graph_repository.py tests/unit/test_graph_importer.py tests/unit/test_graph_api.py
make test
make lint
sed -n '1,320p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,320p' .codex/rules/default.rules
```

## M20.4 Commands Used

```bash
git status --short
sed -n '1,260p' docs/TAURUS_MILESTONE_TODO.md
sed -n '1,260p' docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
rg --files
sed -n '1,260p' apps/web/src/api/client.ts
sed -n '1,260p' apps/web/src/api/types.ts
sed -n '1,260p' apps/web/src/app/routes.tsx
sed -n '1,260p' apps/web/src/components/AppShell.tsx
sed -n '1,260p' apps/web/src/features/ShariahPage.tsx
pnpm build
pnpm test -- GraphPages
make test-ui
make build-ui
make test
make lint
make migrate
make import-taurus-graph DATA_DIR=configs/taurus_data
TAURUS_GRAPH_ENABLED=true make api
make ui
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1000 --virtual-time-budget=5000 --dump-dom http://127.0.0.1:5173/graph
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1000 --virtual-time-budget=5000 --dump-dom http://127.0.0.1:5173/graph/company/INFY
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1000 --virtual-time-budget=5000 --dump-dom http://127.0.0.1:5173/graph/edges/review
'/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' --headless=new --disable-gpu --hide-scrollbars --window-size=1440,1000 --virtual-time-budget=5000 --dump-dom http://127.0.0.1:5173/graph/signals
lsof -iTCP:8000 -sTCP:LISTEN -n -P
lsof -iTCP:5173 -sTCP:LISTEN -n -P
kill 61419 61444 61436
cat /Users/adnaan/.codex/rules/default.rules
cat .codex/rules/default.rules
```

## M20.5 Commands Used

```bash
git status --short
rg --files
sed -n '1,260p' docs/TAURUS_MILESTONE_TODO.md
sed -n '1,260p' docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
sed -n '1,240p' pyproject.toml
sed -n '1,240p' docker-compose.yml
sed -n '1,220p' .env.example
uv add 'neo4j>=6,<7'
uv run pytest tests/unit/test_config.py tests/unit/test_graph_api.py tests/unit/test_neo4j_projection.py
make project-neo4j-graph
make test
make lint
docker compose --profile neo4j config --services
docker compose config --services
sed -n '1,360p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,360p' .codex/rules/default.rules
```

## M20.6 Commands Used

```bash
git status --short
rg --files
sed -n '1,260p' docs/TAURUS_MILESTONE_TODO.md
sed -n '1,260p' docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
sed -n '845,940p' docs/TAURUS_DATA_INTEGRATION.md
sed -n '320,560p' packages/taurus_core/db/models.py
sed -n '1334,1765p' packages/taurus_core/db/repositories.py
uv run pytest tests/unit/test_config.py tests/unit/test_graph_stats.py
uv run pytest tests/unit/test_graph_repository.py tests/unit/test_graph_importer.py tests/unit/test_graph_api.py tests/unit/test_neo4j_projection.py tests/unit/test_graph_stats.py tests/unit/test_config.py
make migrate
make seed-mock
make import-taurus-graph DATA_DIR=configs/taurus_data
make compute-graph-stats AS_OF=2024-12-17
make test
make lint
sed -n '1,360p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,360p' .codex/rules/default.rules
```

## M20.7 Commands Used

```bash
git status --short
rg --files
sed -n '1,260p' docs/TAURUS_MILESTONE_TODO.md
sed -n '1,260p' docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
sed -n '990,1070p' docs/TAURUS_DATA_INTEGRATION.md
sed -n '1,260p' packages/taurus_core/agents/schemas.py
sed -n '1,260p' packages/taurus_core/agents/technical_analyst.py
sed -n '1,260p' packages/taurus_core/agents/roster.py
sed -n '1,320p' packages/taurus_core/agents/runner.py
sed -n '340,620p' packages/taurus_core/db/models.py
sed -n '1334,1908p' packages/taurus_core/db/repositories.py
uv run pytest tests/unit/test_config.py tests/unit/test_graph_analyst.py tests/unit/test_analyst_agents.py
uv run pytest tests/unit/test_graph_analyst.py tests/unit/test_analyst_agents.py
uv run pytest tests/unit/test_paper_runs.py tests/unit/test_ui_aggregate_api.py tests/unit/test_dashboard_observability.py tests/unit/test_alerts_replay_backup.py tests/unit/test_taurus_smoke.py
uv run pytest tests/unit/test_graph_repository.py tests/unit/test_graph_importer.py tests/unit/test_graph_api.py tests/unit/test_neo4j_projection.py tests/unit/test_graph_stats.py tests/unit/test_graph_analyst.py tests/unit/test_config.py
make test
make lint
sed -n '1,260p' /Users/adnaan/.codex/rules/default.rules
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,220p' .codex/rules/default.rules
```

## M20.8 Commands Used

```bash
git status --short
rg -n "M20\.8|Graph-Aware Risk|graph concentration|risk" docs/TAURUS_MILESTONE_TODO.md docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
rg --files apps packages tests docs | rg "risk|graph|TAURUS_MILESTONE_TODO|TAURUS_COMMANDS|GRAPH_INTELLIGENCE"
sed -n '1,260p' packages/taurus_core/risk/engine.py
sed -n '1,260p' packages/taurus_core/risk/schemas.py
sed -n '1,260p' tests/unit/test_risk_approval.py
sed -n '1,260p' packages/taurus_core/graph/stats.py
sed -n '1,260p' packages/taurus_core/config.py
sed -n '320,560p' packages/taurus_core/db/models.py
sed -n '1340,1740p' packages/taurus_core/db/repositories.py
uv run pytest tests/unit/test_graph_risk.py tests/unit/test_config.py tests/unit/test_risk_approval.py
uv run pytest tests/unit/test_graph_repository.py tests/unit/test_graph_importer.py tests/unit/test_graph_api.py tests/unit/test_neo4j_projection.py tests/unit/test_graph_stats.py tests/unit/test_graph_analyst.py tests/unit/test_graph_risk.py tests/unit/test_config.py
make test
make lint
sed -n '1,360p' /Users/adnaan/.codex/rules/default.rules
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,260p' .codex/rules/default.rules
```

## M20.9 Commands Used

```bash
git status --short
rg --files
sed -n '1,260p' docs/TAURUS_MILESTONE_TODO.md
sed -n '1,260p' docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
sed -n '1,620p' packages/taurus_core/observability/metrics.py
sed -n '1,320p' packages/taurus_core/graph/importer.py
sed -n '1,320p' packages/taurus_core/graph/neo4j_projection.py
sed -n '1,320p' packages/taurus_core/graph/stats.py
sed -n '1,320p' packages/taurus_core/agents/runner.py
sed -n '1,340p' tests/unit/test_graph_analyst.py
jq '.panels[] | {id,title,type,gridPos,expr:(.targets[0].expr // null)}' infra/grafana/dashboards/taurus-trading.json
uv run pytest tests/unit/test_graph_observability.py
uv run pytest tests/unit/test_graph_repository.py tests/unit/test_graph_importer.py tests/unit/test_graph_api.py tests/unit/test_neo4j_projection.py tests/unit/test_graph_stats.py tests/unit/test_graph_analyst.py tests/unit/test_graph_risk.py tests/unit/test_graph_observability.py
uv run pytest tests/unit/test_dashboard_observability.py tests/unit/test_health.py
make test
make lint
sed -n '1,240p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,240p' .codex/rules/default.rules
```

## M20.10 Commands Used

```bash
git status --short
sed -n '1,260p' docs/TAURUS_MILESTONE_TODO.md
sed -n '1,260p' docs/TAURUS_GRAPH_INTELLIGENCE_PLAN.md
rg --files | rg 'backtest|strategy|graph|test'
sed -n '1,620p' packages/taurus_core/backtesting/engine.py
sed -n '1,220p' packages/taurus_core/backtesting/context.py
sed -n '1,260p' packages/taurus_core/backtesting/metrics.py
sed -n '1,320p' tests/unit/test_backtest_engine.py
sed -n '1,320p' packages/taurus_core/strategies/base.py
sed -n '1,320p' packages/taurus_core/strategies/factory.py
sed -n '1,320p' packages/taurus_core/strategies/blended_score.py
sed -n '1,320p' packages/taurus_core/strategies/moving_average_crossover.py
sed -n '1334,1908p' packages/taurus_core/db/repositories.py
sed -n '1,360p' packages/taurus_core/agents/graph_analyst.py
sed -n '1,360p' packages/taurus_core/graph/importer.py
head -n 5 configs/taurus_data/company_edges.csv
head -n 5 configs/taurus_data/source_evidence.csv
head -n 5 configs/taurus_data/edge_candidates.csv
uv run pytest tests/unit/test_graph_backtesting.py
uv run pytest tests/unit/test_graph_backtesting.py tests/unit/test_backtest_engine.py
uv run pytest tests/unit/test_graph_repository.py tests/unit/test_graph_analyst.py tests/unit/test_graph_risk.py tests/unit/test_graph_stats.py
uv run pytest tests/unit/test_graph_repository.py tests/unit/test_graph_importer.py tests/unit/test_graph_api.py tests/unit/test_neo4j_projection.py tests/unit/test_graph_stats.py tests/unit/test_graph_analyst.py tests/unit/test_graph_risk.py tests/unit/test_graph_observability.py tests/unit/test_graph_backtesting.py
uv run pytest tests/unit/test_graph_backtesting.py tests/unit/test_backtest_engine.py
make test
make lint
git diff --check
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,260p' .codex/rules/default.rules
sed -n '1,260p' /Users/adnaan/.codex/rules/default.rules
```

## M21 Commands Used

```bash
docker compose up -d postgres
uv run pytest tests/unit/test_config.py tests/unit/test_alerts_replay_backup.py tests/unit/test_graph_repository.py -q
make test
make lint
docker compose ps
docker compose exec -T postgres psql -U taurus -d taurus -Atc "SELECT 'instruments', count(*) FROM instruments UNION ALL SELECT 'daily_candles', count(*) FROM daily_candles UNION ALL SELECT 'graph_nodes', count(*) FROM graph_nodes UNION ALL SELECT 'graph_edges', count(*) FROM graph_edges UNION ALL SELECT 'graph_edge_evidence', count(*) FROM graph_edge_evidence UNION ALL SELECT 'halal_stock_compliance', count(*) FROM halal_stock_compliance;"
docker compose --profile neo4j up -d neo4j
TAURUS_NEO4J_ENABLED=true make project-neo4j-graph
docker compose exec -T neo4j cypher-shell -u neo4j -p taurus-neo4j-local "MATCH (n:TaurusGraphNode) RETURN count(n) AS taurus_graph_nodes;"
docker compose exec -T neo4j cypher-shell -u neo4j -p taurus-neo4j-local "MATCH ()-[r:TAURUS_EDGE]->() RETURN count(r) AS taurus_edges;"
docker compose build api
docker compose up -d api prometheus grafana
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
rg -n "sqlite|sqlite3|taurus\\.db|DATABASE_URL=sqlite" .
find . -type f \( -name '*.db' -o -name '*.sqlite' -o -name '*.sqlite3' \) -print
find /private/tmp -maxdepth 2 -type f -name 'taurus*.db' -print
sed -n '/# END MY CUSTOM ADDITION/,$p' /Users/adnaan/.codex/rules/default.rules
sed -n '1,260p' .codex/rules/default.rules
```

## Current Make Targets

```bash
make setup
make setup-ui
make dev-up
make dev-down
make api
make ui
make build-ui
make test-ui
make migrate
make backtest-mock
make import-mock-news
make import-screener CSV=/path/to/screener.csv
make import-market-data
make import-taurus-graph DATA_DIR=configs/taurus_data
make compute-graph-stats AS_OF=YYYY-MM-DD
make project-neo4j-graph
make sync-halal-stocks
make kite-login-url
make kite-exchange-token REQUEST_TOKEN=<request_token_from_redirect_url>
make kite-sync-instruments
make import-kite-candles
make kite-ltp-smoke
make run-analysts-mock SYMBOL=INFY
make debate-mock SYMBOL=INFY
make trader-proposal-mock SYMBOL=INFY
make risk-review-mock SYMBOL=INFY
make final-approval-mock SYMBOL=INFY
make paper-once-mock SYMBOL=INFY
make paper-loop-once
make paper-loop-start
make paper-loop-kite
make paper-loop-dashboard
make alert-smoke
make alert-test-telegram
make replay-decision DECISION_ID=sample
make backup-local
make backup-db
make restore-local BACKUP=/path/to/backup
make taurus-smoke
make llm-smoke
make test
make lint
```

Optional analyst roster:

```bash
TAURUS_ENABLED_ANALYSTS=technical,news,sentiment,fundamentals,graph make run-analysts-mock SYMBOL=INFY
TAURUS_ENABLED_ANALYSTS=technical make paper-once-mock SYMBOL=INFY
```

Default roster is `technical`; the deterministic graph analyst runs only when
`TAURUS_ENABLED_ANALYSTS` includes `graph`.

LLM-backed analyst workflows use real providers only. The default is local
LM Studio:

```bash
TAURUS_LLM_PROVIDER=lmstudio
TAURUS_LLM_BASE_URL=http://localhost:1234/v1
TAURUS_LLM_MODEL=
TAURUS_LLM_TIMEOUT_SECONDS=20
make llm-smoke
```

Hosted providers are explicit opt-ins:

```bash
TAURUS_LLM_PROVIDER=openai OPENAI_API_KEY=... TAURUS_LLM_MODEL=gpt-5-mini make llm-smoke
TAURUS_LLM_PROVIDER=gemini GEMINI_API_KEY=... TAURUS_LLM_MODEL=gemini-2.5-flash make llm-smoke
```

OpenAI usage requires OpenAI API billing through `OPENAI_API_KEY`; Taurus does
not use ChatGPT subscriptions, browser sessions, cookies, or OAuth workarounds
for backend inference.

`make debate-mock`, `make trader-proposal-mock`, `make final-approval-mock`,
and the paper-run commands now also require the configured real LLM provider
because `BullResearcherAgent`, `BearResearcherAgent`, `ResearchManagerAgent`,
`TraderAgent`, and the final-decision explanation path use provider output
clamped to deterministic guardrails.

## Expected Project Commands By Milestone

```bash
make migrate
make setup-ui
make ui
make build-ui
make test-ui
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
make import-market-data
make import-taurus-graph DATA_DIR=configs/taurus_data
make sync-halal-stocks
make compute-graph-stats AS_OF=YYYY-MM-DD
make project-neo4j-graph
make kite-login-url
make kite-exchange-token REQUEST_TOKEN=<request_token_from_redirect_url>
make kite-sync-instruments
make import-kite-candles
make kite-ltp-smoke
make paper-loop-start
make paper-loop-once
make paper-loop-kite
make paper-loop-dashboard
make replay-decision DECISION_ID=sample
make backup-local
make backup-db
make restore-local BACKUP=/path/to/backup
make alert-smoke
make alert-test-telegram
make taurus-smoke
```

## API Smoke Checks

```bash
curl http://localhost:8000/health
curl http://localhost:8000/ready
curl http://localhost:8000/metrics
curl http://localhost:8000/data/instruments
curl "http://localhost:8000/data/candles?symbol=INFY&timeframe=1d"
curl "http://localhost:8000/data/quotes/latest?symbol=INFY"
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
curl http://localhost:8000/ui/overview
curl http://localhost:8000/ui/history
curl http://localhost:8000/ui/runs/{run_id}
curl http://localhost:8000/ui/runs/{run_id}/symbols/INFY/decision-trail
curl http://localhost:8000/ui/replay/{decision_id}
curl http://localhost:8000/ui/risk
curl http://localhost:8000/ui/portfolio
curl http://localhost:8000/graph/overview
curl http://localhost:8000/graph/company/INFY
curl http://localhost:8000/graph/candidate-edges
curl http://localhost:8000/graph/signals
curl http://localhost:8000/graph/bullish-candidates
curl http://localhost:8000/graph/edges/{edge_key}
curl http://localhost:8000/graph/edges/{edge_key}/evidence
curl -X POST http://localhost:8000/graph/edges/{edge_key}/promote
curl -X POST http://localhost:8000/graph/edges/{edge_key}/reject
curl -X POST http://localhost:8000/alerts/test
curl http://localhost:8000/replay/{decision_id}
```

Post-MVP live-readiness API smoke check, if implemented later:

```bash
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
prefix_rule(pattern=["make", "setup-ui"], decision="allow")
prefix_rule(pattern=["make", "test"], decision="allow")
prefix_rule(pattern=["make", "lint"], decision="allow")
prefix_rule(pattern=["make", "dev-up"], decision="allow")
prefix_rule(pattern=["make", "dev-down"], decision="allow")
prefix_rule(pattern=["make", "api"], decision="allow")
prefix_rule(pattern=["make", "ui"], decision="allow")
prefix_rule(pattern=["make", "build-ui"], decision="allow")
prefix_rule(pattern=["make", "test-ui"], decision="allow")
prefix_rule(pattern=["uv", "run"], decision="allow")
prefix_rule(pattern=["graphify", "update", "."], decision="allow")
prefix_rule(pattern=["make", "migrate"], decision="allow")
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
prefix_rule(pattern=["make", "import-market-data"], decision="allow")
prefix_rule(pattern=["make", "import-taurus-graph"], decision="allow")
prefix_rule(pattern=["make", "compute-graph-stats"], decision="allow")
prefix_rule(pattern=["make", "project-neo4j-graph"], decision="allow")
prefix_rule(pattern=["make", "sync-halal-stocks"], decision="allow")
prefix_rule(pattern=["make", "kite-login-url"], decision="allow")
prefix_rule(pattern=["make", "kite-exchange-token"], decision="allow")
prefix_rule(pattern=["make", "kite-sync-instruments"], decision="allow")
prefix_rule(pattern=["make", "import-kite-candles"], decision="allow")
prefix_rule(pattern=["make", "import-market-data"], decision="allow")
prefix_rule(pattern=["make", "kite-ltp-smoke"], decision="allow")
prefix_rule(pattern=["make", "paper-loop-start"], decision="allow")
prefix_rule(pattern=["make", "paper-loop-once"], decision="allow")
prefix_rule(pattern=["make", "position-monitor"], decision="allow")
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
prefix_rule(pattern=["curl", "-sS", "-o", "/private/tmp/taurus-m16-ui-overview.json", "-w", "%{http_code}", "http://127.0.0.1:8000/ui/overview"], decision="allow")
prefix_rule(pattern=["curl", "-sS", "-o", "/private/tmp/taurus-m16-ui-history.json", "-w", "%{http_code}", "http://127.0.0.1:8000/ui/history"], decision="allow")
prefix_rule(pattern=["curl", "-sS", "-o", "/private/tmp/taurus-m16-ui-run.json", "-w", "%{http_code}", "http://127.0.0.1:8000/ui/runs/pr-75fdbb0381152d57"], decision="allow")
prefix_rule(pattern=["curl", "-sS", "-o", "/private/tmp/taurus-m16-ui-trail.json", "-w", "%{http_code}", "http://127.0.0.1:8000/ui/runs/pr-75fdbb0381152d57/symbols/INFY/decision-trail"], decision="allow")
prefix_rule(pattern=["curl", "-sS", "-o", "/private/tmp/taurus-m16-ui-replay.json", "-w", "%{http_code}", "http://127.0.0.1:8000/ui/replay/dec-1d59184394a64b42"], decision="allow")
prefix_rule(pattern=["curl", "-sS", "-o", "/private/tmp/taurus-m16-ui-risk.json", "-w", "%{http_code}", "http://127.0.0.1:8000/ui/risk"], decision="allow")
prefix_rule(pattern=["curl", "-sS", "-o", "/private/tmp/taurus-m16-ui-portfolio.json", "-w", "%{http_code}", "http://127.0.0.1:8000/ui/portfolio"], decision="allow")
prefix_rule(pattern=["curl", "-sS", "-o", "/private/tmp/taurus-m16-ui-vite.html", "-w", "%{http_code}", "http://127.0.0.1:5173/"], decision="allow")
prefix_rule(pattern=["curl", "-sS", "-o", "/private/tmp/taurus-vite-check.html", "-w", "%{http_code}", "http://127.0.0.1:5173/"], decision="allow")
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
