import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createTaurusQueryClient } from "./providers";
import { routes } from "./routes";

const profile = {
  profile_id: "local-paper",
  display_name: "Local Paper",
  starting_corpus_inr: "10000.0000",
  currency: "INR",
  status: "ACTIVE",
  description: "",
  profile_metadata: {},
  created_at: "2026-06-10T00:00:00Z",
  updated_at: "2026-06-10T00:00:00Z",
};

const overviewPayload = {
  active_profile: profile,
  available_profiles: [profile],
  safety: {
    taurus_mode: "paper",
    broker_provider: "paper",
    live_trading_enabled: false,
    llm_provider: "lmstudio",
    llm_model_version: "lmstudio:local-model",
    llm_failure_count: 0,
    alert_provider: "mock",
  },
  monitor_status: {
    enabled: false,
    provider: "kite",
    trigger_count_today: 0,
  },
  allocation: { enabled: false, config_path: "configs/portfolio/money_management_v1.yaml" },
  latest_account: null,
  latest_run: null,
  latest_trader_proposal: null,
  latest_final_decision: null,
  latest_order: null,
  recent_runs: [],
  positions: [],
  warnings: [],
};

describe("AppShell", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) =>
        new Response(JSON.stringify(String(input).includes("/profiles") ? [profile] : overviewPayload), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );
  });

  it("renders navigation, safety status, and overview route", async () => {
    const router = createMemoryRouter(routes, { initialEntries: ["/"] });
    const queryClient = createTaurusQueryClient();

    render(
      <QueryClientProvider client={queryClient}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Paper Runs" })).toBeInTheDocument();
    expect(screen.getAllByText("Overview")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Shariah")[0]).toBeInTheDocument();
    expect(screen.getAllByText("Graph")[0]).toBeInTheDocument();
    expect(await screen.findAllByText("Live disabled")).toHaveLength(2);
    expect(screen.getByText("No run data")).toBeInTheDocument();
  });
});
