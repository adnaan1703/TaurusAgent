import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { taurusApi } from "../api/client";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { RefreshButton } from "../components/RefreshButton";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { emptyDataCommands, PageScaffold } from "./PageScaffold";

export function HistoryPage() {
  const historyQuery = useQuery({
    queryKey: ["ui", "history"],
    queryFn: taurusApi.history,
    refetchInterval: 15_000,
  });

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
                  { key: "symbols", header: "Symbols", render: (run) => run.symbols.join(", ") || "None" },
                  { key: "errors", header: "Errors", align: "right", render: (run) => run.error_count },
                ]}
                getRowKey={(run) => run.run_id}
                rows={historyQuery.data.runs}
              />
            </DataPanel>
          )}
          <JsonDrawer title="History payload" value={historyQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}
