import { RefreshCw } from "lucide-react";
import clsx from "clsx";

type RefreshButtonProps = {
  isRefreshing?: boolean;
  onRefresh: () => void;
};

export function RefreshButton({ isRefreshing = false, onRefresh }: RefreshButtonProps) {
  return (
    <button
      className="inline-flex items-center gap-2 rounded-md border border-taurus-outline bg-taurus-surfaceRaised px-3 py-2 text-sm font-medium text-taurus-text transition hover:border-taurus-primary hover:text-white disabled:opacity-60"
      disabled={isRefreshing}
      onClick={onRefresh}
      type="button"
    >
      <RefreshCw
        aria-hidden="true"
        className={clsx("h-4 w-4", isRefreshing && "animate-spin")}
      />
      Refresh
    </button>
  );
}
