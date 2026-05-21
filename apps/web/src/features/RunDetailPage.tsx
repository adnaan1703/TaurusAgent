import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { taurusApi } from "../api/client";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { RefreshButton } from "../components/RefreshButton";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
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
          <DataPanel title="Run Status">
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge status={runQuery.data.run.status} />
              <span className="font-mono text-sm text-taurus-muted">{runQuery.data.run.schedule_name}</span>
            </div>
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
                  { key: "pipeline", header: "Pipeline", render: (row) => <StatusBadge status={row.pipeline_status} size="sm" /> },
                  { key: "final", header: "Final", render: (row) => <StatusBadge status={row.final_status} size="sm" /> },
                  { key: "order", header: "Order", render: (row) => <StatusBadge status={row.order_status} size="sm" /> },
                ]}
                getRowKey={(row) => row.symbol}
                rows={runQuery.data.symbols}
              />
            </DataPanel>
          )}

          <JsonDrawer title="Run payload" value={runQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}
