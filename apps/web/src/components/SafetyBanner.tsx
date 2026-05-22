import { ShieldCheck, ShieldOff } from "lucide-react";

import type { UiSafetyStatus } from "../api/types";
import { StatusBadge } from "./StatusBadge";

export function SafetyBanner({ safety }: { safety: UiSafetyStatus }) {
  const Icon = safety.live_trading_enabled ? ShieldOff : ShieldCheck;

  return (
    <section className="rounded-lg border border-taurus-outline bg-taurus-surfaceRaised p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-md border border-taurus-outline bg-taurus-shell">
            <Icon aria-hidden="true" className="h-5 w-5 text-taurus-primary" />
          </div>
          <div>
            <p className="text-sm font-semibold text-taurus-text">Paper-mode safety context</p>
            <p className="mt-1 text-xs text-taurus-muted">
              Taurus mode {safety.taurus_mode}; alert provider {safety.alert_provider ?? "unset"}.
            </p>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <StatusBadge
            label={safety.live_trading_enabled ? "LIVE_TRADING_ENABLED=true" : "LIVE_TRADING_ENABLED=false"}
            status={safety.live_trading_enabled ? "BLOCKED" : "APPROVED"}
            size="sm"
          />
          <StatusBadge label={`BROKER_PROVIDER=${safety.broker_provider}`} status="APPROVED_FOR_PAPER" size="sm" />
        </div>
      </div>
    </section>
  );
}
