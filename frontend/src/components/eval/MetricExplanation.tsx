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
  if (value === null || value === undefined || value === "") return "Chua c�";
  if (typeof value === "number") return formatRoundedNumber(value);
  if (typeof value === "object") return JSON.stringify(roundNumbers(value), null, 2);
  return String(value);
}

function listOrDash(values: unknown[] | undefined): string {
  if (!values || values.length === 0) return "Chua c�";
  return values.map(valueOrDash).join(", ");
}

function runtimeField(result: BenchmarkMetricResult | undefined, key: string): unknown {
  return result ? (result as Record<string, unknown>)[key] : undefined;
}

function hasStructuredTrace(samples: unknown[]): boolean {
  return samples.some((sample) => {
    const record = asRecord(sample);
    return Boolean(record?.query || record?.top_5 || record?.source || record?.artifact_id || record?.trace_url);
  });
}

function sampleLabel(sample: unknown, index: number): string {
  const record = asRecord(sample);
  return valueOrDash(record?.id ?? record?.ticker ?? record?.sample_index ?? `#${index + 1}`);
}

function sampleStatus(sample: unknown): string {
  const record = asRecord(sample);
  if (!record) return "Chua c�";
  if (record.status !== undefined) return String(record.status);
  if (record.passed !== undefined) return record.passed ? "pass" : "fail";
  if (record.hit !== undefined) return record.hit ? "hit" : "miss";
  return "Chua c�";
}

function sampleValue(sample: unknown): string {
  const record = asRecord(sample);
  if (!record) return valueOrDash(sample);
  return valueOrDash(record.value ?? record.score ?? record.reciprocal_rank ?? record.retrieved_source_tier);
}

function sampleEvidence(sample: unknown): string {
  const record = asRecord(sample);
  if (!record) return valueOrDash(sample);
  const top5 = Array.isArray(record.top_5)
    ? record.top_5.slice(0, 3).map((item) => {
      const top = asRecord(item);
      if (!top) return valueOrDash(item);
      return `rank ${valueOrDash(top.rank)} � tier ${valueOrDash(top.reliability_tier)} � ${valueOrDash(top.extraction_method)}`;
    }).join("; ")
    : "";
  const parts = [
    record.query ? `query: ${valueOrDash(record.query)}` : "",
    record.detail ? `detail: ${valueOrDash(record.detail)}` : "",
    record.source ? `source: ${valueOrDash(record.source)}` : "",
    record.source_metric_id ? `source_metric: ${valueOrDash(record.source_metric_id)}` : "",
    record.fiscal_year ? `year: ${valueOrDash(record.fiscal_year)}` : "",
    record.retrieved_chunks !== undefined ? `retrieved_chunks: ${valueOrDash(record.retrieved_chunks)}` : "",
    record.source_tier_hit !== undefined ? `source_tier_hit: ${valueOrDash(record.source_tier_hit)}` : "",
    top5 ? `top evidence: ${top5}` : "",
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" | ") : "Metric result kh�ng c� trace chi ti?t trong sample n�y.";
}

export function MetricExplanation({ def, result }: { def: MetricDef; result?: BenchmarkMetricResult }) {
  const status = resolveMetricStatus(def, result);
  const calculation = result?.calculation;
  const samples = calculation?.per_sample_results ?? [];
  const failures = result?.failed_examples ?? [];
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
          <div><dt>Tr?ng th�i</dt><dd><StatusPill status={status} /></dd></div>
          <div><dt>K?t qu?</dt><dd><code>{formatRuntimeMetricResult(def, result)}</code></dd></div>
          <div><dt>Ngu?ng d?t</dt><dd><code>{valueOrDash(result?.threshold ?? formatPassCondition(def))}</code></dd></div>
          <div><dt>Sample size</dt><dd>{valueOrDash(result?.sample_size)}</dd></div>
        </dl>
      </div>

      <section className="metric-explanation__section">
        <h3>B?ng ch?ng th?c thi</h3>
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
            Metric result n�y chua ch?a artifact id, trace URL, sample result ho?c failed example; v� v?y dashboard ch? x�c nh?n du?c tr?ng th�i t?ng h?p, chua x�c nh?n du?c b?ng ch?ng chi ti?t.
          </p>
        )}
        {hasEvidence && !hasDeepTrace && (
          <p className="metric-explanation__warning">
            Packet dang hi?n th? l� cohort summary; sample hi?n c� chua ch?a trace c?p truy v?n/chunk. C?n m? artifact ticker ho?c b? sung evidence.artifact_ids d? audit s�u hon.
          </p>
        )}
      </section>

      <section className="metric-explanation__section">
        <h3>C�ch t�nh v� ngu?ng</h3>
        <p>{calculation?.formula ?? def.formula}</p>
        <dl>
          <div><dt>Aggregation</dt><dd>{valueOrDash(calculation?.aggregation)}</dd></div>
          <div><dt>Numerator</dt><dd>{valueOrDash(calculation?.numerator)}</dd></div>
          <div><dt>Denominator</dt><dd>{valueOrDash(calculation?.denominator)}</dd></div>
          <div><dt>Threshold profile</dt><dd>{valueOrDash(result?.threshold_policy?.profile)}</dd></div>
        </dl>
        <p>{result?.threshold_policy?.rationale ?? "Chua c� gi?i tr�nh threshold trong registry."}</p>
      </section>

      <section className="metric-explanation__section">
        <h3>Arguments v� parameters</h3>
        {Object.keys(calculation?.inputs ?? {}).length === 0 && Object.keys(calculation?.parameters ?? {}).length === 0 ? (
          <p>Evaluator kh�ng ghi th�m input/parameter runtime trong metric result n�y.</p>
        ) : (
          <pre>{valueOrDash({
            inputs: calculation?.inputs ?? {},
            parameters: calculation?.parameters ?? {},
          })}</pre>
        )}
      </section>

      <section className="metric-explanation__section">
        <h3>K?t qu? t?ng sample ({samples.length})</h3>
        {samples.length === 0 ? (
          <p>Metric result kh�ng c� per-sample evidence.</p>
        ) : (
          <div className="metric-explanation__table-scroll">
            <table className="metric-explanation__sample-table">
              <thead>
                <tr>
                  <th>Sample</th>
                  <th>Status</th>
                  <th>Value</th>
                  <th>B?ng ch?ng / trace</th>
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
        {failures.length === 0 ? <p>Kh�ng c� failed example trong metric result.</p> : <pre>{valueOrDash(failures)}</pre>}
        <p>{result?.remediation_hint ?? "Chua c� hu?ng kh?c ph?c."}</p>
      </section>
    </div>
  );
}
