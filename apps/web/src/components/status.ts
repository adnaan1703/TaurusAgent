import type { LucideIcon } from "lucide-react";
import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Circle,
  Clock3,
  MinusCircle,
  ShieldAlert,
  ShieldCheck,
  XCircle,
} from "lucide-react";

import type { StageStatus } from "../api/types";

export type StatusTone = "neutral" | "success" | "caution" | "failure" | "info";

export type StatusConfig = {
  label: string;
  tone: StatusTone;
  icon: LucideIcon;
};

const DEFAULT_STATUS: StatusConfig = {
  label: "Unknown",
  tone: "neutral",
  icon: Circle,
};

const STATUS_MAP: Record<string, StatusConfig> = {
  RUNNING: { label: "Running", tone: "info", icon: Clock3 },
  COMPLETED: { label: "Completed", tone: "success", icon: CheckCircle2 },
  PARTIAL_FAILED: { label: "Partial failed", tone: "caution", icon: AlertTriangle },
  FAILED: { label: "Failed", tone: "failure", icon: XCircle },

  complete: { label: "Complete", tone: "success", icon: CheckCircle2 },
  running: { label: "Running", tone: "info", icon: Clock3 },
  blocked: { label: "Blocked", tone: "failure", icon: Ban },
  rejected: { label: "Rejected", tone: "failure", icon: XCircle },
  failed: { label: "Failed", tone: "failure", icon: XCircle },
  missing: { label: "Missing", tone: "neutral", icon: MinusCircle },
  skipped: { label: "Skipped", tone: "neutral", icon: MinusCircle },

  APPROVED: { label: "Approved", tone: "success", icon: ShieldCheck },
  APPROVED_WITH_REDUCTION: {
    label: "Reduced",
    tone: "caution",
    icon: ShieldAlert,
  },
  APPROVED_FOR_PAPER: { label: "Approved for paper", tone: "success", icon: ShieldCheck },
  REJECTED: { label: "Rejected", tone: "failure", icon: XCircle },
  BLOCKED: { label: "Blocked", tone: "failure", icon: Ban },

  CREATED: { label: "Created", tone: "info", icon: Circle },
  ACCEPTED: { label: "Accepted", tone: "info", icon: CheckCircle2 },
  PARTIALLY_FILLED: { label: "Partially filled", tone: "caution", icon: Clock3 },
  FILLED: { label: "Filled", tone: "success", icon: CheckCircle2 },
  CANCELLED: { label: "Cancelled", tone: "neutral", icon: MinusCircle },

  halal: { label: "Halal", tone: "success", icon: ShieldCheck },
  haram: { label: "Haram", tone: "failure", icon: Ban },
};

export function getStatusConfig(status: string | StageStatus | null | undefined): StatusConfig {
  if (!status) {
    return DEFAULT_STATUS;
  }
  return STATUS_MAP[status] ?? {
    label: humanizeStatus(status),
    tone: "neutral",
    icon: Circle,
  };
}

function humanizeStatus(status: string): string {
  return status
    .toLowerCase()
    .split("_")
    .filter(Boolean)
    .map((part) => part[0].toUpperCase() + part.slice(1))
    .join(" ");
}
