import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createTaurusQueryClient } from "./providers";
import { routes } from "./routes";

const runSummary = {
  run_id: "pr-test",
  status: "COMPLETED",
  schedule_name: "daily_after_close",
  started_at: "2026-05-21T15:00:00Z",
  completed_at: "2026-05-21T15:01:00Z",
  duration_seconds: 60,
  symbols: ["INFY"],
  succeeded_symbols: ["INFY"],
  failed_symbols: [],
  error_count: 0,
  market_provider: "mock",
  final_status_counts: { APPROVED_FOR_PAPER: 1 },
  order_status_counts: { FILLED: 1 },
};

const safety = {
  taurus_mode: "paper",
  broker_provider: "paper",
  live_trading_enabled: false,
  alert_provider: "mock",
};

const payloads = {
  overview: {
    safety,
    latest_account: null,
    latest_run: runSummary,
    latest_final_decision: null,
    latest_order: null,
    recent_runs: [runSummary],
    positions: [],
    warnings: [],
  },
  run: {
    safety,
    run: runSummary,
    symbols: [
      {
        symbol: "INFY",
        run_id: "pr-test",
        pipeline_status: "complete",
        final_status: "APPROVED_FOR_PAPER",
        final_action: "BUY",
        order_status: "FILLED",
        decision_id: "dec-test",
        stages: [],
        errors: [],
      },
    ],
    market_data_summary: {},
    strategy_summary: {},
    errors: [],
    artifacts: {},
    warnings: [],
  },
  trail: {
    run: runSummary,
    symbol: "INFY",
    company_name: "Infosys",
    decision_id: "dec-test",
    final_status: "APPROVED_FOR_PAPER",
    final_action: "BUY",
    can_send_to_broker: true,
    selected_stage_id: "inputs",
    stages: [],
    warnings: [],
  },
  replay: {
    decision_id: "dec-test",
    run_id: "pr-test",
    symbol: "INFY",
    status: "APPROVED_FOR_PAPER",
    generated_at: "2026-05-21T15:02:00Z",
    note: "test replay",
    stages: [],
  },
  risk: {
    safety,
    latest_risk_reviews: [],
    hard_rule_results: [],
    persona_reviews: [],
    latest_final_decisions: [],
    status_counts: {},
  },
  portfolio: {
    safety,
    latest_account: null,
    positions: [],
    orders: [],
    fills: [],
    summary_metrics: [],
  },
  history: {
    runs: [runSummary],
    status_counts: { COMPLETED: 1 },
    filters_metadata: {},
  },
};

describe("route skeletons", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        const payload =
          url.includes("/ui/runs/pr-test/symbols/INFY/decision-trail")
            ? payloads.trail
            : url.includes("/ui/runs/pr-test")
              ? payloads.run
              : url.includes("/ui/replay/dec-test")
                ? payloads.replay
                : url.includes("/ui/risk")
                  ? payloads.risk
                  : url.includes("/ui/portfolio")
                    ? payloads.portfolio
                    : url.includes("/ui/history")
                      ? payloads.history
                      : payloads.overview;

        return new Response(JSON.stringify(payload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );
  });

  it.each([
    ["/", "Paper Runs"],
    ["/runs/pr-test", "pr-test"],
    ["/runs/pr-test/symbols/INFY", "INFY in pr-test"],
    ["/replay/dec-test", "dec-test"],
    ["/risk", "Risk And Controls"],
    ["/portfolio", "Portfolio And Account"],
    ["/history", "History"],
  ])("renders %s", async (path, heading) => {
    const router = createMemoryRouter(routes, { initialEntries: [path] });
    const queryClient = createTaurusQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: heading })).toBeInTheDocument();
  });
});
