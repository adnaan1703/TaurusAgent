import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, ExternalLink } from "lucide-react";
import { useState } from "react";

import { taurusApi } from "../api/client";
import type { ShariahStatusFilter, UiShariahRow } from "../api/types";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { EmptyState } from "../components/EmptyState";
import { JsonDrawer } from "../components/JsonDrawer";
import { KeyValueGrid } from "../components/KeyValueGrid";
import { MetricCard } from "../components/MetricCard";
import { RefreshButton } from "../components/RefreshButton";
import { ErrorState, LoadingState } from "../components/States";
import { StatusBadge } from "../components/StatusBadge";
import { formatNumber, formatTimestamp } from "../utils/format";
import { PageScaffold } from "./PageScaffold";

const PAGE_SIZE = 50;

export function ShariahPage() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<ShariahStatusFilter>("all");
  const [page, setPage] = useState(1);
  const shariahQuery = useQuery({
    queryKey: ["ui", "shariah", query, status, page, PAGE_SIZE],
    queryFn: () =>
      taurusApi.shariah({
        query,
        status,
        page,
        pageSize: PAGE_SIZE,
      }),
    placeholderData: (previousData) => previousData,
    refetchInterval: 60_000,
  });

  const payload = shariahQuery.data;
  const pagination = payload?.pagination;
  const hasNoComplianceRows = payload?.counts.active_total === 0;

  return (
    <PageScaffold
      actions={
        <RefreshButton
          isRefreshing={shariahQuery.isFetching}
          onRefresh={() => void shariahQuery.refetch()}
        />
      }
      eyebrow="Compliance universe"
      title="Shariah"
    >
      {shariahQuery.isLoading && <LoadingState label="Loading Shariah compliance" />}
      {shariahQuery.isError && <ErrorState message={shariahQuery.error.message} />}
      {payload && (
        <div className="grid gap-6">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
            <MetricCard
              label="Active stocks"
              value={formatNumber(payload.counts.active_total)}
            />
            <MetricCard
              label="Halal"
              tone="success"
              value={formatNumber(payload.counts.halal)}
            />
            <MetricCard
              label="Haram"
              tone="failure"
              value={formatNumber(payload.counts.haram)}
            />
            <MetricCard
              label="Latest sync"
              supportingText={payload.latest_import?.import_id ?? "No import"}
              value={formatTimestamp(payload.latest_import?.fetched_at)}
            />
            <MetricCard
              label="Halal NSE export"
              supportingText={payload.halal_universe_export.universe_name ?? "YAML not loaded"}
              tone={payload.halal_universe_export.loaded ? "success" : "caution"}
              value={formatNumber(payload.halal_universe_export.exported_symbol_count)}
            />
          </div>

          <DataPanel title="Filters">
            <div className="grid gap-3 md:grid-cols-[minmax(0,1fr)_220px]">
              <input
                aria-label="Search Shariah compliance"
                className="rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none placeholder:text-taurus-muted focus:border-taurus-primary"
                onChange={(event) => {
                  setPage(1);
                  setQuery(event.target.value);
                }}
                placeholder="Search name, NSE symbol, or BSE code"
                value={query}
              />
              <select
                aria-label="Compliance status"
                className="rounded-md border border-taurus-outline bg-taurus-shell px-3 py-2 text-sm text-taurus-text outline-none focus:border-taurus-primary"
                onChange={(event) => {
                  setPage(1);
                  setStatus(event.target.value as ShariahStatusFilter);
                }}
                value={status}
              >
                <option value="all">All statuses</option>
                <option value="halal">Halal only</option>
                <option value="haram">Haram only</option>
              </select>
            </div>
          </DataPanel>

          {hasNoComplianceRows ? (
            <EmptyState
              commands={["make sync-halal-stocks"]}
              message="No active HalalStock compliance rows are stored in the configured Taurus database."
              title="No Shariah compliance data"
            />
          ) : (
            <DataPanel
              actions={
                pagination ? (
                  <PaginationControls
                    onPageChange={setPage}
                    page={pagination.page}
                    total={pagination.total}
                    totalPages={pagination.total_pages}
                  />
                ) : undefined
              }
              title="Compliance Rows"
            >
              <DataTable
                columns={[
                  {
                    key: "name",
                    header: "Name",
                    render: (row) => (
                      <div className="min-w-56">
                        <p className="font-medium">{row.name}</p>
                        <p className="mt-1 text-xs text-taurus-muted">{row.industry || "-"}</p>
                      </div>
                    ),
                  },
                  {
                    key: "nse",
                    header: "NSE",
                    render: (row) => row.nse_code || "-",
                  },
                  {
                    key: "bse",
                    header: "BSE",
                    render: (row) => row.bse_code || "-",
                  },
                  {
                    key: "status",
                    header: "Status",
                    render: (row) => <StatusBadge status={row.compliance_status} size="sm" />,
                  },
                  {
                    key: "first",
                    header: "First seen",
                    render: (row) => formatTimestamp(row.first_seen_at),
                  },
                  {
                    key: "last",
                    header: "Last seen",
                    render: (row) => formatTimestamp(row.last_seen_at),
                  },
                  {
                    key: "changed",
                    header: "Changed",
                    render: (row) => formatTimestamp(row.status_changed_at),
                  },
                  {
                    key: "links",
                    header: "Links",
                    render: (row) => <SourceLinks row={row} />,
                  },
                ]}
                emptyLabel="No compliance rows match the selected filters"
                getRowKey={(row) => `${row.name}-${row.bse_code}-${row.nse_code}`}
                rows={payload.rows}
              />
              {pagination && (
                <p className="mt-4 text-xs text-taurus-muted">
                  Showing {rangeStart(pagination.page, pagination.page_size, pagination.total)}
                  {" - "}
                  {rangeEnd(pagination.page, pagination.page_size, pagination.total)} of{" "}
                  {formatNumber(pagination.total)}
                </p>
              )}
            </DataPanel>
          )}

          <div className="grid gap-6 xl:grid-cols-2">
            <DataPanel title="Latest Import">
              <KeyValueGrid
                items={
                  payload.latest_import
                    ? [
                        { label: "Fetched", value: formatTimestamp(payload.latest_import.fetched_at) },
                        { label: "Imported", value: formatTimestamp(payload.latest_import.imported_at) },
                        { label: "Rows seen", value: formatNumber(payload.latest_import.rows_seen) },
                        { label: "Rows imported", value: formatNumber(payload.latest_import.rows_imported) },
                        { label: "Duplicates", value: formatNumber(payload.latest_import.duplicate_count) },
                        {
                          label: "Source",
                          value: (
                            <ExternalTextLink href={payload.latest_import.source_url}>
                              HalalStock source
                            </ExternalTextLink>
                          ),
                        },
                      ]
                    : []
                }
              />
            </DataPanel>
            <DataPanel title="Exported Universe">
              <KeyValueGrid
                items={[
                  {
                    label: "YAML path",
                    value: payload.halal_universe_export.yaml_path ?? "-",
                  },
                  {
                    label: "Universe",
                    value: payload.halal_universe_export.universe_name ?? "-",
                  },
                  {
                    label: "Symbols",
                    value: formatNumber(payload.halal_universe_export.exported_symbol_count),
                  },
                  {
                    label: "Loaded",
                    value: payload.halal_universe_export.loaded ? "Yes" : "No",
                  },
                  {
                    label: "Error",
                    value: payload.halal_universe_export.error ?? "-",
                  },
                ]}
              />
            </DataPanel>
          </div>

          <JsonDrawer title="Shariah payload" value={payload} />
        </div>
      )}
    </PageScaffold>
  );
}

function PaginationControls({
  page,
  total,
  totalPages,
  onPageChange,
}: {
  page: number;
  total: number;
  totalPages: number;
  onPageChange: (page: number) => void;
}) {
  const safeTotalPages = Math.max(totalPages, 1);
  return (
    <div className="flex items-center gap-2">
      <button
        aria-label="Previous Shariah page"
        className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-taurus-outline bg-taurus-shell text-taurus-muted hover:border-taurus-primary hover:text-taurus-text disabled:opacity-50"
        disabled={page <= 1}
        onClick={() => onPageChange(Math.max(1, page - 1))}
        type="button"
      >
        <ChevronLeft aria-hidden="true" className="h-4 w-4" />
      </button>
      <span className="min-w-28 text-center text-sm text-taurus-muted">
        Page {Math.min(page, safeTotalPages)} of {safeTotalPages}
      </span>
      <button
        aria-label="Next Shariah page"
        className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-taurus-outline bg-taurus-shell text-taurus-muted hover:border-taurus-primary hover:text-taurus-text disabled:opacity-50"
        disabled={page >= safeTotalPages || total === 0}
        onClick={() => onPageChange(Math.min(safeTotalPages, page + 1))}
        type="button"
      >
        <ChevronRight aria-hidden="true" className="h-4 w-4" />
      </button>
    </div>
  );
}

function SourceLinks({ row }: { row: UiShariahRow }) {
  return (
    <div className="flex flex-wrap gap-2">
      <ExternalTextLink href={row.details_url}>Details</ExternalTextLink>
      <ExternalTextLink href={row.source_url}>Source</ExternalTextLink>
    </div>
  );
}

function ExternalTextLink({
  href,
  children,
}: {
  href: string | null | undefined;
  children: string;
}) {
  if (!href) {
    return <span className="text-taurus-muted">-</span>;
  }
  return (
    <a
      className="inline-flex items-center gap-1 rounded border border-taurus-outline bg-taurus-shell px-2 py-1 text-xs text-taurus-primary hover:border-taurus-primary hover:text-sky-200"
      href={href}
      rel="noreferrer"
      target="_blank"
    >
      {children}
      <ExternalLink aria-hidden="true" className="h-3 w-3" />
    </a>
  );
}

function rangeStart(page: number, pageSize: number, total: number) {
  if (total === 0) {
    return 0;
  }
  return formatNumber((page - 1) * pageSize + 1);
}

function rangeEnd(page: number, pageSize: number, total: number) {
  if (total === 0) {
    return 0;
  }
  return formatNumber(Math.min(page * pageSize, total));
}
