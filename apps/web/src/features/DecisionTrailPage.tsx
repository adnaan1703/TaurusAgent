import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { taurusApi } from "../api/client";
import { DataPanel } from "../components/DataPanel";
import { JsonDrawer } from "../components/JsonDrawer";
import { RefreshButton } from "../components/RefreshButton";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { PageScaffold } from "./PageScaffold";

export function DecisionTrailPage() {
  const { runId = "", symbol = "" } = useParams();
  const trailQuery = useQuery({
    queryKey: ["ui", "decision-trail", runId, symbol],
    queryFn: () => taurusApi.decisionTrail(runId, symbol),
    enabled: runId.length > 0 && symbol.length > 0,
    refetchInterval: (query) => (query.state.data?.run.status === "RUNNING" ? 5_000 : false),
  });

  return (
    <PageScaffold
      actions={<RefreshButton isRefreshing={trailQuery.isFetching} onRefresh={() => void trailQuery.refetch()} />}
      eyebrow="Decision trail"
      title={`${symbol || "Symbol"} in ${runId || "run"}`}
    >
      {trailQuery.isLoading && <LoadingState label="Loading decision trail" />}
      {trailQuery.isError && <ErrorState message={trailQuery.error.message} />}
      {trailQuery.data && (
        <div className="grid gap-6">
          <DataPanel title="Outcome">
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge status={trailQuery.data.final_status} />
              <span className="font-mono text-sm text-taurus-muted">
                {trailQuery.data.decision_id ?? "No decision ID"}
              </span>
            </div>
          </DataPanel>

          <DataPanel title="Stages">
            <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {trailQuery.data.stages.map((stage) => (
                <li className="rounded-md border border-taurus-outline bg-taurus-shell p-4" key={stage.id}>
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="font-medium text-taurus-text">{stage.label}</p>
                      <p className="mt-2 text-sm text-taurus-muted">{stage.summary}</p>
                    </div>
                    <StatusBadge status={stage.status} size="sm" />
                  </div>
                </li>
              ))}
            </ol>
          </DataPanel>

          <JsonDrawer title="Decision trail payload" value={trailQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}
