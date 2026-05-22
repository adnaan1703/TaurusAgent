import { AlertTriangle, Info } from "lucide-react";

import type { UiWarning } from "../api/types";
import { formatTimestamp } from "../utils/format";

const severityClasses = {
  info: "border-sky-300/35 bg-sky-400/10 text-sky-100",
  warning: "border-amber-300/45 bg-amber-300/10 text-amber-100",
  critical: "border-rose-300/45 bg-rose-400/10 text-rose-100",
};

export function WarningsPanel({ warnings }: { warnings: UiWarning[] }) {
  if (warnings.length === 0) {
    return null;
  }

  return (
    <div className="grid gap-3">
      {warnings.map((warning) => {
        const Icon = warning.severity === "info" ? Info : AlertTriangle;
        return (
          <article
            className={`rounded-md border p-4 ${severityClasses[warning.severity]}`}
            key={warning.id}
          >
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="flex min-w-0 gap-3">
                <Icon aria-hidden="true" className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  <h2 className="text-sm font-semibold">{warning.title}</h2>
                  <p className="mt-1 text-sm opacity-85">{warning.message}</p>
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2 font-mono text-xs opacity-75">
                {warning.symbol && <span>{warning.symbol}</span>}
                {warning.run_id && <span>{warning.run_id}</span>}
                {warning.created_at && <span>{formatTimestamp(warning.created_at)}</span>}
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}
