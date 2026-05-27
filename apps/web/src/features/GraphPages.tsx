import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import clsx from "clsx";
import {
  ArrowRight,
  CheckCircle2,
  GitBranch,
  Inspect,
  Search,
  X,
  XCircle,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useMemo, useState } from "react";
import { Link, NavLink, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { taurusApi } from "../api/client";
import type {
  GraphCompanySubgraphResponse,
  GraphEdge,
  GraphEdgeDetailResponse,
  GraphEdgeStatusFilter,
  GraphNode,
  GraphReviewAction,
  GraphSignal,
} from "../api/types";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { MetricCard } from "../components/MetricCard";
import { RefreshButton } from "../components/RefreshButton";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import {
  formatId,
  formatNumber,
  formatPercent,
  formatTimestamp,
  humanizeKey,
} from "../utils/format";
import { PageScaffold } from "./PageScaffold";

const GRAPH_EMPTY_COMMANDS = [
  "make migrate",
  "make import-taurus-graph DATA_DIR=configs/taurus_data",
];

const GRAPH_STATUS_OPTIONS: GraphEdgeStatusFilter[] = [
  "all",
  "active",
  "candidate",
  "rejected",
];

const graphNavItems = [
  { to: "/graph", label: "Overview", end: true },
  { to: "/graph/company/INFY", label: "Company" },
  { to: "/graph/edges/review", label: "Review" },
  { to: "/graph/signals", label: "Signals" },
];

export function GraphOverviewPage() {
  const navigate = useNavigate();
  const [symbol, setSymbol] = useState("INFY");

  const overviewQuery = useQuery({
    queryKey: ["graph", "overview"],
    queryFn: taurusApi.graphOverview,
    refetchInterval: 30_000,
  });
  const candidateQuery = useQuery({
    queryKey: ["graph", "candidate-edges", "overview"],
    queryFn: () => taurusApi.graphCandidateEdges({ limit: 5 }),
  });
  const signalsQuery = useQuery({
    queryKey: ["graph", "signals", "overview"],
    queryFn: () => taurusApi.graphSignals({ includeContributions: false, limit: 5 }),
  });

  const overview = overviewQuery.data;
  const counts = overview?.counts ?? {};
  const hasGraphData = (counts.nodes ?? 0) > 0 || (counts.edges ?? 0) > 0;

  function submitCompanySearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalized = symbol.trim().toUpperCase();
    if (normalized) {
      navigate(`/graph/company/${encodeURIComponent(normalized)}`);
    }
  }

  return (
    <PageScaffold
      actions={
        <RefreshButton
          isRefreshing={overviewQuery.isFetching || candidateQuery.isFetching || signalsQuery.isFetching}
          onRefresh={() => {
            void overviewQuery.refetch();
            void candidateQuery.refetch();
            void signalsQuery.refetch();
          }}
        />
      }
      eyebrow="Graph intelligence"
      title="Graph"
    >
      <GraphSubnav />
      {overviewQuery.isLoading && <LoadingState label="Loading graph overview" />}
      {overviewQuery.isError && <ErrorState message={overviewQuery.error.message} />}
      {overview && (
        <div className="grid gap-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Nodes" value={formatNumber(counts.nodes)} />
            <MetricCard label="Edges" value={formatNumber(counts.edges)} />
            <MetricCard
              label="Candidate edges"
              tone={(counts.candidate_edges ?? 0) > 0 ? "caution" : "neutral"}
              value={formatNumber(counts.candidate_edges)}
            />
            <MetricCard
              label="Graph signals"
              tone={(counts.signals ?? 0) > 0 ? "success" : "neutral"}
              value={formatNumber(counts.signals)}
            />
          </div>

          <DataPanel title="Runtime Flags">
            <div className="flex flex-wrap gap-2">
              <StatusBadge
                label={overview.graph_enabled ? "Review enabled" : "Review disabled"}
                status={overview.graph_enabled ? "APPROVED" : "BLOCKED"}
                size="sm"
              />
              <StatusBadge
                label={overview.graph_risk_enabled ? "Graph risk enabled" : "Graph risk disabled"}
                status={overview.graph_risk_enabled ? "APPROVED" : "BLOCKED"}
                size="sm"
              />
              <StatusBadge
                label={overview.graph_auto_promote_edges ? "Auto-promote enabled" : "Auto-promote disabled"}
                status={overview.graph_auto_promote_edges ? "BLOCKED" : "APPROVED"}
                size="sm"
              />
              <StatusBadge
                label={overview.neo4j_enabled ? "Neo4j enabled" : "Neo4j absent"}
                status={overview.neo4j_enabled ? "APPROVED" : "missing"}
                size="sm"
              />
            </div>
            <p className="mt-3 text-xs text-taurus-muted">
              Generated {formatTimestamp(overview.generated_at)}
            </p>
          </DataPanel>

          {!hasGraphData && (
            <EmptyState
              commands={GRAPH_EMPTY_COMMANDS}
              message="No graph nodes or edges are stored in the configured Taurus database."
              title="No graph data"
            />
          )}

          <DataPanel title="Open Company Graph">
            <form className="flex flex-col gap-3 sm:flex-row" onSubmit={submitCompanySearch}>
              <input
                aria-label="Company symbol"
                className="min-w-0 flex-1 rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none placeholder:text-taurus-muted focus:border-taurus-primary"
                onChange={(event) => setSymbol(event.target.value)}
                placeholder="INFY"
                value={symbol}
              />
              <button
                className="inline-flex items-center justify-center gap-2 rounded-md border border-taurus-primary bg-sky-400/10 px-4 py-2 text-sm font-medium text-taurus-text hover:bg-sky-400/15"
                type="submit"
              >
                <Search aria-hidden="true" className="h-4 w-4" />
                Open
              </button>
            </form>
          </DataPanel>

          <div className="grid gap-6 xl:grid-cols-2">
            <DataPanel
              actions={<LinkButton to="/graph/edges/review">Review queue</LinkButton>}
              title="Candidate Edges"
            >
              {candidateQuery.isError && <ErrorState message={candidateQuery.error.message} />}
              {candidateQuery.data && (
                <EdgeTable
                  edges={candidateQuery.data.edges}
                  emptyLabel="No candidate graph edges"
                  renderActions={(edge) => (
                    <LinkIconButton label="Review edge" to={`/graph/edges/review?edge=${encodeURIComponent(edge.edge_key)}`} />
                  )}
                />
              )}
            </DataPanel>

            <DataPanel actions={<LinkButton to="/graph/signals">Signals</LinkButton>} title="Latest Signals">
              {signalsQuery.isError && <ErrorState message={signalsQuery.error.message} />}
              {signalsQuery.data && (
                <SignalTable
                  emptyLabel="No graph signals"
                  signals={signalsQuery.data.signals}
                />
              )}
            </DataPanel>
          </div>

          <JsonDrawer title="Graph overview payload" value={overview} />
        </div>
      )}
    </PageScaffold>
  );
}

export function GraphCompanyPage() {
  const params = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedEdgeKey, setSelectedEdgeKey] = useState<string | null>(null);
  const symbol = (params.symbol ?? "INFY").toUpperCase();
  const status = normalizeStatus(searchParams.get("status"));

  const companyQuery = useQuery({
    queryKey: ["graph", "company", symbol, status],
    queryFn: () => taurusApi.graphCompany({ symbol, status }),
    retry: false,
  });

  const payload = companyQuery.data;

  return (
    <PageScaffold
      actions={
        <RefreshButton
          isRefreshing={companyQuery.isFetching}
          onRefresh={() => void companyQuery.refetch()}
        />
      }
      eyebrow="Company graph"
      title={`${symbol} Graph`}
    >
      <GraphSubnav />
      {companyQuery.isLoading && <LoadingState label={`Loading ${symbol} graph`} />}
      {companyQuery.isError && <ErrorState message={companyQuery.error.message} />}
      {payload && (
        <div className="grid gap-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Visible nodes" value={formatNumber(payload.counts.nodes)} />
            <MetricCard label="Visible edges" value={formatNumber(payload.counts.edges)} />
            <MetricCard label="Active edges" tone="success" value={formatNumber(payload.counts.active_edges)} />
            <MetricCard label="Candidate edges" tone="caution" value={formatNumber(payload.counts.candidate_edges)} />
          </div>

          <DataPanel title="Filters">
            <label className="grid max-w-xs gap-2 text-sm text-taurus-muted">
              Edge status
              <select
                aria-label="Graph edge status"
                className="rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none focus:border-taurus-primary"
                onChange={(event) => setSearchParams({ status: event.target.value })}
                value={status}
              >
                {GRAPH_STATUS_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option === "all" ? "All statuses" : humanizeKey(option)}
                  </option>
                ))}
              </select>
            </label>
          </DataPanel>

          {payload.edges.length === 0 ? (
            <EmptyState
              commands={GRAPH_EMPTY_COMMANDS}
              message={`No ${status === "all" ? "" : `${status} `}graph edges are connected to ${symbol}.`}
              title="No connected edges"
            />
          ) : (
            <>
              <DataPanel title="Relationship Map">
                <GraphCanvas
                  graph={payload}
                  onSelectEdge={setSelectedEdgeKey}
                  selectedEdgeKey={selectedEdgeKey}
                />
              </DataPanel>

              <DataPanel title="Edges">
                <EdgeTable
                  edges={payload.edges}
                  emptyLabel="No graph edges"
                  renderActions={(edge) => (
                    <IconButton
                      label="Inspect edge"
                      onClick={() => setSelectedEdgeKey(edge.edge_key)}
                    >
                      <Inspect aria-hidden="true" className="h-4 w-4" />
                    </IconButton>
                  )}
                />
              </DataPanel>
            </>
          )}

          <JsonDrawer title={`${symbol} graph payload`} value={payload} />
          <EdgeDetailDrawer edgeKey={selectedEdgeKey} onClose={() => setSelectedEdgeKey(null)} />
        </div>
      )}
    </PageScaffold>
  );
}

export function GraphReviewPage() {
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [edgeType, setEdgeType] = useState("");
  const [reviewNote, setReviewNote] = useState("");
  const [selectedEdgeKey, setSelectedEdgeKey] = useState<string | null>(searchParams.get("edge"));
  const [reviewError, setReviewError] = useState<string | null>(null);

  const candidateQuery = useQuery({
    queryKey: ["graph", "candidate-edges", edgeType],
    queryFn: () => taurusApi.graphCandidateEdges({ edgeType: edgeType.trim() || undefined }),
  });

  const reviewMutation = useMutation({
    mutationFn: ({
      edgeKey,
      action,
    }: {
      edgeKey: string;
      action: GraphReviewAction;
    }) =>
      taurusApi.graphReviewEdge({
        edgeKey,
        action,
        note: reviewNote.trim(),
        reviewedBy: "dashboard",
      }),
    onError: (error) => setReviewError(error.message),
    onSuccess: (detail) => {
      setReviewError(null);
      setSelectedEdgeKey(detail.edge.edge_key);
      void queryClient.invalidateQueries({ queryKey: ["graph", "candidate-edges"] });
      void queryClient.invalidateQueries({ queryKey: ["graph", "edge", detail.edge.edge_key] });
      void queryClient.invalidateQueries({ queryKey: ["graph", "overview"] });
    },
  });

  function selectEdge(edgeKey: string) {
    setSelectedEdgeKey(edgeKey);
  }

  function review(edgeKey: string, action: GraphReviewAction) {
    reviewMutation.mutate({ edgeKey, action });
  }

  return (
    <PageScaffold
      actions={
        <RefreshButton
          isRefreshing={candidateQuery.isFetching || reviewMutation.isPending}
          onRefresh={() => void candidateQuery.refetch()}
        />
      }
      eyebrow="Graph edge review"
      title="Review Edges"
    >
      <GraphSubnav />
      {candidateQuery.isLoading && <LoadingState label="Loading candidate edges" />}
      {candidateQuery.isError && <ErrorState message={candidateQuery.error.message} />}
      <div className="grid gap-6">
        <DataPanel title="Review Filters">
          <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
            <label className="grid gap-2 text-sm text-taurus-muted">
              Edge type
              <input
                aria-label="Candidate edge type"
                className="rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none placeholder:text-taurus-muted focus:border-taurus-primary"
                onChange={(event) => setEdgeType(event.target.value)}
                placeholder="peer_momentum"
                value={edgeType}
              />
            </label>
            <label className="grid gap-2 text-sm text-taurus-muted">
              Review note
              <input
                aria-label="Review note"
                className="rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none placeholder:text-taurus-muted focus:border-taurus-primary"
                onChange={(event) => setReviewNote(event.target.value)}
                placeholder="Evidence reviewed locally"
                value={reviewNote}
              />
            </label>
          </div>
          {reviewError && <p className="mt-3 text-sm text-rose-100">{reviewError}</p>}
        </DataPanel>

        {candidateQuery.data?.edges.length === 0 ? (
          <EmptyState
            commands={GRAPH_EMPTY_COMMANDS}
            message="No candidate graph edges are waiting for review."
            title="No candidate edges"
          />
        ) : (
          <DataPanel title="Candidate Queue">
            <EdgeTable
              edges={candidateQuery.data?.edges ?? []}
              emptyLabel="No candidate graph edges"
              renderActions={(edge) => (
                <div className="flex flex-wrap justify-end gap-2">
                  <IconButton label="Inspect edge" onClick={() => selectEdge(edge.edge_key)}>
                    <Inspect aria-hidden="true" className="h-4 w-4" />
                  </IconButton>
                  <IconButton
                    disabled={reviewMutation.isPending}
                    label="Promote edge"
                    onClick={() => review(edge.edge_key, "promote")}
                  >
                    <CheckCircle2 aria-hidden="true" className="h-4 w-4 text-emerald-200" />
                  </IconButton>
                  <IconButton
                    disabled={reviewMutation.isPending}
                    label="Reject edge"
                    onClick={() => review(edge.edge_key, "reject")}
                  >
                    <XCircle aria-hidden="true" className="h-4 w-4 text-rose-100" />
                  </IconButton>
                </div>
              )}
            />
          </DataPanel>
        )}

        <EdgeDetailDrawer edgeKey={selectedEdgeKey} onClose={() => setSelectedEdgeKey(null)} />
      </div>
    </PageScaffold>
  );
}

export function GraphSignalsPage() {
  const [symbol, setSymbol] = useState("");
  const [sourceAgent, setSourceAgent] = useState("");
  const [selectedSignalId, setSelectedSignalId] = useState<string | null>(null);

  const signalsQuery = useQuery({
    queryKey: ["graph", "signals", symbol, sourceAgent],
    queryFn: () =>
      taurusApi.graphSignals({
        symbol: symbol.trim().toUpperCase() || undefined,
        sourceAgent: sourceAgent.trim() || undefined,
      }),
  });
  const bullishQuery = useQuery({
    queryKey: ["graph", "bullish-candidates", symbol],
    queryFn: () =>
      taurusApi.graphBullishCandidates({
        symbol: symbol.trim().toUpperCase() || undefined,
        includeContributions: false,
      }),
  });

  const selectedSignal = useMemo(
    () => signalsQuery.data?.signals.find((signal) => signal.signal_id === selectedSignalId) ?? null,
    [selectedSignalId, signalsQuery.data?.signals],
  );

  return (
    <PageScaffold
      actions={
        <RefreshButton
          isRefreshing={signalsQuery.isFetching || bullishQuery.isFetching}
          onRefresh={() => {
            void signalsQuery.refetch();
            void bullishQuery.refetch();
          }}
        />
      }
      eyebrow="Graph signals"
      title="Signals"
    >
      <GraphSubnav />
      {signalsQuery.isLoading && <LoadingState label="Loading graph signals" />}
      {signalsQuery.isError && <ErrorState message={signalsQuery.error.message} />}
      <div className="grid gap-6">
        <DataPanel title="Filters">
          <div className="grid gap-3 md:grid-cols-2">
            <input
              aria-label="Signal symbol"
              className="rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none placeholder:text-taurus-muted focus:border-taurus-primary"
              onChange={(event) => setSymbol(event.target.value)}
              placeholder="Symbol"
              value={symbol}
            />
            <input
              aria-label="Signal source agent"
              className="rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none placeholder:text-taurus-muted focus:border-taurus-primary"
              onChange={(event) => setSourceAgent(event.target.value)}
              placeholder="Source agent"
              value={sourceAgent}
            />
          </div>
        </DataPanel>

        {signalsQuery.data?.signals.length === 0 ? (
          <EmptyState
            commands={GRAPH_EMPTY_COMMANDS}
            message="No graph signals are stored in the configured Taurus database."
            title="No graph signals"
          />
        ) : (
          <DataPanel title="Stored Signals">
            <SignalTable
              emptyLabel="No graph signals"
              renderActions={(signal) => (
                <IconButton
                  label="Inspect signal"
                  onClick={() => setSelectedSignalId(signal.signal_id)}
                >
                  <Inspect aria-hidden="true" className="h-4 w-4" />
                </IconButton>
              )}
              signals={signalsQuery.data?.signals ?? []}
            />
          </DataPanel>
        )}

        <div className="grid gap-6 xl:grid-cols-2">
          <DataPanel title="Bullish Candidates">
            {bullishQuery.isError && <ErrorState message={bullishQuery.error.message} />}
            {bullishQuery.data && (
              <SignalTable
                emptyLabel="No bullish graph candidates"
                signals={bullishQuery.data.candidates}
              />
            )}
          </DataPanel>

          <DataPanel title="Signal Detail">
            {selectedSignal ? (
              <SignalDetail signal={selectedSignal} />
            ) : (
              <div className="rounded-md border border-dashed border-taurus-outline bg-taurus-shell p-5 text-sm text-taurus-muted">
                Select a signal to inspect contributions.
              </div>
            )}
          </DataPanel>
        </div>

        {signalsQuery.data && <JsonDrawer title="Graph signals payload" value={signalsQuery.data} />}
      </div>
    </PageScaffold>
  );
}

function GraphSubnav() {
  return (
    <nav className="flex flex-wrap gap-2" aria-label="Graph navigation">
      {graphNavItems.map((item) => (
        <NavLink
          className={({ isActive }) =>
            clsx(
              "inline-flex items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium",
              isActive
                ? "border-taurus-primary bg-sky-400/10 text-taurus-text"
                : "border-taurus-outline bg-taurus-surface text-taurus-muted hover:border-taurus-primary hover:text-taurus-text",
            )
          }
          end={item.end}
          key={item.to}
          to={item.to}
        >
          <GitBranch aria-hidden="true" className="h-4 w-4" />
          {item.label}
        </NavLink>
      ))}
    </nav>
  );
}

function EdgeTable({
  edges,
  emptyLabel,
  renderActions,
}: {
  edges: GraphEdge[];
  emptyLabel: string;
  renderActions?: (edge: GraphEdge) => ReactNode;
}) {
  return (
    <DataTable
      columns={[
        {
          key: "edge",
          header: "Edge",
          render: (edge) => (
            <div className="min-w-56">
              <p className="font-mono text-xs text-taurus-primary">{formatId(edge.edge_key)}</p>
              <p className="mt-1 text-sm font-medium">{humanizeKey(edge.edge_type)}</p>
            </div>
          ),
        },
        {
          key: "source",
          header: "Source",
          render: (edge) => <NodeText name={edge.source_display_name} nodeKey={edge.source_node_key} />,
        },
        {
          key: "target",
          header: "Target",
          render: (edge) => <NodeText name={edge.target_display_name} nodeKey={edge.target_node_key} />,
        },
        {
          key: "status",
          header: "Status",
          render: (edge) => <StatusBadge status={edge.status} size="sm" />,
        },
        {
          key: "confidence",
          header: "Confidence",
          align: "right",
          render: (edge) => formatPercent(edge.confidence),
        },
        {
          key: "strength",
          header: "Strength",
          align: "right",
          render: (edge) => formatNumber(edge.strength ?? undefined),
        },
        {
          key: "actions",
          header: "Actions",
          align: "right",
          render: (edge) => renderActions?.(edge) ?? "-",
        },
      ]}
      emptyLabel={emptyLabel}
      getRowKey={(edge) => edge.edge_key}
      rows={edges}
    />
  );
}

function SignalTable({
  signals,
  emptyLabel,
  renderActions,
}: {
  signals: GraphSignal[];
  emptyLabel: string;
  renderActions?: (signal: GraphSignal) => ReactNode;
}) {
  return (
    <DataTable
      columns={[
        {
          key: "signal",
          header: "Signal",
          render: (signal) => (
            <div className="min-w-48">
              <p className="font-medium">{signal.symbol}</p>
              <p className="mt-1 font-mono text-xs text-taurus-muted">{formatId(signal.signal_id)}</p>
            </div>
          ),
        },
        { key: "score", header: "Score", align: "right", render: (signal) => formatNumber(signal.score) },
        {
          key: "confidence",
          header: "Confidence",
          align: "right",
          render: (signal) => formatPercent(signal.confidence),
        },
        { key: "horizon", header: "Horizon", render: (signal) => signal.horizon || "-" },
        { key: "source", header: "Source", render: (signal) => signal.source_agent || "-" },
        { key: "asof", header: "As of", render: (signal) => formatTimestamp(signal.as_of) },
        {
          key: "actions",
          header: "Actions",
          align: "right",
          render: (signal) => renderActions?.(signal) ?? "-",
        },
      ]}
      emptyLabel={emptyLabel}
      getRowKey={(signal) => signal.signal_id}
      rows={signals}
    />
  );
}

function GraphCanvas({
  graph,
  selectedEdgeKey,
  onSelectEdge,
}: {
  graph: GraphCompanySubgraphResponse;
  selectedEdgeKey: string | null;
  onSelectEdge: (edgeKey: string) => void;
}) {
  const layout = useMemo(() => buildGraphLayout(graph.nodes, graph.center_node), [graph.nodes, graph.center_node]);
  const visibleEdges = graph.edges.filter(
    (edge) => layout.positions.has(edge.source_node_key) && layout.positions.has(edge.target_node_key),
  );

  return (
    <div className="overflow-x-auto rounded-lg border border-taurus-outline bg-taurus-shell">
      <svg
        aria-label={`${graph.symbol} relationship map`}
        className="h-[420px] min-w-[720px] w-full"
        role="img"
        viewBox="0 0 760 420"
      >
        <rect fill="#07101d" height="420" width="760" />
        {visibleEdges.map((edge) => {
          const source = layout.positions.get(edge.source_node_key);
          const target = layout.positions.get(edge.target_node_key);
          if (!source || !target) {
            return null;
          }
          const midpoint = { x: (source.x + target.x) / 2, y: (source.y + target.y) / 2 };
          const selected = selectedEdgeKey === edge.edge_key;
          return (
            <g
              aria-label={`${edge.source_display_name} to ${edge.target_display_name}`}
              className="cursor-pointer outline-none"
              key={edge.edge_key}
              onClick={() => onSelectEdge(edge.edge_key)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  onSelectEdge(edge.edge_key);
                }
              }}
              role="button"
              tabIndex={0}
            >
              <line
                stroke={edgeStroke(edge.status)}
                strokeOpacity={selected ? 1 : 0.62}
                strokeWidth={selected ? 4 : 2}
                x1={source.x}
                x2={target.x}
                y1={source.y}
                y2={target.y}
              />
              <text
                fill={selected ? "#e8f0fb" : "#8ea1b8"}
                fontSize="10"
                textAnchor="middle"
                x={midpoint.x}
                y={midpoint.y - 8}
              >
                {shortLabel(humanizeKey(edge.edge_type), 22)}
              </text>
            </g>
          );
        })}
        {layout.nodes.map((node) => {
          const position = layout.positions.get(node.node_key);
          if (!position) {
            return null;
          }
          const isCenter = node.node_key === graph.center_node.node_key;
          return (
            <g key={node.node_key}>
              <circle
                cx={position.x}
                cy={position.y}
                fill={isCenter ? "#38bdf8" : nodeFill(node.node_type)}
                r={isCenter ? 28 : 22}
                stroke={isCenter ? "#e0f2fe" : "#334155"}
                strokeWidth="2"
              />
              <text
                fill={isCenter ? "#07101d" : "#e8f0fb"}
                fontSize={isCenter ? "12" : "11"}
                fontWeight={isCenter ? 700 : 600}
                textAnchor="middle"
                x={position.x}
                y={position.y + 4}
              >
                {shortLabel(node.symbol || node.display_name, isCenter ? 9 : 12)}
              </text>
              <text
                fill="#8ea1b8"
                fontSize="10"
                textAnchor="middle"
                x={position.x}
                y={position.y + 38}
              >
                {shortLabel(humanizeKey(node.node_type), 16)}
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function EdgeDetailDrawer({
  edgeKey,
  onClose,
}: {
  edgeKey: string | null;
  onClose: () => void;
}) {
  const detailQuery = useQuery({
    queryKey: ["graph", "edge", edgeKey],
    queryFn: () => taurusApi.graphEdgeDetail(edgeKey ?? ""),
    enabled: Boolean(edgeKey),
  });

  if (!edgeKey) {
    return null;
  }

  const detail = detailQuery.data;

  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-black/50">
      <aside className="h-full w-full max-w-2xl overflow-y-auto border-l border-taurus-outline bg-taurus-shell shadow-2xl">
        <div className="sticky top-0 z-10 flex items-start justify-between gap-4 border-b border-taurus-outline bg-taurus-shell px-5 py-4">
          <div>
            <p className="text-xs font-semibold uppercase text-taurus-primary">Edge detail</p>
            <h2 className="mt-1 break-all text-lg font-semibold text-taurus-text">
              {formatId(edgeKey)}
            </h2>
          </div>
          <IconButton label="Close edge detail" onClick={onClose}>
            <X aria-hidden="true" className="h-4 w-4" />
          </IconButton>
        </div>
        <div className="grid gap-5 p-5">
          {detailQuery.isLoading && <LoadingState label="Loading edge detail" />}
          {detailQuery.isError && <ErrorState message={detailQuery.error.message} />}
          {detail && <EdgeDetailContent detail={detail} />}
        </div>
      </aside>
    </div>
  );
}

function EdgeDetailContent({ detail }: { detail: GraphEdgeDetailResponse }) {
  return (
    <>
      <DrawerSection title="Relationship">
        <div className="grid gap-4 md:grid-cols-2">
          <NodeSummary label="Source" node={detail.source_node} />
          <NodeSummary label="Target" node={detail.target_node} />
        </div>
        <div className="mt-4 flex flex-wrap gap-2">
          <StatusBadge status={detail.edge.status} size="sm" />
          <Badge>{humanizeKey(detail.edge.edge_type)}</Badge>
          <Badge>{humanizeKey(detail.edge.expected_sign)}</Badge>
          {detail.edge.inferred && <Badge>Inferred</Badge>}
        </div>
        <p className="mt-4 text-sm leading-6 text-slate-200">
          {detail.edge.mechanism || "No mechanism recorded."}
        </p>
      </DrawerSection>

      <DrawerSection title="Evidence">
        <DataTable
          columns={[
            { key: "claim", header: "Claim", render: (item) => item.claim_summary || "-" },
            { key: "source", header: "Source", render: (item) => item.source_title || item.source_type || "-" },
            {
              key: "confidence",
              header: "Confidence",
              align: "right",
              render: (item) => formatPercent(item.confidence),
            },
          ]}
          emptyLabel="No evidence is linked to this edge"
          getRowKey={(item) => item.evidence_id}
          rows={detail.evidence}
        />
      </DrawerSection>

      <DrawerSection title="Stats">
        <DataTable
          columns={[
            { key: "window", header: "Window", render: (item) => item.window },
            { key: "asof", header: "As of", render: (item) => item.as_of_date },
            { key: "sample", header: "Sample", align: "right", render: (item) => formatNumber(item.sample_size) },
            {
              key: "raw",
              header: "Raw corr.",
              align: "right",
              render: (item) => formatNumber(item.raw_correlation ?? undefined),
            },
          ]}
          emptyLabel="No edge stats are stored"
          getRowKey={(item) => `${item.edge_key}-${item.window}-${item.as_of_date}`}
          rows={detail.stats}
        />
      </DrawerSection>

      <JsonDrawer title="Edge detail payload" value={detail} />
    </>
  );
}

function SignalDetail({ signal }: { signal: GraphSignal }) {
  return (
    <div className="grid gap-5">
      <div>
        <div className="flex flex-wrap gap-2">
          <Badge>{signal.symbol}</Badge>
          <Badge>{humanizeKey(signal.horizon)}</Badge>
          <Badge>{signal.source_agent}</Badge>
        </div>
        <p className="mt-4 text-sm leading-6 text-slate-200">
          {signal.explanation || "No explanation recorded."}
        </p>
      </div>
      <DataTable
        columns={[
          { key: "type", header: "Type", render: (item) => humanizeKey(item.contribution_type) },
          { key: "direction", header: "Direction", render: (item) => <StatusBadge status={item.direction} size="sm" /> },
          { key: "score", header: "Score", align: "right", render: (item) => formatNumber(item.score_contribution) },
          { key: "weight", header: "Weight", align: "right", render: (item) => formatNumber(item.weight) },
          { key: "edge", header: "Edge", render: (item) => formatId(item.edge_key) },
          { key: "explanation", header: "Explanation", render: (item) => item.explanation || "-" },
        ]}
        emptyLabel="No signal contributions"
        getRowKey={(item) => item.contribution_id}
        rows={signal.contributions}
      />
    </div>
  );
}

function NodeText({ name, nodeKey }: { name: string; nodeKey: string }) {
  return (
    <div className="min-w-44">
      <p className="font-medium">{name || "-"}</p>
      <p className="mt-1 break-all font-mono text-xs text-taurus-muted">{nodeKey}</p>
    </div>
  );
}

function NodeSummary({ label, node }: { label: string; node: GraphNode }) {
  return (
    <div className="rounded-md border border-taurus-outline bg-[#07101d] p-4">
      <p className="text-xs font-semibold uppercase text-taurus-muted">{label}</p>
      <p className="mt-2 font-medium text-taurus-text">{node.display_name}</p>
      <p className="mt-1 font-mono text-xs text-taurus-muted">{node.node_key}</p>
      <div className="mt-3 flex flex-wrap gap-2">
        <Badge>{humanizeKey(node.node_type)}</Badge>
        {node.symbol && <Badge>{node.symbol}</Badge>}
      </div>
    </div>
  );
}

function DrawerSection({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="rounded-lg border border-taurus-outline bg-taurus-surface p-4">
      <h3 className="text-sm font-semibold text-taurus-text">{title}</h3>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function LinkButton({ to, children }: { to: string; children: ReactNode }) {
  return (
    <Link
      className="inline-flex items-center gap-2 rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm font-medium text-taurus-muted hover:border-taurus-primary hover:text-taurus-text"
      to={to}
    >
      {children}
      <ArrowRight aria-hidden="true" className="h-4 w-4" />
    </Link>
  );
}

function LinkIconButton({ to, label }: { to: string; label: string }) {
  return (
    <Link
      aria-label={label}
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-taurus-outline bg-taurus-shell text-taurus-muted hover:border-taurus-primary hover:text-taurus-text"
      to={to}
    >
      <ArrowRight aria-hidden="true" className="h-4 w-4" />
    </Link>
  );
}

function IconButton({
  label,
  onClick,
  disabled = false,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      aria-label={label}
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-taurus-outline bg-taurus-shell text-taurus-muted hover:border-taurus-primary hover:text-taurus-text disabled:opacity-50"
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      {children}
    </button>
  );
}

function Badge({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-md border border-taurus-outline bg-taurus-shell px-2 py-1 text-xs font-medium text-taurus-muted">
      {children}
    </span>
  );
}

function normalizeStatus(value: string | null): GraphEdgeStatusFilter {
  return GRAPH_STATUS_OPTIONS.includes(value as GraphEdgeStatusFilter)
    ? (value as GraphEdgeStatusFilter)
    : "all";
}

function buildGraphLayout(nodes: GraphNode[], centerNode: GraphNode) {
  const visibleNodes = [
    centerNode,
    ...nodes.filter((node) => node.node_key !== centerNode.node_key).slice(0, 28),
  ];
  const positions = new Map<string, { x: number; y: number }>();
  positions.set(centerNode.node_key, { x: 380, y: 210 });

  const outerNodes = visibleNodes.filter((node) => node.node_key !== centerNode.node_key);
  outerNodes.forEach((node, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(outerNodes.length, 1) - Math.PI / 2;
    positions.set(node.node_key, {
      x: 380 + Math.cos(angle) * 270,
      y: 210 + Math.sin(angle) * 145,
    });
  });

  return { nodes: visibleNodes, positions };
}

function nodeFill(nodeType: string) {
  if (nodeType === "company") {
    return "#1e293b";
  }
  if (nodeType.includes("industry") || nodeType.includes("segment")) {
    return "#0f766e";
  }
  if (nodeType.includes("risk")) {
    return "#7f1d1d";
  }
  return "#334155";
}

function edgeStroke(status: string) {
  if (status === "active") {
    return "#34d399";
  }
  if (status === "candidate") {
    return "#fbbf24";
  }
  if (status === "rejected") {
    return "#fb7185";
  }
  return "#64748b";
}

function shortLabel(value: string, maxLength: number) {
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, Math.max(1, maxLength - 3))}...`;
}
