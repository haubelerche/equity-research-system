export type Comparator = "gte" | "lte";
export type MetricStatus = "pass" | "fail" | "warning" | "not_evaluable";

export interface MetricDef {
  id: string;
  label: string;
  englishLabel?: string;
  unit: string;
  comparator: Comparator;
  threshold: number;
  thresholdLabel?: string;
  technology: string;
  formula: string;
  aliases?: string[];
  metricType?: string;
  scope?: string;
  severity?: string;
  blocksPublish?: boolean;
}

export function evalMetricStatus(
  def: MetricDef,
  value: number | null | undefined,
): MetricStatus {
  if (value === null || value === undefined || Number.isNaN(value)) return "not_evaluable";
  if (def.comparator === "gte") return value >= def.threshold ? "pass" : "fail";
  return value <= def.threshold ? "pass" : "fail";
}

export function normalizeMetricStatus(status: string | null | undefined): MetricStatus {
  const normalized = (status ?? "").toLowerCase();
  if (normalized === "pass" || normalized === "passed" || normalized === "ok") return "pass";
  if (normalized === "warning" || normalized === "warn" || normalized === "measured_only") return "warning";
  if (normalized === "not_evaluable" || normalized === "blocked" || normalized === "not_measured") {
    return "not_evaluable";
  }
  return "fail";
}

export function formatMetricNumber(def: MetricDef, value: number): string {
  return def.unit === "%" ? `${(value * 100).toFixed(value === def.threshold ? 0 : 1)}%` : `${value}`;
}

export function formatPassCondition(def: MetricDef): string {
  if (def.thresholdLabel) return def.thresholdLabel;
  const comparator = def.comparator === "gte" ? "≥" : "≤";
  return `${comparator} ${formatMetricNumber(def, def.threshold)}`;
}

export function formatFailCondition(def: MetricDef): string {
  const comparator = def.comparator === "gte" ? "<" : ">";
  return `${comparator} ${formatMetricNumber(def, def.threshold)}`;
}
