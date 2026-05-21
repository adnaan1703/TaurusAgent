import type { ReactNode } from "react";
import clsx from "clsx";

type MetricCardProps = {
  label: string;
  value: ReactNode;
  supportingText?: string;
  tone?: "neutral" | "success" | "caution" | "failure";
};

const toneClasses = {
  neutral: "border-taurus-outline",
  success: "border-emerald-400/45",
  caution: "border-amber-300/50",
  failure: "border-rose-300/50",
};

export function MetricCard({
  label,
  value,
  supportingText,
  tone = "neutral",
}: MetricCardProps) {
  return (
    <div className={clsx("rounded-lg border bg-taurus-surfaceRaised p-4", toneClasses[tone])}>
      <p className="text-sm text-taurus-muted">{label}</p>
      <div className="mt-2 text-2xl font-semibold text-taurus-text">{value}</div>
      {supportingText && <p className="mt-2 text-sm text-taurus-muted">{supportingText}</p>}
    </div>
  );
}
