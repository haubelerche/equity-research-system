import type { BenchmarkMetricResult } from "../../api/types";
import {
  evalMetricStatus,
  formatMetricNumber,
  formatPassCondition,
  normalizeMetricStatus,
  type MetricDef,
  type MetricStatus,
} from "../../lib/evalStatus";
import { StatusPill } from "./StatusPill";

interface Props {
  def: MetricDef;
  value: number | null | undefined;
  result?: BenchmarkMetricResult;
  onSelect?: (def: MetricDef, result?: BenchmarkMetricResult) => void;
}

function formatResultValue(
  def: MetricDef,
  result: BenchmarkMetricResult | undefined,
  value: number | null | undefined,
): string {
  const benchmarkValue = result?.value;
  if (typeof benchmarkValue === "number") return formatMetricNumber(def, benchmarkValue);
  if (typeof benchmarkValue === "boolean") return benchmarkValue ? "true" : "false";
  if (typeof benchmarkValue === "string" && benchmarkValue.length > 0) return benchmarkValue;
  if (value === null || value === undefined) return "Thiếu dữ liệu";
  return formatMetricNumber(def, value);
}

function statusFor(
  def: MetricDef,
  result: BenchmarkMetricResult | undefined,
  value: number | null | undefined,
): MetricStatus {
  return result?.status ? normalizeMetricStatus(String(result.status)) : evalMetricStatus(def, value);
}

export function MetricRow({ def, value, result, onSelect }: Props) {
  const status = statusFor(def, result, value);
  const threshold = result?.threshold ?? formatPassCondition(def);
  return (
    <tr
      className={onSelect ? "metric-row metric-row--clickable" : "metric-row"}
      tabIndex={onSelect ? 0 : undefined}
      onClick={() => onSelect?.(def, result)}
      onKeyDown={(event) => {
        if (onSelect && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          onSelect(def, result);
        }
      }}
    >
      <td>
        <strong>{def.label}</strong>
        <span className="metric-technology">{def.englishLabel ?? def.technology}</span>
      </td>
      <td className="num">{String(threshold)}</td>
      <td className="num">{formatResultValue(def, result, value)}</td>
      <td><StatusPill status={status} /></td>
    </tr>
  );
}
