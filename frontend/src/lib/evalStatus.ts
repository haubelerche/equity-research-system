export type Comparator = "gte" | "lte";
export type MetricStatus = "pass" | "fail";

export interface MetricDef {
  id: string;
  label: string;
  unit: string;
  comparator: Comparator;
  threshold: number;
  technology: string;
  formula: string;
}

export function evalMetricStatus(
  def: MetricDef,
  value: number | null | undefined,
): MetricStatus {
  if (value === null || value === undefined || Number.isNaN(value)) return "fail";
  if (def.comparator === "gte") return value >= def.threshold ? "pass" : "fail";
  return value <= def.threshold ? "pass" : "fail";
}

export function formatMetricNumber(def: MetricDef, value: number): string {
  return def.unit === "%" ? `${(value * 100).toFixed(value === def.threshold ? 0 : 1)}%` : `${value}`;
}

export function formatPassCondition(def: MetricDef): string {
  const comparator = def.comparator === "gte" ? "≥" : "≤";
  return `${comparator} ${formatMetricNumber(def, def.threshold)}`;
}

export function formatFailCondition(def: MetricDef): string {
  const comparator = def.comparator === "gte" ? "<" : ">";
  return `${comparator} ${formatMetricNumber(def, def.threshold)}`;
}
