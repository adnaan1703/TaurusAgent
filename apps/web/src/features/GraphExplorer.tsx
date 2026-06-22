import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Maximize2,
  Network,
  RefreshCw,
  RotateCcw,
  Search,
  ZoomIn,
  ZoomOut,
} from "lucide-react";
import type { FormEvent, ReactNode } from "react";
import { useEffect, useMemo, useRef, useState } from "react";
import {
  darkTheme,
  GraphCanvas as ReagraphCanvas,
  type GraphCanvasRef,
  type GraphEdge as ReagraphEdge,
  type GraphNode as ReagraphNode,
  type InternalGraphEdge,
  type InternalGraphNode,
} from "reagraph";

import { taurusApi } from "../api/client";
import type {
  GraphEdge,
  GraphEdgeDetailResponse,
  GraphNeighborhoodResponse,
  GraphNeighborhoodStatusFilter,
  GraphNode,
} from "../api/types";
import { DataTable } from "../components/DataTable";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import {
  formatId,
  formatNumber,
  formatPercent,
  formatTimestamp,
  humanizeKey,
} from "../utils/format";

type GraphExplorerProps = {
  symbol: string;
  payload: GraphNeighborhoodResponse;
  statuses: GraphNeighborhoodStatusFilter[];
  statusOptions: GraphNeighborhoodStatusFilter[];
  isRefreshing: boolean;
  onRefresh: () => void;
  onStatusChange: (statuses: GraphNeighborhoodStatusFilter[]) => void;
  onSymbolSubmit: (symbol: string) => void;
};

type Selection =
  | { type: "node"; id: string }
  | { type: "edge"; id: string };

type ExplorerGraphState = {
  centerNode: GraphNode;
  nodesByKey: Map<string, GraphNode>;
  edgesByKey: Map<string, GraphEdge>;
};

type NodeExpansionState = {
  error: string | null;
  expanded: boolean;
  isLoading: boolean;
  limit: number;
  returnedEdges: number;
  totalEdges: number;
  truncated: boolean;
};

type FitNodesOptions = {
  animated: boolean;
  fitOnlyIfNodesNotInView?: boolean;
};

const EDGE_TYPE_ALL = "all";
const NEIGHBORHOOD_LIMIT = 1000;

const graphTheme = {
  ...darkTheme,
  canvas: {
    background: "#07101d",
    fog: null,
  },
};

export function GraphExplorer({
  symbol,
  payload,
  statuses,
  statusOptions,
  isRefreshing,
  onRefresh,
  onStatusChange,
  onSymbolSubmit,
}: GraphExplorerProps) {
  const graphRef = useRef<GraphCanvasRef>(null);
  const [symbolDraft, setSymbolDraft] = useState(symbol);
  const [edgeTypeFilter, setEdgeTypeFilter] = useState(EDGE_TYPE_ALL);
  const [explorerGraph, setExplorerGraph] = useState<ExplorerGraphState>(() =>
    initialExplorerGraph(payload),
  );
  const [expansionsByNode, setExpansionsByNode] = useState<Record<string, NodeExpansionState>>(
    {},
  );
  const [pendingFocusNodeIds, setPendingFocusNodeIds] = useState<string[] | null>(null);
  const [selection, setSelection] = useState<Selection>({
    type: "node",
    id: payload.center_node.node_key,
  });

  const graphData = useMemo(
    () => buildVisibleGraph(explorerGraph, edgeTypeFilter),
    [explorerGraph, edgeTypeFilter],
  );
  const edgeTypes = useMemo(
    () =>
      Array.from(
        new Set(Array.from(explorerGraph.edgesByKey.values()).map((edge) => edge.edge_type)),
      ).sort(),
    [explorerGraph.edgesByKey],
  );
  const selectedNode =
    selection.type === "node" ? graphData.nodeByKey.get(selection.id) ?? null : null;
  const selectedEdge =
    selection.type === "edge" ? graphData.edgeByKey.get(selection.id) ?? null : null;

  useEffect(() => {
    setSymbolDraft(symbol);
  }, [symbol]);

  useEffect(() => {
    setExplorerGraph(initialExplorerGraph(payload));
    setExpansionsByNode({});
    setSelection({ type: "node", id: payload.center_node.node_key });
  }, [payload]);

  useEffect(() => {
    if (edgeTypeFilter !== EDGE_TYPE_ALL && !edgeTypes.includes(edgeTypeFilter)) {
      setEdgeTypeFilter(EDGE_TYPE_ALL);
    }
  }, [edgeTypeFilter, edgeTypes]);

  useEffect(() => {
    if (
      selection.type === "edge" &&
      !graphData.visibleEdges.some((edge) => edge.edge_key === selection.id)
    ) {
      setSelection({ type: "node", id: payload.center_node.node_key });
    }
  }, [graphData.visibleEdges, payload.center_node.node_key, selection]);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      fitNodesInViewSafely(graphRef.current, undefined, { animated: false });
    }, 0);
    return () => window.clearTimeout(timer);
  }, [payload]);

  useEffect(() => {
    if (!pendingFocusNodeIds) {
      return undefined;
    }

    const timer = window.setTimeout(() => {
      const renderedNodeIds = new Set(graphData.reagraphNodes.map((node) => node.id));
      const focusNodeIds = pendingFocusNodeIds.filter((nodeId) => renderedNodeIds.has(nodeId));
      fitNodesInViewSafely(graphRef.current, focusNodeIds.length > 0 ? focusNodeIds : undefined, {
        animated: true,
        fitOnlyIfNodesNotInView: true,
      });
      setPendingFocusNodeIds(null);
    }, 0);
    return () => window.clearTimeout(timer);
  }, [graphData.reagraphNodes.length, graphData.reagraphEdges.length, pendingFocusNodeIds]);

  function submitSymbol(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSymbolSubmit(symbolDraft);
  }

  function toggleStatus(status: GraphNeighborhoodStatusFilter) {
    const nextStatuses = statuses.includes(status)
      ? statuses.filter((item) => item !== status)
      : [...statuses, status];
    onStatusChange(nextStatuses);
  }

  function fitGraph() {
    fitNodesInViewSafely(graphRef.current, undefined, { animated: true });
  }

  function resetGraph() {
    setExplorerGraph(initialExplorerGraph(payload));
    setExpansionsByNode({});
    setSelection({ type: "node", id: payload.center_node.node_key });
    graphRef.current?.resetControls(true);
    fitNodesInViewSafely(graphRef.current, undefined, { animated: true });
  }

  async function expandNode(node: GraphNode) {
    const nodeKey = node.node_key;
    setExpansionsByNode((current) => ({
      ...current,
      [nodeKey]: {
        ...emptyExpansionState(),
        ...current[nodeKey],
        error: null,
        isLoading: true,
      },
    }));

    try {
      const neighborhood = await taurusApi.graphNeighborhood({
        nodeKey,
        statuses,
        limit: NEIGHBORHOOD_LIMIT,
      });
      setExplorerGraph((current) => mergeNeighborhood(current, neighborhood));
      setExpansionsByNode((current) => ({
        ...current,
        [nodeKey]: {
          error: null,
          expanded: true,
          isLoading: false,
          limit: neighborhood.limit,
          returnedEdges: neighborhood.edges.length,
          totalEdges: neighborhood.total_edges,
          truncated: neighborhood.truncated,
        },
      }));
      setPendingFocusNodeIds(expansionFocusNodeIds(neighborhood));
    } catch (error) {
      setExpansionsByNode((current) => ({
        ...current,
        [nodeKey]: {
          ...emptyExpansionState(),
          ...current[nodeKey],
          error: error instanceof Error ? error.message : "Unable to expand neighborhood",
          isLoading: false,
        },
      }));
    }
  }

  return (
    <section className="flex flex-1 flex-col overflow-hidden rounded-lg border border-taurus-outline bg-taurus-shell shadow-panel">
      <div className="flex flex-wrap items-center gap-3 border-b border-taurus-outline bg-taurus-surface px-4 py-3">
        <form className="flex min-w-64 flex-1 items-center gap-2" onSubmit={submitSymbol}>
          <input
            aria-label="Graph company symbol"
            className="min-w-0 flex-1 rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm font-medium uppercase text-taurus-text outline-none placeholder:text-taurus-muted focus:border-taurus-primary"
            onChange={(event) => setSymbolDraft(event.target.value)}
            placeholder="INFY"
            value={symbolDraft}
          />
          <button
            aria-label="Open company graph"
            className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-taurus-primary bg-sky-400/10 text-taurus-text hover:bg-sky-400/15"
            title="Open company graph"
            type="submit"
          >
            <Search aria-hidden="true" className="h-4 w-4" />
          </button>
        </form>

        <div className="flex flex-wrap items-center gap-2" aria-label="Graph edge status filters">
          {statusOptions.map((status) => (
            <button
              aria-pressed={statuses.includes(status)}
              className={clsx(
                "rounded-md border px-3 py-2 text-xs font-semibold uppercase transition",
                statuses.includes(status)
                  ? statusChipClass(status)
                  : "border-taurus-outline bg-taurus-shell text-taurus-muted hover:border-taurus-primary hover:text-taurus-text",
              )}
              key={status}
              onClick={() => toggleStatus(status)}
              type="button"
            >
              {humanizeKey(status)}
            </button>
          ))}
        </div>

        <select
          aria-label="Graph edge type"
          className="h-9 rounded-md border border-taurus-outline bg-taurus-shell px-3 text-sm text-taurus-text outline-none focus:border-taurus-primary"
          onChange={(event) => setEdgeTypeFilter(event.target.value)}
          value={edgeTypeFilter}
        >
          <option value={EDGE_TYPE_ALL}>All edge types</option>
          {edgeTypes.map((edgeType) => (
            <option key={edgeType} value={edgeType}>
              {humanizeKey(edgeType)}
            </option>
          ))}
        </select>

        <div className="flex items-center gap-2">
          <ToolbarIconButton label="Fit view" onClick={fitGraph}>
            <Maximize2 aria-hidden="true" className="h-4 w-4" />
          </ToolbarIconButton>
          <ToolbarIconButton label="Zoom in" onClick={() => graphRef.current?.zoomIn()}>
            <ZoomIn aria-hidden="true" className="h-4 w-4" />
          </ToolbarIconButton>
          <ToolbarIconButton label="Zoom out" onClick={() => graphRef.current?.zoomOut()}>
            <ZoomOut aria-hidden="true" className="h-4 w-4" />
          </ToolbarIconButton>
          <ToolbarIconButton label="Reset graph" onClick={resetGraph}>
            <RotateCcw aria-hidden="true" className="h-4 w-4" />
          </ToolbarIconButton>
          <ToolbarIconButton disabled={isRefreshing} label="Refresh graph" onClick={onRefresh}>
            <RefreshCw
              aria-hidden="true"
              className={clsx("h-4 w-4", isRefreshing && "animate-spin")}
            />
          </ToolbarIconButton>
        </div>
      </div>

      <div className="grid min-h-[34rem] flex-1 lg:min-h-[calc(100vh-17rem)] lg:grid-cols-[minmax(0,1fr)_24rem]">
        <div className="relative min-h-[34rem] overflow-hidden bg-[#07101d] lg:min-h-0">
          <ReagraphCanvas
            actives={[payload.center_node.node_key]}
            animated
            cameraMode="pan"
            defaultNodeSize={8}
            edgeArrowPosition="end"
            edgeInterpolation="curved"
            edgeLabelPosition="inline"
            edges={graphData.reagraphEdges}
            labelType="all"
            layoutType="forceDirected2d"
            maxDistance={50000}
            minDistance={200}
            nodes={graphData.reagraphNodes}
            onCanvasClick={() => setSelection({ type: "node", id: payload.center_node.node_key })}
            onEdgeClick={(edge: InternalGraphEdge) => setSelection({ type: "edge", id: edge.id })}
            onNodeClick={(node: InternalGraphNode) => setSelection({ type: "node", id: node.id })}
            ref={graphRef}
            selections={[selection.id]}
            theme={graphTheme}
          />
          {graphData.visibleEdges.length === 0 && (
            <div className="pointer-events-none absolute inset-x-4 bottom-4 rounded-md border border-dashed border-taurus-outline bg-taurus-shell/90 p-4 text-sm text-taurus-muted">
              No loaded edges match the current filters.
            </div>
          )}
        </div>

        <aside className="min-h-0 overflow-y-auto border-t border-taurus-outline bg-taurus-surface p-4 lg:border-l lg:border-t-0">
          <div className="grid gap-4">
            <div className="grid grid-cols-2 gap-3">
              <MiniMetric label="Nodes" value={formatNumber(graphData.visibleNodes.length)} />
              <MiniMetric label="Edges" value={formatNumber(graphData.visibleEdges.length)} />
              <MiniMetric label="Returned" value={formatNumber(payload.edges.length)} />
              <MiniMetric label="Total" value={formatNumber(payload.total_edges)} />
            </div>
            {payload.truncated && (
              <div className="rounded-md border border-amber-300/40 bg-amber-300/10 p-3 text-xs font-medium text-amber-100">
                Returned {formatNumber(payload.limit)} of {formatNumber(payload.total_edges)} matching edges.
              </div>
            )}
            <Inspector
              detailEdgeKey={selectedEdge?.edge_key ?? null}
              edge={selectedEdge}
              expansion={selectedNode ? expansionsByNode[selectedNode.node_key] : undefined}
              onExpandNode={expandNode}
              node={selectedNode}
              payload={payload}
              visibleEdges={graphData.visibleEdges}
            />
          </div>
        </aside>
      </div>
    </section>
  );
}

function initialExplorerGraph(payload: GraphNeighborhoodResponse): ExplorerGraphState {
  const nodesByKey = new Map<string, GraphNode>();
  uniqueNodes([payload.center_node, ...payload.nodes]).forEach((node) =>
    nodesByKey.set(node.node_key, node),
  );
  const edgesByKey = new Map<string, GraphEdge>();
  payload.edges.forEach((edge) => edgesByKey.set(edge.edge_key, edge));
  return {
    centerNode: payload.center_node,
    nodesByKey,
    edgesByKey,
  };
}

function mergeNeighborhood(
  current: ExplorerGraphState,
  neighborhood: GraphNeighborhoodResponse,
): ExplorerGraphState {
  const nodesByKey = new Map(current.nodesByKey);
  uniqueNodes([neighborhood.center_node, ...neighborhood.nodes]).forEach((node) =>
    nodesByKey.set(node.node_key, node),
  );
  const edgesByKey = new Map(current.edgesByKey);
  neighborhood.edges.forEach((edge) => edgesByKey.set(edge.edge_key, edge));
  return {
    ...current,
    nodesByKey,
    edgesByKey,
  };
}

function expansionFocusNodeIds(neighborhood: GraphNeighborhoodResponse) {
  return Array.from(
    new Set([
      neighborhood.center_node.node_key,
      ...neighborhood.nodes.map((node) => node.node_key),
    ]),
  );
}

function fitNodesInViewSafely(
  graph: GraphCanvasRef | null,
  nodeIds: string[] | undefined,
  options: FitNodesOptions,
) {
  try {
    graph?.fitNodesInView(nodeIds, options);
  } catch {
    try {
      graph?.fitNodesInView(undefined, { animated: options.animated });
    } catch {
      // Reagraph may reject fit requests while a large expanded graph is still settling.
    }
  }
}

function emptyExpansionState(): NodeExpansionState {
  return {
    error: null,
    expanded: false,
    isLoading: false,
    limit: NEIGHBORHOOD_LIMIT,
    returnedEdges: 0,
    totalEdges: 0,
    truncated: false,
  };
}

function buildVisibleGraph(graph: ExplorerGraphState, edgeTypeFilter: string) {
  const allNodes = Array.from(graph.nodesByKey.values());
  const nodeByKey = new Map(allNodes.map((node) => [node.node_key, node]));
  const allEdges = Array.from(graph.edgesByKey.values());
  const filteredEdges =
    edgeTypeFilter === EDGE_TYPE_ALL
      ? allEdges
      : allEdges.filter((edge) => edge.edge_type === edgeTypeFilter);
  const visibleEdges = filteredEdges.filter(
    (edge) => nodeByKey.has(edge.source_node_key) && nodeByKey.has(edge.target_node_key),
  );
  const visibleNodeKeys = new Set<string>([graph.centerNode.node_key]);
  visibleEdges.forEach((edge) => {
    visibleNodeKeys.add(edge.source_node_key);
    visibleNodeKeys.add(edge.target_node_key);
  });
  const visibleNodes = allNodes.filter((node) => visibleNodeKeys.has(node.node_key));
  const edgeByKey = new Map(visibleEdges.map((edge) => [edge.edge_key, edge]));

  return {
    nodeByKey,
    edgeByKey,
    visibleNodes,
    visibleEdges,
    reagraphNodes: visibleNodes.map((node) => toReagraphNode(node, graph.centerNode.node_key)),
    reagraphEdges: visibleEdges.map(toReagraphEdge),
  };
}

function uniqueNodes(nodes: GraphNode[]) {
  const byKey = new Map<string, GraphNode>();
  nodes.forEach((node) => byKey.set(node.node_key, node));
  return Array.from(byKey.values());
}

function toReagraphNode(node: GraphNode, centerNodeKey: string): ReagraphNode {
  const isCenter = node.node_key === centerNodeKey;
  return {
    id: node.node_key,
    label: node.symbol || node.display_name || node.node_key,
    subLabel: humanizeKey(node.node_type),
    size: isCenter ? 13 : 9,
    fill: nodeFill(node.node_type, isCenter),
    data: node,
  };
}

function toReagraphEdge(edge: GraphEdge): ReagraphEdge {
  return {
    id: edge.edge_key,
    source: edge.source_node_key,
    target: edge.target_node_key,
    label: humanizeKey(edge.edge_type),
    subLabel: humanizeKey(edge.provenance_type),
    fill: edgeStroke(edge.status),
    dashed: edge.status !== "active",
    data: edge,
  };
}

function Inspector({
  detailEdgeKey,
  edge,
  expansion,
  node,
  onExpandNode,
  payload,
  visibleEdges,
}: {
  detailEdgeKey: string | null;
  edge: GraphEdge | null;
  expansion?: NodeExpansionState;
  node: GraphNode | null;
  onExpandNode: (node: GraphNode) => void;
  payload: GraphNeighborhoodResponse;
  visibleEdges: GraphEdge[];
}) {
  const detailQuery = useQuery({
    queryKey: ["graph", "edge", detailEdgeKey],
    queryFn: () => taurusApi.graphEdgeDetail(detailEdgeKey ?? ""),
    enabled: Boolean(detailEdgeKey),
  });

  if (edge) {
    return (
      <EdgeInspector
        detail={detailQuery.data ?? null}
        edge={edge}
        isError={detailQuery.isError}
        isLoading={detailQuery.isLoading}
        message={detailQuery.error?.message}
      />
    );
  }

  return (
    <NodeInspector
      expansion={expansion}
      node={node ?? payload.center_node}
      onExpandNode={onExpandNode}
      visibleEdges={visibleEdges}
    />
  );
}

function NodeInspector({
  expansion,
  node,
  onExpandNode,
  visibleEdges,
}: {
  expansion?: NodeExpansionState;
  node: GraphNode;
  onExpandNode: (node: GraphNode) => void;
  visibleEdges: GraphEdge[];
}) {
  const connectedEdges = visibleEdges.filter(
    (edge) => edge.source_node_key === node.node_key || edge.target_node_key === node.node_key,
  );
  const expansionState = expansion ?? emptyExpansionState();

  return (
    <section className="rounded-md border border-taurus-outline bg-taurus-shell p-4">
      <p className="text-xs font-semibold uppercase text-taurus-primary">Node inspector</p>
      <h2 className="mt-2 break-words text-lg font-semibold text-taurus-text">
        {node.display_name || node.node_key}
      </h2>
      <p className="mt-1 break-all font-mono text-xs text-taurus-muted">{node.node_key}</p>
      <div className="mt-4 flex flex-wrap gap-2">
        <Badge>{humanizeKey(node.node_type)}</Badge>
        {node.symbol && <Badge>{node.symbol}</Badge>}
        {node.isin && <Badge>{node.isin}</Badge>}
      </div>
      <div className="mt-4 grid gap-3 text-sm">
        <KeyValue label="Visible edges" value={formatNumber(connectedEdges.length)} />
        <KeyValue label="Created" value={formatTimestamp(node.created_at)} />
        <KeyValue label="Updated" value={formatTimestamp(node.updated_at)} />
      </div>
      <div className="mt-5 border-t border-taurus-outline pt-4">
        <button
          aria-label={expansionState.expanded ? "Refresh neighborhood" : "Expand neighborhood"}
          className="inline-flex w-full items-center justify-center gap-2 rounded-md border border-taurus-primary bg-sky-400/10 px-3 py-2 text-sm font-semibold text-taurus-text transition hover:bg-sky-400/15 disabled:opacity-50"
          disabled={expansionState.isLoading}
          onClick={() => onExpandNode(node)}
          type="button"
        >
          <Network aria-hidden="true" className="h-4 w-4" />
          {expansionState.isLoading
            ? "Expanding..."
            : expansionState.expanded
              ? "Refresh neighborhood"
              : "Expand neighborhood"}
        </button>
        {expansionState.error && (
          <div className="mt-3">
            <ErrorState message={expansionState.error} />
          </div>
        )}
        {expansionState.expanded && !expansionState.error && (
          <div className="mt-4 grid gap-3 text-sm">
            <KeyValue label="Loaded edges" value={formatNumber(expansionState.returnedEdges)} />
            <KeyValue label="Total matching" value={formatNumber(expansionState.totalEdges)} />
            {expansionState.truncated && (
              <div className="rounded-md border border-amber-300/40 bg-amber-300/10 p-3 text-xs font-medium text-amber-100">
                Returned {formatNumber(expansionState.returnedEdges)} of{" "}
                {formatNumber(expansionState.totalEdges)} matching edges for this node.
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}

function EdgeInspector({
  detail,
  edge,
  isError,
  isLoading,
  message,
}: {
  detail: GraphEdgeDetailResponse | null;
  edge: GraphEdge;
  isError: boolean;
  isLoading: boolean;
  message?: string;
}) {
  return (
    <section className="rounded-md border border-taurus-outline bg-taurus-shell p-4">
      <p className="text-xs font-semibold uppercase text-taurus-primary">Edge inspector</p>
      <h2 className="mt-2 break-all text-lg font-semibold text-taurus-text">
        {formatId(edge.edge_key)}
      </h2>
      <div className="mt-4 flex flex-wrap gap-2">
        <StatusBadge status={edge.status} size="sm" />
        <Badge>{humanizeKey(edge.edge_type)}</Badge>
        <Badge>{humanizeKey(edge.provenance_type)}</Badge>
      </div>
      <div className="mt-4 grid gap-3 text-sm">
        <KeyValue label="Source" value={edge.source_display_name || edge.source_node_key} />
        <KeyValue label="Target" value={edge.target_display_name || edge.target_node_key} />
        <KeyValue label="Confidence" value={formatPercent(edge.confidence)} />
        <KeyValue label="Strength" value={formatNumber(edge.strength ?? undefined)} />
      </div>
      <p className="mt-4 text-sm leading-6 text-slate-200">
        {edge.mechanism || "No mechanism recorded."}
      </p>

      <div className="mt-5 grid gap-4">
        {isLoading && <LoadingState label="Loading edge detail" />}
        {isError && <ErrorState message={message ?? "Unable to load edge detail"} />}
        {detail && (
          <>
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
            <DataTable
              columns={[
                { key: "window", header: "Window", render: (item) => item.window },
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
          </>
        )}
      </div>
    </section>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-md border border-taurus-outline bg-taurus-shell p-3">
      <p className="text-xs font-medium uppercase text-taurus-muted">{label}</p>
      <p className="mt-1 text-lg font-semibold text-taurus-text">{value}</p>
    </div>
  );
}

function KeyValue({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase text-taurus-muted">{label}</p>
      <p className="mt-1 break-words text-taurus-text">{value || "-"}</p>
    </div>
  );
}

function ToolbarIconButton({
  children,
  disabled = false,
  label,
  onClick,
}: {
  children: ReactNode;
  disabled?: boolean;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      aria-label={label}
      className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-taurus-outline bg-taurus-shell text-taurus-muted transition hover:border-taurus-primary hover:text-taurus-text disabled:opacity-50"
      disabled={disabled}
      onClick={onClick}
      title={label}
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

function statusChipClass(status: GraphNeighborhoodStatusFilter) {
  if (status === "active") {
    return "border-emerald-300/50 bg-emerald-300/10 text-emerald-100";
  }
  if (status === "candidate") {
    return "border-amber-300/50 bg-amber-300/10 text-amber-100";
  }
  return "border-rose-300/50 bg-rose-300/10 text-rose-100";
}

function nodeFill(nodeType: string, isCenter: boolean) {
  if (isCenter) {
    return "#38bdf8";
  }
  if (nodeType === "company") {
    return "#1e293b";
  }
  if (nodeType.includes("industry") || nodeType.includes("segment")) {
    return "#0f766e";
  }
  if (nodeType.includes("risk")) {
    return "#7f1d1d";
  }
  if (nodeType.includes("product")) {
    return "#6d28d9";
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
