import type { BenchmarkMetricResult } from "../../api/types";
import type { MetricDef } from "../../lib/evalStatus";
import {
  formatPassCondition,
  formatRoundedNumber,
  formatRuntimeMetricResult,
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
    ?? record?.artifact
    ?? record?.section_key
    ?? record?.ticker
    ?? record?.sample_index
    ?? record?.row_index
    ?? record?.unit_index
    ?? `#${index + 1}`,
  );
}

function sampleStatus(sample: unknown): string {
  const record = asRecord(sample);
  if (!record) return "Chưa có";
  if (record.status !== undefined) return String(record.status);
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
  return valueOrDash(
    record.value
    ?? record.present
    ?? record.accepted
    ?? record.evidence_available
    ?? record.error
    ?? record.metric_score
    ?? record.score
    ?? record.reciprocal_rank
    ?? record.retrieved_source_tier,
  );
}

function sampleEvidence(sample: unknown): string {
  const record = asRecord(sample);
  if (!record) return valueOrDash(sample);
  const top5 = Array.isArray(record.top_5)
    ? record.top_5.slice(0, 3).map((item) => {
      const top = asRecord(item);
      if (!top) return valueOrDash(item);
      return `rank ${valueOrDash(top.rank)} · tier ${valueOrDash(top.reliability_tier)} · ${valueOrDash(top.extraction_method)}`;
    }).join("; ")
    : "";
  const summaryKeys = new Set([
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
    "artifact",
    "section_key",
    "status",
    "passed",
    "hit",
    "value",
    "score",
    "metric_score",
    "reciprocal_rank",
    "retrieved_source_tier",
  ]);
  const parts = Object.entries(record)
    .filter(([key, value]) => !summaryKeys.has(key) && value !== undefined && value !== null && value !== "")
    .map(([key, value]) => `${key}: ${valueOrDash(value)}`);
  if (top5) parts.push(`top evidence: ${top5}`);
  return parts.length > 0 ? parts.join(" | ") : valueOrDash(record);
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
  const threshold = valueOrDash(result?.threshold ?? formatPassCondition(def));
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

  return (
    <div className="metric-explanation">
      <div className="metric-explanation__summary">
        <dl>
          <div><dt>Metric</dt><dd>{def.label}</dd></div>
          <div><dt>Technology</dt><dd>{def.englishLabel ?? def.technology}</dd></div>
          <div><dt>Trạng thái</dt><dd><StatusPill status={status} /></dd></div>
          <div><dt>Kết quả</dt><dd><code>{formatRuntimeMetricResult(def, result)}</code></dd></div>
          <div><dt>Ngưỡng đạt</dt><dd><code>{valueOrDash(result?.threshold ?? formatPassCondition(def))}</code></dd></div>
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
                    <td>{sampleEvidence(sample)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="metric-explanation__section">
        <h3>Failed examples ({failures.length})</h3>
        {failures.length === 0 ? <p>Không có failed example trong metric result.</p> : <pre>{valueOrDash(failures)}</pre>}
        <p>{result?.remediation_hint ?? "Chưa có hướng khắc phục."}</p>
      </section>
    </div>
  );
}
