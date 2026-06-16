import type { BenchmarkMetricResult } from "../../api/types";
import {
  formatMetricNumber,
  formatMetricScope,
  formatMetricTypeLabel,
  formatPassCondition,
  formatRuntimeMetricResult,
  metricSemanticType,
  parseRuntimeThreshold,
  resolveMetricStatus,
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

function statusFor(
  def: MetricDef,
  result: BenchmarkMetricResult | undefined,
  value: number | null | undefined,
): MetricStatus {
  return resolveMetricStatus(def, result, value);
}

function formatThreshold(
  def: MetricDef,
  result: BenchmarkMetricResult | undefined,
): string {
  const raw = result?.threshold ?? formatPassCondition(def);
  if (def.unit !== "%") return String(raw);
  if (typeof raw === "string" && raw.includes("%")) return raw;
  const numeric = parseRuntimeThreshold(result?.threshold, (result as { unit?: string | null })?.unit)
    ?? def.threshold;
  const comparator = def.comparator === "gte" ? "≥" : "≤";
  return `${comparator} ${formatMetricNumber(def, numeric)}`;
}

export function MetricRow({ def, value, result, onSelect }: Props) {
  const status = statusFor(def, result, value);
  const threshold = formatThreshold(def, result);
  const semanticType = metricSemanticType(def, result);
  const semanticLabel = `${formatMetricTypeLabel(semanticType)} · ${formatMetricScope(def, result)}`;

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
        <span className="metric-technology metric-technology--semantic">{semanticLabel}</span>
      </td>
      <td className="num">{String(threshold)}</td>
      <td className="num">{formatRuntimeMetricResult(def, result, value, { includeFormula: false })}</td>
      <td><StatusPill status={status} /></td>
    </tr>
  );
}
