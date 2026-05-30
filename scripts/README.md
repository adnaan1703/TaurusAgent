# Scripts

Operational scripts for local milestone workflows.

All database-backed scripts use Docker Postgres by default through
`postgresql+psycopg://taurus:taurus@localhost:5432/taurus`. Start the Postgres
service with `docker compose up -d postgres` or `make dev-up` before running
database-backed scripts. SQLite database URLs are rejected.

- `migrate.py`: create or update Postgres database tables.
- `kite_auth.py`: print Kite login URL and exchange a manual request token into local `.env`.
- `sync_kite_instruments.py`, `import_kite_candles.py`, `kite_ltp_smoke.py`: run data-only Kite Connect market-data sync, candle import, and latest quote snapshot smoke checks.
- `run_backtest.py`: run backtests against existing Kite-imported daily candles.
- `import_mock_news.py`: load deterministic mock news and events.
- `run_analysts.py`, `run_research_debate.py`, `run_trader_proposal.py`: run analyst and research workflows with existing Kite-imported market data and the configured real LLM provider.
- `run_risk_review.py`, `run_final_approval.py`: run deterministic risk and portfolio-manager gates.
- `run_paper_once.py`, `run_paper_loop.py`: run local PaperBroker simulation using Kite market data. The canonical `make paper-loop-kite` wrapper enables graph analyst, graph-aware strategy selection, graph readiness preflight, and graph concentration risk; direct script runs use the environment you provide.
- `replay_decision.py`, `backup_local.py`, `restore_local.py`: replay stored decisions and manage Postgres backups.
- `taurus_smoke.py`: run the M13 end-to-end paper MVP smoke check.
- `llm_smoke.py`: optional real LLM provider smoke check. Defaults to LM Studio
  at `http://localhost:1234/v1`; use `TAURUS_LLM_PROVIDER=openai` with
  `OPENAI_API_KEY` or `TAURUS_LLM_PROVIDER=gemini` with `GEMINI_API_KEY` for
  hosted providers.
