import { AlertTriangle, LoaderCircle } from "lucide-react";

import { EmptyState } from "./EmptyState";

export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center gap-2 rounded-lg border border-taurus-outline bg-taurus-shell p-5 text-sm text-taurus-muted">
      <LoaderCircle aria-hidden="true" className="h-4 w-4 animate-spin text-taurus-primary" />
      {label}
    </div>
  );
}

export function ErrorState({ message }: { message: string }) {
  return (
    <div className="rounded-lg border border-rose-300/45 bg-rose-400/10 p-5 text-sm text-rose-100">
      <div className="flex items-center gap-2 font-medium">
        <AlertTriangle aria-hidden="true" className="h-4 w-4" />
        API unavailable
      </div>
      <p className="mt-2 text-rose-100/85">{message}</p>
      <div className="mt-4">
        <EmptyState title="Start the API" message="The dashboard needs the local FastAPI service." commands={["make api"]} />
      </div>
    </div>
  );
}
