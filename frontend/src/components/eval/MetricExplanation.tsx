import { useState } from "react";
import type { BenchmarkMetricResult, SectionScoreDetail } from "../../api/types";
import type { MetricDef } from "../../lib/evalStatus";
import {
  formatMetricNumber,
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
  actual: "Giá trị thực tế",
  add_keys: "Khóa cộng trong công thức",
  agent_id: "Mã tác nhân",
  agent_role: "Vai trò tác nhân",
  artifact_id: "Mã artifact",
  artifact_ids: "Danh sách mã artifact",
  artifact_producer_key: "Nguồn tạo artifact",
  artifact_upload_failures: "Số lần tải artifact thất bại",
  calculation_steps: "Các bước tính",
  cash: "Tiền mặt",
  claim_ledger_path: "Đường dẫn sổ luận điểm",
  components: "Thành phần",
  evidence: "Bằng chứng",
  expected: "Giá trị kỳ vọng",
  expected_source_tiers: "Hạng nguồn kỳ vọng",
  expected_terms: "Từ khóa kỳ vọng",
  explanation_exists: "Có bản giải trình",
  explanation_pdf: "PDF giải trình",
  extraction_method: "Phương pháp trích xuất",
  failure: "Lỗi",
  fiscal_year: "Năm tài chính",
  formula_id: "Mã công thức",
  formula_version: "Phiên bản công thức",
  has_complete_provenance: "Đủ truy xuất nguồn gốc",
  has_value: "Có giá trị",
  material: "Truy vấn trọng yếu",
  output_hash: "Mã băm đầu ra",
  output_key: "Khóa đầu ra",
  path: "Đường dẫn",
  pdf_render_failures: "Số lần render PDF thất bại",
  permission: "Quyền truy cập",
  permission_level: "Cấp quyền",
  query: "Truy vấn",
  question: "Câu hỏi",
  reason: "Lý do",
  reported: "Giá trị báo cáo",
  report_exists: "Có báo cáo",
  report_path: "Đường dẫn báo cáo",
  report_pdf: "PDF báo cáo",
  retrieved_chunks: "Đoạn truy hồi",
  run_id: "Mã lần chạy",
  run_type: "Loại lần chạy",
  sample_origin: "Nguồn mẫu",
  source: "Nguồn",
  source_metric_id: "Mã metric nguồn",
  source_title: "Tiêu đề nguồn",
  source_type: "Loại nguồn",
  source_tier_hit: "Hạng nguồn khớp",
  statement_type: "Loại báo cáo tài chính",
  terminal_status: "Trạng thái kết thúc",
  tolerance: "Dung sai",
  tool_id: "Mã công cụ",
  tool_name: "Tên công cụ",
  top_5: "Bằng chứng hàng đầu",
  total_debt: "Tổng nợ",
  total_duration_seconds: "Tổng thời lượng (giây)",
  total_tokens: "Tổng số token",
  trace_url: "Đường dẫn trace",
  validation_status: "Trạng thái kiểm định",
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

const OPS_LATENCY_METRICS = new Set([
  "duration_seconds",
  "warm_full_report_p95_latency",
  "cold_full_report_p95_latency",
  "render_only_p95_latency",
  "flash_memo_warm_p95_latency",
  "flash_memo_cold_retrieval_p95_latency",
  "latency_regression_ratio",
]);

function reportSampleStatusAndValue(record: Record<string, unknown>): { status: string; value: unknown } | null {
  const sourceMetricId = typeof record.source_metric_id === "string" ? record.source_metric_id : null;
  if (sourceMetricId === "report_pdf_rendered" && typeof record.report_exists === "boolean") {
    return { status: record.report_exists ? "pass" : "fail", value: record.report_exists };
  }
  if (sourceMetricId === "explanation_pdf_rendered" && typeof record.explanation_exists === "boolean") {
    return { status: record.explanation_exists ? "pass" : "fail", value: record.explanation_exists };
  }
  return null;
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

function numericScoreValues(record: Record<string, unknown>): number[] {
  const scores = asRecord(record.scores);
  if (!scores) return [];
  return Object.values(scores).filter((value): value is number => typeof value === "number" && Number.isFinite(value));
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
  const scoreValues = numericScoreValues(record);
  if (scoreValues.length > 0) return scoreValues.every((value) => value >= 85) ? "pass" : "fail";
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

function schemaDecisionValue(record: Record<string, unknown>): boolean | undefined {
  if (record.source_metric_id !== "schema_validity") return undefined;
  const status = typeof record.status === "string" ? record.status.toLowerCase() : "";
  if (status === "pass") return true;
  if (status === "fail") return false;
  return undefined;
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
  const schemaValue = schemaDecisionValue(record);
  if (schemaValue !== undefined) return valueOrDash(schemaValue);
  const scoreValues = numericScoreValues(record);
  if (scoreValues.length > 0) return valueOrDash(scoreValues[0]);
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

function sectionDetailsFromResult(result: BenchmarkMetricResult | undefined): Record<string, SectionScoreDetail> {
  const fromParameters = result?.calculation?.parameters?.section_details;
  if (fromParameters && typeof fromParameters === "object" && !Array.isArray(fromParameters)) {
    return fromParameters;
  }
  const samples = result?.calculation?.per_sample_results ?? [];
  for (const sample of samples) {
    const record = asRecord(sample);
    const details = asRecord(record?.section_details);
    if (details) return details as Record<string, SectionScoreDetail>;
  }
  return {};
}

function SectionDetailsTable({ details }: { details: Record<string, SectionScoreDetail> }) {
  const entries = Object.entries(details);
  if (entries.length === 0) {
    return <p>Kết quả chỉ số chưa có chi tiết thành phần điểm; chỉ hiển thị dữ liệu tính toán gốc.</p>;
  }
  return (
    <div className="metric-explanation__table-scroll">
      <table className="metric-explanation__sample-table">
        <thead>
          <tr>
            <th>Thành phần</th>
            <th>Điểm đạt</th>
            <th>Điểm tối đa</th>
            <th>Trạng thái</th>
            <th>Checks</th>
          </tr>
        </thead>
        <tbody>
          {entries.map(([key, detail]) => (
            <tr key={key}>
              <td>{detail.id ?? key}</td>
              <td className="num">{valueOrDash(detail.earned_points)}</td>
              <td className="num">{valueOrDash(detail.maximum_points)}</td>
              <td>{valueOrDash(detail.status)}</td>
              <td>
                <details>
                  <summary>{detail.checks?.length ?? 0} kiểm tra</summary>
                  <EvidenceFieldList fields={(detail.checks ?? []).map((check, index) => ({
                    key: check.id ?? "check_" + String(index + 1),
                    label: check.id ?? "Check " + String(index + 1),
                    value: {
                      passed: check.passed,
                      actual: check.actual,
                      expected: check.expected,
                      evidence_refs: check.evidence_refs ?? [],
                    },
                  }))} />
                </details>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
    case "cohort_pooled_coverage":
      return "Tỷ lệ bao phủ gộp trên sample nguồn hợp lệ";
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

function numericValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function formatCalculationNumber(value: unknown, suffix = ""): string {
  const numeric = numericValue(value);
  if (numeric === null) return valueOrDash(value);
  return `${formatRoundedNumber(numeric)}${suffix}`;
}

function formatRawPercentRatio(def: MetricDef, numerator: number | null, denominator: number | null): string | null {
  if (numerator === null || denominator === null || denominator === 0) return null;
  return formatMetricNumber({ ...def, unit: "%" }, numerator / denominator);
}

function dashboardValueNote(rawText: string | null, resultText: string): string {
  return rawText && rawText !== resultText ? `; giá trị dashboard = ${resultText}` : "";
}

function formulaResult(def: MetricDef, result: BenchmarkMetricResult | undefined): string {
  return formatRuntimeMetricResult(def, result, undefined, { includeFormula: false });
}

// Format a reconstructed numeric (e.g. a cohort mean) exactly the way the
// dashboard formats the published ``value`` so the "Thay số" substitution and the
// dashboard reading use the same units. When they reconcile, ``dashboardValueNote``
// then suppresses the redundant "; giá trị dashboard = ..." tail.
function formatValueLikeDashboard(def: MetricDef, result: BenchmarkMetricResult | undefined, value: number): string {
  const shadow = { ...(result ?? {}), value } as BenchmarkMetricResult;
  return formatRuntimeMetricResult(def, shadow, undefined, { includeFormula: false });
}

type FormulaExplanation = {
  observedVariable: string;
  theory: string;
  substitution: string;
  thresholdRule: string;
  reviewMeaning: string;
};

// Where the formula and numbers come from, stated in plain Vietnamese so a
// reviewer can see this is not an arbitrary number but the output of a named
// evaluator over a declared aggregation.
function formulaProvenance(def: MetricDef, result: BenchmarkMetricResult | undefined): string {
  const evaluator = result?.evaluator?.framework ?? def.technology ?? "bộ đánh giá nội bộ";
  const metricId = result?.metric_id ?? def.id;
  const aggregation = result?.calculation?.aggregation;
  const aggregationText = aggregation
    ? `cách tổng hợp “${aggregationLabel(aggregation)}”`
    : "cách tổng hợp do bộ đánh giá khai báo";
  const samples = result?.sample_size;
  const sampleText = typeof samples === "number" ? ` trên ${formatRoundedNumber(samples)} mẫu` : "";
  return `Công thức và các con số bên dưới do bộ đánh giá “${evaluator}” (mã metric ${valueOrDash(metricId)}) tính ra theo ${aggregationText}${sampleText}; dashboard chỉ trình bày lại đúng payload đó, không tự suy diễn thêm.`;
}

function thresholdRule(def: MetricDef, result: BenchmarkMetricResult | undefined): string {
  const threshold = formatRuntimeThreshold(def, result);
  const comparator = def.comparator === "lte" || String(result?.threshold_operator ?? result?.threshold ?? "").includes("<=")
    ? "không vượt quá"
    : "tối thiểu";
  return `Metric đạt khi giá trị quan sát ${comparator} ${threshold}; trạng thái cuối cùng được đối chiếu với hồ sơ ngưỡng ${valueOrDash(result?.threshold_policy?.profile)} nếu kết quả có khai báo.`;
}

function calculationFormulaExplanation(def: MetricDef, result: BenchmarkMetricResult | undefined): FormulaExplanation {
  const calculation = result?.calculation;
  const aggregation = String(calculation?.aggregation ?? "").toLowerCase();
  const numerator = numericValue(calculation?.numerator);
  const denominator = numericValue(calculation?.denominator);
  const metricName = result?.metric_name ?? def.label;
  const resultText = formulaResult(def, result);
  const sampleCount = calculation?.per_sample_results?.length ?? result?.sample_size ?? denominator ?? 0;

  if (!calculation) {
    return {
      observedVariable: metricName,
      theory: "Không có calculation payload chi tiết trong artifact, nên dashboard chỉ xác nhận được value, status và threshold đã được evaluator phát hành.",
      substitution: `Kết quả hiển thị = ${resultText}.`,
      thresholdRule: thresholdRule(def, result),
      reviewMeaning: "Muốn tái lập phép tính ngoài dashboard, hãy đối chiếu artifact nguồn hoặc nhật ký của bộ đánh giá.",
    };
  }

  if (aggregation === "coverage" || aggregation === "cohort_pooled_coverage" || aggregation === "cohort_pass_rate") {
    const rawRatio = formatRawPercentRatio(def, numerator, denominator);
    const substitution = denominator && numerator !== null
      ? `Tỷ lệ đạt = ${formatCalculationNumber(numerator)} / ${formatCalculationNumber(denominator)} = ${rawRatio ?? resultText}${dashboardValueNote(rawRatio, resultText)}.`
      : `Tỷ lệ đạt = số sample đạt / số sample hợp lệ = ${resultText}.`;
    return {
      observedVariable: "Tỷ lệ sample đạt điều kiện kiểm định",
      theory: "Công thức lý thuyết: pass_rate = count(sample_status = pass) / count(sample hợp lệ). Mẫu số loại các sample không thuộc phạm vi hoặc không đủ điều kiện đánh giá.",
      substitution,
      thresholdRule: thresholdRule(def, result),
      reviewMeaning: "Metric này trả lời câu hỏi: trong tập kiểm định, bao nhiêu trường hợp thực sự đạt tiêu chuẩn bắt buộc.",
    };
  }

  if (aggregation === "error_rate" || aggregation === "rate") {
    const rawRatio = formatRawPercentRatio(def, numerator, denominator);
    const substitution = denominator && numerator !== null
      ? `Tỷ lệ lỗi = ${formatCalculationNumber(numerator)} / ${formatCalculationNumber(denominator)} = ${rawRatio ?? resultText}${dashboardValueNote(rawRatio, resultText)}.`
      : `Tỷ lệ lỗi = số sự kiện lỗi / tổng sự kiện quan sát = ${resultText}.`;
    return {
      observedVariable: "Tỷ lệ sự kiện lỗi hoặc fallback",
      theory: "Công thức lý thuyết: error_rate = count(error_event) / count(observed_event). Đây là metric lower-is-better, nên giá trị càng thấp càng tốt.",
      substitution,
      thresholdRule: thresholdRule(def, result),
      reviewMeaning: "Metric này đo rủi ro vận hành theo tần suất, không đo mức độ nghiêm trọng của từng lỗi riêng lẻ.",
    };
  }

  if (aggregation === "mean" || aggregation === "cohort_mean" || aggregation === "cohort_mean_observed") {
    const mean = numerator !== null && denominator ? numerator / denominator : null;
    const meanText = mean !== null ? formatValueLikeDashboard(def, result, mean) : null;
    const substitution = mean !== null && meanText !== null
      ? `Điểm trung bình = tổng điểm quan sát / số sample = ${formatCalculationNumber(numerator)} / ${formatCalculationNumber(denominator)} = ${meanText}${dashboardValueNote(meanText, resultText)}.`
      : `Điểm trung bình được lấy trên ${formatCalculationNumber(sampleCount)} sample đánh giá được; giá trị dashboard = ${resultText}.`;
    return {
      observedVariable: "Điểm trung bình trên cohort đánh giá",
      theory: "Công thức lý thuyết: mean_score = sum(score_i) / n, với score_i là điểm của từng mã, từng claim, từng section hoặc từng run tùy metric. Với thang 0-100, tổng điểm có thể lớn hơn 100 vì numerator là tổng cộng dồn của toàn cohort.",
      substitution,
      thresholdRule: thresholdRule(def, result),
      reviewMeaning: "Metric này cho biết chất lượng trung bình của toàn bộ tập đánh giá, không phải một case đơn lẻ.",
    };
  }

  if (aggregation === "weighted_score" || aggregation === "weighted_mean") {
    return {
      observedVariable: "Điểm tổng hợp có trọng số",
      theory: "Công thức lý thuyết: weighted_score = sum(component_score_i * weight_i) / sum(weight_i). Trọng số phản ánh mức quan trọng tương đối của từng thành phần trong rubric.",
      substitution: `Evaluator đã tính điểm tổng hợp = ${resultText}; weights và component inputs nằm trong calculation.parameters nếu artifact có cung cấp.`,
      thresholdRule: thresholdRule(def, result),
      reviewMeaning: "Metric này cần đọc cùng bảng thành phần điểm để biết phần nào kéo điểm lên hoặc xuống.",
    };
  }

  if (aggregation === "rubric_score") {
    return {
      observedVariable: "Điểm rubric nội dung",
      theory: "Công thức lý thuyết: rubric_score = sum(earned_points_i) / sum(maximum_points_i) * scale, trong đó mỗi check phải có tiêu chí expected và evidence tương ứng.",
      substitution: `Điểm rubric đã chuẩn hóa = ${resultText}; chi tiết từng section/check được hiển thị trong phần Thành phần điểm nếu evaluator xuất section_details.`,
      thresholdRule: thresholdRule(def, result),
      reviewMeaning: "Chỉ số này dùng để kiểm tra tính đầy đủ, minh bạch và bằng chứng của báo cáo, thay vì chỉ nhìn một điểm tổng.",
    };
  }

  if (aggregation === "boolean_gate" || aggregation === "presence" || aggregation === "artifact_presence") {
    return {
      observedVariable: "Cổng điều kiện bắt buộc",
      theory: "Công thức lý thuyết: gate_pass = all(required_condition_i = true). Một điều kiện bắt buộc thiếu hoặc sai có thể làm gate không đạt dù các phần khác tốt.",
      substitution: `Kết quả gate hiện tại = ${resultText}.`,
      thresholdRule: thresholdRule(def, result),
      reviewMeaning: "Metric này dùng để bảo vệ ranh giới phát hành, đặc biệt với artifact bắt buộc, schema hoặc phê duyệt.",
    };
  }

  if (aggregation === "error_count") {
    return {
      observedVariable: "Số lỗi tuyệt đối",
      theory: "Công thức lý thuyết: error_count = sum(error_i). Đây là metric lower-is-better; với lỗi P0/P1, ngưỡng thường là bằng 0.",
      substitution: `Số lỗi ghi nhận = ${resultText}.`,
      thresholdRule: thresholdRule(def, result),
      reviewMeaning: "Metric này quan trọng khi chỉ một lỗi cũng có thể chặn phát hành, ví dụ lỗi OCR ảnh hưởng số liệu final hoặc lỗi upload artifact.",
    };
  }

  if (aggregation === "p95") {
    return {
      observedVariable: "Phân vị 95 của độ trễ",
      theory: "Công thức lý thuyết: p95_latency là giá trị tại vị trí ceil(0.95 * n) sau khi sắp xếp latency tăng dần. Đây là cách đo tail latency thay vì chỉ đo trung bình.",
      substitution: `p95 quan sát = ${resultText} trên ${formatCalculationNumber(sampleCount)} sample/run.`,
      thresholdRule: thresholdRule(def, result),
      reviewMeaning: "Metric này cho biết trải nghiệm ở nhóm chậm nhất nhưng vẫn đại diện cho vận hành thường gặp.",
    };
  }

  if (aggregation === "ratio") {
    const rawRatio = numerator !== null && denominator ? formatCalculationNumber(numerator / denominator) : null;
    const substitution = denominator && numerator !== null
      ? `Tỷ số = ${formatCalculationNumber(numerator)} / ${formatCalculationNumber(denominator)} = ${rawRatio ?? resultText}${dashboardValueNote(rawRatio, resultText)}.`
      : `Tỷ số quan sát = ${resultText}.`;
    return {
      observedVariable: "Tỷ số giữa hai đại lượng kiểm định",
      theory: "Công thức lý thuyết: ratio = numerator / denominator. Ý nghĩa nghiệp vụ phụ thuộc vào metric_id và phần inputs/parameters của evaluator.",
      substitution,
      thresholdRule: thresholdRule(def, result),
      reviewMeaning: "Metric này cần đối chiếu numerator, denominator và source artifact để bảo đảm hai đại lượng cùng đơn vị và cùng phạm vi.",
    };
  }

  return {
    observedVariable: metricName,
    theory: `Aggregation '${aggregation || "không khai báo"}' được phát hành bởi evaluator. Dashboard không tự suy diễn công thức ngoài payload để tránh làm sai logic kiểm định.`,
    substitution: `Kết quả hiển thị = ${resultText}; numerator = ${valueOrDash(calculation?.numerator)}, denominator = ${valueOrDash(calculation?.denominator)}.`,
    thresholdRule: thresholdRule(def, result),
    reviewMeaning: "Nên kiểm tra calculation.inputs, calculation.parameters và kết quả từng mẫu bên dưới để tái lập phép tính.",
  };
}

function calculationNarrative(def: MetricDef, result: BenchmarkMetricResult | undefined): string {
  const calculation = result?.calculation;
  const aggregation = String(calculation?.aggregation ?? "");
  const numerator = valueOrDash(calculation?.numerator);
  const denominator = valueOrDash(calculation?.denominator);
  const threshold = formatRuntimeThreshold(def, result);
  const sampleCount = calculation?.per_sample_results?.length
    || calculation?.denominator
    || result?.sample_size
    || 0;
  const metricName = result?.metric_name ?? def.label;

  if (!calculation) {
    return `${metricName}: chưa có calculation payload trong artifact; dashboard chỉ có thể hiển thị trạng thái tổng hợp và ngưỡng ${threshold}.`;
  }
  if (aggregation === "coverage" || aggregation === "cohort_pooled_coverage" || aggregation === "cohort_pass_rate") {
    return `${metricName}: đếm số sample đạt điều kiện chia cho tổng số sample hợp lệ. Tử số hiện là ${numerator}, mẫu số là ${denominator}; kết quả được so với ngưỡng ${threshold}. Bảng bên dưới liệt kê từng sample, trạng thái, giá trị và trace dùng để quyết định đạt hay không đạt.`;
  }
  if (aggregation === "boolean_gate" || aggregation === "presence" || aggregation === "artifact_presence") {
    return `${metricName}: kiểm tra từng điều kiện bắt buộc theo dạng đạt/không đạt. Metric chỉ đạt khi các điều kiện bắt buộc hoặc artifact cần thiết hiện diện đầy đủ; kết quả được so với ngưỡng ${threshold}.`;
  }
  if (aggregation === "error_count") {
    return `${metricName}: đếm tổng số lỗi phát hiện trong các sample kiểm tra. Giá trị tốt là càng thấp càng tốt; thông thường ngưỡng đạt là ${threshold}. Mục ví dụ chưa đạt và bảng mẫu cho biết lỗi nằm ở artifact, luận điểm, công thức hoặc trace nào.`;
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
  if (aggregation === "mean" || aggregation === "cohort_mean" || aggregation === "cohort_mean_observed") {
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
  return `${metricName}: cách tổng hợp '${aggregation || "không khai báo"}' được ghi trong artifact. Dashboard hiển thị tử số, mẫu số, tham số và từng mẫu bên dưới để kiểm tra lại phép tính.`;
}

const SAMPLE_PREVIEW = 5;
const FAILED_PREVIEW = 3;
const ARTIFACT_PREVIEW = 3;

// Centered toggle that collapses long evidence lists by default and reveals the
// full detail only when the reviewer asks for it.
function ShowMoreToggle({
  expanded,
  hiddenCount,
  noun,
  onToggle,
}: {
  expanded: boolean;
  hiddenCount: number;
  noun: string;
  onToggle: () => void;
}) {
  return (
    <div className="metric-explanation__show-more">
      <button type="button" className="metric-explanation__show-more-btn" onClick={onToggle}>
        {expanded ? "Thu gọn" : `Xem thêm ${hiddenCount} ${noun}`}
      </button>
    </div>
  );
}

export function MetricExplanation({ def, result }: { def: MetricDef; result?: BenchmarkMetricResult }) {
  const status = resolveMetricStatus(def, result);
  const [artifactsExpanded, setArtifactsExpanded] = useState(false);
  const [samplesExpanded, setSamplesExpanded] = useState(false);
  const [failuresExpanded, setFailuresExpanded] = useState(false);
  const calculation = result?.calculation;
  const failures = result?.failed_examples ?? [];
  const rawSamples = calculation?.per_sample_results ?? [];
  const samples = rawSamples.length > 0
    ? rawSamples
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
  const sectionDetails = sectionDetailsFromResult(result);
  const formula = calculationFormulaExplanation(def, result);
  const visibleSamples = samplesExpanded ? samples : samples.slice(0, SAMPLE_PREVIEW);
  const hiddenSampleCount = Math.max(samples.length - SAMPLE_PREVIEW, 0);
  const visibleFailures = failuresExpanded ? failures : failures.slice(0, FAILED_PREVIEW);
  const hiddenFailureCount = Math.max(failures.length - FAILED_PREVIEW, 0);
  const visibleArtifactIds = artifactsExpanded ? artifactIds : artifactIds.slice(0, ARTIFACT_PREVIEW);
  const hiddenArtifactCount = Math.max(artifactIds.length - ARTIFACT_PREVIEW, 0);

  return (
    <div className="metric-explanation">
      <div className="metric-explanation__summary">
        <dl>
          <div><dt>Chỉ số</dt><dd>{def.label}</dd></div>
          <div><dt>Phương pháp đánh giá</dt><dd>{def.englishLabel ?? def.technology}</dd></div>
          <div><dt>Trạng thái</dt><dd><StatusPill status={status} /></dd></div>
          <div><dt>Kết quả</dt><dd><code>{formatRuntimeMetricResult(def, result)}</code></dd></div>
          <div><dt>Ngưỡng đạt</dt><dd><code>{formatRuntimeThreshold(def, result)}</code></dd></div>
          <div><dt>Cỡ mẫu</dt><dd>{valueOrDash(result?.sample_size)}</dd></div>
        </dl>
      </div>

      <section className="metric-explanation__section">
        <h3>Bằng chứng thực thi</h3>
        <dl>
          <div><dt>Bộ đánh giá</dt><dd>{result?.evaluator?.framework ?? def.technology}</dd></div>
          <div><dt>Phiên bản framework</dt><dd>{valueOrDash(result?.evaluator?.framework_version)}</dd></div>
          <div><dt>Phiên bản triển khai</dt><dd>{valueOrDash(result?.evaluator?.implementation_version)}</dd></div>
          <div><dt>Trạng thái thực thi</dt><dd>{valueOrDash(result?.evaluator?.execution_status)}</dd></div>
          <div><dt>Mã chỉ số</dt><dd><code>{result?.metric_id ?? def.id}</code></dd></div>
          <div><dt>Thời điểm đánh giá</dt><dd>{valueOrDash(evaluatedAt)}</dd></div>
          <div><dt>Phiên bản dữ liệu</dt><dd>{valueOrDash(result?.dataset_version ?? result?.evidence?.dataset_version)}</dd></div>
          <div><dt>Artifact nguồn</dt><dd>{valueOrDash(result?.artifact_id ?? result?.source)}</dd></div>
          <div>
            <dt>Artifact bằng chứng</dt>
            <dd>
              {listOrDash(visibleArtifactIds)}
              {hiddenArtifactCount > 0 && (
                <ShowMoreToggle
                  expanded={artifactsExpanded}
                  hiddenCount={hiddenArtifactCount}
                  noun="artifact"
                  onToggle={() => setArtifactsExpanded((value) => !value)}
                />
              )}
            </dd>
          </div>
          <div><dt>Đường dẫn trace</dt><dd>{valueOrDash(traceUrl)}</dd></div>
        </dl>
        {!hasEvidence && (
          <p className="metric-explanation__warning">
            Kết quả chỉ số này chưa kèm mã artifact, đường dẫn trace, kết quả mẫu hay ví dụ chưa đạt; vì vậy dashboard chỉ xác nhận được trạng thái tổng hợp, chưa xác nhận được bằng chứng chi tiết.
          </p>
        )}
        {hasEvidence && !hasDeepTrace && (
          <p className="metric-explanation__warning">
            Dữ liệu đang hiển thị là bản tổng hợp theo cohort; các mẫu có thể không kèm trace ở cấp truy vấn/đoạn văn, nhưng bảng bên dưới vẫn cho thấy artifact nguồn và payload mẫu để kiểm tra sâu hơn.
          </p>
        )}
      </section>

      <section className="metric-explanation__section">
        <h3>Cách tính và ngưỡng</h3>
        <p>{calculationNarrative(def, result)}</p>
        <dl className="metric-explanation__formula-list">
          <div><dt>Đại lượng đo</dt><dd>{formula.observedVariable}</dd></div>
          <div><dt>Nguồn công thức</dt><dd>{formulaProvenance(def, result)}</dd></div>
          <div><dt>Công thức lý thuyết</dt><dd>{formula.theory}</dd></div>
          <div><dt>Thay số từ benchmark</dt><dd>{formula.substitution}</dd></div>
          <div><dt>Quy tắc ngưỡng</dt><dd>{formula.thresholdRule}</dd></div>
          <div><dt>Ý nghĩa khi review</dt><dd>{formula.reviewMeaning}</dd></div>
        </dl>
        <dl>
          <div><dt>Cách tổng hợp</dt><dd>{aggregationLabel(calculation?.aggregation)}</dd></div>
          <div><dt>Tử số</dt><dd>{valueOrDash(calculation?.numerator)}</dd></div>
          <div><dt>Mẫu số</dt><dd>{valueOrDash(calculation?.denominator)}</dd></div>
          <div><dt>Bộ ngưỡng áp dụng</dt><dd>{valueOrDash(result?.threshold_policy?.profile)}</dd></div>
        </dl>
        <p>{result?.threshold_policy?.rationale ?? "Chưa có thuyết minh ngưỡng trong sổ đăng ký chỉ số."}</p>
      </section>

      <section className="metric-explanation__section">
        <h3>Thành phần điểm</h3>
        <SectionDetailsTable details={sectionDetails} />
      </section>

      <section className="metric-explanation__section">
        <h3>Tham số đầu vào và cấu hình</h3>
        {Object.keys(calculation?.inputs ?? {}).length === 0 && Object.keys(calculation?.parameters ?? {}).length === 0 ? (
          <p>Bộ đánh giá không ghi thêm tham số đầu vào hay cấu hình runtime cho kết quả này.</p>
        ) : (
          <pre>{valueOrDash({
            inputs: calculation?.inputs ?? {},
            parameters: calculation?.parameters ?? {},
          })}</pre>
        )}
      </section>

      <section className="metric-explanation__section">
        <h3>Kết quả từng mẫu ({samples.length})</h3>
        {samples.length === 0 ? (
          <p>Kết quả chỉ số này không có bằng chứng theo từng mẫu.</p>
        ) : (
          <>
            <div className="metric-explanation__table-scroll">
              <table className="metric-explanation__sample-table">
                <thead>
                  <tr>
                    <th>Mẫu</th>
                    <th>Trạng thái</th>
                    <th>Giá trị</th>
                    <th>Bằng chứng / trace</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleSamples.map((sample, index) => (
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
            {hiddenSampleCount > 0 && (
              <ShowMoreToggle
                expanded={samplesExpanded}
                hiddenCount={hiddenSampleCount}
                noun="mẫu"
                onToggle={() => setSamplesExpanded((value) => !value)}
              />
            )}
          </>
        )}
      </section>

      <section className="metric-explanation__section">
        <h3>Ví dụ chưa đạt ({failures.length})</h3>
        {failures.length === 0 ? (
          <p>Không có ví dụ chưa đạt trong kết quả chỉ số này.</p>
        ) : (
          <>
            <div className="metric-explanation__failed-list">
              {visibleFailures.map((failure, index) => (
                <article className="metric-explanation__failed-item" key={`${failedExampleLabel(failure, index)}-${index}`}>
                  <h4>{failedExampleLabel(failure, index)}</h4>
                  <EvidenceFieldList fields={failedExampleFields(failure)} />
                </article>
              ))}
            </div>
            {hiddenFailureCount > 0 && (
              <ShowMoreToggle
                expanded={failuresExpanded}
                hiddenCount={hiddenFailureCount}
                noun="ví dụ"
                onToggle={() => setFailuresExpanded((value) => !value)}
              />
            )}
          </>
        )}
        <p>{result?.remediation_hint ?? "Chưa có hướng khắc phục."}</p>
      </section>
    </div>
  );
}
