# Taurus Paper-Trading MVP Release

M13 releases the local, observable, paper-trading-first Taurus MVP. The release is designed to run without external credentials by using deterministic mock data, mock news, mock LLM responses, and the internal PaperBroker.

## Local Release Runbook

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
```

Local service URLs:

- Taurus API: `http://localhost:8000`
- Streamlit dashboard: `http://localhost:8501`
- Prometheus: `http://localhost:9090`
- Grafana: `http://localhost:3000`

## Safety Defaults

These defaults are required for the MVP:

```text
TAURUS_MODE=paper
LIVE_TRADING_ENABLED=false
BROKER_PROVIDER=paper
TAURUS_LLM_PROVIDER=mock
TAURUS_ALERT_PROVIDER=mock
```

`Settings` rejects `LIVE_TRADING_ENABLED=true`, non-paper broker providers, and unsupported modes. Trader proposals and risk reviews are not orders. Only final decisions with `APPROVED_FOR_PAPER` can be routed, and the only routed adapter is `PaperBroker`.

## Optional Inputs

The MVP does not require external credentials. These optional inputs can extend paper-mode validation:

- Real OHLCV CSV path: run `make import-price-csv CSV=/path/to/prices.csv`.
- Real Screener CSV path: run `make import-screener CSV=/path/to/screener.csv`.
- Telegram smoke credentials: set `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` locally, then run `make alert-test-telegram`.

Do not commit CSV exports, API keys, broker credentials, Telegram tokens, or chat IDs.

## Paper-Trading Assumptions

- Costs: Paper executions use configurable placeholder India cash-equity costs from `TAURUS_PAPER_BROKERAGE_BPS`, `TAURUS_PAPER_EXCHANGE_TXN_CHARGE_BPS`, and `TAURUS_PAPER_TAX_LEVY_BPS`.
- Slippage: Paper fills use fixed bps slippage from `TAURUS_PAPER_SLIPPAGE_BPS`.
- Fills: PaperBroker fills approved quantity against the latest available daily candle. Orders above the partial-fill threshold are split into two fills.
- Timing: The default schedule is `daily_after_close`, `Asia/Kolkata`, after market close.
- Data freshness: Mock daily candles are deterministic historical fixtures. Freshness metrics can show old wall-clock age in mock mode.
- Fundamentals: Without a real Screener CSV, the fundamentals agent uses mock or previously imported fixture data.
- Alerts: Mock alerting is the default. Real Telegram delivery is optional post-MVP validation.

## Known Limitations

- No Upstox sandbox adapter is part of M13.
- No live broker adapter exists in the MVP path.
- No real-money orders are placed.
- No intraday or high-frequency strategy loop is included.
- Real vendor data and real Screener exports still require user-provided local files or credentials.
- Postgres backup uses local `pg_dump` when available, or the Docker Compose `postgres` service fallback in local development. SQLite backup is file-copy based.
- The local scheduler is a simple loop for MVP operation, not a distributed job system.

## Post-MVP Broker Path

Broker sandbox and production readiness are deferred to M14 and M15. Follow `docs/UPSTOX_INTEGRATION_PLAN.md`; keep `PaperBroker` as the default and `LIVE_TRADING_ENABLED=false` until an explicit later milestone changes the readiness gate.
