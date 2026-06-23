import type { JsonObject } from "../api/types";
import { DataPanel } from "../components/DataPanel";
import { DataTable } from "../components/DataTable";
import { MetricCard } from "../components/MetricCard";
import {
  formatNumber,
  formatPercent,
  getPrimitive,
  getString,
  isJsonObject,
  jsonArray,
} from "../utils/format";

type TechnicalV2PanelProps = {
  technicalV2: JsonObject | null | undefined;
  title?: string;
};

export function TechnicalV2Panel({
  technicalV2,
  title = "Technical V2A Evidence",
}: TechnicalV2PanelProps) {
  if (!technicalV2) {
    return null;
  }

  const contributors = jsonArray(technicalV2.top_contributors).slice(0, 5);
  const missingFeatures = Array.isArray(technicalV2.missing_features)
    ? technicalV2.missing_features.map(String)
    : [];

  return (
    <DataPanel title={title}>
      <div className="grid gap-4">
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-6">
          <MetricCard
            label="Profile"
            supportingText={getString(technicalV2, "score_source") || "technical"}
            value={getString(technicalV2, "profile_name") || "-"}
          />
          <MetricCard
            label="Composite"
            supportingText={`Coverage ${formatPercent(getPrimitive(technicalV2, "coverage"))}`}
            value={formatNumber(getPrimitive(technicalV2, "composite_score"))}
          />
          <MetricCard
            label="Confidence"
            supportingText={`${formatNumber(missingFeatures.length)} missing`}
            value={formatPercent(getPrimitive(technicalV2, "confidence"))}
          />
          <MetricCard
            label="Alpha"
            value={formatNumber(getPrimitive(technicalV2, "alpha_score"))}
          />
          <MetricCard
            label="Risk"
            value={formatNumber(getPrimitive(technicalV2, "risk_score"))}
          />
          <MetricCard
            label="Tradability"
            value={formatNumber(getPrimitive(technicalV2, "tradability_score"))}
          />
        </div>

        <DataTable
          columns={[
            {
              key: "feature",
              header: "Contributor",
              render: (row) =>
                getString(row, "label") || getString(row, "feature_name") || "-",
            },
            {
              key: "family",
              header: "Family",
              render: (row) => getString(row, "family") || "-",
            },
            {
              key: "direction",
              header: "Direction",
              render: (row) => getString(row, "direction") || "-",
            },
            {
              key: "score",
              header: "Score",
              align: "right",
              render: (row) => formatNumber(getPrimitive(row, "score")),
            },
            {
              key: "contribution",
              header: "Contribution",
              align: "right",
              render: (row) => formatNumber(getPrimitive(row, "contribution")),
            },
          ]}
          emptyLabel="No v2A contributors stored"
          getRowKey={(row) =>
            `${getString(row, "feature_name")}-${getString(row, "label")}-${getString(row, "contribution")}`
          }
          rows={contributors}
        />

        {missingFeatures.length > 0 && (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3">
            <p className="text-sm font-medium text-amber-100">Missing v2A features</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {missingFeatures.slice(0, 12).map((feature) => (
                <span
                  className="rounded border border-amber-500/40 bg-taurus-shell px-2 py-1 font-mono text-xs text-amber-100"
                  key={feature}
                >
                  {feature}
                </span>
              ))}
              {missingFeatures.length > 12 && (
                <span className="rounded border border-amber-500/40 bg-taurus-shell px-2 py-1 text-xs text-amber-100">
                  +{missingFeatures.length - 12} more
                </span>
              )}
            </div>
          </div>
        )}
      </div>
    </DataPanel>
  );
}

export function TechnicalV2Inline({
  technicalV2,
}: {
  technicalV2: JsonObject | null | undefined;
}) {
  if (!technicalV2) {
    return <span className="text-taurus-muted">-</span>;
  }

  const contributors = jsonArray(technicalV2.top_contributors);
  const firstContributor = contributors[0];
  const missingFeatures = Array.isArray(technicalV2.missing_features)
    ? technicalV2.missing_features.length
    : 0;

  return (
    <div className="space-y-1 text-xs">
      <p className="font-mono text-taurus-text">
        {getString(technicalV2, "profile_name") || "technical_ohlcv_v2"}
      </p>
      <p className="text-taurus-muted">
        C {formatNumber(getPrimitive(technicalV2, "composite_score"))} / Conf{" "}
        {formatPercent(getPrimitive(technicalV2, "confidence"))}
      </p>
      <p className="text-taurus-muted">
        {firstContributor
          ? getString(firstContributor, "label") ||
            getString(firstContributor, "feature_name")
          : "No contributor"}
        {missingFeatures > 0 ? `, ${missingFeatures} missing` : ""}
      </p>
    </div>
  );
}

export function technicalV2FromObject(
  value: JsonObject | null | undefined,
): JsonObject | null {
  if (!value) {
    return null;
  }
  if (isJsonObject(value.technical_v2)) {
    return value.technical_v2;
  }
  if (isJsonObject(value.score_metadata) && isJsonObject(value.score_metadata.technical_v2)) {
    return value.score_metadata.technical_v2;
  }
  if (isJsonObject(value.metadata) && isJsonObject(value.metadata.technical_v2)) {
    return value.metadata.technical_v2;
  }
  if (isJsonObject(value.explanation)) {
    return technicalV2FromObject(value.explanation);
  }
  if (isJsonObject(value.ranking)) {
    return technicalV2FromObject(value.ranking);
  }
  if (isJsonObject(value.ledger_entry)) {
    return technicalV2FromObject(value.ledger_entry);
  }
  return null;
}
