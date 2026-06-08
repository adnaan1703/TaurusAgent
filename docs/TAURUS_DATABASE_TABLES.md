# Taurus Database Tables

This document summarizes the current Taurus Postgres `public` schema and what
each table stores. It includes active application tables and legacy mock archive
tables created during the migration to Kite-backed market data and paper runs.

## Summary

- Active application tables: 38
- Legacy mock archive tables: 11
- Total tables: 49

## Market Data and Instruments

| Table | Stores |
|---|---|
| `instruments` | Canonical securities/instruments by symbol, exchange, segment, currency, lot size, tick size, and active flag. |
| `instrument_provider_mappings` | Mapping from Taurus symbols to provider-specific identifiers, mainly Kite instrument tokens and provider symbols. |
| `daily_candles` | Kite OHLCV daily candles by symbol, timeframe, and trade date. This is the main price-history table. |
| `market_price_snapshots` | Point-in-time/latest quote snapshots from a market data provider. |
| `portfolio_snapshots` | Aggregate portfolio value snapshots: cash, holdings value, and total value by date. |

## Paper Trading Runtime

| Table | Stores |
|---|---|
| `taurus_profiles` | First-class paper profile catalog keyed by `profile_id`, including display name, starting corpus, currency, status (`ACTIVE` or `ARCHIVED`), description, metadata, and timestamps. The default seeded profile is `local-paper` with INR 10,000 starting corpus. |
| `paper_runs` | One scheduled/manual paper trading run, including symbols, status, errors, market-data summary, and artifacts such as next-open settlement summaries/details. |
| `paper_accounts` | Paper account state per run/portfolio: cash, exposure, equity, realized P&L, and unrealized P&L. |
| `paper_orders` | Paper order records created from final decisions, including pending AMO-style next-open paper orders stored in JSON payload metadata. Pending rows use `status=PENDING_NEXT_OPEN`, `execution_policy=next_open`, `signal_trade_date`, and `scheduled_fill_session=next_open`; terminal settlement rows keep `status_history` and add `filled_trade_date` when applicable. |
| `paper_fills` | Simulated fill records for paper orders, including trade date, costs, slippage, brokerage, and taxes. Settlement fills are simulated from the first newer Kite daily candle open; Kite is not used for order routing. |
| `paper_positions` | Paper portfolio positions by symbol, quantity, cost basis, market value, and P&L. |

## Agent and Decision Pipeline

| Table | Stores |
|---|---|
| `analyst_reports` | Outputs from analyst agents such as technical and graph: score, confidence, stance, key points, risks, and source IDs. |
| `debate_reports` | Bull/bear research debate results and research-manager consensus. |
| `trader_proposals` | Trader agent proposals: action, confidence, target position, stop-loss/take-profit, lifecycle trigger, and rationale. |
| `risk_reviews` | Risk manager outputs: approved position size, hard-rule results, committee summary, and risk status. |
| `final_decisions` | Portfolio manager final decision: final action, approval status, approved quantity, and broker-send eligibility. |

## Graph Intelligence

| Table | Stores |
|---|---|
| `graph_nodes` | Graph nodes such as companies, sectors, products, industries, dependencies, and risks. |
| `graph_edges` | Relationships between graph nodes: competitor, supplier/customer, cost driver, dependency, and related edge types. |
| `graph_edge_evidence` | Evidence backing graph edges, including source title, source type, source date, confidence, excerpt, and reference. |
| `graph_edge_stats` | Statistical validation for graph edges: correlation, residual correlation, lead-lag score, stability, p-value, and sample size. |
| `graph_signals` | Per-symbol graph analyst signals: score, confidence, horizon, and explanation. |
| `graph_signal_contributions` | Edge/node-level contribution breakdown behind each graph signal. |

## Backtesting

| Table | Stores |
|---|---|
| `backtest_runs` | Backtest run metadata: strategy, seed, date range, capital, metrics, and parameters. |
| `backtest_signals` | Strategy signals generated during backtests. |
| `backtest_orders` | Simulated orders generated during backtests. |
| `backtest_fills` | Simulated fills for backtest orders. |
| `backtest_positions` | Backtest positions and P&L by run/symbol. |
| `backtest_equity_points` | Backtest equity curve points by date. |
| `feature_values` | Feature snapshots used by strategies and agents, such as technical features. |

## News, Sentiment, and Documents

| Table | Stores |
|---|---|
| `raw_documents` | Ingested source documents/news items with title, body, symbols, entities, checksum, and metadata. |
| `company_events` | Extracted company events from raw documents. |
| `sentiment_scores` | Sentiment/event scores per symbol/event with confidence and rationale. |

## Fundamentals and Compliance

| Table | Stores |
|---|---|
| `fundamental_imports` | Metadata for imported fundamentals files: source, hash, row counts, status, and missing columns. |
| `fundamental_snapshots` | Raw/normalized fundamental metric values by symbol and reporting/import date. |
| `fundamental_scores` | Derived fundamental quality, valuation, leverage-risk, ownership, and composite scores. |
| `halal_stock_imports` | Halal-stock universe import metadata: source URL, counts, checksum, and generated YAML path. |
| `halal_stock_compliance` | Per-stock Shariah/halal compliance status and source metadata. |

## Ops and Audit

| Table | Stores |
|---|---|
| `audit_log` | Generic audit events with actor, event type, payload, note, and created timestamp. |

## Legacy Mock Archive Tables

These are archive copies from cleanup, not active runtime tables.

| Table | Stores |
|---|---|
| `daily_candles_legacy_mock_archive` | Archived legacy `mock_market_data` candles removed before Kite import. |
| `paper_runs_legacy_mock_archive` | Archived old mock-backed paper runs. |
| `paper_accounts_legacy_mock_archive` | Archived paper account rows tied to old mock-backed runs. |
| `paper_orders_legacy_mock_archive` | Archived paper orders tied to old mock-backed runs. |
| `paper_fills_legacy_mock_archive` | Archived paper fills tied to old mock-backed runs. |
| `paper_positions_legacy_mock_archive` | Archived paper positions tied to old mock-backed runs. |
| `analyst_reports_legacy_mock_archive` | Archived analyst reports tied to old mock-backed runs. |
| `debate_reports_legacy_mock_archive` | Archived debate reports tied to old mock-backed runs. |
| `trader_proposals_legacy_mock_archive` | Archived trader proposals tied to old mock-backed runs. |
| `risk_reviews_legacy_mock_archive` | Archived risk reviews tied to old mock-backed runs. |
| `final_decisions_legacy_mock_archive` | Archived final decisions tied to old mock-backed runs. |
