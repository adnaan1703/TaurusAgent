import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import { taurusApi } from "../api/client";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { MetricCard } from "../components/MetricCard";
import { RefreshButton } from "../components/RefreshButton";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import {
  formatDuration,
  formatNumber,
  formatTimestamp,
  getString,
  isJsonObject,
} from "../utils/format";
import { emptyDataCommands, PageScaffold } from "./PageScaffold";

export function HistoryPage() {
  const [search, setSearch] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [symbolFilter, setSymbolFilter] = useState("all");
  const historyQuery = useQuery({
    queryKey: ["ui", "history"],
    queryFn: taurusApi.history,
    refetchInterval: 15_000,
  });

  const filters = useMemo(() => {
    const metadata = historyQuery.data?.filters_metadata;
    const statuses = Array.isArray(metadata?.statuses) ? metadata.statuses.map(String) : [];
    const symbols = Array.isArray(metadata?.symbols) ? metadata.symbols.map(String) : [];
    const dateRange = isJsonObject(metadata?.date_range) ? metadata.date_range : null;
    return {
      statuses,
      symbols,
      dateStart: getString(dateRange, "start"),
      dateEnd: getString(dateRange, "end"),
    };
  }, [historyQuery.data]);

  const filteredRuns = useMemo(() => {
    const normalizedSearch = search.trim().toUpperCase();
    return (historyQuery.data?.runs ?? []).filter((run) => {
      const matchesSearch =
        normalizedSearch.length === 0 ||
        run.run_id.toUpperCase().includes(normalizedSearch) ||
        run.symbols.some((symbol) => symbol.toUpperCase().includes(normalizedSearch));
      const matchesStatus = statusFilter === "all" || run.status === statusFilter;
      const matchesSymbol = symbolFilter === "all" || run.symbols.includes(symbolFilter);
      return matchesSearch && matchesStatus && matchesSymbol;
    });
  }, [historyQuery.data, search, statusFilter, symbolFilter]);

  return (
    <PageScaffold
      actions={<RefreshButton isRefreshing={historyQuery.isFetching} onRefresh={() => void historyQuery.refetch()} />}
      eyebrow="Run history"
      title="History"
    >
      {historyQuery.isLoading && <LoadingState label="Loading history" />}
      {historyQuery.isError && <ErrorState message={historyQuery.error.message} />}
      {historyQuery.data && (
        <div className="grid gap-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {Object.entries(historyQuery.data.status_counts).length === 0 ? (
              <MetricCard label="Runs" value="None" />
            ) : (
              Object.entries(historyQuery.data.status_counts).map(([status, count]) => (
                <MetricCard
                  key={status}
                  label={status.replace(/_/g, " ")}
                  value={<StatusBadge label={`${formatNumber(count)} run(s)`} status={status} />}
                />
              ))
            )}
          </div>

          <DataPanel title="Filters">
            <div className="grid gap-3 md:grid-cols-3">
              <input
                className="rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none placeholder:text-taurus-muted focus:border-taurus-primary"
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search run ID or symbol"
                value={search}
              />
              <select
                className="rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none focus:border-taurus-primary"
                onChange={(event) => setStatusFilter(event.target.value)}
                value={statusFilter}
              >
                <option value="all">All statuses</option>
                {filters.statuses.map((status) => (
                  <option key={status} value={status}>
                    {status}
                  </option>
                ))}
              </select>
              <select
                className="rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none focus:border-taurus-primary"
                onChange={(event) => setSymbolFilter(event.target.value)}
                value={symbolFilter}
              >
                <option value="all">All symbols</option>
                {filters.symbols.map((symbol) => (
                  <option key={symbol} value={symbol}>
                    {symbol}
                  </option>
                ))}
              </select>
            </div>
            <p className="mt-3 text-xs text-taurus-muted">
              Range: {formatTimestamp(filters.dateStart)} to {formatTimestamp(filters.dateEnd)}
            </p>
          </DataPanel>

          {historyQuery.data.runs.length === 0 ? (
            <EmptyState commands={emptyDataCommands} message="No historical runs are available." title="No history" />
          ) : (
            <DataPanel title="Runs">
              <DataTable
                columns={[
                  {
                    key: "run",
                    header: "Run",
                    render: (run) => (
                      <Link className="font-mono text-taurus-primary hover:text-sky-200" to={`/runs/${run.run_id}`}>
                        {run.run_id}
                      </Link>
                    ),
                  },
                  { key: "status", header: "Status", render: (run) => <StatusBadge status={run.status} size="sm" /> },
                  { key: "started", header: "Started", render: (run) => formatTimestamp(run.started_at) },
                  { key: "duration", header: "Duration", render: (run) => formatDuration(run.duration_seconds) },
                  {
                    key: "symbols",
                    header: "Symbols",
                    render: (run) => (
                      <div className="flex flex-wrap gap-2">
                        {run.symbols.map((symbol) => (
                          <Link
                            className="rounded border border-taurus-outline bg-taurus-shell px-2 py-1 font-mono text-xs text-taurus-primary hover:border-taurus-primary"
                            key={symbol}
                            to={`/runs/${run.run_id}/symbols/${symbol}`}
                          >
                            {symbol}
                          </Link>
                        ))}
                      </div>
                    ),
                  },
                  {
                    key: "success",
                    header: "Succeeded / failed",
                    render: (run) => `${run.succeeded_symbols.length} / ${run.failed_symbols.length}`,
                  },
                  {
                    key: "final",
                    header: "Final statuses",
                    render: (run) => <CompactStatusCounts counts={run.final_status_counts} />,
                  },
                  {
                    key: "orders",
                    header: "Orders",
                    render: (run) => <CompactStatusCounts counts={run.order_status_counts} />,
                  },
                  { key: "errors", header: "Errors", align: "right", render: (run) => run.error_count },
                ]}
                emptyLabel="No runs match the selected filters"
                getRowKey={(run) => run.run_id}
                rows={filteredRuns}
              />
            </DataPanel>
          )}
          <JsonDrawer title="History payload" value={historyQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}

function CompactStatusCounts({ counts }: { counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  if (entries.length === 0) {
    return <span className="text-taurus-muted">None</span>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {entries.map(([status, count]) => (
        <span className="inline-flex items-center gap-1" key={status}>
          <StatusBadge status={status} size="sm" />
          <span className="text-xs text-taurus-muted">{count}</span>
        </span>
      ))}
    </div>
  );
}
