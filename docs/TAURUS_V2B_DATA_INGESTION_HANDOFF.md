# Taurus V2B Data Ingestion Handoff

Intent: capture the current `technical_official_v2b` state, the data still
needed before promotion-quality v2B validation, and the existing import paths
for official v2B inputs.

Last updated: 2026-06-24

## Status

V2B implementation is complete and opt-in. The shipped code includes:

- `technical_official_v2b` scoring in `TechnicalSignalService`.
- `configs/strategies/graph_aware_score_v2b.yaml`.
- Official context construction through `build_official_technical_context()`.
- Strategy, analyst, paper summary, backtesting, money-management mapping, and
  validation-profile wiring.
- CSV import and readiness commands for official index, India VIX, delivery,
  circuit, and tradability inputs.

V2B is not promoted to the canonical paper-loop strategy. After M86,
`graph_aware_score_v1` remains canonical, while `graph_aware_score_v2` and
`graph_aware_score_v2b` are explicit opt-ins. The latest completed validation
closeout deferred promotion because local candle coverage was insufficient for
comparable v1/v2A/v2B evidence.

Current `make validate-technical-v2` runs intentionally exclude v2B by default.
The command compares v1 and v2A only until official v2B data readiness exists.
Re-enable v2B validation explicitly with:

```bash
TECHNICAL_VALIDATION_INCLUDE_V2B=true make validate-technical-v2
```

Read-only local DB snapshot on 2026-06-24:

- `daily_candles`: 139248 rows.
- `official_index_candles`: 0 rows.
- `official_security_microstructure`: 0 rows.
- Current validation universe: `configs/market_data/nifty_50_shariah.yaml`.
- Validation universe symbols with candles: 17 of 17.
- Common daily candles across that universe: 282.
- Standard validation requirement: 1009 common candles.

## What Remains

Data readiness remains the blocker, not v2B code.

Required before meaningful v2B validation:

- Deeper Kite daily candle history across the validation universe.
- Official benchmark index history for `NIFTY_50`.
- Official volatility index history for `INDIA_VIX`.
- Optional sector-index history for any symbol-to-sector mappings configured in
  `graph_aware_score_v2b.yaml`.
- Security-wise delivery participation rows for validation symbols.
- Security-wise circuit or price-band rows for validation symbols.
- Tradability or implementability rows for validation symbols. Official impact
  cost is preferred; documented proxies such as average trade value can be
  ingested only when explicitly labelled as proxy data.

V2B must not silently behave like v2A when official context is absent. Missing
official context makes v2B unavailable or lowers coverage/confidence through
the v2B scoring metadata.

## Data Families

### Kite Daily Candles

Purpose:

- Provide OHLCV history for v2A base features and the full-system backtest
  window used by v1/v2A/v2B comparisons.

Current path:

```bash
TAURUS_MARKET_DATA_LOOKBACK_DAYS=1434 make import-kite-candles
```

`1434` calendar days is the current standard-mode import guidance for a
3-year evaluation window after a 252-trading-day warm-up. Strong 5-year
validation needs a deeper import.

Validation command:

```bash
make validate-technical-v2
make validate-technical-v2 TECHNICAL_VALIDATION_MODE=strong
TECHNICAL_VALIDATION_INCLUDE_V2B=true make validate-technical-v2
```

### Official Index and VIX Data

Purpose:

- `NIFTY_50` benchmark rows support market-relative return and market regime.
- `INDIA_VIX` rows support volatility level, volatility change, and volatility
  regime.
- Optional sector-index rows support sector-relative returns and sector regime
  when `sector_index_by_symbol` is configured.

Existing storage:

- Table: `official_index_candles`.
- Domain object: `OfficialIndexCandle`.
- Import script: `scripts/import_official_index_data.py`.
- Readiness command: `make check-official-index-readiness`.

Accepted CSV fields:

- Required, either in CSV or command variables:
  `index_symbol`, `index_name`, `index_family`.
- Required per row: `trade_date`, `open`, `high`, `low`, `close`.
- Optional metadata: `source`, `source_url`, `timeframe`,
  `data_available_time`.

Accepted aliases include:

- `index_symbol`: `index_symbol`, `symbol`, `index`.
- `index_name`: `index_name`, `name`.
- `index_family`: `index_family`, `family`, `type`.
- `trade_date`: `trade_date`, `date`.
- `source_url`: `source_url`, `url`.
- `timeframe`: `timeframe`, `interval`.
- `data_available_time`: `data_available_time`, `available_time`,
  `available_at`.

Canonical families:

- `benchmark`
- `sector`
- `volatility`
- `other`

Import examples:

```bash
make import-official-index-data \
  OFFICIAL_INDEX_CSV=/path/to/nifty50.csv \
  OFFICIAL_INDEX_SYMBOL=NIFTY_50 \
  OFFICIAL_INDEX_NAME="Nifty 50" \
  OFFICIAL_INDEX_FAMILY=benchmark \
  OFFICIAL_INDEX_SOURCE=nse_official_index_csv \
  OFFICIAL_INDEX_SOURCE_URL=https://www.nseindia.com/reports-indices-historical-index-data

make import-official-index-data \
  OFFICIAL_INDEX_CSV=/path/to/india-vix.csv \
  OFFICIAL_INDEX_SYMBOL=INDIA_VIX \
  OFFICIAL_INDEX_NAME="India VIX" \
  OFFICIAL_INDEX_FAMILY=volatility \
  OFFICIAL_INDEX_SOURCE=nse_official_vix_csv \
  OFFICIAL_INDEX_SOURCE_URL=https://www.nseindia.com/reports-indices-historical-vix

make import-official-index-data \
  OFFICIAL_INDEX_CSV=/path/to/nifty-it.csv \
  OFFICIAL_INDEX_SYMBOL=NIFTY_IT \
  OFFICIAL_INDEX_NAME="Nifty IT" \
  OFFICIAL_INDEX_FAMILY=sector
```

Readiness examples:

```bash
make check-official-index-readiness
make check-official-index-readiness OFFICIAL_INDEX_SECTOR_SYMBOLS=NIFTY_IT,NIFTY_BANK
```

Default readiness requires `NIFTY_50` and `INDIA_VIX`. Sector indexes are only
required when `OFFICIAL_INDEX_SECTOR_SYMBOLS` is set.

Source candidates:

- NSE Historical Index Data:
  `https://www.nseindia.com/reports-indices-historical-index-data`
- NSE Historical Data - India VIX:
  `https://www.nseindia.com/reports-indices-historical-vix`

## Official Microstructure Data

Purpose:

- Delivery rows support delivery participation and delivery z-score evidence.
- Circuit/price-band rows penalize circuit hits or near-band conditions.
- Tradability rows support implementability evidence, preferably through
  official impact cost or explicitly labelled proxy metrics.

Existing storage:

- Table: `official_security_microstructure`.
- Domain object: `OfficialSecurityMicrostructure`.
- Import script: `scripts/import_official_microstructure_data.py`.
- Readiness command: `make check-official-microstructure-readiness`.

Required CSV fields:

- `symbol`
- `trade_date`

Useful delivery fields:

- `delivery_quantity`
- `delivery_percentage`

Accepted delivery aliases include:

- `delivery_quantity`, `delivery_qty`, `deliverable_quantity`,
  `deliverable_qty`, `deliv_qty`.
- `delivery_percentage`, `delivery_percent`, `delivery_pct`,
  `deliverable_percent`, `deliverable_pct`,
  `percent_deliverable_quantity_to_traded_quantity`,
  `percent_deliverble_quantity_to_traded_quantity`.

Useful circuit fields:

- `price_band_percent`
- `upper_circuit_price`
- `lower_circuit_price`
- `circuit_status`
- `circuit_hit`

Accepted circuit aliases include:

- `price_band_percent`, `price_band_pct`, `price_band`, `band_percent`.
- `upper_circuit_price`, `upper_band`, `upper_price_band`.
- `lower_circuit_price`, `lower_band`, `lower_price_band`.
- `circuit_status`, `price_band_status`.
- `circuit_hit`, `hit_circuit`, `circuit`.

Circuit statuses accepted by the importer:

- `upper_circuit`
- `lower_circuit`
- `near_upper`
- `near_lower`
- `none`
- `no_band`

Useful tradability fields:

- `impact_cost_bps`
- `impact_cost_source_kind`
- `impact_cost_proxy_name`
- `average_trade_value`
- `turnover`

Impact-cost source kinds:

- `official`
- `proxy`
- `unavailable`

Proxy impact-cost rows must name `impact_cost_proxy_name`; otherwise the import
fails. This is deliberate so proxy evidence cannot look like official evidence.

Optional metadata:

- `source`
- `source_url`
- `timeframe`
- `data_available_time`

Import examples:

```bash
make import-official-microstructure-data \
  OFFICIAL_MICROSTRUCTURE_CSV=/path/to/security-wise.csv \
  OFFICIAL_MICROSTRUCTURE_SOURCE=nse_security_wise_csv \
  OFFICIAL_MICROSTRUCTURE_SOURCE_URL=https://www.nseindia.com/report-detail/eq_security

make import-official-microstructure-data \
  OFFICIAL_MICROSTRUCTURE_CSV=/path/to/impact-proxy.csv \
  OFFICIAL_MICROSTRUCTURE_IMPACT_COST_SOURCE_KIND=proxy \
  OFFICIAL_MICROSTRUCTURE_IMPACT_COST_PROXY_NAME=average_trade_value_proxy
```

Readiness examples:

```bash
make check-official-microstructure-readiness OFFICIAL_MICROSTRUCTURE_SYMBOLS=INFY,TCS

make check-official-microstructure-readiness \
  OFFICIAL_MICROSTRUCTURE_SYMBOLS=INFY,TCS \
  OFFICIAL_MICROSTRUCTURE_REQUIRED_FAMILIES=delivery,circuit
```

Default readiness requires all three families:

- `delivery`
- `circuit`
- `tradability`

Source candidates:

- NSE Security-wise Archives:
  `https://www.nseindia.com/report-detail/eq_security`
- NSE Security wise Trades Data:
  `https://www.nseindia.com/historical/security-wise-trades-data`
- NSE All Reports / price-band reports:
  `https://www.nseindia.com/all-reports`
- NSE Historical Surveillance Actions Reports:
  `https://www.nseindia.com/reports/price-band-changes`
- NSE Daily Price Bands background:
  `https://www.nseindia.com/static/regulations/daily-price-bands-reports`

## Injection Contract

All official rows must include enough source metadata to preserve auditability:

- `source`: stable source identifier such as `nse_official_index_csv` or
  `nse_security_wise_csv`.
- `source_url`: page or file URL when available.
- `data_available_time`: when Taurus could have known the row. If omitted, the
  repository/model default is used, but explicit values are preferred for
  no-lookahead validation.
- Raw source row: the importers preserve the raw CSV row in metadata.

The official context builder only uses as-of repository lookups:

- `OfficialIndexCandleRepository.history_as_of(...)`
- `OfficialSecurityMicrostructureRepository.history_as_of(...)`

This means future official rows should not leak into historical validation as
long as `data_available_time` is populated correctly.

## Validation Flow After Data Import

1. Import deeper Kite candles:

```bash
TAURUS_MARKET_DATA_LOOKBACK_DAYS=1434 make import-kite-candles
```

2. Import official index and India VIX CSVs.

3. Import official delivery/circuit/tradability CSVs for the validation symbols.

4. Run readiness checks:

```bash
make check-official-index-readiness
make check-official-microstructure-readiness \
  OFFICIAL_MICROSTRUCTURE_SYMBOLS=ASIANPAINT,CIPLA,DRREDDY,HCLTECH,HINDALCO,HINDUNILVR,INFY,MAXHEALTH,NESTLEIND,ONGC,SUNPHARMA,TATACONSUM,TCS,TECHM,TMPV,TRENT,ULTRACEMCO
```

5. Run technical validation without v2B first:

```bash
make validate-technical-v2
```

6. Once official readiness checks are sufficient, run v2B validation explicitly:

```bash
TECHNICAL_VALIDATION_INCLUDE_V2B=true make validate-technical-v2
```

7. Inspect:

- `artifacts/technical_validation/<run_id>/validation_manifest.json`
- `artifacts/technical_validation/<run_id>/data_readiness.json`
- `artifacts/technical_validation/<run_id>/technical_agent_predictive_report.md`
- `artifacts/technical_validation/<run_id>/system_backtest_report.md`
- `artifacts/technical_validation/<run_id>/profile_comparison_matrix.csv`
- `artifacts/technical_validation/<run_id>/promotion_gate.json`
- `docs/reports/technical_validation/<run_id>.md`

## Acceptance Checklist For A Future Data-Ingestion Milestone

- Import enough Kite candles for at least standard validation.
- Import `NIFTY_50` benchmark history covering the validation window and warm-up.
- Import `INDIA_VIX` history covering the validation window and warm-up.
- Decide whether sector-relative scoring is in scope. If yes, add
  `sector_index_by_symbol` mappings in `graph_aware_score_v2b.yaml` and import
  the required sector indexes.
- Import delivery data for every validation symbol and validation date.
- Import circuit/price-band data for every validation symbol and validation date.
- Import tradability or implementability data for every validation symbol and
  validation date, explicitly labelled as `official`, `proxy`, or
  `unavailable`.
- Run both official readiness checks and keep their JSON artifacts.
- Run `make validate-technical-v2` for the default v1/v2A gate.
- Run `TECHNICAL_VALIDATION_INCLUDE_V2B=true make validate-technical-v2` only
  after official readiness checks pass.
- Confirm the v2B rows in `validation_manifest.json` are present only in the
  explicit v2B run and have comparable profile runs instead of `not_applicable`
  placeholders.
- Keep v2B opt-in unless the promotion gate has sufficient evidence and a
  separate approved promotion milestone changes defaults.

## Open Decisions

- Which sector-index taxonomy should map validation symbols to sector indexes?
- Which source should be canonical for circuit or price-band history when daily
  archive formats differ from current report formats?
- Is official impact-cost data available for the target universe, or should the
  first milestone use a labelled proxy such as average trade value?
- Should the ingestion worker normalize downloaded NSE files directly, or
  should it first land raw files under a cache directory and transform them into
  importer-ready CSVs?
- Should strong 5-year validation become the target immediately, or should the
  next milestone first unblock standard 3-year validation?
