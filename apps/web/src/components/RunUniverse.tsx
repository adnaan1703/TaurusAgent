import type { UiRunUniverse } from "../api/types";
import { formatNumber } from "../utils/format";

export function RunUniverseSummary({ universe }: { universe?: UiRunUniverse | null }) {
  if (!universe) {
    return <span className="text-taurus-muted">Not recorded</span>;
  }

  const selected = universe.selected_symbol_count ?? universe.symbols.length;
  const available = universe.available_symbol_count;
  return (
    <div className="space-y-1 text-xs">
      <p className="font-medium text-taurus-text">{runUniverseTitle(universe)}</p>
      <p className="text-taurus-muted">
        {universe.provider ?? "provider unknown"} / {formatNumber(selected)} selected
        {available !== null && available !== undefined
          ? ` of ${formatNumber(available)}`
          : ""}
      </p>
    </div>
  );
}

export function runUniverseTitle(universe?: UiRunUniverse | null): string {
  if (!universe) {
    return "Not recorded";
  }
  if (universe.source === "market_data_universe") {
    return universe.universe_name || "Market-data universe";
  }
  if (universe.source === "manual_symbols") {
    return "Manual symbols";
  }
  return universe.source;
}
