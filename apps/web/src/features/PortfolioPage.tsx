import { useQuery } from "@tanstack/react-query";

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

export function PortfolioPage() {
  const portfolioQuery = useQuery({
    queryKey: ["ui", "portfolio"],
    queryFn: taurusApi.portfolio,
    refetchInterval: 15_000,
  });

  return (
    <PageScaffold
      actions={<RefreshButton isRefreshing={portfolioQuery.isFetching} onRefresh={() => void portfolioQuery.refetch()} />}
      eyebrow="Paper execution"
      title="Portfolio And Account"
    >
      {portfolioQuery.isLoading && <LoadingState label="Loading portfolio" />}
      {portfolioQuery.isError && <ErrorState message={portfolioQuery.error.message} />}
      {portfolioQuery.data && (
        <div className="grid gap-6">
          {portfolioQuery.data.latest_account ? (
            <div className="grid gap-4 md:grid-cols-3">
              {portfolioQuery.data.summary_metrics.slice(0, 3).map((metric) => (
                <MetricCard key={metric.label} label={metric.label} value={String(metric.value ?? "-")} />
              ))}
            </div>
          ) : (
            <EmptyState commands={emptyDataCommands} message="No paper account snapshot is available." title="No account data" />
          )}

          <DataPanel title="Orders">
            <DataTable
              columns={[
                { key: "order", header: "Order", render: (row) => String(row.order_id ?? "") },
                { key: "symbol", header: "Symbol", render: (row) => String(row.symbol ?? "") },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={String(row.status ?? "")} size="sm" /> },
              ]}
              emptyLabel="No orders"
              getRowKey={(row) => String(row.order_id)}
              rows={portfolioQuery.data.orders}
            />
          </DataPanel>
          <JsonDrawer title="Portfolio payload" value={portfolioQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}
