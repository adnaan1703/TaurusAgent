import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { taurusApi } from "../api/client";
import { DataPanel } from "../components/DataPanel";
import { JsonDrawer } from "../components/JsonDrawer";
import { RefreshButton } from "../components/RefreshButton";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { PageScaffold } from "./PageScaffold";

export function ReplayPage() {
  const { decisionId = "" } = useParams();
  const replayQuery = useQuery({
    queryKey: ["ui", "replay", decisionId],
    queryFn: () => taurusApi.replay(decisionId),
    enabled: decisionId.length > 0,
  });

  return (
    <PageScaffold
      actions={<RefreshButton isRefreshing={replayQuery.isFetching} onRefresh={() => void replayQuery.refetch()} />}
      eyebrow="Decision replay"
      title={decisionId || "Decision"}
    >
      {replayQuery.isLoading && <LoadingState label="Loading replay" />}
      {replayQuery.isError && <ErrorState message={replayQuery.error.message} />}
      {replayQuery.data && (
        <div className="grid gap-6">
          <DataPanel title="Replay">
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge status={replayQuery.data.status} />
              <span className="font-mono text-sm text-taurus-muted">{replayQuery.data.run_id}</span>
              <span className="font-mono text-sm text-taurus-muted">{replayQuery.data.symbol}</span>
            </div>
          </DataPanel>
          <DataPanel title="Stages">
            <div className="grid gap-3">
              {replayQuery.data.stages.map((stage) => (
                <details className="rounded-md border border-taurus-outline bg-taurus-shell" key={stage.id}>
                  <summary className="cursor-pointer px-4 py-3 text-sm font-medium text-taurus-text">
                    {stage.label}
                  </summary>
                  <div className="border-t border-taurus-outline px-4 py-3 text-sm text-taurus-muted">
                    {stage.summary}
                  </div>
                </details>
              ))}
            </div>
          </DataPanel>
          <JsonDrawer title="Replay payload" value={replayQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}
