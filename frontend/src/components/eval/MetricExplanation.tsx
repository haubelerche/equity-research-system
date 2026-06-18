import type { BenchmarkMetricResult } from "../../api/types";
import type { MetricDef } from "../../lib/evalStatus";
import {
  formatRoundedNumber,
  formatRuntimeMetricResult,
  formatRuntimeThreshold,
  resolveMetricStatus,
} from "../../lib/evalStatus";
import { StatusPill } from "./StatusPill";

function roundNumbers(value: unknown): unknown {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return value;
    return Number(value.toFixed(3));
  }
  if (Array.isArray(value)) return value.map(roundNumbers);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, roundNumbers(item)]),
    );
  }
  return value;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : null;
}

function valueOrDash(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Chưa có";
  if (typeof value === "number") return formatRoundedNumber(value);
  if (typeof value === "object") return JSON.stringify(roundNumbers(value), null, 2);
  return String(value);
}

type EvidenceField = {
  key: string;
  label: string;
  value: unknown;
};

const SUMMARY_KEYS = new Set([
  "id",
  "ticker",
  "sample_index",
  "row_index",
  "unit_index",
  "claim_id",
  "canonical_key",
  "metric",
  "stage",
  "check",
  "file",
  "cohort_ticker",
  "source_samples",
  "source_calculation",
  "artifact",
  "section_key",
  "status",
  "passed",
  "hit",
  "value",
  "present",
  "accepted",
  "record_count",
  "evidence_available",
  "metric_score",
  "score",
  "reciprocal_rank",
  "retrieved_source_tier",
]);

const FIELD_LABELS: Record<string, string> = {
  actual: "Actual",
  add_keys: "Formula add keys",
  agent_id: "Agent ID",
  agent_role: "Agent role",
  artifact_id: "Artifact ID",
  artifact_ids: "Artifact IDs",
  artifact_producer_key: "Artifact producer",
  artifact_upload_failures: "Artifact upload failures",
  calculation_steps: "Calculation steps",
  cash: "Cash",
  claim_ledger_path: "Claim ledger path",
  components: "Components",
  expected: "Expected",
  expected_source_tiers: "Expected source tiers",
  expected_terms: "Expected terms",
  explanation_exists: "Explanation exists",
  explanation_pdf: "Explanation PDF",
  extraction_method: "Extraction method",
  failure: "Failure",
  fiscal_year: "Fiscal year",
  formula_id: "Formula ID",
  formula_version: "Formula version",
  has_complete_provenance: "Complete provenance",
  has_value: "Has value",
  material: "Material query",
  output_hash: "Output hash",
  output_key: "Output key",
  path: "Path",
  pdf_render_failures: "PDF render failures",
  permission: "Permission",
  permission_level: "Permission level",
  query: "Query",
  question: "Question",
  reason: "Reason",
  reported: "Reported",
  report_exists: "Report exists",
  report_path: "Report path",
  report_pdf: "Report PDF",
  retrieved_chunks: "Retrieved chunks",
  run_id: "Run ID",
  run_type: "Run type",
  sample_origin: "Sample origin",
  source: "Source",
  source_metric_id: "Source metric ID",
  source_title: "Source title",
  source_type: "Source type",
  source_tier_hit: "Source tier hit",
  statement_type: "Statement type",
  terminal_status: "Terminal status",
  tolerance: "Tolerance",
  tool_id: "Tool ID",
  tool_name: "Tool name",
  top_5: "Top-k evidence",
  total_debt: "Total debt",
  total_duration_seconds: "Total duration seconds",
  total_tokens: "Total tokens",
  trace_url: "Trace URL",
  validation_status: "Validation status",
};

const FIELD_PRIORITY = [
  "query",
  "question",
  "reason",
  "source",
  "path",
  "report_path",
  "report_pdf",
  "explanation_pdf",
  "artifact_id",
  "source_metric_id",
  "sample_origin",
  "material",
  "fiscal_year",
  "expected_terms",
  "expected_source_tiers",
  "retrieved_chunks",
  "top_5",
  "source_tier_hit",
  "reported",
  "expected",
  "tolerance",
  "components",
  "add_keys",
  "scores",
  "permission",
  "output_hash",
  "failure",
  "evidence",
];

function listOrDash(values: unknown[] | undefined): string {
  if (!values || values.length === 0) return "Chưa có";
  return values.map(valueOrDash).join(", ");
}

function runtimeField(result: BenchmarkMetricResult | undefined, key: string): unknown {
  return result ? (result as Record<string, unknown>)[key] : undefined;
}

function nestedSampleResults(sample: unknown): unknown[] {
  const record = asRecord(sample);
  if (!record) return [];
  if (Array.isArray(record.source_samples)) return record.source_samples;
  const sourceCalculation = asRecord(record.source_calculation);
  return Array.isArray(sourceCalculation?.per_sample_results)
    ? sourceCalculation.per_sample_results
    : [];
}

function expandSampleResults(samples: unknown[]): unknown[] {
  return samples.flatMap((sample, sampleIndex) => {
    const record = asRecord(sample);
    const nestedSamples = nestedSampleResults(sample);
    if (!record || nestedSamples.length === 0) return [sample];
    return nestedSamples.map((nestedSample, nestedIndex) => {
      const nestedRecord = asRecord(nestedSample);
      if (!nestedRecord) {
        return {
          cohort_ticker: record.ticker,
          artifact_id: record.artifact_id,
          source_metric_id: record.source_metric_id,
          evidence: record.evidence,
          sample_index: nestedIndex + 1,
          sample_origin: `nested_${sampleIndex + 1}`,
          value: nestedSample,
        };
      }
      return {
        cohort_ticker: record.ticker,
        artifact_id: record.artifact_id,
        source_metric_id: record.source_metric_id,
        ...nestedRecord,
        evidence: nestedRecord.evidence ?? record.evidence,
        sample_index: nestedRecord.sample_index ?? nestedIndex + 1,
        sample_origin: nestedRecord.sample_origin ?? `nested_${sampleIndex + 1}`,
      };
    });
  });
}

function hasStructuredTrace(samples: unknown[]): boolean {
  return samples.some((sample) => {
    const record = asRecord(sample);
    return Boolean(
      record?.query
      || record?.question
      || record?.top_5
      || record?.scores
      || record?.source
      || record?.artifact_id
      || record?.trace_url
      || record?.canonical_key
      || record?.claim_id
      || record?.sample_origin
      || record?.reported !== undefined
      || record?.expected !== undefined
      || record?.evidence_available !== undefined,
    );
  });
}

function sampleLabel(sample: unknown, index: number): string {
  const record = asRecord(sample);
  return valueOrDash(
    record?.id
    ?? record?.claim_id
    ?? record?.canonical_key
    ?? record?.metric
    ?? record?.stage
    ?? record?.check
    ?? record?.tool_name
    ?? record?.file
    ?? record?.artifact
    ?? record?.section_key
    ?? record?.ticker
    ?? record?.source_metric_id
    ?? record?.sample_index
    ?? record?.row_index
    ?? record?.unit_index
    ?? `#${index + 1}`,
  );
}

const REPORT_SCORE_THRESHOLDS: Record<string, { key: string; threshold: number }> = {
  "report.completeness": { key: "completeness", threshold: 90 },
  "report.financial_analysis_depth": { key: "financial_analysis_depth", threshold: 80 },
  "report.forecast_rationale": { key: "forecast_rationale", threshold: 80 },
  "report.valuation_transparency": { key: "valuation_transparency", threshold: 85 },
  "report.evidence_integration": { key: "evidence_integration", threshold: 80 },
};

const REPORT_TOTAL_WEIGHTS: Record<string, number> = {
  completeness: 0.20,
  financial_analysis_depth: 0.20,
  forecast_rationale: 0.20,
  valuation_transparency: 0.20,
  evidence_integration: 0.15,
  presentation_quality: 0.05,
};

const OPS_LATENCY_METRICS = new Set([
  "duration_seconds",
  "warm_full_report_p95_latency",
  "cold_full_report_p95_latency",
  "render_only_p95_latency",
  "flash_memo_warm_p95_latency",
  "flash_memo_cold_retrieval_p95_latency",
  "latency_regression_ratio",
]);

function reportTotalScore(scores: Record<string, unknown>): number | null {
  let total = 0;
  for (const [key, weight] of Object.entries(REPORT_TOTAL_WEIGHTS)) {
    const value = scores[key];
    if (typeof value !== "number") return null;
    total += value * weight;
  }
  return Number(total.toFixed(2));
}

function reportSampleStatusAndValue(record: Record<string, unknown>): { status: string; value: unknown } | null {
  const sourceMetricId = typeof record.source_metric_id === "string" ? record.source_metric_id : null;
  if (sourceMetricId === "report_pdf_rendered" && typeof record.report_exists === "boolean") {
    return { status: record.report_exists ? "pass" : "fail", value: record.report_exists };
  }
  if (sourceMetricId === "explanation_pdf_rendered" && typeof record.explanation_exists === "boolean") {
    return { status: record.explanation_exists ? "pass" : "fail", value: record.explanation_exists };
  }
  const scores = asRecord(record.scores);
  if (!scores) return null;
  if (sourceMetricId === "report.quality_total" || sourceMetricId === "report_quality_score") {
    const total = reportTotalScore(scores);
    if (total === null) return { status: "not_evaluable", value: null };
    return { status: total >= 85 ? "pass" : "fail", value: total };
  }
  const scoreThreshold = sourceMetricId ? REPORT_SCORE_THRESHOLDS[sourceMetricId] : undefined;
  if (!scoreThreshold) return null;
  const value = scores[scoreThreshold.key];
  if (typeof value !== "number") return { status: "not_evaluable", value: null };
  return { status: value >= scoreThreshold.threshold ? "pass" : "fail", value };
}

function opsSampleStatusAndValue(record: Record<string, unknown>): { status: string; value: unknown } | null {
  const sourceMetricId = typeof record.source_metric_id === "string" ? record.source_metric_id : null;
  if (typeof record.artifact_upload_failures === "number") {
    return {
      status: record.artifact_upload_failures === 0 ? "pass" : "fail",
      value: record.artifact_upload_failures,
    };
  }
  if (typeof record.pdf_render_failures === "number") {
    return {
      status: record.pdf_render_failures === 0 ? "pass" : "fail",
      value: record.pdf_render_failures,
    };
  }
  if (sourceMetricId === "llm_retry_rate" && typeof record.retry_count === "number") {
    return { status: record.retry_count === 0 ? "pass" : "fail", value: record.retry_count };
  }
  if (sourceMetricId === "retrieval_fallback_rate" && typeof record.fallback_triggered === "boolean") {
    return { status: record.fallback_triggered ? "fail" : "pass", value: record.fallback_triggered };
  }
  let terminalStatus = typeof record.terminal_status === "string"
    ? record.terminal_status.toLowerCase()
    : "";
  const rawStatus = typeof record.status === "string" ? record.status.toLowerCase() : "";
  if (!terminalStatus && ["completed", "success", "failed", "error"].includes(rawStatus)) {
    terminalStatus = rawStatus;
  }
  if (terminalStatus === "failed" || terminalStatus === "error") {
    return { status: "fail", value: terminalStatus };
  }
  if (sourceMetricId === "cost_per_report") {
    if (typeof record.estimated_cost_usd === "number") {
      return { status: "measured_only", value: record.estimated_cost_usd };
    }
    if (typeof record.cost_estimate === "number") {
      return { status: "measured_only", value: record.cost_estimate };
    }
  }
  if (sourceMetricId && OPS_LATENCY_METRICS.has(sourceMetricId)) {
    const duration = typeof record.duration_seconds === "number"
      ? record.duration_seconds
      : typeof record.total_duration_seconds === "number"
        ? record.total_duration_seconds
        : null;
    if (duration !== null) return { status: "measured_only", value: duration };
  }
  if (terminalStatus) return { status: "pass", value: terminalStatus };
  return null;
}

function inferredSampleStatus(record: Record<string, unknown>): string | null {
  if (typeof record.component_score === "number") return record.component_score >= 1 ? "pass" : "warning";
  const reportStatus = reportSampleStatusAndValue(record)?.status;
  if (reportStatus) return reportStatus;
  const opsStatus = opsSampleStatusAndValue(record)?.status;
  if (opsStatus) return opsStatus;
  for (const key of ["passed", "hit", "present", "complete", "accepted", "schema_valid", "reconciled", "in_range"]) {
    if (typeof record[key] === "boolean") return record[key] ? "pass" : "fail";
  }
  for (const key of ["material_ocr_error", "is_duplicate"]) {
    if (typeof record[key] === "boolean") return record[key] ? "fail" : "pass";
  }
  if (typeof record.generic_citations === "number") return record.generic_citations === 0 ? "pass" : "fail";
  if (typeof record.source_mentions === "number") return record.source_mentions > 0 ? "pass" : "fail";
  if (typeof record.financial_decision === "string") return record.financial_decision === "pass" ? "pass" : "fail";
  if ("financial_decision" in record) return "not_evaluable";
  const permission = asRecord(record.permission);
  if (permission) return permission.tool_id && permission.agent_id ? "pass" : "fail";
  if (record.evidence_available === false) return "not_evaluable";
  if (typeof record.validation_status === "string" && record.validation_status.length > 0) {
    return record.validation_status.toLowerCase() === "accepted" ? "pass" : "fail";
  }
  return null;
}

function sampleStatus(sample: unknown): string {
  const record = asRecord(sample);
  if (!record) return "Chưa có";
  if (record.status !== undefined) return String(record.status);
  const inferred = inferredSampleStatus(record);
  if (inferred) return inferred;
  if (record.passed !== undefined) return record.passed ? "pass" : "fail";
  if (record.hit !== undefined) return record.hit ? "hit" : "miss";
  return "Chưa có";
}

function sampleValue(sample: unknown): string {
  const record = asRecord(sample);
  if (!record) return valueOrDash(sample);
  if (record.reported !== undefined || record.expected !== undefined) {
    return `${valueOrDash(record.reported)} / ${valueOrDash(record.expected)}`;
  }
  const scoreValue = record.metric_score ?? record.score ?? record.reciprocal_rank;
  if (typeof scoreValue === "number") {
    return formatRoundedNumber(Math.abs(scoreValue) <= 1 ? scoreValue * 100 : scoreValue) + "%";
  }
  if (typeof record.component_score === "number") {
    return formatRoundedNumber(Math.abs(record.component_score) <= 1 ? record.component_score * 100 : record.component_score) + "%";
  }
  const reportValue = reportSampleStatusAndValue(record)?.value;
  if (reportValue !== undefined) return valueOrDash(reportValue);
  const opsValue = opsSampleStatusAndValue(record)?.value;
  if (opsValue !== undefined) return valueOrDash(opsValue);
  const permission = asRecord(record.permission);
  if (permission) {
    return valueOrDash(permission.permission_level ?? permission.tool_id ?? true);
  }
  return valueOrDash(
    record.value
    ?? record.present
    ?? record.complete
    ?? record.in_range
    ?? record.accepted
    ?? record.schema_valid
    ?? record.reconciled
    ?? record.verified
    ?? record.generic_citations
    ?? record.source_mentions
    ?? record.financial_decision
    ?? record.record_count
    ?? record.evidence_available
    ?? record.error
    ?? record.retrieved_source_tier,
  );
}

function fieldLabel(key: string): string {
  return FIELD_LABELS[key]
    ?? key.replace(/_/g, " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function isEmptyEvidenceValue(value: unknown): boolean {
  return value === undefined
    || value === null
    || value === ""
    || (Array.isArray(value) && value.length === 0);
}

function compareEvidenceFields(a: EvidenceField, b: EvidenceField): number {
  const aPriority = FIELD_PRIORITY.indexOf(a.key);
  const bPriority = FIELD_PRIORITY.indexOf(b.key);
  if (aPriority !== -1 || bPriority !== -1) {
    return (aPriority === -1 ? Number.MAX_SAFE_INTEGER : aPriority)
      - (bPriority === -1 ? Number.MAX_SAFE_INTEGER : bPriority);
  }
  return a.label.localeCompare(b.label);
}

function topEvidenceSummary(items: unknown[]): string[] {
  return items.map((item, index) => {
    const top = asRecord(item);
    if (!top) return valueOrDash(item);
    const rank = top.rank ?? index + 1;
    const tier = top.reliability_tier ?? top.source_tier ?? "Chưa có";
    const fiscalYear = top.fiscal_year !== undefined ? ` fiscal_year ${valueOrDash(top.fiscal_year)}` : "";
    const method = top.extraction_method !== undefined ? ` ${valueOrDash(top.extraction_method)}` : "";
    return `rank ${valueOrDash(rank)} | tier ${valueOrDash(tier)}${fiscalYear}${method}`;
  });
}

function sampleEvidenceFields(sample: unknown): EvidenceField[] {
  const record = asRecord(sample);
  if (!record) return [{ key: "value", label: "Value", value: sample }];
  const fields = Object.entries(record)
    .filter(([key, value]) => !SUMMARY_KEYS.has(key) && !isEmptyEvidenceValue(value))
    .map(([key, value]) => ({
      key,
      label: fieldLabel(key),
      value: key === "top_5" && Array.isArray(value) ? topEvidenceSummary(value) : value,
    }))
    .sort(compareEvidenceFields);
  return fields.length > 0 ? fields : [{ key: "sample", label: "Raw sample", value: record }];
}

function renderEvidenceValue(value: unknown) {
  if (Array.isArray(value)) {
    if (value.every((item) => typeof item !== "object" || item === null)) {
      return <span>{value.map(valueOrDash).join(", ")}</span>;
    }
    return <pre>{valueOrDash(value)}</pre>;
  }
  if (value && typeof value === "object") {
    return <pre>{valueOrDash(value)}</pre>;
  }
  return <span>{valueOrDash(value)}</span>;
}

function EvidenceFieldList({ fields }: { fields: EvidenceField[] }) {
  return (
    <dl className="metric-explanation__field-list">
      {fields.map((field, index) => (
        <div key={`${field.key}-${index}`}>
          <dt>{field.label}</dt>
          <dd>{renderEvidenceValue(field.value)}</dd>
        </div>
      ))}
    </dl>
  );
}

function failedExampleLabel(failure: unknown, index: number): string {
  const record = asRecord(failure);
  return valueOrDash(
    record?.id
    ?? record?.claim_id
    ?? record?.canonical_key
    ?? record?.metric_id
    ?? record?.reason
    ?? `#${index + 1}`,
  );
}

function failedExampleFields(failure: unknown): EvidenceField[] {
  const record = asRecord(failure);
  if (!record) return [{ key: "failure", label: "Failure", value: failure }];
  return Object.entries(record)
    .filter(([, value]) => !isEmptyEvidenceValue(value))
    .map(([key, value]) => ({ key, label: fieldLabel(key), value }))
    .sort(compareEvidenceFields);
}

function aggregationLabel(aggregation: unknown): string {
  switch (String(aggregation ?? "")) {
    case "coverage":
      return "Tỷ lệ bao phủ";
    case "cohort_pass_rate":
      return "Tỷ lệ đạt trên toàn bộ cohort";
    case "boolean_gate":
      return "Cổng đúng/sai";
    case "presence":
    case "artifact_presence":
      return "Kiểm tra hiện diện artifact";
    case "error_count":
      return "Đếm số lỗi";
    case "error_rate":
    case "rate":
      return "Tỷ lệ lỗi hoặc sự kiện";
    case "weighted_score":
    case "weighted_mean":
      return "Điểm tổng hợp có trọng số";
    case "rubric_score":
      return "Điểm rubric";
    case "schema_validation":
      return "Kiểm tra hợp đồng schema";
    case "mean":
      return "Trung bình mẫu";
    case "p95":
      return "Phân vị p95";
    case "ratio":
      return "Tỷ số";
    case "sum":
      return "Tổng";
    case "max":
      return "Giá trị lớn nhất";
    default:
      return valueOrDash(aggregation);
  }
}

function calculationNarrative(def: MetricDef, result: BenchmarkMetricResult | undefined): string {
  const calculation = result?.calculation;
  const aggregation = String(calculation?.aggregation ?? "");
  const numerator = valueOrDash(calculation?.numerator);
  const denominator = valueOrDash(calculation?.denominator);
  const threshold = formatRuntimeThreshold(def, result);
  const sampleCount = calculation?.per_sample_results?.length ?? 0;
  const metricName = result?.metric_name ?? def.label;

  if (!calculation) {
    return `${metricName}: chưa có calculation payload trong artifact; dashboard chỉ có thể hiển thị trạng thái tổng hợp và ngưỡng ${threshold}.`;
  }
  if (aggregation === "coverage" || aggregation === "cohort_pass_rate") {
    return `${metricName}: đếm số sample đạt điều kiện chia cho tổng số sample hợp lệ. Tử số hiện là ${numerator}, mẫu số là ${denominator}; kết quả được so với ngưỡng ${threshold}. Bảng bên dưới liệt kê từng sample, trạng thái, giá trị và trace dùng để quyết định đạt hay không đạt.`;
  }
  if (aggregation === "boolean_gate" || aggregation === "presence" || aggregation === "artifact_presence") {
    return `${metricName}: kiểm tra từng điều kiện bắt buộc theo dạng đạt/không đạt. Metric chỉ đạt khi các điều kiện bắt buộc hoặc artifact cần thiết hiện diện đầy đủ; kết quả được so với ngưỡng ${threshold}.`;
  }
  if (aggregation === "error_count") {
    return `${metricName}: đếm tổng số lỗi phát hiện trong các sample kiểm tra. Giá trị tốt là càng thấp càng tốt; thông thường ngưỡng đạt là ${threshold}. Failed examples và bảng sample cho biết lỗi nằm ở artifact, claim, công thức hoặc trace nào.`;
  }
  if (aggregation === "error_rate" || aggregation === "rate") {
    return `${metricName}: lấy số sự kiện lỗi hoặc fallback chia cho tổng số sự kiện quan sát được. Tử số là ${numerator}, mẫu số là ${denominator}; kết quả được so với ngưỡng ${threshold}.`;
  }
  if (aggregation === "weighted_score" || aggregation === "weighted_mean") {
    return `${metricName}: tổng hợp nhiều nhóm kiểm tra theo trọng số đã ghi trong calculation parameters. Điểm cuối cùng chỉ đáng tin cậy khi các sample thành phần và evidence artifacts bên dưới đều có dữ liệu.`;
  }
  if (aggregation === "rubric_score") {
    return `${metricName}: chấm theo rubric nội dung trên report artifact, nhưng chỉ được xem là đánh giá được khi có artifact bằng chứng đi kèm như claim ledger hoặc evidence packet.`;
  }
  if (aggregation === "schema_validation") {
    return `${metricName}: kiểm tra payload runtime với schema bắt buộc; mỗi sample đại diện cho một artifact hoặc nhóm field cần hợp lệ.`;
  }
  if (aggregation === "p95") {
    return `${metricName}: sắp xếp các latency sample và lấy phân vị 95 để so với budget ${threshold}. Bảng sample cho biết từng run/stage đóng góp vào phân vị.`;
  }
  if (aggregation === "mean") {
    return `${metricName}: lấy trung bình điểm của ${sampleCount} sample đánh giá được và so sánh với ngưỡng ${threshold}.`;
  }
  if (aggregation === "sum") {
    return `${metricName}: cộng các giá trị sample thành tổng quan sát được; bảng sample cho biết từng thành phần đóng góp.`;
  }
  if (aggregation === "max") {
    return `${metricName}: lấy giá trị lớn nhất trong các sample quan sát được để áp dụng chính sách thận trọng.`;
  }
  if (aggregation === "ratio") {
    return `${metricName}: tính tỷ số giữa tử số ${numerator} và mẫu số ${denominator}, rồi so với ngưỡng ${threshold}.`;
  }
  return `${metricName}: aggregation '${aggregation || "không khai báo"}' được ghi trong artifact. Dashboard hiển thị numerator, denominator, parameters và từng sample bên dưới để reviewer kiểm tra lại phép tính.`;
}

export function MetricExplanation({ def, result }: { def: MetricDef; result?: BenchmarkMetricResult }) {
  const status = resolveMetricStatus(def, result);
  const calculation = result?.calculation;
  const failures = result?.failed_examples ?? [];
  const rawSamples = calculation?.per_sample_results ?? [];
  const samples = rawSamples.length > 0
    ? expandSampleResults(rawSamples)
    : failures.map((failure, index) => ({
      sample_origin: "failed_example",
      sample_index: index + 1,
      status: "fail",
      failure,
    }));
  const artifactIds = result?.evidence?.artifact_ids ?? [];
  const traceUrl = result?.evidence?.trace_url ?? runtimeField(result, "trace_url");
  const evaluatedAt = runtimeField(result, "evaluated_at");
  const hasEvidence = samples.length > 0 || failures.length > 0 || artifactIds.length > 0 || Boolean(traceUrl);
  const hasDeepTrace = hasStructuredTrace(samples);

  return (
    <div className="metric-explanation">
      <div className="metric-explanation__summary">
        <dl>
          <div><dt>Metric</dt><dd>{def.label}</dd></div>
          <div><dt>Technology</dt><dd>{def.englishLabel ?? def.technology}</dd></div>
          <div><dt>Trạng thái</dt><dd><StatusPill status={status} /></dd></div>
          <div><dt>Kết quả</dt><dd><code>{formatRuntimeMetricResult(def, result)}</code></dd></div>
          <div><dt>Ngưỡng đạt</dt><dd><code>{formatRuntimeThreshold(def, result)}</code></dd></div>
          <div><dt>Sample size</dt><dd>{valueOrDash(result?.sample_size)}</dd></div>
        </dl>
      </div>

      <section className="metric-explanation__section">
        <h3>Bằng chứng thực thi</h3>
        <dl>
          <div><dt>Evaluator</dt><dd>{result?.evaluator?.framework ?? def.technology}</dd></div>
          <div><dt>Framework version</dt><dd>{valueOrDash(result?.evaluator?.framework_version)}</dd></div>
          <div><dt>Implementation version</dt><dd>{valueOrDash(result?.evaluator?.implementation_version)}</dd></div>
          <div><dt>Execution status</dt><dd>{valueOrDash(result?.evaluator?.execution_status)}</dd></div>
          <div><dt>Metric ID</dt><dd><code>{result?.metric_id ?? def.id}</code></dd></div>
          <div><dt>Evaluated at</dt><dd>{valueOrDash(evaluatedAt)}</dd></div>
          <div><dt>Dataset version</dt><dd>{valueOrDash(result?.dataset_version ?? result?.evidence?.dataset_version)}</dd></div>
          <div><dt>Source artifact</dt><dd>{valueOrDash(result?.artifact_id ?? result?.source)}</dd></div>
          <div><dt>Evidence artifacts</dt><dd>{listOrDash(artifactIds)}</dd></div>
          <div><dt>Trace URL</dt><dd>{valueOrDash(traceUrl)}</dd></div>
        </dl>
        {!hasEvidence && (
          <p className="metric-explanation__warning">
            Metric result này chưa chứa artifact id, trace URL, sample result hoặc failed example; vì vậy dashboard chỉ xác nhận được trạng thái tổng hợp, chưa xác nhận được bằng chứng chi tiết.
          </p>
        )}
        {hasEvidence && !hasDeepTrace && (
          <p className="metric-explanation__warning">
            Packet đang hiển thị là cohort summary; sample hiện có thể không chứa trace cấp truy vấn/chunk, nhưng bảng dưới đây vẫn hiển thị artifact nguồn và payload sample để audit sâu hơn.
          </p>
        )}
      </section>

      <section className="metric-explanation__section">
        <h3>Cách tính và ngưỡng</h3>
        <p>{calculationNarrative(def, result)}</p>
        <dl>
          <div><dt>Aggregation</dt><dd>{aggregationLabel(calculation?.aggregation)}</dd></div>
          <div><dt>Numerator</dt><dd>{valueOrDash(calculation?.numerator)}</dd></div>
          <div><dt>Denominator</dt><dd>{valueOrDash(calculation?.denominator)}</dd></div>
          <div><dt>Threshold profile</dt><dd>{valueOrDash(result?.threshold_policy?.profile)}</dd></div>
        </dl>
        <p>{result?.threshold_policy?.rationale ?? "Chưa có giải trình threshold trong registry."}</p>
      </section>

      <section className="metric-explanation__section">
        <h3>Arguments và parameters</h3>
        {Object.keys(calculation?.inputs ?? {}).length === 0 && Object.keys(calculation?.parameters ?? {}).length === 0 ? (
          <p>Evaluator không ghi thêm input/parameter runtime trong metric result này.</p>
        ) : (
          <pre>{valueOrDash({
            inputs: calculation?.inputs ?? {},
            parameters: calculation?.parameters ?? {},
          })}</pre>
        )}
      </section>

      <section className="metric-explanation__section">
        <h3>Kết quả từng sample ({samples.length})</h3>
        {samples.length === 0 ? (
          <p>Metric result không có per-sample evidence.</p>
        ) : (
          <div className="metric-explanation__table-scroll">
            <table className="metric-explanation__sample-table">
              <thead>
                <tr>
                  <th>Sample</th>
                  <th>Status</th>
                  <th>Value</th>
                  <th>Bằng chứng / trace</th>
                </tr>
              </thead>
              <tbody>
                {samples.map((sample, index) => (
                  <tr key={`${sampleLabel(sample, index)}-${index}`}>
                    <td>{sampleLabel(sample, index)}</td>
                    <td>{sampleStatus(sample)}</td>
                    <td className="num">{sampleValue(sample)}</td>
                    <td><EvidenceFieldList fields={sampleEvidenceFields(sample)} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="metric-explanation__section">
        <h3>Failed examples ({failures.length})</h3>
        {failures.length === 0 ? (
          <p>Không có failed example trong metric result.</p>
        ) : (
          <div className="metric-explanation__failed-list">
            {failures.map((failure, index) => (
              <article className="metric-explanation__failed-item" key={`${failedExampleLabel(failure, index)}-${index}`}>
                <h4>{failedExampleLabel(failure, index)}</h4>
                <EvidenceFieldList fields={failedExampleFields(failure)} />
              </article>
            ))}
          </div>
        )}
        <p>{result?.remediation_hint ?? "Chưa có hướng khắc phục."}</p>
      </section>
    </div>
  );
}
