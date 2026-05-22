import { useQuery } from "@tanstack/react-query";

import { taurusApi } from "../api/client";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { KeyValueGrid } from "../components/KeyValueGrid";
import { MetricCard } from "../components/MetricCard";
import { RefreshButton } from "../components/RefreshButton";
import { SafetyBanner } from "../components/SafetyBanner";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import {
  formatId,
  formatInr,
  formatMetric,
  formatNumber,
  formatTimestamp,
  getPrimitive,
  getString,
  objectEntries,
} from "../utils/format";
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
          <SafetyBanner safety={portfolioQuery.data.safety} />

          {portfolioQuery.data.latest_account ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              {portfolioQuery.data.summary_metrics.map((metric) => (
                <MetricCard
                  key={metric.label}
                  label={metric.label}
                  tone={metric.tone}
                  value={formatMetric(metric)}
                />
              ))}
            </div>
          ) : (
            <EmptyState commands={emptyDataCommands} message="No paper account snapshot is available." title="No account data" />
          )}

          <DataPanel title="Latest Account">
            <KeyValueGrid items={objectEntries(portfolioQuery.data.latest_account)} />
          </DataPanel>

          <DataPanel title="Positions">
            <DataTable
              columns={[
                { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
                { key: "qty", header: "Qty", align: "right", render: (row) => formatNumber(getPrimitive(row, "quantity")) },
                { key: "avg", header: "Average cost", align: "right", render: (row) => formatInr(getPrimitive(row, "average_cost_inr")) },
                { key: "last", header: "Last price", align: "right", render: (row) => formatInr(getPrimitive(row, "last_price_inr")) },
                { key: "value", header: "Market value", align: "right", render: (row) => formatInr(getPrimitive(row, "market_value_inr")) },
                { key: "realized", header: "Realized P&L", align: "right", render: (row) => formatInr(getPrimitive(row, "realized_pnl_inr")) },
                { key: "unrealized", header: "Unrealized P&L", align: "right", render: (row) => formatInr(getPrimitive(row, "unrealized_pnl_inr")) },
              ]}
              emptyLabel="No positions"
              getRowKey={(row) => `${getString(row, "run_id")}-${getString(row, "symbol")}`}
              rows={portfolioQuery.data.positions}
            />
          </DataPanel>

          <DataPanel title="Orders">
            <DataTable
              columns={[
                { key: "order", header: "Order", render: (row) => formatId(getString(row, "order_id")) },
                { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
                { key: "side", header: "Side", render: (row) => getString(row, "side") || "-" },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={getString(row, "status")} size="sm" /> },
                { key: "qty", header: "Qty", align: "right", render: (row) => formatNumber(getPrimitive(row, "quantity")) },
                { key: "filled", header: "Filled", align: "right", render: (row) => formatNumber(getPrimitive(row, "filled_quantity")) },
                { key: "avg", header: "Average fill", align: "right", render: (row) => formatInr(getPrimitive(row, "average_fill_price_inr")) },
                { key: "cost", header: "Costs", align: "right", render: (row) => formatInr(getPrimitive(row, "total_cost_inr")) },
                { key: "slippage", header: "Slippage", align: "right", render: (row) => `${formatNumber(getPrimitive(row, "slippage_bps"))} bps` },
              ]}
              emptyLabel="No orders"
              getRowKey={(row) => getString(row, "order_id")}
              rows={portfolioQuery.data.orders}
            />
          </DataPanel>

          <DataPanel title="Fills">
            <DataTable
              columns={[
                { key: "fill", header: "Fill", render: (row) => formatId(getString(row, "fill_id")) },
                { key: "order", header: "Order", render: (row) => formatId(getString(row, "order_id")) },
                { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
                { key: "seq", header: "Seq", align: "right", render: (row) => formatNumber(getPrimitive(row, "fill_sequence")) },
                { key: "qty", header: "Qty", align: "right", render: (row) => formatNumber(getPrimitive(row, "quantity")) },
                { key: "reference", header: "Reference", align: "right", render: (row) => formatInr(getPrimitive(row, "reference_price_inr")) },
                { key: "price", header: "Fill price", align: "right", render: (row) => formatInr(getPrimitive(row, "fill_price_inr")) },
                { key: "cost", header: "Costs", align: "right", render: (row) => formatInr(getPrimitive(row, "cost_inr")) },
                { key: "slippage", header: "Slippage", align: "right", render: (row) => `${formatNumber(getPrimitive(row, "slippage_bps"))} bps` },
                { key: "filled", header: "Filled at", render: (row) => formatTimestamp(getString(row, "filled_at")) },
              ]}
              emptyLabel="No fills"
              getRowKey={(row) => getString(row, "fill_id")}
              rows={portfolioQuery.data.fills}
            />
          </DataPanel>

          <JsonDrawer title="Portfolio payload" value={portfolioQuery.data} />
        </div>
      )}
    </PageScaffold>
  );
}
