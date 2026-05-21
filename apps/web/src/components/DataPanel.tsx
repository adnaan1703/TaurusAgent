import type { ReactNode } from "react";
import clsx from "clsx";

type DataPanelProps = {
  title?: string;
  eyebrow?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
};

export function DataPanel({ title, eyebrow, actions, children, className }: DataPanelProps) {
  return (
    <section
      className={clsx(
        "rounded-lg border border-taurus-outline bg-taurus-surface shadow-panel",
        className,
      )}
    >
      {(title || eyebrow || actions) && (
        <div className="flex flex-wrap items-start justify-between gap-3 border-b border-taurus-outline px-5 py-4">
          <div>
            {eyebrow && (
              <p className="text-xs font-semibold uppercase text-taurus-primary">{eyebrow}</p>
            )}
            {title && <h2 className="mt-1 text-lg font-semibold text-taurus-text">{title}</h2>}
          </div>
          {actions}
        </div>
      )}
      <div className="p-5">{children}</div>
    </section>
  );
}
