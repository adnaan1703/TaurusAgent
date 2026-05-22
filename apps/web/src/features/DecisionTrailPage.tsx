import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";

import { taurusApi } from "../api/client";
import type { JsonObject, UiTimelineStage } from "../api/types";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { JsonDrawer } from "../components/JsonDrawer";
import { KeyValueGrid } from "../components/KeyValueGrid";
import { MetricCard } from "../components/MetricCard";
import { RefreshButton } from "../components/RefreshButton";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { WarningsPanel } from "../components/WarningsPanel";
import {
  formatId,
  formatInr,
  formatMetricValue,
  formatNumber,
  formatPercent,
  formatTimestamp,
  getPrimitive,
  getString,
  jsonArray,
  objectEntries,
} from "../utils/format";
import { PageScaffold } from "./PageScaffold";

export function DecisionTrailPage() {
  const { runId = "", symbol = "" } = useParams();
  const [selectedStageId, setSelectedStageId] = useState<string | null>(null);
  const trailQuery = useQuery({
    queryKey: ["ui", "decision-trail", runId, symbol],
    queryFn: () => taurusApi.decisionTrail(runId, symbol),
    enabled: runId.length > 0 && symbol.length > 0,
    refetchInterval: (query) => (query.state.data?.run.status === "RUNNING" ? 5_000 : false),
  });

  const selectedStage = useMemo(() => {
    if (!trailQuery.data?.stages.length) {
      return null;
    }
    return (
      trailQuery.data.stages.find((stage) => stage.id === selectedStageId) ??
      trailQuery.data.stages.find((stage) => stage.id === trailQuery.data.selected_stage_id) ??
      trailQuery.data.stages[0]
    );
  }, [selectedStageId, trailQuery.data]);

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
          <WarningsPanel warnings={trailQuery.data.warnings} />

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard
              label="Final status"
              supportingText={trailQuery.data.company_name ?? trailQuery.data.symbol}
              value={<StatusBadge status={trailQuery.data.final_status} />}
            />
            <MetricCard
              label="Final action"
              supportingText={`Broker route: ${trailQuery.data.can_send_to_broker ? "eligible" : "not eligible"}`}
              value={trailQuery.data.final_action ?? "-"}
            />
            <MetricCard
              label="Decision replay"
              supportingText={trailQuery.data.decision_id ?? "No decision ID"}
              value={
                trailQuery.data.decision_id ? (
                  <Link className="text-taurus-primary hover:text-sky-200" to={`/replay/${trailQuery.data.decision_id}`}>
                    Open replay
                  </Link>
                ) : (
                  "Unavailable"
                )
              }
            />
            <MetricCard
              label="Run status"
              supportingText={trailQuery.data.run.run_id}
              value={<StatusBadge status={trailQuery.data.run.status} />}
            />
          </div>

          <DataPanel title="Stages">
            <ol className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {trailQuery.data.stages.map((stage) => (
                <li key={stage.id}>
                  <button
                    aria-pressed={selectedStage?.id === stage.id}
                    className="h-full w-full rounded-md border border-taurus-outline bg-taurus-shell p-4 text-left transition hover:border-taurus-primary aria-pressed:border-taurus-primary aria-pressed:bg-sky-400/10"
                    onClick={() => setSelectedStageId(stage.id)}
                    type="button"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <p className="font-medium text-taurus-text">{stage.label}</p>
                        <p className="mt-2 text-sm leading-6 text-taurus-muted">{stage.summary}</p>
                      </div>
                      <StatusBadge status={stage.status} size="sm" />
                    </div>
                    <div className="mt-3 flex flex-wrap items-center gap-2 font-mono text-xs text-taurus-muted">
                      {stage.timestamp && <span>{formatTimestamp(stage.timestamp)}</span>}
                      <span>{stage.artifact_ids.length} artifact id(s)</span>
                    </div>
                  </button>
                </li>
              ))}
            </ol>
          </DataPanel>

          {selectedStage && <StageDetail stage={selectedStage} />}

          <JsonDrawer title="Decision trail payload" value={trailQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}

function StageDetail({ stage }: { stage: UiTimelineStage }) {
  return (
    <DataPanel
      actions={<StatusBadge status={stage.status} />}
      eyebrow="Selected stage"
      title={stage.label}
    >
      <div className="grid gap-5">
        <p className="text-sm leading-6 text-taurus-muted">{stage.summary}</p>

        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_minmax(18rem,0.65fr)]">
          <div className="grid gap-5">
            <KeyValueGrid items={objectEntries(stage.metrics)} />
            <StageArtifactTable stage={stage} />
          </div>
          <div className="grid content-start gap-5">
            <section className="rounded-md border border-taurus-outline bg-taurus-shell p-4">
              <h3 className="text-sm font-semibold text-taurus-text">Artifact IDs</h3>
              {stage.artifact_ids.length === 0 ? (
                <p className="mt-3 text-sm text-taurus-muted">No artifact IDs are linked to this stage.</p>
              ) : (
                <div className="mt-3 flex flex-wrap gap-2">
                  {stage.artifact_ids.map((id) => (
                    <code
                      className="rounded border border-taurus-outline bg-taurus-shell px-2 py-1 text-xs text-taurus-text"
                      key={id}
                      title={id}
                    >
                      {formatId(id)}
                    </code>
                  ))}
                </div>
              )}
            </section>
            <JsonDrawer title={`${stage.label} raw artifacts`} value={stage.raw ?? stage.artifacts} />
          </div>
        </div>
      </div>
    </DataPanel>
  );
}

function StageArtifactTable({ stage }: { stage: UiTimelineStage }) {
  if (stage.artifacts.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-taurus-outline bg-taurus-shell p-5 text-sm text-taurus-muted">
        This stage has no stored artifacts. Its status remains visible as {stage.status}.
      </div>
    );
  }

  if (stage.id === "analyst_reports") {
    return (
      <DataTable
        columns={[
          { key: "agent", header: "Agent", render: (row) => getString(row, "agent_name") || "-" },
          { key: "stance", header: "Stance", render: (row) => getString(row, "stance") || "-" },
          { key: "score", header: "Score", align: "right", render: (row) => formatNumber(getPrimitive(row, "score")) },
          { key: "confidence", header: "Confidence", align: "right", render: (row) => formatPercent(getPrimitive(row, "confidence")) },
          { key: "points", header: "Key points", render: (row) => listSummary(row, "key_points") },
        ]}
        getRowKey={(row) => getString(row, "report_id")}
        rows={stage.artifacts}
      />
    );
  }

  if (stage.id === "risk_review") {
    const review = stage.artifacts[0];
    const rules = jsonArray(review?.hard_rule_results);
    const personas = jsonArray(review?.persona_reviews);
    return (
      <div className="grid gap-5">
        <DataTable
          columns={[
            { key: "rule", header: "Rule", render: (row) => getString(row, "rule") || getString(row, "name") || "-" },
            { key: "status", header: "Status", render: (row) => <StatusBadge status={getString(row, "status") || getString(row, "result")} size="sm" /> },
            { key: "message", header: "Message", render: (row) => getString(row, "message") || getString(row, "reason") || "-" },
          ]}
          emptyLabel="No hard-rule results"
          getRowKey={(row) => `${getString(row, "rule")}-${getString(row, "status")}-${getString(row, "message")}`}
          rows={rules}
        />
        <DataTable
          columns={[
            { key: "persona", header: "Persona", render: (row) => getString(row, "persona") || getString(row, "agent_name") || "-" },
            { key: "stance", header: "Stance", render: (row) => getString(row, "stance") || getString(row, "status") || "-" },
            { key: "summary", header: "Summary", render: (row) => getString(row, "summary") || getString(row, "recommendation") || "-" },
          ]}
          emptyLabel="No persona reviews"
          getRowKey={(row) => `${getString(row, "persona")}-${getString(row, "stance")}-${getString(row, "summary")}`}
          rows={personas}
        />
      </div>
    );
  }

  if (stage.id === "paper_fills") {
    return (
      <DataTable
        columns={[
          { key: "fill", header: "Fill", render: (row) => formatId(getString(row, "fill_id")) },
          { key: "seq", header: "Seq", align: "right", render: (row) => formatNumber(getPrimitive(row, "fill_sequence")) },
          { key: "qty", header: "Qty", align: "right", render: (row) => formatNumber(getPrimitive(row, "quantity")) },
          { key: "reference", header: "Reference", align: "right", render: (row) => formatInr(getPrimitive(row, "reference_price_inr")) },
          { key: "price", header: "Fill price", align: "right", render: (row) => formatInr(getPrimitive(row, "fill_price_inr")) },
          { key: "cost", header: "Costs", align: "right", render: (row) => formatInr(getPrimitive(row, "cost_inr")) },
          { key: "slippage", header: "Slippage", align: "right", render: (row) => `${formatNumber(getPrimitive(row, "slippage_bps"))} bps` },
        ]}
        getRowKey={(row) => getString(row, "fill_id")}
        rows={stage.artifacts}
      />
    );
  }

  if (stage.id === "paper_order") {
    return (
      <DataTable
        columns={[
          { key: "order", header: "Order", render: (row) => formatId(getString(row, "order_id")) },
          { key: "status", header: "Status", render: (row) => <StatusBadge status={getString(row, "status")} size="sm" /> },
          { key: "side", header: "Side", render: (row) => getString(row, "side") || "-" },
          { key: "qty", header: "Qty", align: "right", render: (row) => formatNumber(getPrimitive(row, "quantity")) },
          { key: "filled", header: "Filled", align: "right", render: (row) => formatNumber(getPrimitive(row, "filled_quantity")) },
          { key: "avg", header: "Average fill", align: "right", render: (row) => formatInr(getPrimitive(row, "average_fill_price_inr")) },
          { key: "cost", header: "Costs", align: "right", render: (row) => formatInr(getPrimitive(row, "total_cost_inr")) },
        ]}
        getRowKey={(row) => getString(row, "order_id")}
        rows={stage.artifacts}
      />
    );
  }

  if (stage.id === "audit_log") {
    return (
      <DataTable
        columns={[
          { key: "event", header: "Event", render: (row) => getString(row, "event_type") || "-" },
          { key: "actor", header: "Actor", render: (row) => getString(row, "actor") || "-" },
          { key: "note", header: "Note", render: (row) => getString(row, "note") || "-" },
          { key: "created", header: "Created", render: (row) => formatTimestamp(getString(row, "created_at")) },
        ]}
        getRowKey={(row) => String(getPrimitive(row, "id") ?? getString(row, "event_type"))}
        rows={stage.artifacts}
      />
    );
  }

  return (
    <DataTable
      columns={genericColumns(stage.artifacts)}
      getRowKey={(row) => stage.artifact_ids.find((id) => Object.values(row).includes(id)) ?? JSON.stringify(row)}
      rows={stage.artifacts}
    />
  );
}

function genericColumns(rows: JsonObject[]) {
  const keys = Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 6);
  return keys.map((key) => ({
    key,
    header: key.replace(/_/g, " "),
    render: (row: JsonObject) => formatMetricValue(key, getPrimitive(row, key)),
  }));
}

function listSummary(row: JsonObject, key: string) {
  const value = row[key];
  if (!Array.isArray(value) || value.length === 0) {
    return "-";
  }
  return (
    <ul className="max-w-md space-y-1">
      {value.slice(0, 2).map((item, index) => (
        <li className="text-sm text-taurus-muted" key={`${key}-${index}`}>
          {String(item)}
        </li>
      ))}
    </ul>
  );
}
