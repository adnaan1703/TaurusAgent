import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { taurusApi } from "../api/client";
import type { JsonObject, UiRunSelectionRow, UiRunSummary } from "../api/types";
import { useProfilePath, useSelectedProfileId } from "../app/profileSelection";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { MetricCard } from "../components/MetricCard";
import { RefreshButton } from "../components/RefreshButton";
import { RunUniverseSummary } from "../components/RunUniverse";
import { SafetyBanner } from "../components/SafetyBanner";
import { SettlementPanel } from "../components/SettlementPanel";
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
import { AllocationPanels } from "./AllocationPanels";
import { emptyDataCommands, PageScaffold } from "./PageScaffold";

export function OverviewPage() {
  const { selectedProfileId } = useSelectedProfileId();
  const profilePath = useProfilePath();
  const overviewQuery = useQuery({
    queryKey: ["ui", "overview", selectedProfileId ?? "default"],
    queryFn: () => taurusApi.overview({ profileId: selectedProfileId }),
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

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <MetricCard
              label="Latest run"
              supportingText={
                overviewQuery.data.latest_run?.graph_enabled_profile
                  ? `Graph profile; ${overviewQuery.data.latest_run.graph_signal_count ?? 0} signal(s)`
                  : overviewQuery.data.latest_run?.run_id ?? "No run"
              }
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
              supportingText={
                getString(overviewQuery.data.latest_trader_proposal, "lifecycle_trigger") ||
                formatId(getString(overviewQuery.data.latest_final_decision, "decision_id"))
              }
              value={
                overviewQuery.data.latest_final_decision ? (
                  <StatusBadge status={getString(overviewQuery.data.latest_final_decision, "status")} />
                ) : (
                  "None"
                )
              }
            />
            <MetricCard
              label="Monitor"
              supportingText={
                getString(overviewQuery.data.monitor_status, "last_iteration_time")
                  ? `Last ${formatTimestamp(getString(overviewQuery.data.monitor_status, "last_iteration_time"))}`
                  : "No monitor iteration"
              }
              value={
                getPrimitive(overviewQuery.data.monitor_status, "enabled") ? (
                  <StatusBadge
                    label={`${formatNumber(getPrimitive(overviewQuery.data.monitor_status, "trigger_count_today"))} trigger(s) today`}
                    status="APPROVED"
                  />
                ) : (
                  <StatusBadge label="Disabled" status="missing" />
                )
              }
            />
            <MetricCard
              label="Latest order"
              supportingText={
                getString(overviewQuery.data.latest_final_decision, "status") === "NO_ACTION"
                  ? "No paper order expected"
                  : formatId(getString(overviewQuery.data.latest_order, "order_id"))
              }
              value={
                overviewQuery.data.latest_order ? (
                  <StatusBadge status={getString(overviewQuery.data.latest_order, "status")} />
                ) : getString(overviewQuery.data.latest_final_decision, "status") === "NO_ACTION" ? (
                  <StatusBadge status="NO_ACTION" />
                ) : (
                  "None"
                )
              }
            />
          </div>

          {overviewQuery.data.latest_run && (
            <DataPanel title="Full-Universe Run Summary">
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
                <MetricCard
                  label="Universe"
                  supportingText={`${formatNumber(overviewQuery.data.latest_run.analyzed_count)} analyzed`}
                  value={formatNumber(overviewQuery.data.latest_run.universe_count)}
                />
                <MetricCard
                  label="Ranked"
                  supportingText={`${formatNumber(overviewQuery.data.latest_run.proposal_count)} proposal(s)`}
                  value={formatNumber(overviewQuery.data.latest_run.ranked_count)}
                />
                <MetricCard
                  label="Selected"
                  supportingText={`${formatNumber(overviewQuery.data.latest_run.not_selected_count)} not selected`}
                  value={formatNumber(overviewQuery.data.latest_run.selected_count)}
                />
                <MetricCard
                  label="Rejected"
                  supportingText={`${formatNumber(overviewQuery.data.latest_run.risk_rejected_count)} risk rejected`}
                  value={formatNumber(overviewQuery.data.latest_run.allocation_rejected_count)}
                />
                <MetricCard
                  label="Executed"
                  supportingText="Paper orders routed"
                  value={formatNumber(overviewQuery.data.latest_run.executed_count)}
                />
              </div>
            </DataPanel>
          )}

          {overviewQuery.data.latest_run && (
            <SettlementPanel
              settlement={overviewQuery.data.latest_run.settlement_summary}
              showDetails={false}
              title="Latest Settlement"
            />
          )}

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
                      <Link className="font-mono text-taurus-primary hover:text-sky-200" to={profilePath(`/runs/${run.run_id}`)}>
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
                    key: "counts",
                    header: "Run counts",
                    render: (run) => <RunCountSummary run={run} />,
                  },
                  {
                    key: "selection",
                    header: "Selection",
                    render: (run) => <RunSelectionSummary run={run} />,
                  },
                  {
                    key: "graph",
                    header: "Graph",
                    render: (run) => <GraphProfileSummary run={run} />,
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
                  {
                    key: "settlement",
                    header: "Settlement",
                    render: (run) => <SettlementCounts run={run} />,
                  },
                  { key: "errors", header: "Errors", align: "right", render: (run) => run.error_count },
                ]}
                emptyLabel="No runs"
                getRowKey={(run) => run.run_id}
                rows={overviewQuery.data.recent_runs.slice(0, 8)}
              />
            </DataPanel>
          )}

          {overviewQuery.data.latest_run && (
            <DataPanel title="Latest Selection Preview">
              <SelectionPreviewTable
                rows={overviewQuery.data.latest_run.selection_preview}
                runId={overviewQuery.data.latest_run.run_id}
              />
            </DataPanel>
          )}

          <div className="grid gap-6 xl:grid-cols-3">
            <ArtifactCard
              artifact={overviewQuery.data.latest_trader_proposal}
              emptyTitle="No trader proposal"
              fields={[
                ["proposal_id", "Proposal ID"],
                ["symbol", "Symbol"],
                ["action", "Action"],
                ["lifecycle_trigger", "Lifecycle"],
                ["evaluation_mode", "Mode"],
                ["current_position_quantity", "Current qty"],
                ["current_position_pct_nav", "Current NAV"],
                ["target_position_pct_nav", "Target NAV"],
                ["position_management_summary", "Lifecycle summary"],
              ]}
              statusKey="action"
              title="Latest Trader Proposal"
            />
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
              emptyTitle={
                getString(overviewQuery.data.latest_final_decision, "status") === "NO_ACTION"
                  ? "No paper order expected"
                  : "No paper order"
              }
              fields={[
                ["order_id", "Order ID"],
                ["symbol", "Symbol"],
                ["side", "Side"],
                ["quantity", "Quantity"],
                ["filled_quantity", "Filled"],
                ["average_fill_price_inr", "Average fill"],
                ["total_cost_inr", "Costs"],
                ["slippage_bps", "Slippage"],
                ["signal_trade_date", "Signal date"],
                ["scheduled_fill_session", "Fill session"],
                ["filled_trade_date", "Filled trade date"],
              ]}
              statusKey="status"
              title="Latest Paper Order"
            />
          </div>

          <AllocationPanels allocation={overviewQuery.data.allocation} />

          <DataPanel title="Active Positions">
            <DataTable
              columns={[
                { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
                { key: "sleeve", header: "Sleeve", render: (row) => getString(row, "sleeve_name") || getString(row, "sleeve_id") || "-" },
                { key: "strategy", header: "Strategy", render: (row) => getString(row, "strategy_name") || "-" },
                { key: "quantity", header: "Qty", align: "right", render: (row) => formatNumber(getPrimitive(row, "quantity")) },
                { key: "avg", header: "Average cost", align: "right", render: (row) => formatInr(getPrimitive(row, "average_cost_inr")) },
                { key: "last", header: "Last price", align: "right", render: (row) => formatInr(getPrimitive(row, "last_price_inr")) },
                { key: "quote", header: "Quote LTP", align: "right", render: (row) => formatInr(getPrimitive(row, "latest_quote_ltp_inr")) },
                { key: "sl", header: "SL price", align: "right", render: (row) => formatInr(getPrimitive(row, "stop_loss_price_inr")) },
                { key: "tp", header: "TP price", align: "right", render: (row) => formatInr(getPrimitive(row, "take_profit_price_inr")) },
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

function RunCountSummary({ run }: { run: UiRunSummary }) {
  return (
    <div className="space-y-1 text-xs">
      <p className="text-taurus-text">
        {formatNumber(run.analyzed_count)} analyzed / {formatNumber(run.ranked_count)} ranked
      </p>
      <p className="text-taurus-muted">{formatNumber(run.proposal_count)} proposal(s)</p>
    </div>
  );
}

function RunSelectionSummary({ run }: { run: UiRunSummary }) {
  return (
    <div className="space-y-1 text-xs">
      <p className="text-taurus-text">
        {formatNumber(run.selected_count)} selected / {formatNumber(run.executed_count)} executed
      </p>
      <p className="text-taurus-muted">
        {formatNumber(run.allocation_rejected_count)} allocation rejected, {formatNumber(run.risk_rejected_count)} risk rejected
      </p>
    </div>
  );
}

function SelectionPreviewTable({
  rows,
  runId,
}: {
  rows: UiRunSelectionRow[];
  runId: string;
}) {
  const profilePath = useProfilePath();
  return (
    <DataTable
      columns={[
        {
          key: "symbol",
          header: "Symbol",
          render: (row) => (
            <Link className="font-semibold text-taurus-primary hover:text-sky-200" to={profilePath(`/runs/${runId}/symbols/${row.symbol}`)}>
              {row.symbol}
            </Link>
          ),
        },
        { key: "rank", header: "Rank", align: "right", render: (row) => formatNumber(row.rank ?? undefined) },
        { key: "score", header: "Raw score", align: "right", render: (row) => formatNumber(row.strategy_score ?? undefined) },
        { key: "allocationScore", header: "Allocation score", align: "right", render: (row) => formatNumber(row.candidate_score ?? undefined) },
        { key: "action", header: "Action", render: (row) => row.trader_action ?? "-" },
        { key: "allocation", header: "Allocation", render: (row) => <StatusBadge status={row.allocation_status} size="sm" /> },
        { key: "final", header: "Final", render: (row) => <StatusBadge status={row.final_status} size="sm" /> },
        { key: "execution", header: "Execution", render: (row) => <StatusBadge status={row.execution_status} size="sm" /> },
        { key: "reason", header: "Reason", render: (row) => row.reason ?? "-" },
      ]}
      emptyLabel="No run-level selection ledger is available for this run"
      getRowKey={(row) => `${runId}-${row.symbol}-${row.proposal_id ?? ""}`}
      rows={rows}
    />
  );
}

function SymbolLinks({ run }: { run: UiRunSummary }) {
  const profilePath = useProfilePath();
  if (run.symbols.length === 0) {
    return "None";
  }

  return (
    <div className="flex flex-wrap gap-2">
      {run.symbols.map((symbol) => (
        <Link
          className="rounded border border-taurus-outline bg-taurus-shell px-2 py-1 font-mono text-xs text-taurus-primary hover:border-taurus-primary"
          key={symbol}
          to={profilePath(`/runs/${run.run_id}/symbols/${symbol}`)}
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

function SettlementCounts({ run }: { run: UiRunSummary }) {
  const settlementSummary = run.settlement_summary ?? {};
  const settled = Number(getPrimitive(settlementSummary, "settled") ?? 0);
  const rejected = Number(getPrimitive(settlementSummary, "rejected") ?? 0);
  const stillPending = Number(getPrimitive(settlementSummary, "still_pending") ?? 0);
  const skipped = Number(getPrimitive(settlementSummary, "skipped") ?? 0);
  const entries = [
    ["FILLED", settled],
    ["REJECTED", rejected],
    ["PENDING_NEXT_OPEN", stillPending],
    ["skipped", skipped],
  ] as const;
  if (!Object.keys(settlementSummary).length) {
    return <span className="text-taurus-muted">Not recorded</span>;
  }
  if (entries.every(([, count]) => count === 0)) {
    return <span className="text-taurus-muted">No activity</span>;
  }
  return (
    <div className="flex flex-wrap gap-2">
      {entries
        .filter(([, count]) => count > 0)
        .map(([status, count]) => (
          <span className="inline-flex items-center gap-1" key={status}>
            <StatusBadge status={status} size="sm" />
            <span className="text-xs text-taurus-muted">{count}</span>
          </span>
        ))}
    </div>
  );
}

function GraphProfileSummary({ run }: { run: UiRunSummary }) {
  if (!run.graph_enabled_profile) {
    return <span className="text-taurus-muted">Off</span>;
  }

  return (
    <div className="space-y-1 text-xs">
      <p className="text-taurus-text">
        {run.graph_signal_count ?? 0} signal(s), {run.graph_selected_symbols.length} selected
      </p>
      <p className="text-taurus-muted">{run.graph_risk_enabled ? "Risk on" : "Risk off"}</p>
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
