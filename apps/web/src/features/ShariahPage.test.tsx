import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createTaurusQueryClient } from "../app/providers";
import { routes } from "../app/routes";

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

const shariahPayload = {
  rows: [
    {
      name: "Alpha Foods Ltd",
      nse_code: "ALPHA",
      bse_code: "543210",
      industry: "Food",
      compliance_status: "halal",
      active: true,
      first_seen_at: "2026-05-24T09:00:00Z",
      last_seen_at: "2026-05-24T09:00:00Z",
      status_changed_at: "2026-05-24T09:00:00Z",
      details_url: "https://example.test/alpha",
      source_url: "https://example.test/halal-list",
    },
    {
      name: "Beta Finance Ltd",
      nse_code: "BETA",
      bse_code: "654321",
      industry: "Finance",
      compliance_status: "haram",
      active: true,
      first_seen_at: "2026-05-24T09:00:00Z",
      last_seen_at: "2026-05-24T09:00:00Z",
      status_changed_at: "2026-05-24T09:00:00Z",
      details_url: "https://example.test/beta",
      source_url: "https://example.test/halal-list",
    },
  ],
  pagination: { page: 1, page_size: 50, total: 51, total_pages: 2 },
  counts: { active_total: 51, halal: 31, haram: 20 },
  latest_import: {
    import_id: "hsi-test",
    source_url: "https://example.test/halal-list",
    source_checksum: "checksum",
    fetched_at: "2026-05-24T09:00:00Z",
    imported_at: "2026-05-24T09:01:00Z",
    rows_seen: 51,
    rows_imported: 51,
    halal_count: 31,
    haram_count: 20,
    unknown_count: 0,
    duplicate_count: 0,
    generated_yaml_path: "configs/market_data/halal_nse_cash.yaml",
    status: "IMPORTED",
  },
  halal_universe_export: {
    yaml_path: "configs/market_data/halal_nse_cash.yaml",
    universe_name: "halal_nse_cash",
    exported_symbol_count: 31,
    loaded: true,
    error: null,
  },
};

describe("ShariahPage", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes("/ui/shariah")) {
          const parsed = new URL(url);
          const page = Number(parsed.searchParams.get("page") ?? "1");
          return jsonResponse({
            ...shariahPayload,
            pagination: { ...shariahPayload.pagination, page },
          });
        }
        return jsonResponse(overviewPayload);
      }),
    );
  });

  it("renders Shariah rows, filters, badges, and pagination", async () => {
    renderShariah();

    expect(await screen.findByRole("heading", { name: "Shariah" })).toBeInTheDocument();
    expect(await screen.findByText("Active stocks")).toBeInTheDocument();
    expect(screen.getByText("Halal NSE export")).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Search name, NSE symbol, or BSE code")).toBeInTheDocument();
    expect(screen.getByLabelText("Compliance status")).toBeInTheDocument();
    expect(screen.getByText("Alpha Foods Ltd")).toBeInTheDocument();
    expect(screen.getByText("Beta Finance Ltd")).toBeInTheDocument();
    expect(screen.getAllByText("Halal").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Haram").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Next Shariah page" })).toBeEnabled();
    expect(screen.getAllByText("Details").length).toBeGreaterThan(0);
  });

  it("resets to the first page when search changes and requests filters", async () => {
    const user = userEvent.setup();
    renderShariah();

    await screen.findByText("Alpha Foods Ltd");
    await user.click(screen.getByRole("button", { name: "Next Shariah page" }));
    await waitFor(() => expect(fetchUrls()).toContainEqual(expect.stringContaining("page=2")));

    await user.type(screen.getByLabelText("Search Shariah compliance"), "Beta");

    await waitFor(() =>
      expect(fetchUrls()).toContainEqual(
        expect.stringContaining("/ui/shariah?query=Beta&status=all&page=1"),
      ),
    );

    await user.selectOptions(screen.getByLabelText("Compliance status"), "haram");
    await waitFor(() =>
      expect(fetchUrls()).toContainEqual(expect.stringContaining("status=haram&page=1")),
    );
  });
});

function renderShariah() {
  const router = createMemoryRouter(routes, { initialEntries: ["/shariah"] });
  const queryClient = createTaurusQueryClient();

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function jsonResponse(payload: object) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function fetchUrls() {
  const fetchMock = vi.mocked(fetch);
  return fetchMock.mock.calls.map((call) => String(call[0]));
}
