import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { taurusApi } from "../api/client";
import type { JsonObject, UiRunSummary } from "../api/types";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { MetricCard } from "../components/MetricCard";
import { RefreshButton } from "../components/RefreshButton";
import { RunUniverseSummary } from "../components/RunUniverse";
import { SafetyBanner } from "../components/SafetyBanner";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { WarningsPanel } from "../components/WarningsPanel";
import {
  formatDuration,
  formatId,
  formatInr,
  formatNumber,
  formatTimestamp,
  getPrimitive,
  getString,
} from "../utils/format";
import { emptyDataCommands, PageScaffold } from "./PageScaffold";

export function OverviewPage() {
  const overviewQuery = useQuery({
    queryKey: ["ui", "overview"],
    queryFn: taurusApi.overview,
    refetchInterval: 15_000,
  });

  return (
    <PageScaffold
      actions={
        <RefreshButton
          isRefreshing={overviewQuery.isFetching}
          onRefresh={() => void overviewQuery.refetch()}
        />
      }
      eyebrow="Run overview"
      title="Paper Runs"
    >
      {overviewQuery.isLoading && <LoadingState label="Loading overview" />}
      {overviewQuery.isError && <ErrorState message={overviewQuery.error.message} />}
      {overviewQuery.data && (
        <div className="grid gap-6">
          <SafetyBanner safety={overviewQuery.data.safety} />
          <WarningsPanel warnings={overviewQuery.data.warnings} />

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Latest run"
              supportingText={overviewQuery.data.latest_run?.run_id ?? "No run"}
              value={
                overviewQuery.data.latest_run ? (
                  <StatusBadge status={overviewQuery.data.latest_run.status} />
                ) : (
                  "None"
                )
              }
            />
            <MetricCard
              label="Paper equity"
              supportingText={overviewQuery.data.latest_account ? getString(overviewQuery.data.latest_account, "run_id") : "No account"}
              value={formatInr(getPrimitive(overviewQuery.data.latest_account, "equity_inr"))}
            />
            <MetricCard
              label="Latest decision"
              supportingText={formatId(getString(overviewQuery.data.latest_final_decision, "decision_id"))}
              value={
                overviewQuery.data.latest_final_decision ? (
                  <StatusBadge status={getString(overviewQuery.data.latest_final_decision, "status")} />
                ) : (
                  "None"
                )
              }
            />
            <MetricCard
              label="Latest order"
              supportingText={formatId(getString(overviewQuery.data.latest_order, "order_id"))}
              value={
                overviewQuery.data.latest_order ? (
                  <StatusBadge status={getString(overviewQuery.data.latest_order, "status")} />
                ) : (
                  "None"
                )
              }
            />
          </div>

          {overviewQuery.data.recent_runs.length === 0 ? (
            <EmptyState
              commands={emptyDataCommands}
              message="No paper runs are available in the configured Taurus database."
              title="No run data"
            />
          ) : (
            <DataPanel title="Recent Runs">
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
                  {
                    key: "status",
                    header: "Status",
                    render: (run) => <StatusBadge status={run.status} size="sm" />,
                  },
                  {
                    key: "started",
                    header: "Started",
                    render: (run) => formatTimestamp(run.started_at),
                  },
                  {
                    key: "duration",
                    header: "Duration",
                    render: (run) => formatDuration(run.duration_seconds),
                  },
                  {
                    key: "symbols",
                    header: "Symbols",
                    render: (run) => <SymbolLinks run={run} />,
                  },
                  {
                    key: "universe",
                    header: "Universe",
                    render: (run) => <RunUniverseSummary universe={run.universe} />,
                  },
                  {
                    key: "decisions",
                    header: "Final decisions",
                    render: (run) => <StatusCounts counts={run.final_status_counts} />,
                  },
                  {
                    key: "orders",
                    header: "Orders",
                    render: (run) => <StatusCounts counts={run.order_status_counts} />,
                  },
                  { key: "errors", header: "Errors", align: "right", render: (run) => run.error_count },
                ]}
                emptyLabel="No runs"
                getRowKey={(run) => run.run_id}
                rows={overviewQuery.data.recent_runs.slice(0, 8)}
              />
            </DataPanel>
          )}

          <div className="grid gap-6 xl:grid-cols-2">
            <ArtifactCard
              artifact={overviewQuery.data.latest_final_decision}
              emptyTitle="No final decision"
              fields={[
                ["final_decision_id", "Final ID"],
                ["symbol", "Symbol"],
                ["final_action", "Action"],
                ["approved_quantity", "Approved quantity"],
                ["reason", "Reason"],
              ]}
              statusKey="status"
              title="Latest Final Decision"
            />
            <ArtifactCard
              artifact={overviewQuery.data.latest_order}
              emptyTitle="No paper order"
              fields={[
                ["order_id", "Order ID"],
                ["symbol", "Symbol"],
                ["side", "Side"],
                ["quantity", "Quantity"],
                ["filled_quantity", "Filled"],
                ["average_fill_price_inr", "Average fill"],
                ["total_cost_inr", "Costs"],
                ["slippage_bps", "Slippage"],
              ]}
              statusKey="status"
              title="Latest Paper Order"
            />
          </div>

          <DataPanel title="Active Positions">
            <DataTable
              columns={[
                { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
                { key: "quantity", header: "Qty", align: "right", render: (row) => formatNumber(getPrimitive(row, "quantity")) },
                { key: "avg", header: "Average cost", align: "right", render: (row) => formatInr(getPrimitive(row, "average_cost_inr")) },
                { key: "last", header: "Last price", align: "right", render: (row) => formatInr(getPrimitive(row, "last_price_inr")) },
                { key: "value", header: "Market value", align: "right", render: (row) => formatInr(getPrimitive(row, "market_value_inr")) },
                { key: "pnl", header: "Unrealized P&L", align: "right", render: (row) => formatInr(getPrimitive(row, "unrealized_pnl_inr")) },
              ]}
              emptyLabel="No open paper positions"
              getRowKey={(row) => `${getString(row, "run_id")}-${getString(row, "symbol")}`}
              rows={overviewQuery.data.positions}
            />
          </DataPanel>

          <JsonDrawer title="Overview payload" value={overviewQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}

function SymbolLinks({ run }: { run: UiRunSummary }) {
  if (run.symbols.length === 0) {
    return "None";
  }

  return (
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
  );
}

function StatusCounts({ counts }: { counts: Record<string, number> }) {
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

function ArtifactCard({
  artifact,
  title,
  emptyTitle,
  statusKey,
  fields,
}: {
  artifact: JsonObject | null | undefined;
  title: string;
  emptyTitle: string;
  statusKey: string;
  fields: [string, string][];
}) {
  return (
    <DataPanel
      actions={artifact ? <StatusBadge status={getString(artifact, statusKey)} size="sm" /> : undefined}
      title={title}
    >
      {!artifact ? (
        <p className="text-sm text-taurus-muted">{emptyTitle}</p>
      ) : (
        <dl className="grid gap-3 sm:grid-cols-2">
          {fields.map(([key, label]) => (
            <div className="min-w-0" key={key}>
              <dt className="text-xs uppercase text-taurus-muted">{label}</dt>
              <dd className="mt-1 break-words text-sm text-taurus-text">
                {key.endsWith("_inr")
                  ? formatInr(getPrimitive(artifact, key))
                  : key.includes("slippage")
                    ? `${formatNumber(getPrimitive(artifact, key))} bps`
                    : String(getPrimitive(artifact, key) ?? "-")}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </DataPanel>
  );
}
