import type { ReactNode } from "react";

export type KeyValueGridItem = {
  label: string;
  value: ReactNode;
};

export function KeyValueGrid({ items }: { items: KeyValueGridItem[] }) {
  if (items.length === 0) {
    return <p className="text-sm text-taurus-muted">No details available.</p>;
  }

  return (
    <dl className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {items.map((item) => (
        <div className="rounded-md border border-taurus-outline bg-taurus-shell p-3" key={item.label}>
          <dt className="text-xs font-medium uppercase text-taurus-muted">{item.label}</dt>
          <dd className="mt-1 break-words text-sm font-medium text-taurus-text">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
