# Taurus Multi-Profile Paper Trading Plan

Last updated: 2026-06-07

This document is the implementation plan for making Taurus support multiple
paper-trading profiles, where each profile represents one client/account with
its own corpus, run history, orders, fills, positions, account snapshots, and
P&L. Each milestone below is a standalone milestone intended to be executed in
a separate Codex thread. Stop after completing and documenting the current
milestone; do not automatically continue to the next milestone.

## Target Behavior

Taurus should support multiple logical profiles inside one local Taurus stack:

```text
Profile: local-paper
  Starting corpus: INR 10,000
  Own paper runs, account, positions, orders, fills, proposals, risk, and P&L

Profile: client-a
  Starting corpus: operator-defined
  Own paper runs, account, positions, orders, fills, proposals, risk, and P&L

Shared platform data:
  Instruments, daily candles, market-data imports, Shariah/compliance data,
  graph data, fundamentals, Kite credentials, LLM provider settings, and UI app.
```

The first implementation is logical profile isolation, not one Postgres database
or one Docker stack per client. Physical database/stack isolation remains
deferred until there is an explicit approved milestone for that harder
operational model.

## Existing Foundation

- `Settings.taurus_paper_portfolio_id` already exists and is backed by
  `TAURUS_PAPER_PORTFOLIO_ID`.
- `paper_accounts`, `paper_orders`, `paper_fills`, `paper_positions`, and
  `trader_proposals` already store `portfolio_id`.
- `paper_runs` does not currently store `portfolio_id`, so run history can
  still bleed across clients unless it is made profile-scoped.
- `RiskReview` and `FinalDecision` payloads do not currently include profile
  identity. They are run-scoped today, so profile-safe run identity must be
  added before list endpoints can be filtered safely.
- `PaperBroker._rebuild_state_from_fills()` currently derives starting cash from
  `TAURUS_INITIAL_CAPITAL_INR`; profile corpus must replace that path for paper
  execution.
- The React app is mostly a thin client over `/ui/*`, so profile support should
  primarily flow through API query parameters and query keys.

## Global Rules For M51-M55

- Keep Taurus paper-only. Do not add live Kite/broker order routing.
- Keep `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` as defaults.
- Use flat milestone IDs. Do not create submilestones.
- Use existing SQLAlchemy metadata plus idempotent helpers in `scripts/migrate.py`;
  Taurus does not use Alembic.
- Preserve backward compatibility for existing `local-paper` data.
- Treat `portfolio_id` as the persisted database field for v1, but expose it to
  operators as `profile_id` where user-facing naming is new.
- Keep market/reference data shared in v1: instruments, candles, Shariah data,
  graph data, fundamentals, Kite tokens, and LLM settings are platform-level.
- Run exactly one profile per paper-loop invocation in v1. All-active-profile
  batch scheduling is deferred.
- Corpus means starting capital. Deposits, withdrawals, and historical capital
  event ledgers are deferred.
- Any API payload or dashboard behavior change must include matching React type,
  client, UI, and test updates in the same milestone.
- At milestone completion, run the stated verification commands and include a
  completion summary with assumptions made, mocks created, and mocks used. Use
  `None` for empty categories.
- At milestone cleanup, inspect `/Users/adnaan/.codex/rules/default.rules` and
  follow the repo's global approval cleanup rule from
  `docs/MILESTONE.md`.

## M51 - Profile Catalog, Config Alias, And CLI Creation

Purpose: make profiles first-class persistent records while preserving the
current `local-paper` behavior.

Instructions:

- Add a profile schema/model, preferably in the shared DB/model layer:
  - table name: `taurus_profiles`
  - primary key: `profile_id`
  - fields: `display_name`, `starting_corpus_inr`, `currency`, `status`,
    `description`, `profile_metadata`, `created_at`, `updated_at`
  - allowed statuses: `ACTIVE`, `ARCHIVED`
  - default profile: `local-paper`, display name `Local Paper`, corpus INR
    `10_000`, currency `INR`, status `ACTIVE`
- Add Pydantic schemas for profile create/update/response. Keep validation
  deterministic:
  - `profile_id`: lowercase slug characters only (`a-z`, `0-9`, `-`, `_`),
    1-64 characters
  - `starting_corpus_inr`: positive Decimal or int, stored to money precision
  - `display_name`: non-empty
- Add a repository/service for profile lifecycle:
  - `ensure_default_profile()`
  - `get_profile(profile_id)`
  - `list_profiles(include_archived=False)`
  - `create_profile(...)`
  - `archive_profile(profile_id)`
  - `update_profile_corpus(profile_id, starting_corpus_inr)`
- Guard corpus updates:
  - allow corpus changes only while the profile has no fills and no account
    snapshots beyond the initial/backfilled state
  - reject changes after trading activity exists, with a clear error that
    deposits/withdrawals need a later capital-events milestone
- Extend settings:
  - add preferred alias `TAURUS_PROFILE_ID`
  - keep `TAURUS_PAPER_PORTFOLIO_ID` as a backward-compatible alias
  - if both are set and differ, fail fast with a clear validation error
  - expose a helper/property that returns the effective profile ID
- Update migrations:
  - create `taurus_profiles`
  - seed/backfill `local-paper`
  - do not mutate trading behavior yet
- Add a small profile management CLI script and Make wrappers:
  - `scripts/manage_profiles.py list`
  - `scripts/manage_profiles.py create --profile-id client-a --display-name "Client A" --corpus-inr 250000`
  - `scripts/manage_profiles.py archive --profile-id client-a`
  - `scripts/manage_profiles.py update-corpus --profile-id client-a --corpus-inr 500000`
  - Make targets should pass `DATABASE_URL` and use `uv run`, matching existing
    repo command style.
- Update docs:
  - `.env.example` should show `TAURUS_PROFILE_ID=local-paper` and keep a note
    that `TAURUS_PAPER_PORTFOLIO_ID` is the legacy alias.
  - `docs/TAURUS_DATABASE_TABLES.md` should describe `taurus_profiles`.
  - `docs/TAURUS_COMMANDS.md` should list profile management commands.

Expected code shape:

- Runtime paper loops should still behave exactly as before after this
  milestone, except settings can now resolve `TAURUS_PROFILE_ID`.
- Avoid API/dashboard work in this milestone unless needed for tests.
- Do not add per-profile run filtering yet; that follows in M52/M54.

Acceptance criteria:

- `make migrate` creates the profile table and seeds `local-paper`.
- Existing tests that rely on `local-paper` keep passing.
- Operators can create/list/archive profiles from CLI/Make.
- Corpus updates are rejected once there is existing trading activity.

Verification:

```bash
uv run pytest tests/unit/test_config.py tests/unit/test_migrations.py -q
uv run pytest tests/unit/test_profile_management.py -q
make lint
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M52 - Run And Agent Artifact Profile Lineage

Purpose: make every paper run and run-derived agent artifact carry profile
identity so profile history cannot bleed across clients.

Instructions:

- Extend paper run schemas and models:
  - add `portfolio_id`/profile identity to `PaperRun`
  - add `portfolio_id` column to `paper_runs`
  - add indexes for `(portfolio_id, started_at)` and `(portfolio_id, status)`
  - backfill existing rows to `local-paper`
  - include profile identity in `PaperRun.payload`
- Update `paper_run_id()`:
  - include profile ID in the stable ID input
  - preserve legacy reads for existing runs, but new runs must be profile-aware
- Add profile lineage to run-derived agent tables and payloads that appear in
  profile-scoped lists:
  - `analyst_reports`
  - `debate_reports`
  - `risk_reviews`
  - `final_decisions`
  - keep existing `trader_proposals.portfolio_id`
- Add idempotent migration helpers for the new columns and indexes:
  - default/backfill to `local-paper`
  - keep existing unique constraints on `(run_id, symbol)` because new run IDs
    include the profile
- Update repositories:
  - `PaperRunRepository.list(profile_id=...)`
  - `ResearchRepository` list methods should accept profile filters where
    their tables now carry profile identity
  - `RiskRepository.list_risk_reviews()` and `list_final_decisions()` should
    accept profile filters
  - run-specific detail methods may keep using `run_id`, but should not drop
    profile identity from payloads
- Update the pipeline writers:
  - `PaperRunService` stores the effective profile on every run
  - analyst, debate, risk, and final-decision persistence includes the same
    profile ID as the run
  - audit log payloads for paper run start/completion include profile ID
- Update exact artifact-key tests if new run payload fields affect top-level
  artifacts or API response assertions.

Expected code shape:

- This milestone should not yet redesign the dashboard. The main goal is
  persisted lineage and repository-level filtering.
- Existing `/runs` behavior may keep defaulting to all rows until M54, but new
  repository tests must prove profile filters work.
- Keep old payloads readable by defaulting missing profile identity to
  `local-paper`.

Acceptance criteria:

- New paper runs persist profile identity in `paper_runs` and payloads.
- Run-derived agent artifacts for the same run carry the same profile ID.
- Repository list filters can return only one profile's runs and decisions.
- Legacy rows without explicit profile identity still load as `local-paper`.

Verification:

```bash
uv run pytest tests/unit/test_paper_runs.py tests/unit/test_ui_aggregate_api.py -q
uv run pytest tests/unit/test_research_debate.py tests/unit/test_risk_approval.py -q
make lint
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M53 - Corpus-Aware Paper Execution Isolation

Purpose: make selected profiles drive starting cash and paper execution state,
so each client has independent corpus, positions, cash, settlement, and P&L.

Instructions:

- Add a profile resolver used by runtime services:
  - load the effective profile at paper-loop startup
  - reject missing or archived profiles before migrations/expensive work
  - include profile ID and starting corpus in setup/progress output
- Update `PaperBroker` state rebuild:
  - starting cash comes from the profile's `starting_corpus_inr`
  - do not use `TAURUS_INITIAL_CAPITAL_INR` for profile-backed paper execution
  - keep `TAURUS_INITIAL_CAPITAL_INR` as a legacy fallback only for tests or
    explicit non-profile contexts, if needed
- Ensure all existing profile-aware execution paths use the selected profile:
  - `PaperRunService`
  - `PaperBroker.place_order()`
  - `PaperBroker.settle_pending_next_open_orders()`
  - `ExecutionRepository.latest_account_by_portfolio()`
  - `TraderAgent` current portfolio context
  - `PortfolioManagerAgent` paper profile context
  - `RiskEngine` and allocation code that reads current account/positions
  - `PositionMonitorService`
- Preserve next-open semantics:
  - pending orders settle only for the selected profile
  - terminal settlement rows and account snapshots keep that profile ID
  - same-run replacement cleanup must not delete another profile's state
- Update Make/run command behavior:
  - `PROFILE_ID=client-a make paper-loop-kite` should set
    `TAURUS_PROFILE_ID=client-a`
  - existing `make paper-loop-kite` should continue using `local-paper`
  - document the legacy `TAURUS_PAPER_PORTFOLIO_ID` override as supported but
    secondary
- Update LLM usage/run artifacts:
  - include profile ID in run artifacts or operator summaries where useful
  - do not include client-sensitive display names in logs unless already
    operator-visible

Expected code shape:

- No UI selector yet; operators should be able to run different profiles from
  commands and validate through API/DB inspection.
- Avoid all-active-profile batch scheduling.
- Keep paper execution long-only/equity-only under existing money-management
  and universe rules.

Acceptance criteria:

- Two profiles with different corpus values produce different starting cash and
  independent account snapshots.
- Buying/selling in one profile does not change the other profile's account,
  positions, pending orders, settlement, or P&L.
- Position monitor only watches the selected profile.
- `local-paper` remains the default when no profile override is set.

Verification:

```bash
uv run pytest tests/unit/test_paper_broker.py tests/unit/test_paper_runs.py -q
uv run pytest tests/unit/test_position_monitor.py tests/unit/test_run_level_allocation.py -q
make lint
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M54 - Profile APIs And React Profile Selector

Purpose: expose profiles to operators through stable APIs and make the React
dashboard profile-scoped by default.

Instructions:

- Add FastAPI profile endpoints:
  - `GET /profiles`
  - `POST /profiles`
  - `GET /profiles/{profile_id}`
  - `PATCH /profiles/{profile_id}`
  - `POST /profiles/{profile_id}/archive`
  - keep validation and error messages aligned with the M51 CLI
- Add optional `profile_id` query parameters:
  - `/runs`
  - `/paper/orders`
  - `/paper/fills`
  - `/paper/positions`
  - `/paper/account`
  - `/ui/overview`
  - `/ui/history`
  - `/ui/portfolio`
  - `/ui/risk`
  - research/risk list endpoints where profile-scoped rows are exposed
- Query-parameter rules:
  - if omitted, default to effective settings profile
  - if supplied and profile is missing or archived, return a clear 404/422
  - run detail endpoints should derive profile from the stored run; if a
    mismatched `profile_id` is supplied, return 404
  - profile-specific list endpoints must not return all profiles by accident
- Extend UI response models:
  - include `active_profile`
  - include available profile summaries where the dashboard needs selector data
  - keep `portfolio_id` in raw paper payloads for backward compatibility
- Update React:
  - add a compact profile selector in `AppShell`
  - persist selected profile in URL search params or local storage; prefer URL
    params when practical so copied links keep context
  - include selected profile in React Query keys
  - pass `profile_id` to overview, history, risk, portfolio, and paper views
  - show selected profile display name and starting corpus in a small header or
    selector state
  - keep Graph and Shariah pages clearly platform-level/shared
- Update TypeScript API types/client methods to include profile inputs and
  profile response types.
- Add UI states:
  - no profiles beyond default
  - selected profile has no account yet
  - archived/missing profile from stale URL or local storage

Expected code shape:

- Do not build full dashboard CRUD in React in this milestone. Profile creation
  remains API/CLI from M51; the dashboard selector is read-only.
- Keep the UI dense and operational. Avoid a new marketing/landing page.
- Keep old API consumers working by defaulting omitted profile filters.

Acceptance criteria:

- The dashboard can switch between at least two profiles without data mixing.
- Overview, Portfolio, History, and Risk all reflect the selected profile.
- Run detail and decision trail remain stable for links.
- Shared pages are still available and not misleadingly profile-specific.

Verification:

```bash
uv run pytest tests/unit/test_ui_aggregate_api.py tests/unit/test_paper_broker.py -q
make test-ui
make build-ui
```

Browser smoke:

```bash
make api
make ui
```

Then open the React dashboard, switch between two profiles, and confirm account,
positions, history, orders, fills, risk, and latest-run cards change together.

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## M55 - Multi-Profile Regression, Docs, And Cleanup

Purpose: close the profile sequence with deterministic regression coverage,
operator documentation, and repo cleanup.

Instructions:

- Add an end-to-end deterministic test scenario:
  - create `local-paper` and `client-a`
  - give them different starting corpus values
  - create/run or seed BUY/settlement flows for both profiles
  - verify independent cash, positions, pending orders, filled orders, realized
    P&L, unrealized P&L, run history, latest decisions, and dashboard payloads
  - verify a stale/mismatched profile filter does not leak data
- Add an operator smoke script or extend `scripts/taurus_smoke.py`:
  - create a temporary profile
  - run a bounded paper loop for that profile
  - inspect `/profiles`, `/paper/account`, `/paper/orders`, `/ui/overview`,
    `/ui/history`, and `/ui/portfolio` with `profile_id`
  - leave shared market-data setup unchanged
- Update docs:
  - `README.md`: concise multi-profile quickstart
  - `docs/TAURUS_USAGE_GUIDE.md`: profile workflow, command examples,
    dashboard selector semantics, and limitations
  - `docs/TAURUS_COMMANDS.md`: profile management and run commands
  - `docs/TAURUS_DATABASE_TABLES.md`: final table descriptions and profile
    scoping notes
  - `docs/TAURUS_AGENT_ARCHITECTURE.md`: profile boundary and shared/global
    data boundary
  - `docs/TAURUS_MOCK_MIGRATION_STATUS.md`: note any new test fakes or confirm
    none were added
- Run final regression:
  - backend tests
  - UI tests/build
  - browser smoke
  - optional focused API curl checks for two profile IDs
- Perform milestone cleanup:
  - update `docs/MILESTONE.md` completion summaries for M51-M55
  - inspect `/Users/adnaan/.codex/rules/default.rules`
  - move any Taurus-specific accidental global approvals into
    `.codex/rules/default.rules` and document them in `docs/TAURUS_COMMANDS.md`
  - do not copy unrelated global approvals

Expected code shape:

- This milestone should mostly test, document, and tighten behavior. Avoid new
  feature work unless required to close a concrete regression gap.
- If a physical database-per-client option is still desired, document it as
  deferred work rather than starting it here.

Acceptance criteria:

- Multi-profile support is documented and reproducible from a clean local setup.
- The deterministic regression proves two profiles do not mix account state or
  dashboard data.
- All planned M51-M55 milestone summaries are present with assumptions made,
  mocks created, and mocks used.
- The plan can be moved out of Active Sources after implementation completes,
  following repo maintenance rules.

Verification:

```bash
make test
make test-ui
make build-ui
make lint
```

Completion summary requirements:

- Assumptions made
- Mocks created
- Mocks used

## Deferred Work

- Physical isolation per client through separate Postgres databases, schemas, or
  full Docker stacks.
- Running all active profiles automatically in one scheduler/batch command.
- Dashboard profile CRUD.
- Deposits, withdrawals, fees outside paper fills, and a capital-events ledger.
- Per-profile Kite credentials, LLM providers, alert destinations, or custom
  universes.
- Authentication/authorization for dashboard use beyond a trusted local machine.
- Live broker order routing. This remains out of scope.
