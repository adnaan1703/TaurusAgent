import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { taurusApi } from "../api/client";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { MetricCard } from "../components/MetricCard";
import { RefreshButton } from "../components/RefreshButton";
import { SafetyBanner } from "../components/SafetyBanner";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import {
  formatId,
  formatNumber,
  formatPercent,
  formatTimestamp,
  getPrimitive,
  getString,
} from "../utils/format";
import { emptyDataCommands, PageScaffold } from "./PageScaffold";

export function RiskPage() {
  const riskQuery = useQuery({
    queryKey: ["ui", "risk"],
    queryFn: taurusApi.risk,
    refetchInterval: 15_000,
  });

  return (
    <PageScaffold
      actions={<RefreshButton isRefreshing={riskQuery.isFetching} onRefresh={() => void riskQuery.refetch()} />}
      eyebrow="Risk engine"
      title="Risk And Controls"
    >
      {riskQuery.isLoading && <LoadingState label="Loading risk" />}
      {riskQuery.isError && <ErrorState message={riskQuery.error.message} />}
      {riskQuery.data && (
        <div className="grid gap-6">
          <SafetyBanner safety={riskQuery.data.safety} />

          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            {Object.entries(riskQuery.data.status_counts).length === 0 ? (
              <MetricCard label="Risk reviews" value="None" />
            ) : (
              Object.entries(riskQuery.data.status_counts).map(([status, count]) => (
                <MetricCard
                  key={status}
                  label={status.replace(/_/g, " ")}
                  value={<StatusBadge label={`${formatNumber(count)} review(s)`} status={status} />}
                />
              ))
            )}
          </div>

          {riskQuery.data.latest_risk_reviews.length === 0 ? (
            <EmptyState commands={emptyDataCommands} message="No risk reviews are available." title="No risk data" />
          ) : (
            <DataPanel title="Recent Reviews">
              <DataTable
                columns={[
                  { key: "id", header: "Risk ID", render: (row) => formatId(getString(row, "risk_check_id")) },
                  {
                    key: "run",
                    header: "Run / symbol",
                    render: (row) => (
                      <Link className="text-taurus-primary hover:text-sky-200" to={`/runs/${getString(row, "run_id")}/symbols/${getString(row, "symbol")}`}>
                        {getString(row, "symbol") || "-"}
                      </Link>
                    ),
                  },
                  {
                    key: "decision",
                    header: "Decision",
                    render: (row) =>
                      getString(row, "decision_id") ? (
                        <Link className="font-mono text-xs text-taurus-primary hover:text-sky-200" to={`/replay/${getString(row, "decision_id")}`}>
                          {formatId(getString(row, "decision_id"))}
                        </Link>
                      ) : (
                        "-"
                      ),
                  },
                  { key: "status", header: "Status", render: (row) => <StatusBadge status={getString(row, "status")} size="sm" /> },
                  { key: "requested", header: "Requested", align: "right", render: (row) => formatPercent(getPrimitive(row, "requested_position_pct_nav")) },
                  { key: "approved", header: "Approved", align: "right", render: (row) => formatPercent(getPrimitive(row, "approved_position_pct_nav")) },
                  { key: "broker", header: "Broker eligible", render: (row) => <StatusBadge label={getPrimitive(row, "can_send_to_broker") ? "Yes" : "No"} status={getPrimitive(row, "can_send_to_broker") ? "APPROVED" : "BLOCKED"} size="sm" /> },
                  { key: "asof", header: "As of", render: (row) => formatTimestamp(getString(row, "as_of")) },
                ]}
                getRowKey={(row) => getString(row, "risk_check_id")}
                rows={riskQuery.data.latest_risk_reviews}
              />
            </DataPanel>
          )}

          <DataPanel title="Hard Rules">
            <DataTable
              columns={[
                { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
                { key: "rule", header: "Rule", render: (row) => getString(row, "rule") || getString(row, "name") || "-" },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={getString(row, "status") || getString(row, "result")} size="sm" /> },
                { key: "message", header: "Message", render: (row) => getString(row, "message") || getString(row, "reason") || "-" },
                { key: "risk", header: "Risk ID", render: (row) => formatId(getString(row, "risk_check_id")) },
              ]}
              emptyLabel="No hard-rule results"
              getRowKey={(row) => `${getString(row, "risk_check_id")}-${getString(row, "rule")}-${getString(row, "message")}`}
              rows={riskQuery.data.hard_rule_results}
            />
          </DataPanel>

          <DataPanel title="Persona Reviews">
            <DataTable
              columns={[
                { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
                { key: "persona", header: "Persona", render: (row) => getString(row, "persona") || getString(row, "agent_name") || "-" },
                { key: "stance", header: "Stance", render: (row) => getString(row, "stance") || getString(row, "status") || "-" },
                { key: "summary", header: "Summary", render: (row) => getString(row, "summary") || getString(row, "recommendation") || "-" },
                { key: "risk", header: "Risk ID", render: (row) => formatId(getString(row, "risk_check_id")) },
              ]}
              emptyLabel="No persona reviews"
              getRowKey={(row) => `${getString(row, "risk_check_id")}-${getString(row, "persona")}-${getString(row, "stance")}`}
              rows={riskQuery.data.persona_reviews}
            />
          </DataPanel>

          <DataPanel title="Linked Final Decisions">
            <DataTable
              columns={[
                { key: "decision", header: "Decision", render: (row) => formatId(getString(row, "decision_id")) },
                {
                  key: "symbol",
                  header: "Symbol",
                  render: (row) => (
                    <Link className="text-taurus-primary hover:text-sky-200" to={`/runs/${getString(row, "run_id")}/symbols/${getString(row, "symbol")}`}>
                      {getString(row, "symbol") || "-"}
                    </Link>
                  ),
                },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={getString(row, "status")} size="sm" /> },
                { key: "action", header: "Action", render: (row) => getString(row, "final_action") || "-" },
                { key: "qty", header: "Qty", align: "right", render: (row) => formatNumber(getPrimitive(row, "approved_quantity")) },
                { key: "reason", header: "Reason", render: (row) => getString(row, "reason") || "-" },
              ]}
              emptyLabel="No final decisions"
              getRowKey={(row) => getString(row, "final_decision_id")}
              rows={riskQuery.data.latest_final_decisions}
            />
          </DataPanel>

          <JsonDrawer title="Risk payload" value={riskQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}
