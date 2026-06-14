import { evalMetricStatus, type MetricDef, type Maturity } from "../../lib/evalStatus";
import { StatusPill } from "./StatusPill";

interface Props { def: MetricDef; value: number | null | undefined; maturity: Maturity; }

function fmtThreshold(def: MetricDef, m: Maturity): string {
  const v = def.thresholds[m];
  if (v === null || v === undefined) return "—";
  const cmp = def.comparator === "gte" ? "≥" : "≤";
  return def.unit === "%" ? `${cmp} ${(v * 100).toFixed(0)}%` : `${cmp} ${v}`;
}

function fmtValue(def: MetricDef, value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return def.unit === "%" ? `${(value * 100).toFixed(1)}%` : `${value}`;
}

export function MetricRow({ def, value, maturity }: Props) {
  const status = evalMetricStatus(def, value, maturity);
  return (
    <tr>
      <td>{def.label}</td>
      <td className="num">{fmtThreshold(def, maturity)}</td>
      <td className="num">{fmtValue(def, value)}</td>
      <td><StatusPill status={status} /></td>
    </tr>
  );
}
