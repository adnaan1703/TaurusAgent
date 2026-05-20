# Upstox Integration Plan

Status: Deferred until after the Taurus paper-trading MVP release.

Purpose: add broker connectivity in controlled phases without blocking the current paper-trading MVP. Taurus remains paper-trading-first; `PaperBroker` stays the default execution path until a later explicit approval.

## Phase 0 - Preconditions

- Complete the paper-trading MVP release milestone.
- Keep `LIVE_TRADING_ENABLED=false` and `BROKER_PROVIDER=paper` as defaults.
- Confirm the production broker path is still needed after extended paper trading.
- Re-check current Upstox API documentation before implementation, because sandbox and auth flows can change.

## Phase 1 - Upstox Sandbox Adapter

Goal: validate Taurus order payloads against Upstox Sandbox without real-money execution.

Inputs:

- `UPSTOX_SANDBOX_ACCESS_TOKEN`, supplied through local `.env` or shell environment only.
- Sandbox app/account setup in the Upstox Developer Console.

Implementation:

- Add `UpstoxSandboxBroker` as a separate adapter from `PaperBroker`.
- Use the sandbox access token for sandbox order APIs; do not require OAuth client id/secret/redirect URI at runtime unless Upstox documentation requires it.
- Map approved Taurus paper decisions into Upstox sandbox order payloads.
- Add a sandbox smoke command such as `make broker-sandbox-smoke` that places a tiny sandbox order and cancels it when supported.
- Store structured logs for request IDs, response status, broker order IDs, and sanitized errors.
- Add mocked HTTP tests so the suite passes without credentials.

Acceptance:

- Missing sandbox token fails clearly for the smoke command but does not break normal tests.
- Mocked adapter tests pass without external credentials.
- Sandbox smoke passes when a valid token is provided.
- Paper trading remains unaffected and default.
- No live broker endpoint or production credential is used.

## Phase 2 - Production Readiness Gate

Goal: add safety checks before any production broker path can be considered.

Inputs:

- Explicit manual approval.
- Broker account/compliance details.
- Production Upstox app credentials and token process, supplied locally only.

Implementation:

- Add a live-readiness command that checks broker config, risk config, order tags, kill switch, audit logging, reconciliation readiness, dashboard health, and alerting.
- Require an uncommitted local sign-off file or explicit runtime sign-off flag.
- Add order tagging placeholders and reconciliation interfaces.
- Add tests proving default config blocks production broker use.

Acceptance:

- `LIVE_TRADING_ENABLED=false` remains default.
- Failed preflight blocks production broker routing.
- Missing manual sign-off blocks production broker routing.
- No production orders are placed in this phase.

## Phase 3 - Production Broker Adapter

Goal: implement production Upstox routing only after sandbox and readiness gates pass.

Implementation:

- Add a production Upstox adapter separate from sandbox.
- Require explicit provider selection, live flag, preflight pass, manual sign-off, and kill-switch availability.
- Start with a non-ordering connectivity/account-read smoke test before any order capability.
- Add dry-run order rendering before any live order path is enabled.

Acceptance:

- Production connectivity can be verified without placing orders.
- Live order routing remains unavailable until a separate explicit approval milestone.
- Secrets are never committed or logged.

## Current MVP Decision

Upstox integration is not part of the active MVP path. The next active milestone focuses entirely on observable paper trading, data import, replay, backup, dashboard visibility, and documentation.
