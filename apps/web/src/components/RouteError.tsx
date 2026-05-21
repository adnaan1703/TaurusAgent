import { isRouteErrorResponse, useRouteError } from "react-router-dom";

import { EmptyState } from "./EmptyState";

export function RouteError() {
  const error = useRouteError();
  const message = isRouteErrorResponse(error)
    ? `${error.status} ${error.statusText}`
    : error instanceof Error
      ? error.message
      : "Route error";

  return (
    <div className="min-h-screen bg-taurus-bg p-6 text-taurus-text">
      <EmptyState title="Route unavailable" message={message} commands={["make ui"]} />
    </div>
  );
}
