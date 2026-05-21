import clsx from "clsx";

import { getStatusConfig } from "./status";

type StatusBadgeProps = {
  status: string | null | undefined;
  label?: string;
  size?: "sm" | "md";
};

const toneClasses = {
  neutral: "border-slate-600/70 bg-slate-700/35 text-slate-200",
  success: "border-emerald-400/40 bg-emerald-400/10 text-emerald-200",
  caution: "border-amber-300/45 bg-amber-300/10 text-amber-100",
  failure: "border-rose-300/45 bg-rose-400/10 text-rose-100",
  info: "border-sky-300/45 bg-sky-400/10 text-sky-100",
};

export function StatusBadge({ status, label, size = "md" }: StatusBadgeProps) {
  const config = getStatusConfig(status);
  const Icon = config.icon;

  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-md border font-medium",
        toneClasses[config.tone],
        size === "sm" ? "px-2 py-1 text-xs" : "px-2.5 py-1.5 text-sm",
      )}
    >
      <Icon aria-hidden="true" className={size === "sm" ? "h-3.5 w-3.5" : "h-4 w-4"} />
      {label ?? config.label}
    </span>
  );
}
