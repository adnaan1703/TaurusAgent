import { useQuery } from "@tanstack/react-query";
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
          <div className="grid gap-4 md:grid-cols-3">
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
              label="Recent runs"
              value={overviewQuery.data.recent_runs.length}
            />
            <MetricCard
              label="Positions"
              value={overviewQuery.data.positions.length}
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
                  { key: "status", header: "Status", render: (run) => <StatusBadge status={run.status} size="sm" /> },
                  { key: "symbols", header: "Symbols", render: (run) => run.symbols.join(", ") || "None" },
                  { key: "errors", header: "Errors", align: "right", render: (run) => run.error_count },
                ]}
                emptyLabel="No runs"
                getRowKey={(run) => run.run_id}
                rows={overviewQuery.data.recent_runs.slice(0, 8)}
              />
            </DataPanel>
          )}

          <JsonDrawer title="Overview payload" value={overviewQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}
