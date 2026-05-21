import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createTaurusQueryClient } from "./providers";
import { routes } from "./routes";

const overviewPayload = {
  safety: {
    taurus_mode: "paper",
    broker_provider: "paper",
    live_trading_enabled: false,
    alert_provider: "mock",
  },
  latest_account: null,
  latest_run: null,
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
      vi.fn(async () =>
        new Response(JSON.stringify(overviewPayload), {
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
    expect(await screen.findAllByText("Live disabled")).toHaveLength(2);
    expect(screen.getByText("No run data")).toBeInTheDocument();
  });
});
