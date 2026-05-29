# Real LLM Provider Migration Plan

Last reviewed: 2026-05-30

Execution order: 2 of 10. Run this after
`DOCKER_ONLY_DATABASE_MIGRATION.md` and before any plan that adds LLM support to
Bull/Bear/Manager/Trader/Portfolio agents. Later LLM-agent migrations should
assume `build_llm_provider(settings)` returns a real provider and defaults to
LM Studio.

## Summary

Remove Taurus's runtime mock LLM provider and make the LLM roster real-provider
only:

- `lmstudio`
- `openai`
- `gemini`

The default runtime provider should be `lmstudio`, because it keeps local paper
runs API-cost-free while still using a real local model server. Hosted providers
remain explicit opt-ins through environment configuration and API keys.

This plan is limited to the LLM provider layer and the Taurus workflows that
currently force `TAURUS_LLM_PROVIDER=mock`. It does not remove market-data,
news, alert, fundamentals, broker, or paper-execution mocks.

## Target State

- `TAURUS_LLM_PROVIDER=lmstudio` is the default.
- Runtime config accepts only `lmstudio`, `openai`, and `gemini`.
- `MockLLMProvider` is deleted from runtime code.
- No Make target or script forces `TAURUS_LLM_PROVIDER=mock`.
- Tests use test-only fake providers or direct deterministic fixtures instead
  of importing a runtime mock LLM provider.
- LLM output remains schema-validated before it is persisted as an analyst
  report.
- LLM provider failures are surfaced clearly. Do not silently label
  deterministic fallback output as if it came from an LLM provider.
- Runtime services that need an LLM must build or receive a provider from
  `build_llm_provider(settings)`. Optional constructor injection is allowed for
  tests, but production wiring must provide the default LM Studio-backed
  provider unless a hosted provider is explicitly configured.

## ChatGPT Subscription And OpenAI OAuth Decision

Do not implement OpenAI inference through a ChatGPT subscription or ChatGPT
OAuth flow.

Reasoning:

- ChatGPT subscription billing and OpenAI API billing are separate products.
  A ChatGPT Plus/Pro/Team subscription does not include API usage.
- Programmatic OpenAI model inference should use the OpenAI API with API-key
  bearer authentication.
- OAuth can be relevant when ChatGPT connects to an external app, for example
  in GPT Actions or app integrations, but it is not a supported way for this
  Taurus backend to consume ChatGPT subscription model usage for inference.

Implementation consequence:

- `OpenAIProvider` must require `OPENAI_API_KEY`.
- Do not add browser automation, cookie reuse, ChatGPT session scraping, or
  subscription-backed inference workarounds.
- Keep API spend controllable by making the OpenAI model configurable through
  `TAURUS_LLM_MODEL` and documenting lower-cost model selection.

Official references to check during implementation:

- OpenAI API authentication:
  <https://platform.openai.com/docs/api-reference/introduction>
- ChatGPT subscriptions vs API billing:
  <https://help.openai.com/en/articles/8156019-is-api-usage-included-in-chatgpt-subscriptions-even-if-i-have-a-paid-chatgpt-account>
- ChatGPT billing vs API Platform billing:
  <https://help.openai.com/en/articles/9039756-billing-settings-in-chatgpt-vs-platform>
- OpenAI model list and model-selection guidance:
  <https://developers.openai.com/api/docs/models>

## Implementation Changes

### Configuration

- Change `Settings.taurus_llm_provider` default from `mock` to `lmstudio`.
- Restrict LLM provider validation to:
  - `lmstudio`
  - `openai`
  - `gemini`
- Add or formalize these settings:
  - `TAURUS_LLM_PROVIDER`
  - `TAURUS_LLM_BASE_URL`
  - `TAURUS_LLM_MODEL`
  - `TAURUS_LLM_TIMEOUT_SECONDS`
  - `OPENAI_API_KEY`
  - `GEMINI_API_KEY`
- Redact `gemini_api_key` in `Settings.safe_dict()`.
- Keep hosted-provider credential validation at provider construction or
  request time, not global settings-load time, so unrelated commands can still
  initialize settings without hosted credentials.
- Update `.env.example`:
  - `TAURUS_LLM_PROVIDER=lmstudio`
  - `TAURUS_LLM_BASE_URL=http://localhost:1234/v1`
  - `TAURUS_LLM_MODEL=`
  - `TAURUS_LLM_TIMEOUT_SECONDS=20`
  - `OPENAI_API_KEY=`
  - `GEMINI_API_KEY=`

### Provider Factory And Exports

- Remove `MockLLMProvider` from `packages/taurus_core/llm/__init__.py`.
- Delete `packages/taurus_core/llm/mock_provider.py`.
- Change `build_llm_provider(settings)` so it supports only:
  - `lmstudio`
  - `openai`
  - `gemini`
- Unsupported provider errors should say:
  - provider name received;
  - supported providers;
  - example env values.
- Preserve `LLMProvider` protocol and `LLMProviderError`.

### LM Studio Provider

- Keep LM Studio as the default local provider.
- Continue using the OpenAI-compatible chat completions endpoint:
  - default base URL: `http://localhost:1234/v1`
  - default model: use `TAURUS_LLM_MODEL` if set, otherwise `local-model`
- Keep temperature `0`.
- Keep schema instructions strict:
  - return JSON only;
  - conform to `LLMAnalystOutput`;
  - no prose outside JSON.
- On connection failure, timeout, invalid JSON, or schema validation failure,
  raise `LLMProviderError` with a concise provider-specific message.

### OpenAI Provider

- Keep `OpenAIProvider` API-key based.
- Default base URL: `https://api.openai.com/v1`.
- Require `OPENAI_API_KEY` when `TAURUS_LLM_PROVIDER=openai`.
- Use `TAURUS_LLM_MODEL` for model selection.
- If a default OpenAI model is retained, choose a current cost-balanced model
  during implementation after checking official OpenAI model docs. Do not hard
  code a speculative model ID without verifying availability.
- Prefer structured JSON output where the selected OpenAI API/model supports it.
- Fall back to strict JSON-only prompting only if the selected OpenAI endpoint
  does not support structured output.
- Keep temperature `0`.

### Gemini Provider

- Add `packages/taurus_core/llm/gemini_provider.py`.
- Require `GEMINI_API_KEY` when `TAURUS_LLM_PROVIDER=gemini`.
- Use `TAURUS_LLM_MODEL` for model selection.
- If a default Gemini model is retained, choose a current cost-balanced Gemini
  model during implementation after checking official Gemini API docs.
- Use Gemini's native REST API or official SDK, not a mock-compatible shim.
- Prefer Gemini structured JSON output with a schema equivalent to
  `LLMAnalystOutput`.
- Keep temperature `0`.
- Map provider/API errors to `LLMProviderError`.

Official Gemini references to check during implementation:

- Gemini API structured output:
  <https://ai.google.dev/gemini-api/docs/structured-output>
- Gemini API OpenAI compatibility, only if choosing an OpenAI-compatible Gemini
  route instead of native Gemini REST:
  <https://ai.google.dev/gemini-api/docs/openai>

### Analyst Fallback Semantics

Current `BaseAnalystAgent._build_report()` catches any provider exception and
persists deterministic fallback output with `+llm_fallback`.

For a real-provider-only LLM migration, change this behavior:

- Provider failures should not be presented as successful LLM-backed analyst
  reports.
- Preferred behavior:
  - record `taurus_llm_failures_total`;
  - raise a clear workflow error;
  - let the script/API command fail fast.
- If a later product decision wants deterministic analyst reports without any
  LLM, implement that as a separate explicit rule-only analyst mode, not as an
  LLM provider mock or hidden fallback.
- Keep `GraphAnalystAgent` deterministic because it does not require an LLM.

### Scripts And Make Targets

- Remove forced `TAURUS_LLM_PROVIDER=mock` from LLM-related Make targets:
  - `run-analysts-mock`
  - `debate-mock`
  - `trader-proposal-mock`
  - `risk-review-mock`
  - `final-approval-mock`
  - `paper-once-mock`
  - `paper-loop-mock`
  - `paper-loop-once`
  - `paper-loop-start`
  - `paper-loop-kite`
  - `taurus-smoke`
- Rename LLM-related targets where appropriate so names no longer imply mock
  LLM usage. Existing market-data mock target names may remain if the target
  still uses mock market data.
- Keep `make llm-smoke`, but make it smoke the configured real provider.
- Update `scripts/llm_smoke.py` output to include:
  - selected provider;
  - model version;
  - validated analyst output.
- Do not add an automatic hosted-provider smoke in normal `make test`; tests
  must not require real API credentials.

### Observability

- Keep `taurus_llm_provider_info`.
- Make its `model_version` label use the provider's actual model version if
  available, not just `settings.taurus_llm_provider`.
- Keep `taurus_llm_failures_total`.
- Update its description if fallback behavior is removed. It should track real
  provider failures, not "failures that used deterministic fallback output."

### API And React Dashboard

- Expose the configured LLM provider and model version through an existing
  status/health/config endpoint or a narrow new read-only endpoint.
- Update the React dashboard overview/status surfaces to show:
  - LLM provider name
  - model name/version when known
  - last LLM failure count or degraded status if exposed by the API
- Do not create a separate LLM page for this migration.
- Dashboard labels must not mention `mock` as an active LLM provider after this
  migration. Historical records with `mock-llm-v1` may still appear as old run
  artifacts.

### Documentation

Update these docs after implementation:

- `.env.example`
- `README.md`
- `docs/TAURUS_USAGE_GUIDE.md`
- `docs/TAURUS_COMMANDS.md`
- `docs/TAURUS_MILESTONE_TODO.md`
- `docs/TAURUS_MOCK_MIGRATION_STATUS.md`
- `scripts/README.md`

Required documentation changes:

- LLM provider default is `lmstudio`.
- Supported LLM providers are `lmstudio`, `openai`, and `gemini`.
- OpenAI requires API billing through `OPENAI_API_KEY`; ChatGPT subscription
  usage is not supported for Taurus backend inference.
- Gemini requires `GEMINI_API_KEY`.
- LM Studio requires a compatible local server running before LLM workflows.
- Test-only fake providers are allowed, but runtime mock LLM is removed.

## Test Plan

### Unit Tests

- Replace every test import of `MockLLMProvider` with a test-local fake provider.
- Add tests for `build_llm_provider()`:
  - default returns `LMStudioProvider`;
  - `lmstudio` builds with default base URL/model;
  - `openai` builds or fails clearly based on `OPENAI_API_KEY`;
  - `gemini` builds or fails clearly based on `GEMINI_API_KEY`;
  - `mock` is rejected.
- Update config tests:
  - default `taurus_llm_provider == "lmstudio"`;
  - `TAURUS_LLM_PROVIDER=mock` fails validation;
  - `TAURUS_LLM_PROVIDER=gemini` is accepted;
  - `GEMINI_API_KEY` is redacted.
- Add provider request-shape tests without live network calls:
  - LM Studio/OpenAI-compatible payload includes model, strict schema prompt,
    symbol, agent name, context, and temperature `0`.
  - OpenAI provider includes bearer auth and rejects missing API key.
  - Gemini provider includes API key handling, model path, strict JSON/schema
    configuration, symbol, agent name, context, and temperature `0`.
- Update analyst failure tests:
  - provider failure records the metric;
  - workflow raises a clear error instead of persisting `+llm_fallback` output.
- Keep graph analyst tests deterministic with a test fake provider if the runner
  requires an `LLMProvider` argument.

### Integration And Smoke

- Required verification:
  - `make test`
  - `make lint`
- Optional local real-provider smoke:
  - start LM Studio local server;
  - configure a local model;
  - run `make llm-smoke`.
- Optional hosted-provider smoke:
  - `TAURUS_LLM_PROVIDER=openai OPENAI_API_KEY=... TAURUS_LLM_MODEL=... make llm-smoke`
  - `TAURUS_LLM_PROVIDER=gemini GEMINI_API_KEY=... TAURUS_LLM_MODEL=... make llm-smoke`
- Hosted smoke commands should not be required for normal CI or local unit
  tests because they incur cost and require credentials.

## Rollout Notes

- This is a breaking runtime change for users relying on
  `TAURUS_LLM_PROVIDER=mock`.
- Local workflows will require LM Studio to be running unless the user selects a
  hosted provider.
- Existing local databases do not require migration for this LLM-only change.
- Existing analyst reports with `model_version=mock-llm-v1` can remain as
  historical records, but new runtime reports must not use mock LLM versions.

## Assumptions And Constraints

- User preference: delete all runtime mock LLM code.
- User preference: default provider is LM Studio.
- User preference: OpenAI default should be cost-balanced if a default model is
  chosen.
- Test-only fake providers are allowed and are not runtime mocks.
- This plan does not remove mock market data, mock news, mock alerts, or mock
  fundamentals fallbacks.
- This plan does not add live trading or broker order routing.
- This plan does not use ChatGPT subscription sessions, browser automation, or
  OAuth to avoid API billing.
- Dedicated system prompts for LLM agents should live with each agent migration
  plan. Existing analyst prompts that are not otherwise migrated are tracked in
  `docs/agent_improvement_plans/LLM_AGENT_SYSTEM_PROMPTS_BACKLOG.md`.

## Completion Summary Template

When this plan is implemented, include this section in the milestone completion
summary:

- Assumptions made:
  - List implementation-time model defaults and provider-doc versions checked.
- Mocks created:
  - List test-only fakes, or `None`.
- Mocks used:
  - List test-only fakes used during verification, or `None`.

At milestone completion and cleanup, inspect
`/Users/adnaan/.codex/rules/default.rules`. Treat entries after the user's
`# END MY CUSTOM ADDITION` marker as accidental global approvals. Any
Taurus-specific approved prefixes found after that marker must be copied into
`.codex/rules/default.rules` if missing, documented in
`docs/TAURUS_COMMANDS.md`, and removed from the global rules file. Do not copy
unrelated global approvals into this project.
