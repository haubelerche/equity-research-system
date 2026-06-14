import type { BenchmarkMetricResult } from "../../api/types";
import type { MetricDef } from "../../lib/evalStatus";
import { StatusPill } from "./StatusPill";
import { formatPassCondition, normalizeMetricStatus } from "../../lib/evalStatus";

function valueOrDash(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Chưa có";
  if (typeof value === "object") return JSON.stringify(value, null, 2);
  return String(value);
}

export function MetricExplanation({ def, result }: { def: MetricDef; result?: BenchmarkMetricResult }) {
  const status = result?.status ? normalizeMetricStatus(String(result.status)) : "not_evaluable";
  const calculation = result?.calculation;
  const samples = calculation?.per_sample_results ?? [];
  const failures = result?.failed_examples ?? [];

  return (
    <div className="metric-explanation">
      <div className="metric-explanation__summary">
        <dl>
          <div><dt>Tên tiếng Việt</dt><dd>{def.label}</dd></div>
          <div><dt>Tên tiếng Anh</dt><dd>{def.englishLabel ?? "Chưa có"}</dd></div>
          <div><dt>Trạng thái</dt><dd><StatusPill status={status} /></dd></div>
          <div><dt>Kết quả</dt><dd><code>{valueOrDash(result?.value)}</code></dd></div>
          <div><dt>Đạt khi</dt><dd><code>{valueOrDash(result?.threshold ?? formatPassCondition(def))}</code></dd></div>
          <div><dt>Sample size</dt><dd>{valueOrDash(result?.sample_size)}</dd></div>
        </dl>
      </div>

      <section className="metric-explanation__section">
        <h3>Evaluator thực thi</h3>
        <dl>
          <div><dt>Framework</dt><dd>{result?.evaluator?.framework ?? def.technology}</dd></div>
          <div><dt>Metric ID</dt><dd><code>{result?.metric_id ?? def.id}</code></dd></div>
          <div><dt>Framework version</dt><dd>{valueOrDash(result?.evaluator?.framework_version)}</dd></div>
          <div><dt>Execution status</dt><dd>{valueOrDash(result?.evaluator?.execution_status)}</dd></div>
          <div><dt>Dataset version</dt><dd>{valueOrDash(result?.dataset_version ?? result?.evidence?.dataset_version)}</dd></div>
          <div><dt>Artifact</dt><dd>{valueOrDash(result?.artifact_id ?? result?.source)}</dd></div>
        </dl>
      </section>

      <section className="metric-explanation__section">
        <h3>Cách tính điểm</h3>
        <p>{calculation?.formula ?? def.formula}</p>
        <dl>
          <div><dt>Numerator</dt><dd>{valueOrDash(calculation?.numerator)}</dd></div>
          <div><dt>Denominator</dt><dd>{valueOrDash(calculation?.denominator)}</dd></div>
          <div><dt>Aggregation</dt><dd>{valueOrDash(calculation?.aggregation)}</dd></div>
          <div><dt>Threshold profile</dt><dd>{valueOrDash(result?.threshold_policy?.profile)}</dd></div>
        </dl>
        <p>{result?.threshold_policy?.rationale ?? "Chưa có giải trình threshold trong registry."}</p>
      </section>

      <section className="metric-explanation__section">
        <h3>Arguments và parameters</h3>
        <pre>{valueOrDash({
          inputs: calculation?.inputs ?? {},
          parameters: calculation?.parameters ?? {},
        })}</pre>
      </section>

      <section className="metric-explanation__section">
        <h3>Kết quả từng sample ({samples.length})</h3>
        <pre>{valueOrDash(samples)}</pre>
      </section>

      <section className="metric-explanation__section">
        <h3>Failed examples ({failures.length})</h3>
        <pre>{valueOrDash(failures)}</pre>
        <p>{result?.remediation_hint ?? "Chưa có hướng khắc phục."}</p>
      </section>
    </div>
  );
}
