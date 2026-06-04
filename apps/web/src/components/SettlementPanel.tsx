import type { JsonObject, JsonValue } from "../api/types";
import {
  formatDate,
  formatId,
  formatInr,
  formatNumber,
  getPrimitive,
  getString,
  isJsonObject,
  jsonArray,
} from "../utils/format";
import { DataPanel } from "./DataPanel";
import { DataTable } from "./DataTable";
import { MetricCard } from "./MetricCard";
import { StatusBadge } from "./StatusBadge";

type SettlementPanelProps = {
  settlement: JsonValue | null | undefined;
  title?: string;
  showDetails?: boolean;
};

export function SettlementPanel({
  settlement,
  title = "Next-Open Settlement",
  showDetails = true,
}: SettlementPanelProps) {
  const artifact = isJsonObject(settlement) ? settlement : null;
  const details = artifact ? jsonArray(artifact.details) : [];
  const pendingSymbols = symbolsFromArtifact(artifact);
  const settled = settlementCount(artifact, "settled");
  const rejected = settlementCount(artifact, "rejected");
  const stillPending = settlementCount(artifact, "still_pending");
  const skipped = settlementCount(artifact, "skipped");
  const hasArtifact = artifact !== null && Object.keys(artifact).length > 0;

  return (
    <DataPanel
      actions={<StatusBadge label={settlementLabel(settled, rejected, stillPending, hasArtifact)} status={settlementStatus(settled, rejected, stillPending, hasArtifact)} size="sm" />}
      title={title}
    >
      {!hasArtifact ? (
        <p className="text-sm text-taurus-muted">No settlement artifact is recorded for this run.</p>
      ) : (
        <div className="grid gap-4">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <MetricCard label="Settled" value={formatNumber(settled)} />
            <MetricCard label="Rejected" value={formatNumber(rejected)} tone={rejected > 0 ? "failure" : "neutral"} />
            <MetricCard label="Still pending" value={formatNumber(stillPending)} tone={stillPending > 0 ? "caution" : "neutral"} />
            <MetricCard label="Skipped" value={formatNumber(skipped)} tone={skipped > 0 ? "caution" : "neutral"} />
          </div>

          {pendingSymbols.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {pendingSymbols.map((symbol) => (
                <code
                  className="rounded border border-taurus-outline bg-taurus-shell px-2 py-1 text-xs text-taurus-text"
                  key={symbol}
                >
                  {symbol}
                </code>
              ))}
            </div>
          )}

          {showDetails && (
            <DataTable
              columns={[
                { key: "order", header: "Order", render: (row) => formatId(getString(row, "order_id")) },
                { key: "symbol", header: "Symbol", render: (row) => getString(row, "symbol") || "-" },
                { key: "side", header: "Side", render: (row) => getString(row, "side") || "-" },
                { key: "signal", header: "Signal date", render: (row) => formatDate(getPrimitive(row, "signal_trade_date")) },
                { key: "execution", header: "Fill trade date", render: (row) => formatDate(getPrimitive(row, "execution_trade_date")) },
                { key: "qty", header: "Qty", align: "right", render: (row) => formatNumber(getPrimitive(row, "quantity")) },
                { key: "status", header: "Status", render: (row) => <StatusBadge status={getString(row, "status")} size="sm" /> },
                { key: "reference", header: "Reference", align: "right", render: (row) => formatInr(getPrimitive(row, "reference_price_inr")) },
                { key: "fill", header: "Fill price", align: "right", render: (row) => formatInr(getPrimitive(row, "fill_price_inr")) },
                { key: "outcome", header: "Outcome", render: settlementOutcome },
              ]}
              emptyLabel="No settlement order details"
              getRowKey={(row) => `${getString(row, "order_id")}-${getString(row, "status")}-${getString(row, "outcome_reason")}`}
              rows={details}
            />
          )}
        </div>
      )}
    </DataPanel>
  );
}

function settlementCount(artifact: JsonObject | null, key: string): number {
  const value = getPrimitive(artifact, key);
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

function symbolsFromArtifact(artifact: JsonObject | null): string[] {
  const raw = artifact?.pending_next_open_order_symbols;
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw.map((symbol) => String(symbol).toUpperCase()).filter(Boolean);
}

function settlementStatus(
  settled: number,
  rejected: number,
  stillPending: number,
  hasArtifact: boolean,
) {
  if (!hasArtifact) {
    return "missing";
  }
  if (rejected > 0) {
    return "REJECTED";
  }
  if (stillPending > 0) {
    return "PENDING_NEXT_OPEN";
  }
  if (settled > 0) {
    return "FILLED";
  }
  return "skipped";
}

function settlementLabel(
  settled: number,
  rejected: number,
  stillPending: number,
  hasArtifact: boolean,
) {
  if (!hasArtifact) {
    return "Not recorded";
  }
  if (rejected > 0) {
    return `${rejected} rejected`;
  }
  if (stillPending > 0) {
    return `${stillPending} queued`;
  }
  if (settled > 0) {
    return `${settled} settled`;
  }
  return "No activity";
}

function settlementOutcome(row: JsonObject) {
  return (
    getString(row, "outcome_reason") ||
    getString(row, "rejection_reason") ||
    "-"
  );
}
