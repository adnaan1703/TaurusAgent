import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { taurusApi } from "../api/client";
import type { UiRunDetailResponse } from "../api/types";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { KeyValueGrid } from "../components/KeyValueGrid";
import { MetricCard } from "../components/MetricCard";
import { RefreshButton } from "../components/RefreshButton";
import { SafetyBanner } from "../components/SafetyBanner";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { WarningsPanel } from "../components/WarningsPanel";
import {
  formatDuration,
  formatId,
  formatNumber,
  formatTimestamp,
  objectEntries,
} from "../utils/format";
import { PageScaffold } from "./PageScaffold";

export function RunDetailPage() {
  const { runId = "" } = useParams();
  const runQuery = useQuery({
    queryKey: ["ui", "run", runId],
    queryFn: () => taurusApi.run(runId),
    enabled: runId.length > 0,
    refetchInterval: (query) => (query.state.data?.run.status === "RUNNING" ? 5_000 : false),
  });

  return (
    <PageScaffold
      actions={<RefreshButton isRefreshing={runQuery.isFetching} onRefresh={() => void runQuery.refetch()} />}
      eyebrow="Run detail"
      title={runId || "Run"}
    >
      {runQuery.isLoading && <LoadingState label="Loading run" />}
      {runQuery.isError && <ErrorState message={runQuery.error.message} />}
      {runQuery.data && (
        <div className="grid gap-6">
          <SafetyBanner safety={runQuery.data.safety} />
          <WarningsPanel warnings={runQuery.data.warnings} />

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Run status"
              supportingText={runQuery.data.run.run_id}
              value={<StatusBadge status={runQuery.data.run.status} />}
            />
            <MetricCard
              label="Duration"
              supportingText={`${formatTimestamp(runQuery.data.run.started_at)} -> ${formatTimestamp(runQuery.data.run.completed_at)}`}
              value={formatDuration(runQuery.data.run.duration_seconds)}
            />
            <MetricCard
              label="Symbols"
              supportingText={`${runQuery.data.run.succeeded_symbols.length} succeeded, ${runQuery.data.run.failed_symbols.length} failed`}
              value={runQuery.data.run.symbols.length}
            />
            <MetricCard
              label="Schedule"
              supportingText={runQuery.data.run.timezone}
              value={runQuery.data.run.schedule_name}
            />
          </div>

          <DataPanel title="Run Metadata">
            <KeyValueGrid
              items={[
                { label: "Started", value: formatTimestamp(runQuery.data.run.started_at) },
                { label: "Completed", value: formatTimestamp(runQuery.data.run.completed_at) },
                { label: "Timezone", value: runQuery.data.run.timezone },
                {
                  label: "After market close",
                  value: runQuery.data.run.run_after_market_close ? "Yes" : "No",
                },
                { label: "Market provider", value: runQuery.data.run.market_provider ?? "-" },
                { label: "Error count", value: formatNumber(runQuery.data.run.error_count) },
              ]}
            />
          </DataPanel>

          {runQuery.data.symbols.length === 0 ? (
            <EmptyState message="This run does not contain symbol rows." title="No symbols" />
          ) : (
            <DataPanel title="Symbols">
              <DataTable
                columns={[
                  {
                    key: "symbol",
                    header: "Symbol",
                    render: (row) => (
                      <Link className="font-semibold text-taurus-primary hover:text-sky-200" to={`/runs/${row.run_id}/symbols/${row.symbol}`}>
                        {row.symbol}
                      </Link>
                    ),
                  },
                  {
                    key: "pipeline",
                    header: "Pipeline",
                    render: (row) => <StatusBadge status={row.pipeline_status} size="sm" />,
                  },
                  {
                    key: "decision",
                    header: "Decision",
                    render: (row) =>
                      row.decision_id ? (
                        <Link className="font-mono text-xs text-taurus-primary hover:text-sky-200" to={`/replay/${row.decision_id}`}>
                          {formatId(row.decision_id)}
                        </Link>
                      ) : (
                        <span className="text-taurus-muted">-</span>
                      ),
                  },
                  {
                    key: "final",
                    header: "Final",
                    render: (row) => (
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusBadge status={row.final_status} size="sm" />
                        {row.final_action && <span className="text-xs text-taurus-muted">{row.final_action}</span>}
                      </div>
                    ),
                  },
                  {
                    key: "order",
                    header: "Order",
                    render: (row) => <StatusBadge status={row.order_status} size="sm" />,
                  },
                  {
                    key: "stages",
                    header: "Stage progress",
                    render: (row) => (
                      <div className="flex max-w-xl flex-wrap gap-1.5">
                        {row.stages.map((stage) => (
                          <StatusBadge
                            key={stage.id}
                            label={stage.label}
                            status={stage.status}
                            size="sm"
                          />
                        ))}
                      </div>
                    ),
                  },
                  {
                    key: "analysts",
                    header: "Analysts",
                    render: (row) => <AnalystRosterSummary row={row} />,
                  },
                ]}
                getRowKey={(row) => row.symbol}
                rows={runQuery.data.symbols}
              />
            </DataPanel>
          )}

          <div className="grid gap-6 xl:grid-cols-2">
            <DataPanel title="Market Data Summary">
              <KeyValueGrid items={objectEntries(runQuery.data.market_data_summary)} />
            </DataPanel>
            <DataPanel title="Strategy Summary">
              <KeyValueGrid items={objectEntries(runQuery.data.strategy_summary)} />
            </DataPanel>
          </div>

          <DataPanel title="Run Errors">
            <DataTable
              columns={[
                { key: "symbol", header: "Symbol", render: (row) => String(row.symbol ?? "*") },
                { key: "stage", header: "Stage", render: (row) => String(row.stage ?? "-") },
                { key: "type", header: "Type", render: (row) => String(row.error_type ?? "-") },
                { key: "message", header: "Message", render: (row) => String(row.message ?? "-") },
              ]}
              emptyLabel="No run errors"
              getRowKey={(row) => `${String(row.symbol ?? "*")}-${String(row.stage ?? "")}-${String(row.message ?? "")}`}
              rows={runQuery.data.errors}
            />
          </DataPanel>

          <JsonDrawer title="Run payload" value={runQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}

function AnalystRosterSummary({
  row,
}: {
  row: UiRunDetailResponse["symbols"][number];
}) {
  const roster = row.analyst_roster;
  if (!roster) {
    return <span className="text-taurus-muted">Not recorded</span>;
  }

  return (
    <div className="space-y-1 text-xs">
      <p className="text-taurus-text">
        {roster.enabled.length} enabled, {roster.skipped.length} skipped
      </p>
      <p className="text-taurus-muted">
        Reports: {roster.report_count}/{roster.min_required}
      </p>
    </div>
  );
}
