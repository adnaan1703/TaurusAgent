# Kite-Only Market Data Migration Plan

Last updated: 2026-05-30

Execution order: 3 of 10. Run this after the Docker/Postgres and real LLM
provider migrations. It prepares the real-data paper path that graph and
position lifecycle plans will build on.

## Summary

Remove market-data mocks from Taurus runtime completely and make Zerodha Kite the
only supported market-data provider for the current system. Keep the provider
architecture extensible through a real-provider registry so future vendors can be
added later without reintroducing mock or placeholder providers.

This plan is intentionally limited to the market-data component and the thin
consumer wiring needed to stop market-data seeding/import mocks. It does not
migrate LLM, news, alert, analyst, risk, broker, or paper-execution mocks.

## Target State

- `TAURUS_MARKET_DATA_PROVIDER=kite` is the default and only accepted runtime
  market-data provider.
- Runtime code has no `MockMarketDataProvider`, no `seed_mock_data.py`, no CSV
  market-data provider path, and no disabled external placeholder provider.
- Market-data ingestion uses Kite instrument sync, Kite historical daily candle
  import, and Kite latest quote snapshots.
- Provider selection remains extensible through a registry of real providers.
  The initial registry contains only `kite`.
- Tests may use direct repository fixtures or fake Kite clients, but there is no
  production mock market-data provider or seed script.
- Existing mock rows are not silently mixed with Kite rows. Kite runs fail with
  a clear preflight error if old `mock_market_data` candles are present in the
  selected database.

## Implementation Changes

### Provider Layer

- Replace the current provider factory with a real-provider registry.
  - Keep `MarketDataProvider` and `MarketQuoteProvider` protocols.
  - Register `kite` as the only built-in provider.
  - Make unsupported provider names fail with an explicit error listing the
    supported real providers.
- Remove runtime exports/imports for:
  - `MockMarketDataProvider`
  - `CSVMarketDataProvider`
  - `DisabledExternalMarketDataProvider`
- Delete or quarantine the provider implementations that are no longer runtime
  supported:
  - `packages/taurus_core/data/providers/mock_market_data.py`
  - `packages/taurus_core/data/providers/csv_market_data.py`
- Keep `KiteMarketDataProvider` as the canonical implementation.
- Preserve fake Kite client injection in tests only. This is a vendor API test
  double, not a Taurus mock market-data provider.

### Configuration

- Change `Settings.taurus_market_data_provider` default from `mock` to `kite`.
- Restrict market-data provider validation to `{"kite"}`.
- Remove runtime config fields that exist only for mock or CSV market data:
  - `taurus_mock_seed`
  - `taurus_mock_candle_count`
  - `taurus_price_csv_path`
  - `taurus_price_csv_dir`
- Keep Kite credential fields:
  - `kite_api_key`
  - `kite_api_secret`
  - `kite_access_token`
  - `taurus_kite_exchange`
  - `taurus_market_data_universe_path`
  - `taurus_market_data_lookback_days`
- Keep Kite credential validation at provider construction/use time instead of
  settings-load time, so non-data commands and unit tests can still initialize
  settings without live credentials.
- Update `.env.example` to use `TAURUS_MARKET_DATA_PROVIDER=kite` and remove
  mock/CSV market-data settings.

### Database And Data Safety

- Change `DailyCandle.source` and `DailyCandleModel.source` defaults away from
  `mock_market_data`.
  - Prefer no domain default, or use a neutral internal default only where tests
    construct candles directly.
  - Real imports must always provide provider-specific sources such as
    `kite:historical:NSE`.
- Add a market-data preflight used by Kite imports and paper runs:
  - Reject databases containing `daily_candles.source = "mock_market_data"`.
  - Reject paper-run summaries with `provider_name = "mock"` if they would be
    considered by the current run.
  - Do not auto-delete user data.
  - Error message should tell the operator to use a fresh database or run an
    explicit cleanup/reset command.
- If an explicit cleanup command is added, make it opt-in and targeted. It must
  not run automatically during Kite import or paper loop execution.

### Scripts And Make Targets

- Remove market-data mock seed entry points:
  - Delete or retire `scripts/seed_mock_data.py`.
  - Remove `make seed-mock`.
- Remove CSV market-data runtime entry points:
  - Delete or retire `scripts/import_price_csv.py`.
  - Remove `make import-price-csv`.
  - Remove `make backtest-real-data` if it only means CSV-backed market data.
- Make Kite the primary market-data command path:
  - Keep `make kite-login-url`.
  - Keep `make kite-exchange-token`.
  - Keep `make kite-sync-instruments`.
  - Keep `make import-kite-candles`.
  - Keep `make kite-ltp-smoke`.
  - Add or alias `make import-market-data` to the Kite candle import path.
- Update scripts that currently seed market data as a convenience for analyst or
  agent workflows.
  - They must require existing Kite-imported instruments/candles instead of
    creating mock market data.
  - Keep their non-market mock behavior unchanged for this migration.
- Update `scripts/run_backtest.py` so backtesting uses existing Kite-imported
  candles or a Kite import step, not mock or CSV provider imports.
- Keep `make paper-loop-kite` as the canonical paper-loop path.
  - Optionally rename or alias it to `make paper-loop-market-data`.
  - Remove market-data-provider-specific mock loop targets only where they seed
    or rely on mock market data.

### API, UI, And Docs

- API data routes can continue reading persisted instruments, candles, and quote
  snapshots; no API contract change is required.
- API responses that expose provider metadata should consistently report
  provider `kite` for new runs/imports.
- React dashboard updates:
  - show provider `kite` from persisted paper-run summaries;
  - show Kite quote/candle freshness where the API already exposes timestamps;
  - remove active UI copy that suggests mock or CSV market-data providers are
    selectable runtime choices;
  - show the clear preflight error when old `mock_market_data` rows block a Kite
    run, instead of rendering it as a generic run failure.
- Update documentation to remove mock market data as a current capability:
  - `README.md`
  - `docs/TAURUS_USAGE_GUIDE.md`
  - `docs/TAURUS_COMMANDS.md`
  - `docs/TAURUS_MOCK_MIGRATION_STATUS.md`
  - `scripts/README.md`
  - `docs/TAURUS_MILESTONE_TODO.md`
- Keep non-market mocks documented separately as remaining migration work.

## Test Plan

- Replace `tests/unit/test_mock_market_data.py` with tests that verify:
  - default provider is `kite`;
  - unsupported providers such as `mock`, `csv`, and `external` are rejected;
  - the provider registry exposes only real providers;
  - missing Kite credentials fail clearly when building/using Kite provider.
- Update existing Kite tests to remain the primary provider tests:
  - instrument master resolution;
  - universe validation;
  - historical daily candle mapping;
  - latest quote snapshot mapping;
  - retry and token-expiry error handling;
  - persistence of provider mappings and quote snapshots.
- Update tests that currently call `seed_mock_data`.
  - For market-data unit tests, use direct repository fixtures with synthetic
    `Instrument` and `DailyCandle` objects.
  - For Kite provider behavior, use fake Kite clients injected into
    `KiteMarketDataProvider`.
  - Do not add a reusable runtime provider that returns synthetic candles.
- Update config tests:
  - assert `taurus_market_data_provider == "kite"`;
  - remove assertions for mock seed/candle settings;
  - assert `TAURUS_MARKET_DATA_PROVIDER=mock` fails validation.
- Update backtest/paper-loop tests:
  - verify backtests can run after Kite-shaped candle fixtures exist;
  - verify paper-loop universe provenance remains `market_data_universe` with
    provider `kite`;
  - verify old mock candle rows cause a clear preflight failure.
- Required verification commands:
  - `uv run pytest tests/unit/test_kite_market_data.py tests/unit/test_config.py`
  - `uv run pytest`
  - `make lint`
- Optional real-credential smoke after implementation:
  - `make kite-sync-instruments`
  - `make import-kite-candles`
  - `make kite-ltp-smoke`
  - `make paper-loop-kite`

## Assumptions And Constraints

- Kite-only runtime was chosen over keeping CSV import as a secondary market-data
  path.
- Existing local databases may contain mock market data; implementation must
  fail clearly rather than mixing old mock rows into Kite runs.
- Test-only fake Kite clients are allowed. Runtime mock market-data providers,
  seed scripts, Make targets, and docs are not.
- Kite remains data-only. `PaperBroker` continues to simulate execution.
- Non-market mocks are out of scope and should not be removed in this task unless
  they directly import or create market-data mocks.
- No Kite credentials, request tokens, access tokens, user CSV exports, or broker
  credentials should be committed.

## Completion Summary Template

When this migration is implemented, include the required milestone completion
summary:

- Assumptions made: list concrete assumptions, or `None`.
- Mocks created: should be `None` for runtime code; mention test-only fake Kite
  clients if new ones were added.
- Mocks used: should be `None` for runtime verification; mention test-only fake
  Kite clients or synthetic repository fixtures if used in tests.
