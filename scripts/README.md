# Scripts

Operational scripts for local milestone workflows.

- `migrate.py`: create or update local database tables.
- `seed_mock_data.py`: load deterministic mock instruments and daily candles.
- `import_price_csv.py`: import user-supplied or synthetic OHLCV CSV candles.
- `kite_auth.py`: print Kite login URL and exchange a manual request token into local `.env`.
- `sync_kite_instruments.py`, `import_kite_candles.py`, `kite_ltp_smoke.py`: run data-only Kite Connect market-data sync, candle import, and latest quote snapshot smoke checks.
- `run_backtest.py`: run deterministic mock or CSV-backed backtests.
- `import_mock_news.py`: load deterministic mock news and events.
- `run_analysts.py`, `run_research_debate.py`, `run_trader_proposal.py`: run mock analyst and research workflows.
- `run_risk_review.py`, `run_final_approval.py`: run deterministic risk and portfolio-manager gates.
- `run_paper_once.py`, `run_paper_loop.py`: run PaperBroker mock execution.
- `replay_decision.py`, `backup_local.py`, `restore_local.py`: replay stored decisions and manage local backups.
- `taurus_smoke.py`: run the M13 end-to-end paper MVP smoke check.
- `llm_smoke.py`: optional LLM provider smoke check.
