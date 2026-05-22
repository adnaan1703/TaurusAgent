import { useQuery } from "@tanstack/react-query";
import { FormEvent, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { taurusApi } from "../api/client";
import type { JsonObject, UiTimelineStage } from "../api/types";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { JsonDrawer } from "../components/JsonDrawer";
import { MetricCard } from "../components/MetricCard";
import { RefreshButton } from "../components/RefreshButton";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import {
  formatId,
  formatMetricValue,
  formatNumber,
  formatTimestamp,
  getPrimitive,
  getString,
  objectEntries,
} from "../utils/format";
import { PageScaffold } from "./PageScaffold";

export function ReplayPage() {
  const { decisionId = "" } = useParams();
  const navigate = useNavigate();
  const [searchValue, setSearchValue] = useState(decisionId);
  const replayQuery = useQuery({
    queryKey: ["ui", "replay", decisionId],
    queryFn: () => taurusApi.replay(decisionId),
    enabled: decisionId.length > 0,
  });

  useEffect(() => {
    setSearchValue(decisionId);
  }, [decisionId]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextDecisionId = searchValue.trim();
    if (nextDecisionId) {
      navigate(`/replay/${nextDecisionId}`);
    }
  }

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
          <DataPanel title="Open Replay">
            <form className="flex flex-col gap-3 sm:flex-row" onSubmit={handleSubmit}>
              <input
                className="min-w-0 flex-1 rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 font-mono text-sm text-taurus-text outline-none transition placeholder:text-taurus-muted focus:border-taurus-primary"
                onChange={(event) => setSearchValue(event.target.value)}
                placeholder="decision_id"
                value={searchValue}
              />
              <button
                className="rounded-md border border-taurus-outline bg-taurus-surfaceRaised px-4 py-2 text-sm font-medium text-taurus-text hover:border-taurus-primary"
                type="submit"
              >
                Open
              </button>
            </form>
          </DataPanel>

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Replay status" value={<StatusBadge status={replayQuery.data.status} />} />
            <MetricCard
              label="Run"
              value={
                <Link className="font-mono text-taurus-primary hover:text-sky-200" to={`/runs/${replayQuery.data.run_id}`}>
                  {formatId(replayQuery.data.run_id)}
                </Link>
              }
            />
            <MetricCard
              label="Symbol"
              value={
                <Link className="font-mono text-taurus-primary hover:text-sky-200" to={`/runs/${replayQuery.data.run_id}/symbols/${replayQuery.data.symbol}`}>
                  {replayQuery.data.symbol}
                </Link>
              }
            />
            <MetricCard
              label="Generated"
              supportingText={replayQuery.data.note}
              value={formatTimestamp(replayQuery.data.generated_at)}
            />
          </div>

          <DataPanel title="Stages">
            <div className="grid gap-3">
              {replayQuery.data.stages.map((stage) => (
                <details className="rounded-md border border-taurus-outline bg-taurus-shell" key={stage.id} open={stage.status !== "missing"}>
                  <summary className="cursor-pointer px-4 py-3">
                    <span className="flex flex-wrap items-center justify-between gap-3">
                      <span className="text-sm font-medium text-taurus-text">{stage.label}</span>
                      <span className="flex items-center gap-2">
                        <StatusBadge status={stage.status} size="sm" />
                        <span className="font-mono text-xs text-taurus-muted">
                          {formatNumber(stage.metrics.artifact_count ?? stage.artifacts.length)} artifact(s)
                        </span>
                      </span>
                    </span>
                  </summary>
                  <div className="grid gap-4 border-t border-taurus-outline px-4 py-4">
                    <p className="text-sm leading-6 text-taurus-muted">{stage.summary}</p>
                    <ReplayStageTable stage={stage} />
                    <JsonDrawer title={`${stage.label} raw artifacts`} value={stage.raw ?? stage.artifacts} />
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

function ReplayStageTable({ stage }: { stage: UiTimelineStage }) {
  if (stage.artifacts.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-taurus-outline bg-taurus-surface p-4 text-sm text-taurus-muted">
        No stored artifacts for this replay stage.
      </div>
    );
  }

  const metricItems = objectEntries(stage.metrics);
  const keys = Array.from(new Set(stage.artifacts.flatMap((artifact) => Object.keys(artifact)))).slice(0, 5);

  return (
    <div className="grid gap-4">
      {metricItems.length > 0 && (
        <div className="flex flex-wrap gap-2">
          {metricItems.map((item) => (
            <span className="rounded border border-taurus-outline bg-taurus-surface px-2 py-1 text-xs text-taurus-muted" key={item.label}>
              {item.label}: {item.value}
            </span>
          ))}
        </div>
      )}
      <DataTable<JsonObject>
        columns={keys.map((key) => ({
          key,
          header: key.replace(/_/g, " "),
          render: (row) =>
            key.endsWith("_id") ? formatId(getString(row, key)) : formatMetricValue(key, getPrimitive(row, key)),
        }))}
        getRowKey={(row) =>
          getString(row, "report_id") ||
          getString(row, "event_id") ||
          getString(row, "debate_id") ||
          getString(row, "proposal_id") ||
          getString(row, "risk_check_id") ||
          getString(row, "final_decision_id") ||
          getString(row, "order_id") ||
          getString(row, "fill_id") ||
          JSON.stringify(row)
        }
        rows={stage.artifacts}
      />
    </div>
  );
}
