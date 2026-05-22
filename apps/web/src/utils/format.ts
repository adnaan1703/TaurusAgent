import type { JsonObject, JsonPrimitive, JsonValue, UiMetric } from "../api/types";

const INR_FORMATTER = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 0,
  style: "currency",
  currency: "INR",
});

const NUMBER_FORMATTER = new Intl.NumberFormat("en-IN", {
  maximumFractionDigits: 2,
});

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat("en-IN", {
  dateStyle: "medium",
  timeStyle: "short",
});

export type KeyValueItem = {
  label: string;
  value: string;
};

export function isJsonObject(value: JsonValue | unknown): value is JsonObject {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

export function getPrimitive(
  record: JsonObject | null | undefined,
  key: string,
): JsonPrimitive | undefined {
  const value = record?.[key];
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean" ||
    value === null
  ) {
    return value;
  }
  return undefined;
}

export function getString(record: JsonObject | null | undefined, key: string): string {
  const value = getPrimitive(record, key);
  return value === undefined || value === null ? "" : String(value);
}

export function getNumber(record: JsonObject | null | undefined, key: string): number | null {
  const value = getPrimitive(record, key);
  if (typeof value === "number") {
    return value;
  }
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

export function jsonArray(value: JsonValue | unknown): JsonObject[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value.filter(isJsonObject);
}

export function formatNumber(value: JsonPrimitive | undefined): string {
  if (value === undefined || value === null || value === "") {
    return "-";
  }
  if (typeof value === "boolean") {
    return value ? "Yes" : "No";
  }
  const numberValue = typeof value === "number" ? value : Number(value);
  if (Number.isFinite(numberValue)) {
    return NUMBER_FORMATTER.format(numberValue);
  }
  return String(value);
}

export function formatInr(value: JsonPrimitive | undefined): string {
  if (value === undefined || value === null || value === "") {
    return "-";
  }
  const numberValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numberValue)) {
    return String(value);
  }
  return INR_FORMATTER.format(numberValue);
}

export function formatPercent(value: JsonPrimitive | undefined): string {
  if (value === undefined || value === null || value === "") {
    return "-";
  }
  const numberValue = typeof value === "number" ? value : Number(value);
  if (!Number.isFinite(numberValue)) {
    return String(value);
  }
  const percent = Math.abs(numberValue) <= 1 ? numberValue * 100 : numberValue;
  return `${NUMBER_FORMATTER.format(percent)}%`;
}

export function formatTimestamp(value: string | null | undefined): string {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return DATE_TIME_FORMATTER.format(date);
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return "-";
  }
  if (seconds < 60) {
    return `${Math.round(seconds)}s`;
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = Math.round(seconds % 60);
  if (minutes < 60) {
    return `${minutes}m ${remainingSeconds}s`;
  }
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes}m`;
}

export function formatMetric(metric: UiMetric): string {
  const value = metric.value;
  if (metric.unit === "INR") {
    return formatInr(value);
  }
  if (metric.unit === "%") {
    return formatPercent(value);
  }
  return formatNumber(value);
}

export function formatMetricValue(label: string, value: JsonPrimitive | undefined): string {
  const lower = label.toLowerCase();
  if (lower.includes("inr") || lower.includes("cash") || lower.includes("equity")) {
    return formatInr(value);
  }
  if (lower.includes("pct") || lower.includes("percent") || lower.includes("bps")) {
    return lower.includes("bps") ? `${formatNumber(value)} bps` : formatPercent(value);
  }
  return formatNumber(value);
}

export function formatId(id: string | null | undefined): string {
  if (!id) {
    return "-";
  }
  if (id.length <= 18) {
    return id;
  }
  return `${id.slice(0, 10)}...${id.slice(-4)}`;
}

export function objectEntries(record: JsonObject | null | undefined): KeyValueItem[] {
  if (!record) {
    return [];
  }
  return Object.entries(record)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => ({
      label: humanizeKey(key),
      value: primitiveToText(value),
    }));
}

export function humanizeKey(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (match) => match.toUpperCase());
}

function primitiveToText(value: JsonValue): string {
  if (
    typeof value === "string" ||
    typeof value === "number" ||
    typeof value === "boolean" ||
    value === null
  ) {
    return formatNumber(value);
  }
  if (Array.isArray(value)) {
    return `${value.length} item${value.length === 1 ? "" : "s"}`;
  }
  return `${Object.keys(value).length} fields`;
}
