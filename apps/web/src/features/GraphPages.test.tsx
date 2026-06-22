import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { createTaurusQueryClient } from "../app/providers";
import { routes } from "../app/routes";

vi.mock("reagraph", async () => {
  const React = await import("react");

  const GraphCanvas = React.forwardRef(
    (
      {
        edges = [],
        nodes = [],
        onEdgeClick,
        onNodeClick,
      }: {
        edges?: Array<{ id: string; label?: string; data?: object }>;
        nodes?: Array<{ id: string; label?: string; data?: object }>;
        onEdgeClick?: (edge: { id: string; data?: object }) => void;
        onNodeClick?: (node: { id: string; data?: object }) => void;
      },
      ref,
    ) => {
      React.useImperativeHandle(ref, () => ({
        centerGraph: () => undefined,
        exportCanvas: () => "",
        fitNodesInView: () => undefined,
        getControls: () => ({}),
        getGraph: () => ({}),
        renderScene: () => undefined,
        resetControls: () => undefined,
        zoomIn: () => undefined,
        zoomOut: () => undefined,
      }));

      return (
        <div aria-label="Graph explorer canvas" role="img">
          {nodes.map((node) => (
            <button
              key={node.id}
              onClick={() => onNodeClick?.({ id: node.id, data: node.data })}
              type="button"
            >
              {node.label}
            </button>
          ))}
          {edges.map((edge) => (
            <button
              aria-label={`Select edge ${edge.label ?? edge.id}`}
              key={edge.id}
              onClick={() => onEdgeClick?.({ id: edge.id, data: edge.data })}
              type="button"
            >
              {edge.label ?? edge.id}
            </button>
          ))}
        </div>
      );
    },
  );
  GraphCanvas.displayName = "MockReagraphCanvas";

  return {
    GraphCanvas,
    darkTheme: {
      canvas: {},
    },
  };
});

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

const graphOverviewPayload = {
  graph_enabled: true,
  graph_risk_enabled: false,
  graph_auto_promote_edges: false,
  neo4j_enabled: false,
  generated_at: "2026-05-27T09:15:00Z",
  counts: {
    nodes: 3,
    edges: 2,
    active_edges: 1,
    candidate_edges: 1,
    edge_evidence: 1,
    edge_stats: 1,
    signals: 1,
    signal_contributions: 1,
  },
};

const emptyGraphOverviewPayload = {
  ...graphOverviewPayload,
  counts: {
    nodes: 0,
    edges: 0,
    active_edges: 0,
    candidate_edges: 0,
    edge_evidence: 0,
    edge_stats: 0,
    signals: 0,
    signal_contributions: 0,
  },
};

const candidateEdge = {
  id: 2,
  edge_key: "ge-candidate-infy-tcs-peer",
  source_node_id: 1,
  source_node_key: "company:INFY",
  source_display_name: "Infosys Limited",
  target_node_id: 2,
  target_node_key: "company:TCS",
  target_display_name: "Tata Consultancy Services",
  edge_type: "peer_momentum",
  direction: "bidirectional",
  expected_sign: "positive",
  strength: "0.80",
  evidence_type: "curated_profile_overlap",
  confidence: "0.70",
  provenance_type: "inferred",
  mechanism: "Indian IT services peers share demand drivers.",
  tradability_relevance: "signal",
  status: "candidate",
  valid_from: null,
  valid_to: null,
  source_file: "fixture.csv",
  source_row_hash: "row-candidate",
  metadata: { basis: "fixture" },
  created_at: "2026-05-27T09:00:00Z",
  updated_at: "2026-05-27T09:00:00Z",
};

const activeEdge = {
  ...candidateEdge,
  id: 1,
  edge_key: "ge-active-infy-it-services",
  target_node_id: 3,
  target_node_key: "industry:it-services",
  target_display_name: "IT Services",
  edge_type: "classified_as_industry",
  expected_sign: "unknown",
  strength: "0.90",
  evidence_type: "classification",
  confidence: "0.90",
  provenance_type: "deterministic",
  mechanism: "NSE classifies Infosys as IT Services.",
  tradability_relevance: "context",
  status: "active",
  source_row_hash: "row-active",
};

const riskNode = {
  id: 4,
  node_key: "risk:digital-demand",
  node_type: "risk",
  display_name: "Digital Demand Risk",
  symbol: null,
  isin: null,
  metadata: { fixture: true },
  created_at: "2026-05-27T09:00:00Z",
  updated_at: "2026-05-27T09:00:00Z",
};

const sectorRiskEdge = {
  ...candidateEdge,
  id: 4,
  edge_key: "ge-active-it-services-digital-risk",
  source_node_id: 3,
  source_node_key: "industry:it-services",
  source_display_name: "IT Services",
  target_node_id: 4,
  target_node_key: "risk:digital-demand",
  target_display_name: "Digital Demand Risk",
  edge_type: "sector_risk",
  expected_sign: "negative",
  strength: "0.65",
  evidence_type: "risk_mapping",
  confidence: "0.75",
  provenance_type: "derived",
  mechanism: "IT services demand is sensitive to digital transformation budgets.",
  tradability_relevance: "risk_context",
  status: "active",
  source_row_hash: "row-sector-risk",
};

const companyPayload = {
  symbol: "INFY",
  center_node: {
    id: 1,
    node_key: "company:INFY",
    node_type: "company",
    display_name: "Infosys Limited",
    symbol: "INFY",
    isin: "INE009A01021",
    metadata: { fixture: true },
    created_at: "2026-05-27T09:00:00Z",
    updated_at: "2026-05-27T09:00:00Z",
  },
  nodes: [
    {
      id: 1,
      node_key: "company:INFY",
      node_type: "company",
      display_name: "Infosys Limited",
      symbol: "INFY",
      isin: "INE009A01021",
      metadata: { fixture: true },
      created_at: "2026-05-27T09:00:00Z",
      updated_at: "2026-05-27T09:00:00Z",
    },
    {
      id: 2,
      node_key: "company:TCS",
      node_type: "company",
      display_name: "Tata Consultancy Services",
      symbol: "TCS",
      isin: "INE467B01029",
      metadata: { fixture: true },
      created_at: "2026-05-27T09:00:00Z",
      updated_at: "2026-05-27T09:00:00Z",
    },
    {
      id: 3,
      node_key: "industry:it-services",
      node_type: "industry",
      display_name: "IT Services",
      symbol: null,
      isin: null,
      metadata: { fixture: true },
      created_at: "2026-05-27T09:00:00Z",
      updated_at: "2026-05-27T09:00:00Z",
    },
  ],
  edges: [activeEdge, candidateEdge],
  counts: { nodes: 3, edges: 2, active_edges: 1, candidate_edges: 1 },
};

const neighborhoodPayload = {
  center_node: companyPayload.center_node,
  nodes: companyPayload.nodes,
  edges: companyPayload.edges,
  counts: companyPayload.counts,
  limit: 1000,
  total_edges: 2,
  truncated: false,
};

const industryExpansionPayload = {
  center_node: companyPayload.nodes[2],
  nodes: [companyPayload.nodes[2], riskNode],
  edges: [activeEdge, sectorRiskEdge],
  counts: { nodes: 2, edges: 2, active_edges: 2 },
  limit: 1000,
  total_edges: 1200,
  truncated: true,
};

const edgeDetailPayload = {
  edge: candidateEdge,
  source_node: companyPayload.nodes[0],
  target_node: companyPayload.nodes[1],
  evidence: [
    {
      evidence_id: "evidence:peer:infy:tcs",
      edge_key: candidateEdge.edge_key,
      claim_type: "peer_mapping",
      claim_summary: "Both companies are IT services peers.",
      source_title: "Fixture research",
      source_type: "test_fixture",
      source_date: "2026-05-27",
      source_url_or_reference: "",
      page_or_section: "",
      verbatim_excerpt_short: "",
      confidence: "0.80",
      source_file: "source_evidence.csv",
      source_row_hash: "row-evidence",
      metadata: {},
      created_at: "2026-05-27T09:00:00Z",
      updated_at: "2026-05-27T09:00:00Z",
    },
  ],
  stats: [
    {
      id: 1,
      edge_key: candidateEdge.edge_key,
      window: "90d",
      as_of_date: "2026-05-27",
      sample_size: 90,
      raw_correlation: "0.42",
      residual_correlation: null,
      lead_lag_score: null,
      stability_score: null,
      p_value: null,
      insufficient_data_reason: "",
      model_version: "fixture",
      metadata: {},
      created_at: "2026-05-27T09:00:00Z",
      updated_at: "2026-05-27T09:00:00Z",
    },
  ],
};

const signalPayload = {
  signal_id: "signal:INFY:2026-05-27",
  symbol: "INFY",
  as_of: "2026-05-27T09:15:00Z",
  score: "0.42",
  confidence: "0.76",
  horizon: "swing",
  explanation: "Peer graph signal is bullish for INFY.",
  source_agent: "graph",
  metadata: {},
  contributions: [
    {
      contribution_id: "contribution:signal:INFY:TCS",
      signal_id: "signal:INFY:2026-05-27",
      edge_key: candidateEdge.edge_key,
      node_key: null,
      contribution_type: "peer_momentum",
      direction: "bullish",
      score_contribution: "0.42",
      weight: "1.00",
      explanation: "TCS peer signal supports INFY.",
      metadata: {},
      created_at: "2026-05-27T09:00:00Z",
      updated_at: "2026-05-27T09:00:00Z",
    },
  ],
  created_at: "2026-05-27T09:00:00Z",
  updated_at: "2026-05-27T09:00:00Z",
};

describe("GraphPages", () => {
  beforeEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders empty overview state cleanly", async () => {
    stubGraphFetch({
      graphOverview: emptyGraphOverviewPayload,
      candidateEdges: { total_returned: 0, edges: [] },
      signals: { total_returned: 0, signals: [] },
      bullishCandidates: { total_returned: 0, candidates: [] },
    });

    renderRoute("/graph");

    expect(await screen.findByRole("heading", { name: "Graph" })).toBeInTheDocument();
    expect(await screen.findByText("No graph data")).toBeInTheDocument();
    expect(screen.getByText("make import-taurus-graph DATA_DIR=configs/taurus_data")).toBeInTheDocument();
    expect(screen.getByLabelText("Company symbol")).toBeInTheDocument();
  });

  it("renders a company graph and opens edge detail", async () => {
    const user = userEvent.setup();
    stubGraphFetch();

    renderRoute("/graph/company/INFY");

    expect(await screen.findByRole("heading", { name: "INFY Graph" })).toBeInTheDocument();
    expect(await screen.findByLabelText("Graph company symbol")).toHaveValue("INFY");
    expect(await screen.findByLabelText("Graph explorer canvas")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Active" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Candidate" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByRole("button", { name: "Rejected" })).toHaveAttribute("aria-pressed", "false");
    expect(await screen.findByText("Node inspector")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Select edge Peer Momentum" }));

    expect(await screen.findByText("Edge inspector")).toBeInTheDocument();
    expect(screen.getAllByText("Inferred").length).toBeGreaterThan(0);
    expect(screen.getByText("Both companies are IT services peers.")).toBeInTheDocument();
    expect(screen.getByText("90")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Rejected" }));
    await waitFor(() =>
      expect(fetchUrls()).toContainEqual(
        expect.stringContaining("status=rejected"),
      ),
    );
  });

  it("expands selected graph nodes only through the inspector action", async () => {
    const user = userEvent.setup();
    stubGraphFetch({ expansionNeighborhood: industryExpansionPayload });

    renderRoute("/graph/company/INFY");

    expect(await screen.findByLabelText("Graph explorer canvas")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "IT Services" }));

    expect(screen.getByText("industry:it-services")).toBeInTheDocument();
    expect(
      fetchUrls().some((url) => url.includes("node_key=industry%3Ait-services")),
    ).toBe(false);

    await user.click(screen.getByRole("button", { name: "Expand neighborhood" }));

    await waitFor(() =>
      expect(fetchUrls()).toContainEqual(
        expect.stringContaining("node_key=industry%3Ait-services"),
      ),
    );
    expect(
      await screen.findByRole("button", { name: "Digital Demand Risk" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Returned 2 of 1,200 matching edges for this node."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Refresh neighborhood" }));
    await waitFor(() =>
      expect(
        fetchUrls().filter((url) => url.includes("node_key=industry%3Ait-services")),
      ).toHaveLength(2),
    );
    expect(screen.getAllByRole("button", { name: "Digital Demand Risk" })).toHaveLength(1);
    expect(screen.getAllByRole("button", { name: "Select edge Sector Risk" })).toHaveLength(1);

    const companyNeighborhoodCalls = fetchUrls().filter((url) =>
      url.includes("node_key=company%3AINFY"),
    ).length;
    await user.click(screen.getByRole("button", { name: "Rejected" }));
    await waitFor(() =>
      expect(
        fetchUrls().filter((url) => url.includes("node_key=company%3AINFY")),
      ).toHaveLength(companyNeighborhoodCalls + 1),
    );
    expect(screen.queryByRole("button", { name: "Digital Demand Risk" })).not.toBeInTheDocument();
  });

  it("posts candidate review actions using the approved API shape", async () => {
    const user = userEvent.setup();
    const reviewedDetail = {
      ...edgeDetailPayload,
      edge: {
        ...candidateEdge,
        status: "active",
        metadata: {
          latest_review: {
            reviewed_by: "dashboard",
            note: "Evidence reviewed locally.",
          },
        },
      },
    };
    stubGraphFetch({ reviewedDetail });

    renderRoute("/graph/edges/review");

    expect(await screen.findByRole("heading", { name: "Review Edges" })).toBeInTheDocument();
    await user.type(screen.getByLabelText("Review note"), "Evidence reviewed locally.");
    await user.click(screen.getByRole("button", { name: "Promote edge" }));

    await waitFor(() =>
      expect(fetchUrls()).toContainEqual(
        expect.stringContaining("/graph/edges/ge-candidate-infy-tcs-peer/promote"),
      ),
    );
    const promoteCall = fetchCalls().find((call) =>
      String(call[0]).includes("/graph/edges/ge-candidate-infy-tcs-peer/promote"),
    );
    expect(promoteCall?.[1]?.method).toBe("POST");
    expect(JSON.parse(String(promoteCall?.[1]?.body))).toEqual({
      reviewed_by: "dashboard",
      note: "Evidence reviewed locally.",
    });
    expect(await screen.findByText("Active")).toBeInTheDocument();
  });

  it("renders graph signals and contribution details", async () => {
    const user = userEvent.setup();
    stubGraphFetch();

    renderRoute("/graph/signals");

    expect(await screen.findByRole("heading", { name: "Signals" })).toBeInTheDocument();
    expect((await screen.findAllByText("INFY")).length).toBeGreaterThan(0);

    await user.click(screen.getByRole("button", { name: "Inspect signal" }));

    expect(screen.getByText("Peer graph signal is bullish for INFY.")).toBeInTheDocument();
    expect(screen.getByText("TCS peer signal supports INFY.")).toBeInTheDocument();
    expect(screen.getByText("Peer Momentum")).toBeInTheDocument();
  });
});

function renderRoute(initialEntry: string) {
  const router = createMemoryRouter(routes, { initialEntries: [initialEntry] });
  const queryClient = createTaurusQueryClient();

  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

function stubGraphFetch({
  graphOverview = graphOverviewPayload,
  neighborhood = neighborhoodPayload,
  expansionNeighborhood = industryExpansionPayload,
  candidateEdges = { total_returned: 1, edges: [candidateEdge] },
  signals = { total_returned: 1, signals: [signalPayload] },
  bullishCandidates = { total_returned: 1, candidates: [signalPayload] },
  reviewedDetail = edgeDetailPayload,
}: {
  graphOverview?: object;
  neighborhood?: object;
  expansionNeighborhood?: object;
  candidateEdges?: object;
  signals?: object;
  bullishCandidates?: object;
  reviewedDetail?: object;
} = {}) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);

      if (url.includes("/ui/overview")) {
        return jsonResponse(overviewPayload);
      }
      if (url.includes("/profiles")) {
        return jsonResponse([profile]);
      }
      if (url.includes("/graph/overview")) {
        return jsonResponse(graphOverview);
      }
      if (url.includes("/graph/company/INFY")) {
        return jsonResponse(companyPayload);
      }
      if (url.includes("/graph/neighborhood")) {
        const parsedUrl = new URL(url, "http://localhost");
        if (parsedUrl.searchParams.get("node_key") === "industry:it-services") {
          return jsonResponse(expansionNeighborhood);
        }
        return jsonResponse(neighborhood);
      }
      if (url.includes("/graph/candidate-edges")) {
        return jsonResponse(candidateEdges);
      }
      if (url.includes("/graph/bullish-candidates")) {
        return jsonResponse(bullishCandidates);
      }
      if (url.includes("/graph/signals")) {
        return jsonResponse(signals);
      }
      if (url.includes("/graph/edges/ge-candidate-infy-tcs-peer/promote") && init?.method === "POST") {
        return jsonResponse(reviewedDetail);
      }
      if (url.includes("/graph/edges/ge-candidate-infy-tcs-peer/reject") && init?.method === "POST") {
        return jsonResponse({
          ...reviewedDetail,
          edge: { ...edgeDetailPayload.edge, status: "rejected" },
        });
      }
      if (url.includes("/graph/edges/ge-candidate-infy-tcs-peer")) {
        return jsonResponse(reviewedDetail);
      }

      return jsonResponse({});
    }),
  );
}

function jsonResponse(payload: object) {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function fetchCalls() {
  return vi.mocked(fetch).mock.calls;
}

function fetchUrls() {
  return fetchCalls().map((call) => String(call[0]));
}
