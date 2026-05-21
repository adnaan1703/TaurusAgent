import type { ReactNode } from "react";

export type DataTableColumn<Row> = {
  key: string;
  header: string;
  render: (row: Row) => ReactNode;
  align?: "left" | "right";
};

type DataTableProps<Row> = {
  columns: DataTableColumn<Row>[];
  rows: Row[];
  getRowKey: (row: Row) => string;
  emptyLabel?: string;
};

export function DataTable<Row>({
  columns,
  rows,
  getRowKey,
  emptyLabel = "No rows",
}: DataTableProps<Row>) {
  if (rows.length === 0) {
    return (
      <div className="rounded-md border border-dashed border-taurus-outline bg-taurus-shell p-5 text-sm text-taurus-muted">
        {emptyLabel}
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="min-w-full divide-y divide-taurus-outline text-sm">
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                className="px-3 py-2 text-left font-medium text-taurus-muted"
                key={column.key}
                scope="col"
              >
                <span className={column.align === "right" ? "block text-right" : undefined}>
                  {column.header}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-taurus-outline">
          {rows.map((row) => (
            <tr className="hover:bg-taurus-surfaceRaised/60" key={getRowKey(row)}>
              {columns.map((column) => (
                <td className="px-3 py-3 text-taurus-text" key={column.key}>
                  <span className={column.align === "right" ? "block text-right" : undefined}>
                    {column.render(row)}
                  </span>
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
