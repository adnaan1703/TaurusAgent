# Kite Connect Integration Plan

Status: Implemented in M17. Real Kite smoke checks still require a valid local `KITE_ACCESS_TOKEN`.

Purpose: integrate Zerodha Kite Connect as a real market data provider for Taurus while preserving the paper-trading-first safety model and keeping provider replacement straightforward for Angel, Upstox, or another provider later.

References:

- Kite Connect Python docs: https://kite.trade/docs/pykiteconnect/v4/
- pykiteconnect README: https://github.com/zerodha/pykiteconnect/blob/master/README.md
- Kite market quotes API docs: https://kite.trade/docs/connect/v3/market-quotes/
- Existing deferred broker plan: `docs/UPSTOX_INTEGRATION_PLAN.md`

## Decisions Locked

- First implementation is data-only. No Kite orders, account reads, holdings sync, WebSocket ticks, OAuth callback flow, or live broker routing.
- `PaperBroker` remains the only execution path.
- `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` remain safe defaults.
- Kite historical daily candles drive paper runs and backtests when Kite is selected as the market data provider.
- Kite LTP/OHLC snapshots are stored for monitoring, API visibility, freshness checks, and auditability, but do not affect paper fills in the first milestone.
- Kite authentication starts with manual local credentials: `KITE_API_KEY` and `KITE_ACCESS_TOKEN`.
- Configured symbols are maintained in a YAML file, not in a long comma-separated environment variable.
- The enabled symbols in that YAML file define both Kite ingestion scope and the effective Kite-backed paper universe.
- The universe file should be provider-neutral, with optional provider-specific aliases or metadata under each symbol.
- Use the current stable `kiteconnect` major version at implementation time, expected as `kiteconnect>=5,<6`, while relying only on APIs stable in the supplied docs.

## Current Repo Context

Taurus already has a market data provider abstraction in `packages/taurus_core/domain/market_data.py` and provider implementations under `packages/taurus_core/data/providers/`.

Current providers:

- `mock`: deterministic in-memory instruments and daily candles.
- `csv`: user-supplied historical OHLCV CSV import.
- `external`: disabled placeholder that fails clearly without configured provider credentials.

There is no existing `providers/universe` module, no `configs/universe` folder, and no universe file loader. `TAURUS_UNIVERSE=NIFTY_100` currently exists only as a simple setting. The practical current universe is whatever active instruments are imported into the database by the selected provider.

The Kite milestone should therefore introduce a new provider-neutral universe config concept.

## Configuration

Add safe defaults to `Settings` and `.env.example`:

```env
TAURUS_MARKET_DATA_PROVIDER=mock
TAURUS_MARKET_DATA_UNIVERSE_PATH=configs/market_data/kite_nse_cash.yaml
TAURUS_MARKET_DATA_LOOKBACK_DAYS=400
TAURUS_KITE_EXCHANGE=NSE
KITE_API_KEY=
KITE_API_SECRET=
KITE_ACCESS_TOKEN=
```

Do not add `TAURUS_MARKET_DATA_SYMBOLS`. A 100-symbol list belongs in a maintained config file, not in `.env`.

Secret handling:

- Redact `KITE_API_KEY`, `KITE_API_SECRET`, and `KITE_ACCESS_TOKEN` in `Settings.safe_dict()`.
- Never log tokens.
- Missing Kite credentials should fail only when a Kite provider command or Kite-backed run is attempted.

## Universe Config

Create the default file:

```text
configs/market_data/kite_nse_cash.yaml
```

Recommended schema:

```yaml
universe_name: kite_nse_cash
default_exchange: NSE
default_segment: EQUITY
symbols:
  - symbol: INFY
    name: Infosys Ltd
    enabled: true
    providers:
      kite:
        exchange: NSE
        tradingsymbol: INFY

  - symbol: TCS
    name: Tata Consultancy Services Ltd
    enabled: true
    providers:
      kite:
        exchange: NSE
        tradingsymbol: TCS
```

Loader behavior:

- Load the path from `TAURUS_MARKET_DATA_UNIVERSE_PATH`.
- Require `symbols` to be a non-empty list for the Kite provider.
- Ignore entries with `enabled: false`.
- Normalize canonical `symbol` to uppercase.
- Use top-level defaults when per-symbol exchange or segment is omitted.
- Treat canonical `symbol` as Taurus identity.
- Treat provider-specific `tradingsymbol` as the provider identity.
- Validate duplicate canonical symbols as an error.
- Record the source file path in import summaries and run metadata.

Future provider example:

```yaml
providers:
  kite:
    exchange: NSE
    tradingsymbol: INFY
  upstox:
    exchange: NSE_EQ
    instrument_key: NSE_EQ|INE009A01021
  angel:
    exchange: NSE
    symboltoken: "1594"
```

Provider-specific fields should be optional hints. The provider adapter may still resolve fresh metadata against its instrument master during sync.

## Domain And Interfaces

Keep existing candle interfaces provider-neutral:

- `MarketDataProvider`
- `DailyCandle`
- `MarketDataProviderError`

Add quote support:

- `MarketQuoteProvider` protocol with a method such as `get_latest_snapshots(symbols: list[str]) -> list[MarketPriceSnapshot]`.
- `MarketPriceSnapshot` domain type with:
  - `symbol`
  - `provider`
  - `exchange`
  - `provider_symbol`
  - `instrument_token` or provider instrument key, nullable
  - `last_price`
  - `open`
  - `high`
  - `low`
  - `close`
  - `volume`, nullable
  - `fetched_at`
  - `source`
  - `raw`, optional mapping for provider payload details

Provider behavior:

- `mock` and `csv` should implement quote snapshots from each symbol's latest candle so tests and UI paths stay provider-independent.
- `kite` should implement actual quote snapshots from Kite LTP/OHLC APIs.
- Application code should depend on Taurus protocols, not on Kite classes.

## Persistence

Add `instrument_provider_mappings`:

- `id`
- `provider`
- `symbol`
- `exchange`
- `provider_symbol`
- `instrument_token`
- `segment`
- `currency`
- `lot_size`
- `tick_size`
- `active`
- `raw`
- `synced_at`
- unique constraint on `(provider, symbol)`

Add `market_price_snapshots`:

- `id`
- `provider`
- `symbol`
- `exchange`
- `provider_symbol`
- `instrument_token`
- `last_price`
- `open`
- `high`
- `low`
- `close`
- `volume`
- `fetched_at`
- `source`
- `raw`
- index on `(provider, symbol, fetched_at)`

Continue storing daily candles in the existing `daily_candles` table. Use `source` values such as:

- `kite:historical:NSE`
- `kite:quote:NSE`

## Kite Provider

Add `packages/taurus_core/data/providers/kite_market_data.py`.

Responsibilities:

- Initialize the Kite client with `KITE_API_KEY` and `KITE_ACCESS_TOKEN`.
- Load enabled symbols from the universe YAML file.
- Fetch and cache the Kite instrument master for configured exchange only.
- Resolve canonical symbols to Kite instruments.
- Persist provider mappings.
- Fetch historical daily candles for each enabled symbol for the configured lookback window.
- Fetch LTP/OHLC snapshots for enabled symbols.
- Chunk quote requests to remain within Kite API limits.
- Add conservative request pacing and bounded retries for transient failures.
- Translate Kite errors into Taurus provider errors with actionable messages.

Historical candle behavior:

- Default lookback: `TAURUS_MARKET_DATA_LOOKBACK_DAYS=400`.
- Timeframe: existing Taurus default `1d`.
- `data_available_time`: use after-market timestamp for daily candles, consistent with current CSV/mock behavior.
- If Kite returns no candles for an enabled symbol, fail that symbol clearly and record the error in import or smoke output.

Instrument sync behavior:

- A sync command should resolve all enabled YAML symbols against Kite's instrument master.
- If a symbol cannot be resolved, report the missing symbol and do not silently import partial mappings unless the command explicitly supports partial mode.

## Factory And Commands

Extend `build_market_data_provider()`:

- `mock` returns `MockMarketDataProvider`.
- `csv` returns `CSVMarketDataProvider`.
- `kite` returns `KiteMarketDataProvider`.
- `external` remains disabled unless later removed or repurposed.

Add Make targets:

```make
kite-sync-instruments
import-kite-candles
kite-ltp-smoke
```

Script intent:

- `scripts/sync_kite_instruments.py`: resolve and persist instrument mappings for enabled YAML symbols.
- `scripts/import_kite_candles.py`: import historical candles for enabled YAML symbols.
- `scripts/kite_ltp_smoke.py`: fetch and persist latest LTP/OHLC snapshots, then print a sanitized summary.

Manual usage:

```bash
TAURUS_MARKET_DATA_PROVIDER=kite make kite-sync-instruments
TAURUS_MARKET_DATA_PROVIDER=kite make import-kite-candles
TAURUS_MARKET_DATA_PROVIDER=kite make kite-ltp-smoke
```

## API

Add:

```http
GET /data/quotes/latest?symbol=INFY
```

Behavior:

- Reads the latest stored `market_price_snapshots` row.
- Does not call Kite from the request path.
- Returns 404 when no snapshot exists for the symbol.
- Includes provider, source, fetched timestamp, and OHLC/LTP values.

Keep existing endpoints unchanged:

- `GET /data/instruments`
- `GET /data/candles`

## Paper Trading Flow

When `TAURUS_MARKET_DATA_PROVIDER=kite`:

- Paper run loads Kite-backed daily candles through the existing import path.
- The enabled YAML symbols become the active Kite-backed universe.
- Strategies operate on imported daily candles, as they do today.
- Paper fills continue to use the latest imported daily candle in `PaperBroker`.
- LTP/OHLC snapshots are available for dashboards and monitoring only in the first milestone.

Do not route final decisions to Kite. Do not add live order placement.

## Testing

Unit tests:

- Default settings remain safe.
- Kite secrets are redacted.
- Unsupported provider names still fail.
- `TAURUS_MARKET_DATA_PROVIDER=kite` is accepted.
- Missing Kite credentials fail clearly when Kite provider is built or used.
- Universe YAML loader validates:
  - non-empty symbols,
  - duplicate symbols,
  - disabled symbols,
  - missing provider hints,
  - uppercase normalization.
- Fake Kite client resolves instruments.
- Fake Kite client maps historical candles into `DailyCandle`.
- Fake Kite client maps LTP/OHLC into `MarketPriceSnapshot`.
- Snapshot repository returns latest snapshot per symbol.
- Expired-token or auth failures become clear provider errors.
- Rate limiter and retry behavior are deterministic with injected fake sleeper/time.

API tests:

- `/data/quotes/latest?symbol=INFY` returns latest stored snapshot.
- Missing symbol returns 404.
- Existing `/data/instruments` and `/data/candles` continue to work.

Regression checks:

```bash
make test
make lint
DATABASE_URL=sqlite:////private/tmp/taurus-kite-plan-smoke.db make paper-loop-mock
```

Manual real-credential smoke checks:

```bash
TAURUS_MARKET_DATA_PROVIDER=kite make kite-sync-instruments
TAURUS_MARKET_DATA_PROVIDER=kite make import-kite-candles
TAURUS_MARKET_DATA_PROVIDER=kite make kite-ltp-smoke
curl "http://localhost:8000/data/quotes/latest?symbol=INFY"
```

Manual token workflow:

1. Start the local API with `make api`.
2. Run `make kite-login-url` to print the Kite login URL for the configured local `KITE_API_KEY`.
3. Open the URL and complete Kite login.
4. Kite redirects to `http://127.0.0.1:8000/` with `request_token=...`; Taurus exchanges it with `KITE_API_SECRET` and stores `KITE_ACCESS_TOKEN` in ignored `.env`.
5. Rerun `make kite-sync-instruments`, `make import-kite-candles`, or `make kite-ltp-smoke`.
6. If the API was not running during login, run `make kite-exchange-token REQUEST_TOKEN=<request_token_from_redirect_url>` as a manual fallback.
7. If a command reports that the access token is invalid or expired, regenerate the token and update `.env`.

Taurus does not persist tokens in the database and does not call Kite from the request path.

Automated tests must not require real Kite credentials.

## Documentation And Milestone Tracking

During implementation:

- Add M17 to `docs/TAURUS_MILESTONE_TODO.md`.
- Keep completion reporting consistent with repo rules:
  - assumptions made,
  - mocks created,
  - mocks used.
- Update `.env.example`, README, `docs/TAURUS_COMMANDS.md`, and this file.
- Document the manual Kite token workflow and token expiry behavior.
- Document that the YAML universe defines the Kite-backed paper universe.

At milestone cleanup:

- Inspect `/Users/adnaan/.codex/rules/default.rules`.
- Treat entries after the user's `# END MY CUSTOM ADDITION` marker as accidental global approvals.
- Move Taurus-specific approved prefixes into `.codex/rules/default.rules` if missing.
- Document those commands in `docs/TAURUS_COMMANDS.md`.
- Remove Taurus-specific accidental approvals from the global rules file.
- Do not copy unrelated global approvals.

## Acceptance Criteria

- Mock and CSV market data paths still pass tests.
- Kite provider can be selected only when explicitly configured.
- Missing Kite credentials do not break default test runs.
- Kite instrument sync resolves enabled YAML symbols.
- Kite candle import persists daily candles with provider source metadata.
- Kite LTP/OHLC smoke persists snapshots.
- `/data/quotes/latest` serves persisted snapshots without making live Kite calls.
- Paper trading remains paper-only.
- No real secrets are committed or logged.

## Deferred Work

- Kite order placement.
- Kite account, profile, holdings, and positions read APIs.
- OAuth callback and token storage.
- WebSocket tick ingestion.
- Intraday candle strategy support.
- LTP-based paper fill pricing.
- Full Kite instrument master import.
- Provider implementations for Angel and Upstox using the same universe schema.
