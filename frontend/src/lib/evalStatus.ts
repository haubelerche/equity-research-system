export type Maturity = "P0" | "P1" | "P2";
export type Comparator = "gte" | "lte";
export type MetricStatus = "pass" | "fail" | "measured_only";

export interface MetricDef {
  id: string;
  label: string;
  unit: string;
  comparator: Comparator;
  thresholds: Record<Maturity, number | null>;
}

export function evalMetricStatus(
  def: MetricDef,
  value: number | null | undefined,
  maturity: Maturity
): MetricStatus {
  const threshold = def.thresholds[maturity];
  if (threshold === null || threshold === undefined) return "measured_only";
  if (value === null || value === undefined || Number.isNaN(value)) return "measured_only";
  if (def.comparator === "gte") return value >= threshold ? "pass" : "fail";
  return value <= threshold ? "pass" : "fail";
}
