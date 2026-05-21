import type { ReactNode } from "react";

type PageScaffoldProps = {
  title: string;
  eyebrow?: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
};

export const emptyDataCommands = [
  "make migrate",
  "make seed-mock",
  "make import-mock-news",
  "make paper-loop-mock",
];

export function PageScaffold({
  title,
  eyebrow,
  description,
  actions,
  children,
}: PageScaffoldProps) {
  return (
    <div className="mx-auto flex max-w-7xl flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          {eyebrow && (
            <p className="text-xs font-semibold uppercase text-taurus-primary">{eyebrow}</p>
          )}
          <h1 className="mt-2 text-2xl font-semibold text-taurus-text sm:text-3xl">{title}</h1>
          {description && <p className="mt-2 max-w-3xl text-sm text-taurus-muted">{description}</p>}
        </div>
        {actions}
      </div>
      {children}
    </div>
  );
}
