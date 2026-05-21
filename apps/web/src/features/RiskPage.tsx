import { useQuery } from "@tanstack/react-query";

import { taurusApi } from "../api/client";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { RefreshButton } from "../components/RefreshButton";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
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
          {riskQuery.data.latest_risk_reviews.length === 0 ? (
            <EmptyState commands={emptyDataCommands} message="No risk reviews are available." title="No risk data" />
          ) : (
            <DataPanel title="Recent Reviews">
              <DataTable
                columns={[
                  { key: "id", header: "Risk ID", render: (row) => String(row.risk_check_id ?? "") },
                  { key: "symbol", header: "Symbol", render: (row) => String(row.symbol ?? "") },
                  { key: "status", header: "Status", render: (row) => <StatusBadge status={String(row.status ?? "")} size="sm" /> },
                ]}
                getRowKey={(row) => String(row.risk_check_id)}
                rows={riskQuery.data.latest_risk_reviews}
              />
            </DataPanel>
          )}
          <JsonDrawer title="Risk payload" value={riskQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}
