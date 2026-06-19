export type Comparator = "gte" | "lte";
export type MetricStatus = "pass" | "fail" | "warning" | "not_evaluable" | "blocked" | "not_measured";

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

interface RuntimeMetricFields {
  value?: number | string | boolean | null;
  status?: string | null;
  threshold?: number | string | boolean | null;
  threshold_operator?: string | null;
  unit?: string | null;
  metric_type?: string | null;
  metric_id?: string | null;
  id?: string | null;
  sample_size?: number | null;
  failed_examples?: unknown[] | null;
  detail?: string | null;
  evaluator?: {
    execution_status?: string | null;
  } | null;
  calculation?: {
    aggregation?: string | null;
    numerator?: number | null;
    denominator?: number | null;
  } | null;
}

export function coerceMetricValue(value: unknown): number | null {
  if (typeof value === "number") return Number.isFinite(value) ? value : null;
  if (typeof value === "boolean") return value ? 1 : 0;
  return null;
}

export function parseRuntimeThreshold(threshold: unknown, unit?: string | null): number | null {
  if (typeof threshold === "number") return Number.isFinite(threshold) ? threshold : null;
  if (typeof threshold === "boolean") return threshold ? 1 : 0;
  if (typeof threshold !== "string") return null;

  // Relative contracts need their reference series to be evaluated correctly.
  // Parsing the percentage delta as an absolute threshold (for example,
  // "<= baseline p95 + 30%" -> 0.3 seconds) produces a false failure.
  if (/\bbaseline\b/i.test(threshold)) return null;

  const ratio = threshold.match(/(-?\d+(?:\.\d+)?)\s*\/\s*(-?\d+(?:\.\d+)?)/);
  if (ratio) {
    const numerator = Number(ratio[1]);
    const denominator = Number(ratio[2]);
    if (Number.isFinite(numerator) && Number.isFinite(denominator) && denominator !== 0) {
      return numerator / denominator;
    }
  }

  const match = threshold.match(/-?\d+(?:\.\d+)?/);
  if (!match) return null;

  const parsed = Number(match[0]);
  if (!Number.isFinite(parsed)) return null;

  const isPercent = threshold.includes("%") || unit === "%" || unit === "percent";
  return isPercent && Math.abs(parsed) > 1 ? parsed / 100 : parsed;
}

function runtimeAggregation(result?: RuntimeMetricFields): string {
  return String(result?.calculation?.aggregation ?? "").toLowerCase();
}

function isMeanAggregation(aggregation: string): boolean {
  return [
    "mean",
    "cohort_mean",
    "cohort_mean_observed",
    "weighted_mean",
    "weighted_score",
    "rubric_score",
  ].includes(aggregation);
}

function isRatioAggregation(aggregation: string): boolean {
  return [
    "coverage",
    "cohort_pooled_coverage",
    "cohort_pass_rate",
    "rate",
    "ratio",
  ].includes(aggregation);
}

function ratioMatchesValue(
  numerator: number | null | undefined,
  denominator: number | null | undefined,
  value: unknown,
): boolean {
  if (numerator === null || numerator === undefined || denominator === null || denominator === undefined) {
    return false;
  }
  if (denominator === 0) return false;
  const numeric = coerceMetricValue(value);
  if (numeric === null) return false;
  return Math.abs((numerator / denominator) - numeric) <= 0.0005;
}

export function inferRuntimeComparator(
  threshold: unknown,
  thresholdOperator?: string | null,
  metricType?: string | null,
  metricId?: string | null,
): Comparator {
  const operator = `${thresholdOperator ?? ""} ${typeof threshold === "string" ? threshold : ""}`.trim();
  if (/[<≤]/.test(operator)) return "lte";
  if (/[>≥]/.test(operator)) return "gte";

  const lowerIsBetter = `${metricType ?? ""} ${metricId ?? ""}`.toLowerCase();
  if (
    lowerIsBetter.includes("error")
    || lowerIsBetter.includes("failure")
    || lowerIsBetter.includes("violation")
    || lowerIsBetter.includes("mismatch")
    || lowerIsBetter.includes("duplicate")
    || lowerIsBetter.includes("latency")
    || lowerIsBetter.includes("retry")
    || lowerIsBetter.includes("fallback")
  ) {
    return "lte";
  }

  return "gte";
}

export function resolveMetricStatus(
  def: MetricDef,
  result?: RuntimeMetricFields,
  fallbackValue?: number | null | undefined,
): MetricStatus {
  const runtimeStatus = result?.status ? normalizeMetricStatus(String(result.status)) : null;
  if (runtimeStatus && ["blocked", "not_evaluable", "not_measured"].includes(runtimeStatus)) {
    return runtimeStatus;
  }
  const rawValue = result && Object.prototype.hasOwnProperty.call(result, "value")
    ? result.value
    : fallbackValue;
  const value = coerceMetricValue(rawValue);
  if (value === null) {
    return runtimeStatus ?? "fail";
  }

  const threshold = parseRuntimeThreshold(result?.threshold, result?.unit) ?? def.threshold;
  if (
    result
    && Object.prototype.hasOwnProperty.call(result, "threshold")
    && parseRuntimeThreshold(result.threshold, result.unit) === null
    && result.status
  ) {
    const status = runtimeStatus ?? normalizeMetricStatus(String(result.status));
    return status;
  }
  const comparator = result?.threshold === undefined || result?.threshold === null
    ? def.comparator
    : inferRuntimeComparator(
      result.threshold,
      result.threshold_operator,
      result.metric_type,
      result.metric_id ?? result.id ?? def.id,
    );

  const computedStatus = evalMetricStatus({ ...def, threshold, comparator }, value);
  return computedStatus;
}

export type MetricSemanticType = "boolean_gate" | "pass_rate" | "error_count" | "error_rate" | "score" | "diagnostic";

export function metricSemanticType(def: MetricDef, result?: RuntimeMetricFields): MetricSemanticType {
  const metricType = String(result?.metric_type ?? def.metricType ?? "").toLowerCase();
  const unit = String(result?.unit ?? def.unit ?? "").toLowerCase();
  const threshold = String(result?.threshold ?? def.thresholdLabel ?? "").toLowerCase();
  const aggregation = runtimeAggregation(result);
  const id = String(result?.metric_id ?? result?.id ?? def.id).toLowerCase();

  if (metricType === "boolean" || unit === "boolean" || threshold.includes("true") || threshold.includes("false")) {
    return "boolean_gate";
  }
  if (aggregation === "boolean_gate") {
    return "boolean_gate";
  }
  if (isMeanAggregation(aggregation)) {
    return metricType === "score" || unit === "score" || unit === "percent" || def.unit === "%" ? "score" : "diagnostic";
  }
  if (metricType === "error_rate") return "error_rate";
  if (
    metricType === "error_count"
    || id.includes("error")
    || id.includes("violation")
    || id.includes("failure")
    || id.includes("mismatch")
  ) {
    return threshold.includes("100%") || aggregation.includes("pass_rate") ? "pass_rate" : "error_count";
  }
  if (
    metricType === "coverage"
    || metricType === "pass_rate"
    || isRatioAggregation(aggregation)
    || unit === "percent"
    || def.unit === "%"
  ) {
    return "pass_rate";
  }
  if (metricType === "score") return "score";
  return "diagnostic";
}

export function formatMetricTypeLabel(type: MetricSemanticType): string {
  if (type === "boolean_gate") return "boolean_gate";
  if (type === "pass_rate") return "pass_rate";
  if (type === "error_count") return "error_count";
  if (type === "error_rate") return "error_rate";
  if (type === "score") return "score";
  return "diagnostic";
}

export function formatMetricScope(def: MetricDef, result?: RuntimeMetricFields): string {
  const type = metricSemanticType(def, result);
  const numerator = result?.calculation?.numerator;
  const denominator = result?.calculation?.denominator;
  const aggregation = runtimeAggregation(result);
  if (
    aggregation === "cohort_mean_observed"
    && denominator !== null
    && denominator !== undefined
    && result?.sample_size !== null
    && result?.sample_size !== undefined
  ) {
    return `${formatRoundedNumber(denominator)}/${formatRoundedNumber(result.sample_size)} samples`;
  }
  if (aggregation === "cohort_mean" && denominator !== null && denominator !== undefined) {
    return `${formatRoundedNumber(denominator)} values`;
  }
  if (aggregation === "cohort_pooled_coverage" && denominator !== null && denominator !== undefined) {
    return `${formatRoundedNumber(denominator)} eligible samples`;
  }
  if ((type === "pass_rate" || type === "error_rate") && denominator !== null && denominator !== undefined) {
    return `${formatRoundedNumber(denominator)} case đủ điều kiện`;
  }
  if (type === "error_count") {
    const sampleSize = result?.sample_size;
    const affected = Array.isArray(result?.failed_examples) ? result.failed_examples.length : null;
    if (affected !== null && sampleSize !== null && sampleSize !== undefined) {
      return `${formatRoundedNumber(affected)}/${formatRoundedNumber(sampleSize)} case ảnh hưởng`;
    }
    if (sampleSize !== null && sampleSize !== undefined) return `${formatRoundedNumber(sampleSize)} mẫu`;
  }
  if (type === "boolean_gate") return "artifact bắt buộc";
  if (numerator !== null && numerator !== undefined && denominator !== null && denominator !== undefined) {
    return `${formatRoundedNumber(numerator)}/${formatRoundedNumber(denominator)}`;
  }
  return result?.sample_size !== null && result?.sample_size !== undefined
    ? `${formatRoundedNumber(result.sample_size)} samples`
    : "runtime metric";
}

export function formatRuntimeMetricResult(
  def: MetricDef,
  result?: RuntimeMetricFields,
  fallbackValue?: number | null,
  options: { includeFormula?: boolean } = {},
): string {
  const type = metricSemanticType(def, result);
  const value = result && Object.prototype.hasOwnProperty.call(result, "value")
    ? result.value
    : fallbackValue;
  const numerator = result?.calculation?.numerator;
  const denominator = result?.calculation?.denominator;

  if (value === null || value === undefined || value === "") {
    const reason = missingMetricReason(result);
    return reason ? `Thiếu dữ liệu: ${reason}` : "Thiếu dữ liệu";
  }
  if (type === "boolean_gate") {
    if (typeof value === "boolean") return value ? "true" : "false";
    return coerceMetricValue(value) === 1 ? "true" : "false";
  }
  if (type === "pass_rate") {
    const numeric = coerceMetricValue(value);
    const percent = numeric === null ? String(value) : formatMetricNumber({ ...def, unit: "%" }, numeric);
    if (
      options.includeFormula !== false
      && numerator !== null
      && numerator !== undefined
      && denominator !== null
      && denominator !== undefined
      && ratioMatchesValue(numerator, denominator, value)
    ) {
      return `${formatRoundedNumber(numerator)}/${formatRoundedNumber(denominator)} = ${percent}`;
    }
    return percent;
  }
  if (type === "error_rate") {
    const numeric = coerceMetricValue(value);
    return numeric === null ? String(value) : formatMetricNumber({ ...def, unit: "%" }, numeric);
  }
  if (type === "error_count") {
    const numeric = coerceMetricValue(value);
    return `${numeric === null ? String(value) : formatRoundedNumber(numeric)} lỗi`;
  }
  if (type === "score") {
    const numeric = coerceMetricValue(value);
    return numeric === null ? String(value) : formatMetricNumber(displayDefForMetric(def, result), numeric);
  }
  if (typeof value === "number") return formatMetricNumber(displayDefForMetric(def, result), value);
  if (typeof value === "boolean") return value ? "true" : "false";
  return String(value);
}

function missingMetricReason(result?: RuntimeMetricFields): string | null {
  const detail = String(result?.detail ?? "").trim();
  if (detail) return detail;
  const examples = result?.failed_examples;
  if (Array.isArray(examples)) {
    for (const item of examples) {
      if (!item || typeof item !== "object") continue;
      const record = item as Record<string, unknown>;
      const reason = String(record.reason ?? record.detail ?? "").trim();
      if (reason) return reason;
    }
  }
  const executionStatus = String(result?.evaluator?.execution_status ?? "").trim();
  return executionStatus === "not_executed" ? "evaluator_not_executed" : null;
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
  if (normalized === "blocked") return "blocked";
  if (normalized === "not_measured") return "not_measured";
  if (normalized === "not_evaluable") return "not_evaluable";
  return "fail";
}

export function formatMetricNumber(def: MetricDef, value: number): string {
  if (!Number.isFinite(value)) return `${value}`;
  if (def.unit !== "%") return formatRoundedNumber(value);
  const displayValue = Math.abs(value) <= 1 ? value * 100 : value;
  const displayThreshold = Math.abs(def.threshold) <= 1 ? def.threshold * 100 : def.threshold;
  return `${formatRoundedNumber(displayValue, displayValue === displayThreshold ? 0 : 1)}%`;
}

function shouldDisplayAsPercent(def: MetricDef, result?: RuntimeMetricFields): boolean {
  const type = metricSemanticType(def, result);
  const unit = String(result?.unit ?? def.unit ?? "").toLowerCase();
  if (type === "pass_rate" || type === "error_rate") return true;
  if (unit === "%" || unit === "percent") return true;
  if (type !== "score") return false;
  if (unit === "usd" || unit === "seconds" || unit === "minutes" || unit === "count" || unit === "ratio") {
    return false;
  }
  return unit === "" || unit === "score";
}

function displayDefForMetric(def: MetricDef, result?: RuntimeMetricFields): MetricDef {
  return shouldDisplayAsPercent(def, result) ? { ...def, unit: "%" } : def;
}

function thresholdOperatorSymbol(result?: RuntimeMetricFields): "=" | "≥" | "≤" | ">" | "<" {
  const operator = String(result?.threshold_operator ?? "").trim();
  if (operator === "=" || operator === ">=" || operator === "<=" || operator === ">" || operator === "<") {
    return operator === ">=" ? "≥" : operator === "<=" ? "≤" : operator;
  }
  const thresholdText = typeof result?.threshold === "string" ? result.threshold.trim() : "";
  if (thresholdText.startsWith(">=")) return "≥";
  if (thresholdText.startsWith("<=")) return "≤";
  if (thresholdText.startsWith(">")) return ">";
  if (thresholdText.startsWith("<")) return "<";
  if (thresholdText.startsWith("=")) return "=";
  return inferRuntimeComparator(
    result?.threshold,
    result?.threshold_operator,
    result?.metric_type,
    result?.metric_id ?? result?.id,
  ) === "gte" ? "≥" : "≤";
}

export function formatRuntimeThreshold(def: MetricDef, result?: RuntimeMetricFields): string {
  if (!result) return formatPassCondition(def);
  const raw = result?.threshold ?? formatPassCondition(def);
  const rawText = String(raw);
  if (raw === null || raw === undefined || rawText === "") return "Chưa có";
  if (typeof raw === "boolean") return raw ? "true" : "false";
  if (rawText.toLowerCase() === "pass" || rawText.toLowerCase() === "present") return rawText;

  const numeric = parseRuntimeThreshold(raw, result?.unit) ?? def.threshold;
  const comparator = thresholdOperatorSymbol(result);

  if (shouldDisplayAsPercent(def, result)) {
    return `${comparator} ${formatMetricNumber({ ...def, unit: "%" }, numeric)}`;
  }
  if (typeof raw === "string" && /[<>]=?|=/.test(raw.trim()) && !raw.includes("/")) return raw;
  return `${comparator} ${formatMetricNumber(def, numeric)}`;
}

export function formatRoundedNumber(value: number, maxFractionDigits = 3): string {
  if (!Number.isFinite(value)) return `${value}`;
  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: Number.isInteger(value) ? 0 : maxFractionDigits,
  }).format(value);
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
