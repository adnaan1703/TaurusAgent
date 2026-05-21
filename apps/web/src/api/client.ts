import type {
  UiDecisionTrailResponse,
  UiHistoryResponse,
  UiOverviewResponse,
  UiPortfolioResponse,
  UiReplayResponse,
  UiRiskResponse,
  UiRunDetailResponse,
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

export const taurusApi = {
  overview: () => apiFetch<UiOverviewResponse>("/ui/overview"),
  history: () => apiFetch<UiHistoryResponse>("/ui/history"),
  run: (runId: string) => apiFetch<UiRunDetailResponse>(`/ui/runs/${runId}`),
  decisionTrail: (runId: string, symbol: string) =>
    apiFetch<UiDecisionTrailResponse>(
      `/ui/runs/${runId}/symbols/${symbol}/decision-trail`,
    ),
  replay: (decisionId: string) =>
    apiFetch<UiReplayResponse>(`/ui/replay/${decisionId}`),
  risk: () => apiFetch<UiRiskResponse>("/ui/risk"),
  portfolio: () => apiFetch<UiPortfolioResponse>("/ui/portfolio"),
};
