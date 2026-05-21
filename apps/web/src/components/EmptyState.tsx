import type { ReactNode } from "react";
import { Terminal } from "lucide-react";

type EmptyStateProps = {
  title: string;
  message: string;
  commands?: string[];
  actions?: ReactNode;
};

export function EmptyState({ title, message, commands = [], actions }: EmptyStateProps) {
  return (
    <div className="rounded-lg border border-dashed border-taurus-outline bg-taurus-shell p-6">
      <h2 className="text-lg font-semibold text-taurus-text">{title}</h2>
      <p className="mt-2 max-w-2xl text-sm leading-6 text-taurus-muted">{message}</p>
      {commands.length > 0 && (
        <div className="mt-5 rounded-md border border-taurus-outline bg-[#07101d] p-4">
          <div className="mb-3 flex items-center gap-2 text-sm font-medium text-taurus-text">
            <Terminal aria-hidden="true" className="h-4 w-4 text-taurus-primary" />
            Commands
          </div>
          <div className="space-y-2">
            {commands.map((command) => (
              <code
                className="block overflow-x-auto rounded bg-taurus-surface px-3 py-2 font-mono text-xs text-slate-100"
                key={command}
              >
                {command}
              </code>
            ))}
          </div>
        </div>
      )}
      {actions && <div className="mt-5">{actions}</div>}
    </div>
  );
}
