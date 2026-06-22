import type {
  GraphBullishCandidateListResponse,
  GraphCompanySubgraphResponse,
  GraphEdgeDetailResponse,
  GraphEdgeListResponse,
  GraphEdgeStatusFilter,
  GraphNeighborhoodResponse,
  GraphNeighborhoodStatusFilter,
  GraphOverviewResponse,
  GraphReviewAction,
  GraphSignalListResponse,
  UiDecisionTrailResponse,
  UiHistoryResponse,
  UiOverviewResponse,
  UiPortfolioResponse,
  UiReplayResponse,
  UiRiskResponse,
  UiRunDetailResponse,
  UiShariahResponse,
  TaurusProfile,
} from "./types";

export const TAURUS_API_BASE_URL =
  import.meta.env.VITE_TAURUS_API_BASE_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

type ErrorPayload = {
  detail?: string | { msg?: string } | Array<{ msg?: string }>;
};

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${TAURUS_API_BASE_URL}${path}`, {
    headers: {
      Accept: "application/json",
      ...init?.headers,
    },
    ...init,
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = (await response.json()) as ErrorPayload;
      detail = normalizeErrorDetail(payload.detail) ?? detail;
    } catch {
      detail = response.statusText || detail;
    }
    throw new ApiError(response.status, detail);
  }

  return (await response.json()) as T;
}

function normalizeErrorDetail(detail: ErrorPayload["detail"]): string | null {
  if (typeof detail === "string") {
    return detail;
  }
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg).filter(Boolean).join(", ") || null;
  }
  return detail?.msg ?? null;
}

type ProfileScopedParams = {
  profileId?: string | null;
};

function withProfileParam(path: string, profileId: string | null | undefined): string {
  if (!profileId) {
    return path;
  }
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}profile_id=${encodeURIComponent(profileId)}`;
}

export const taurusApi = {
  profiles: () => apiFetch<TaurusProfile[]>("/profiles"),
  overview: ({ profileId }: ProfileScopedParams = {}) =>
    apiFetch<UiOverviewResponse>(withProfileParam("/ui/overview", profileId)),
  history: ({ profileId }: ProfileScopedParams = {}) =>
    apiFetch<UiHistoryResponse>(withProfileParam("/ui/history", profileId)),
  shariah: ({
    query = "",
    status = "all",
    page = 1,
    pageSize = 50,
  }: {
    query?: string;
    status?: "all" | "halal" | "haram";
    page?: number;
    pageSize?: number;
  } = {}) => {
    const params = new URLSearchParams({
      query,
      status,
      page: String(page),
      page_size: String(pageSize),
    });
    return apiFetch<UiShariahResponse>(`/ui/shariah?${params.toString()}`);
  },
  run: (runId: string, { profileId }: ProfileScopedParams = {}) =>
    apiFetch<UiRunDetailResponse>(
      withProfileParam(`/ui/runs/${runId}`, profileId),
    ),
  decisionTrail: (runId: string, symbol: string, { profileId }: ProfileScopedParams = {}) =>
    apiFetch<UiDecisionTrailResponse>(
      withProfileParam(`/ui/runs/${runId}/symbols/${symbol}/decision-trail`, profileId),
    ),
  replay: (decisionId: string) =>
    apiFetch<UiReplayResponse>(`/ui/replay/${decisionId}`),
  risk: ({ profileId }: ProfileScopedParams = {}) =>
    apiFetch<UiRiskResponse>(withProfileParam("/ui/risk", profileId)),
  portfolio: ({ profileId }: ProfileScopedParams = {}) =>
    apiFetch<UiPortfolioResponse>(withProfileParam("/ui/portfolio", profileId)),
  graphOverview: () => apiFetch<GraphOverviewResponse>("/graph/overview"),
  graphCompany: ({
    symbol,
    status = "all",
    limit = 250,
  }: {
    symbol: string;
    status?: GraphEdgeStatusFilter;
    limit?: number;
  }) => {
    const params = new URLSearchParams({
      status,
      limit: String(limit),
    });
    return apiFetch<GraphCompanySubgraphResponse>(
      `/graph/company/${encodeURIComponent(symbol)}?${params.toString()}`,
    );
  },
  graphNeighborhood: ({
    nodeKey,
    statuses,
    limit = 1000,
  }: {
    nodeKey: string;
    statuses?: GraphNeighborhoodStatusFilter[];
    limit?: number;
  }) => {
    const params = new URLSearchParams({
      node_key: nodeKey,
      limit: String(limit),
    });
    statuses?.forEach((status) => params.append("status", status));
    return apiFetch<GraphNeighborhoodResponse>(
      `/graph/neighborhood?${params.toString()}`,
    );
  },
  graphCandidateEdges: ({
    edgeType,
    limit = 100,
  }: {
    edgeType?: string;
    limit?: number;
  } = {}) => {
    const params = new URLSearchParams({ limit: String(limit) });
    if (edgeType) {
      params.set("edge_type", edgeType);
    }
    return apiFetch<GraphEdgeListResponse>(`/graph/candidate-edges?${params.toString()}`);
  },
  graphEdgeDetail: (edgeKey: string) =>
    apiFetch<GraphEdgeDetailResponse>(`/graph/edges/${encodeURIComponent(edgeKey)}`),
  graphReviewEdge: ({
    edgeKey,
    action,
    reviewedBy = "dashboard",
    note = "",
  }: {
    edgeKey: string;
    action: GraphReviewAction;
    reviewedBy?: string;
    note?: string;
  }) =>
    apiFetch<GraphEdgeDetailResponse>(
      `/graph/edges/${encodeURIComponent(edgeKey)}/${action}`,
      {
        body: JSON.stringify({ reviewed_by: reviewedBy, note }),
        headers: { "Content-Type": "application/json" },
        method: "POST",
      },
    ),
  graphSignals: ({
    symbol,
    sourceAgent,
    includeContributions = true,
    limit = 100,
  }: {
    symbol?: string;
    sourceAgent?: string;
    includeContributions?: boolean;
    limit?: number;
  } = {}) => {
    const params = new URLSearchParams({
      include_contributions: String(includeContributions),
      limit: String(limit),
    });
    if (symbol) {
      params.set("symbol", symbol);
    }
    if (sourceAgent) {
      params.set("source_agent", sourceAgent);
    }
    return apiFetch<GraphSignalListResponse>(`/graph/signals?${params.toString()}`);
  },
  graphBullishCandidates: ({
    symbol,
    minScore = 0.01,
    includeContributions = true,
    limit = 50,
  }: {
    symbol?: string;
    minScore?: number;
    includeContributions?: boolean;
    limit?: number;
  } = {}) => {
    const params = new URLSearchParams({
      min_score: String(minScore),
      include_contributions: String(includeContributions),
      limit: String(limit),
    });
    if (symbol) {
      params.set("symbol", symbol);
    }
    return apiFetch<GraphBullishCandidateListResponse>(
      `/graph/bullish-candidates?${params.toString()}`,
    );
  },
};
