import { useQuery } from "@tanstack/react-query";
import clsx from "clsx";
import {
  Activity,
  History,
  LayoutDashboard,
  ListTree,
  Network,
  RefreshCw,
  Scale,
  ShieldCheck,
  Wallet,
} from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";

import { taurusApi } from "../api/client";
import type { UiSafetyStatus } from "../api/types";
import { StatusBadge } from "./StatusBadge";

const navItems = [
  { to: "/", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/history", label: "History", icon: History },
  { to: "/risk", label: "Risk", icon: ShieldCheck },
  { to: "/portfolio", label: "Portfolio", icon: Wallet },
  { to: "/shariah", label: "Shariah", icon: Scale },
  { to: "/graph", label: "Graph", icon: Network },
];

export function AppShell() {
  const overviewQuery = useQuery({
    queryKey: ["ui", "overview"],
    queryFn: taurusApi.overview,
    refetchInterval: 15_000,
  });

  const safety = overviewQuery.data?.safety;

  return (
    <div className="min-h-screen bg-taurus-bg text-taurus-text">
      <aside className="fixed inset-y-0 left-0 hidden w-72 border-r border-taurus-outline bg-taurus-shell px-5 py-6 lg:block">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-taurus-outline bg-taurus-surfaceRaised">
            <Activity aria-hidden="true" className="h-5 w-5 text-taurus-primary" />
          </div>
          <div>
            <p className="text-lg font-semibold">Taurus</p>
            <p className="text-xs text-taurus-muted">Paper observability</p>
          </div>
        </div>

        <nav className="mt-8 space-y-1" aria-label="Primary navigation">
          {navItems.map((item) => (
            <NavItem key={item.to} {...item} />
          ))}
        </nav>

        <div className="absolute bottom-6 left-5 right-5 rounded-lg border border-taurus-outline bg-taurus-surface p-4">
          <SafetyStatus isError={overviewQuery.isError} isLoading={overviewQuery.isLoading} safety={safety} />
        </div>
      </aside>

      <div className="lg:pl-72">
        <header className="sticky top-0 z-20 border-b border-taurus-outline bg-taurus-shell/95 px-4 py-3 backdrop-blur lg:px-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-3 lg:hidden">
              <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-taurus-outline bg-taurus-surfaceRaised">
                <Activity aria-hidden="true" className="h-4 w-4 text-taurus-primary" />
              </div>
              <div>
                <p className="font-semibold">Taurus</p>
                <p className="text-xs text-taurus-muted">Paper observability</p>
              </div>
            </div>
            <div className="hidden items-center gap-3 lg:flex">
              <ListTree aria-hidden="true" className="h-5 w-5 text-taurus-primary" />
              <span className="text-sm text-taurus-muted">Run-loop dashboard</span>
            </div>
            <div className="flex items-center gap-2">
              <SafetyPills safety={safety} />
              <button
                aria-label="Refresh safety status"
                className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-taurus-outline bg-taurus-surfaceRaised text-taurus-muted hover:border-taurus-primary hover:text-taurus-text"
                disabled={overviewQuery.isFetching}
                onClick={() => void overviewQuery.refetch()}
                type="button"
              >
                <RefreshCw
                  aria-hidden="true"
                  className={clsx("h-4 w-4", overviewQuery.isFetching && "animate-spin")}
                />
              </button>
            </div>
          </div>

          <nav className="mt-3 flex gap-2 overflow-x-auto lg:hidden" aria-label="Primary navigation">
            {navItems.map((item) => (
              <MobileNavItem key={item.to} {...item} />
            ))}
          </nav>
        </header>

        <main className="px-4 py-6 lg:px-8">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

type NavItemProps = (typeof navItems)[number];

function NavItem({ to, label, icon: Icon, end }: NavItemProps) {
  return (
    <NavLink
      className={({ isActive }) =>
        clsx(
          "flex items-center gap-3 rounded-md px-3 py-2.5 text-sm font-medium transition",
          isActive
            ? "bg-taurus-surfaceRaised text-taurus-text"
            : "text-taurus-muted hover:bg-taurus-surface hover:text-taurus-text",
        )
      }
      end={end}
      to={to}
    >
      <Icon aria-hidden="true" className="h-4 w-4" />
      {label}
    </NavLink>
  );
}

function MobileNavItem({ to, label, icon: Icon, end }: NavItemProps) {
  return (
    <NavLink
      className={({ isActive }) =>
        clsx(
          "inline-flex shrink-0 items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium",
          isActive
            ? "border-taurus-primary bg-sky-400/10 text-taurus-text"
            : "border-taurus-outline bg-taurus-surface text-taurus-muted",
        )
      }
      end={end}
      to={to}
    >
      <Icon aria-hidden="true" className="h-4 w-4" />
      {label}
    </NavLink>
  );
}

function SafetyStatus({
  safety,
  isLoading,
  isError,
}: {
  safety: UiSafetyStatus | undefined;
  isLoading: boolean;
  isError: boolean;
}) {
  if (isLoading) {
    return <p className="text-sm text-taurus-muted">Loading safety status</p>;
  }
  if (isError || !safety) {
    return (
      <div>
        <p className="text-sm font-medium text-rose-100">API unavailable</p>
        <code className="mt-2 block rounded bg-[#07101d] px-2 py-1 font-mono text-xs text-slate-200">
          make api
        </code>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium text-taurus-text">Safety</p>
      <div className="flex flex-wrap gap-2">
        <StatusBadge
          label={safety.live_trading_enabled ? "Live enabled" : "Live disabled"}
          status={safety.live_trading_enabled ? "BLOCKED" : "APPROVED"}
          size="sm"
        />
        <StatusBadge label={safety.broker_provider} status="APPROVED_FOR_PAPER" size="sm" />
      </div>
      <p className="font-mono text-xs text-taurus-muted">{safety.taurus_mode}</p>
    </div>
  );
}

function SafetyPills({
  safety,
}: {
  safety: UiSafetyStatus | undefined;
}) {
  if (!safety) {
    return <StatusBadge label="API unavailable" status="FAILED" size="sm" />;
  }

  return (
    <div className="hidden items-center gap-2 sm:flex">
      <StatusBadge
        label={safety.live_trading_enabled ? "Live enabled" : "Live disabled"}
        status={safety.live_trading_enabled ? "BLOCKED" : "APPROVED"}
        size="sm"
      />
      <StatusBadge label={safety.broker_provider} status="APPROVED_FOR_PAPER" size="sm" />
    </div>
  );
}
