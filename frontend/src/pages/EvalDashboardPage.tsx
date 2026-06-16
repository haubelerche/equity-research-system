import { useEffect, useMemo, useState } from "react";
import type { BenchmarkMetricResult, EvaluationPacket } from "../api/types";
import { fetchEvaluationPacket } from "../api/client";
import { EVAL_LAYERS, type EvalLayer } from "../data/evalFramework";
import {
  formatFailCondition,
  formatMetricNumber,
  formatPassCondition,
  formatRoundedNumber,
  inferRuntimeComparator,
  parseRuntimeThreshold,
  resolveMetricStatus,
} from "../lib/evalStatus";
import { LayerCard } from "../components/eval/LayerCard";
import { PipelineFlow } from "../components/eval/PipelineFlow";
import { EvalModal } from "../components/eval/EvalModal";
import { MetricExplanation } from "../components/eval/MetricExplanation";
import { StatusPill } from "../components/eval/StatusPill";
import type { MetricDef } from "../lib/evalStatus";

type ModalState =
  | { kind: "benchmark"; layer: EvalLayer }
  | { kind: "explanation"; layer: EvalLayer }
  | { kind: "publication" }
  | { kind: "metric"; layer: EvalLayer; metric: MetricDef; result?: BenchmarkMetricResult }
  | null;

type MetricResultMap = Record<string, BenchmarkMetricResult>;
const HIDDEN_DASHBOARD_METRIC_IDS = new Set(["ocr_unresolved_rate", "corpus_ocr_unresolved_rate"]);
type PublicationIssue = {
  artifact: string;
  artifactName: string;
  metricId: string;
  metricName: string;
  reason: string;
  severity?: string;
  status?: string;
  value?: unknown;
  threshold?: unknown;
  failedExamples: number;
};

function artifactFor(packet: EvaluationPacket | null, layer: EvalLayer) {
  const accepted = new Set([layer.artifact, ...(layer.artifactAliases ?? [])]);
  return packet?.artifacts?.find((artifact) => accepted.has(artifact.artifact));
}

function resultKey(result: BenchmarkMetricResult): string {
  return String(result.metric_id ?? result.id ?? "");
}

function resultsForLayer(packet: EvaluationPacket | null, layer: EvalLayer): MetricResultMap {
  const artifact = artifactFor(packet, layer);
  const metricResults = artifact?.metric_results
    ?? (Array.isArray(artifact?.metrics) ? artifact.metrics as BenchmarkMetricResult[] : []);
  const entries = metricResults
    .map((result) => [resultKey(result), result] as const)
    .filter(([key]) => key.length > 0);
  const results = Object.fromEntries(entries);
  for (const metric of layer.metrics) {
    if (results[metric.id]) continue;
    const alias = metric.aliases?.find((key) => results[key]);
    if (alias) results[metric.id] = results[alias];
  }
  return results;
}

function metricFromResult(result: BenchmarkMetricResult): MetricDef {
  const id = resultKey(result);
  const threshold = parseRuntimeThreshold(result.threshold, result.unit) ?? 0;
  const unit = result.unit === "%" || result.unit === "percent" || String(result.threshold ?? "").includes("%") ? "%" : "";
  return {
    id,
    label: String(result.metric_name ?? result.label ?? id),
    englishLabel: String(result.metric_name ?? result.label ?? id),
    unit,
    comparator: inferRuntimeComparator(result.threshold, result.threshold_operator, result.metric_type, id),
    threshold,
    thresholdLabel: result.threshold === null || result.threshold === undefined
      ? undefined
      : String(result.threshold),
    technology: String(result.evaluator?.framework ?? result.category ?? result.source ?? "Benchmark artifact"),
    formula: String(result.calculation?.formula ?? result.detail ?? "Runtime benchmark metric emitted by evaluator."),
    metricType: result.metric_type,
    scope: result.scope,
    severity: result.severity,
    blocksPublish: result.blocks_publish,
  };
}

function metricsForLayer(packet: EvaluationPacket | null, layer: EvalLayer): MetricDef[] {
  const results = resultsForLayer(packet, layer);
  const configured = layer.metrics;
  const configuredIds = new Set(configured.flatMap((metric) => [metric.id, ...(metric.aliases ?? [])]));
  const dynamic = Object.entries(results)
    .filter(([id]) => id && !configuredIds.has(id) && !HIDDEN_DASHBOARD_METRIC_IDS.has(id))
    .map(([, result]) => metricFromResult(result));
  return [...configured, ...dynamic];
}

function layerWithRuntimeMetrics(packet: EvaluationPacket | null, layer: EvalLayer): EvalLayer {
  return { ...layer, metrics: metricsForLayer(packet, layer) };
}

function valuesForLayer(packet: EvaluationPacket | null, layer: EvalLayer): Record<string, number | null> {
  const values = {} as Record<string, number | null>;
  const results = resultsForLayer(packet, layer);
  for (const metric of layer.metrics) {
    const value = results[metric.id]?.value;
    if (typeof value === "number") values[metric.id] = value;
    if (typeof value === "boolean") values[metric.id] = value ? 1 : 0;
  }
  return values;
}

function packetRunId(packet: EvaluationPacket | null, layer: EvalLayer): string {
  return packet?.run_id ?? artifactFor(packet, layer)?.name ?? "not_evaluated";
}

function packetAllowsPublication(packet: EvaluationPacket | null): boolean {
  if (!packet) return false;
  if (packet.client_final_authorized === true) return true;
  const publicationStatus = String(packet.publication_status ?? "").toUpperCase();
  if (publicationStatus.includes("BLOCKED") || publicationStatus.includes("NOT_EVALUATED")) return false;
  if (publicationStatus.includes("AUTHORIZED") || publicationStatus.includes("PUBLISHABLE")) return true;
  return String(packet.overall_status ?? "").toLowerCase() === "pass";
}

function blockingIssueCount(packet: EvaluationPacket | null): number {
  return packet?.artifacts?.reduce(
    (count, artifact) => count + (artifact.blocking_issues?.length ?? 0),
    0,
  ) ?? 0;
}

function publicationStatusTitle(packet: EvaluationPacket | null): string {
  const status = String(packet?.publication_status ?? "NOT_EVALUATED").toUpperCase();
  if (status.includes("BLOCKED_BY_P0")) return "B�o c�o dang b? ch?n b?i l?i P0";
  if (status.includes("BLOCKED")) return "B�o c�o dang b? ch?n";
  if (status.includes("AUTHORIZED") || status.includes("PUBLISHABLE")) return "B�o c�o d? di?u ki?n xu?t b?n";
  if (status.includes("NOT_EVALUATED")) return "Chua c� k?t qu? d�nh gi�";
  return "Tr?ng th�i xu?t b?n c?n ki?m tra";
}

function normalizeIssueReason(reason: string): string {
  return reason
    .replace(/_/g, " ")
    .replace(/\bfcff\b/gi, "FCFF")
    .replace(/\bfcfe\b/gi, "FCFE")
    .replace(/\bwacc\b/gi, "WACC")
    .replace(/\bev\b/gi, "EV");
}

function collectPublicationIssues(packet: EvaluationPacket | null): PublicationIssue[] {
  const issues: PublicationIssue[] = [];
  for (const artifact of packet?.artifacts ?? []) {
    const metrics = artifact.metric_results
      ?? (Array.isArray(artifact.metrics) ? artifact.metrics as BenchmarkMetricResult[] : []);
    const byId = new Map(metrics.map((metric) => [resultKey(metric), metric]));

    for (const rawIssue of artifact.blocking_issues ?? []) {
      const [rawMetricId, ...reasonParts] = String(rawIssue).split(":");
      const metricId = rawMetricId.trim();
      const metric = byId.get(metricId);
      const reason = reasonParts.join(":").trim();
      issues.push({
        artifact: artifact.artifact,
        artifactName: artifact.name,
        metricId,
        metricName: String(metric?.metric_name ?? metric?.label ?? metricId),
        reason: normalizeIssueReason(reason || "Metric n�y dang ch?n xu?t b?n."),
        severity: metric?.severity,
        status: metric?.status,
        value: metric?.value,
        threshold: metric?.threshold,
        failedExamples: metric?.failed_examples?.length ?? 0,
      });
    }

    if ((artifact.blocking_issues ?? []).length === 0) {
      for (const metric of metrics) {
        const status = String(metric.status ?? "").toLowerCase();
        if (metric.blocks_publish && ["fail", "blocked", "not_evaluable"].includes(status)) {
          const metricId = resultKey(metric);
          issues.push({
            artifact: artifact.artifact,
            artifactName: artifact.name,
            metricId,
            metricName: String(metric.metric_name ?? metric.label ?? metricId),
            reason: "Metric P0/P1 chua d?t ngu?ng xu?t b?n.",
            severity: metric.severity,
            status: metric.status,
            value: metric.value,
            threshold: metric.threshold,
            failedExamples: metric.failed_examples?.length ?? 0,
          });
        }
      }
    }
  }
  return issues;
}

function displayMetricValue(layer: EvalLayer, metricId: string, result: BenchmarkMetricResult | undefined, value: number | null | undefined): string {
  const def = layer.metrics.find((metric) => metric.id === metricId);
  if (typeof result?.value === "number" && def) return formatMetricNumber(def, result.value);
  if (typeof result?.value === "boolean") return result.value ? "true" : "false";
  if (typeof result?.value === "string") return result.value;
  if (value === undefined || value === null || !def) return "Thi?u d? li?u";
  return formatMetricNumber(def, value);
}

function displayRuntimeValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "Chua c�";
  if (typeof value === "number") return formatRoundedNumber(value);
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "string") return value;
  return JSON.stringify(roundRuntimeNumbers(value));
}

function roundRuntimeNumbers(value: unknown): unknown {
  if (typeof value === "number") {
    if (!Number.isFinite(value)) return value;
    return Number(value.toFixed(3));
  }
  if (Array.isArray(value)) return value.map(roundRuntimeNumbers);
  if (value && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([key, item]) => [key, roundRuntimeNumbers(item)]),
    );
  }
  return value;
}

export function EvalDashboardPage() {
  const [modal, setModal] = useState<ModalState>(null);
  const [packet, setPacket] = useState<EvaluationPacket | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  useEffect(() => {
    const runId = new URLSearchParams(window.location.search).get("run_id") ?? undefined;
    fetchEvaluationPacket(runId)
      .then((payload) => {
        setPacket(payload);
        setLoadError(null);
      })
      .catch((error: Error) => {
        setLoadError(error.message);
      });
  }, []);

  const allMetricsPassed = useMemo(() => packetAllowsPublication(packet), [packet]);
  const publicationTitle = useMemo(() => publicationStatusTitle(packet), [packet]);
  const publicationIssues = useMemo(() => collectPublicationIssues(packet), [packet]);
  const blockingIssues = publicationIssues.length || blockingIssueCount(packet);

  return (
    <section>
      <header>
        <h1>Khung d�nh gi� ch?t lu?ng h? th?ng</h1>
      </header>

      <PipelineFlow />

      <button
        type="button"
        className={`pub-banner pub-banner--compact pub-banner--clickable ${allMetricsPassed ? "ok" : "blocked"}`}
        onClick={() => setModal({ kind: "publication" })}
      >
        <span className="pub-banner__label">Tr?ng th�i suite</span>
        <strong>{publicationTitle}</strong>
        {!allMetricsPassed && (
          <span>
            {blockingIssues > 0
              ? `${blockingIssues} l?i dang ch?n final export. Nh?n d? xem chi ti?t.`
              : "C� gate ho?c b?ng ch?ng b?t bu?c chua d?t. Nh?n d? xem chi ti?t."}
          </span>
        )}
      </button>
      {loadError && (
        <div className="eval-note" role="note">
          Chua tai duoc evaluation packet truc tiep; dashboard khong hien thi so lieu thay the. Hay chay benchmark suite va refresh lai packet. Chi tiet: {loadError}
        </div>
      )}

      <div className="layer-grid">
        {EVAL_LAYERS.map((layer) => {
          const displayLayer = layerWithRuntimeMetrics(packet, layer);
          return (
            <LayerCard
              key={layer.id}
              layer={displayLayer}
              values={valuesForLayer(packet, displayLayer)}
              results={resultsForLayer(packet, displayLayer)}
              onViewBenchmark={(selected) => setModal({ kind: "benchmark", layer: selected })}
              onExplain={(selected) => setModal({ kind: "explanation", layer: selected })}
              onSelectMetric={(selectedLayer, metric, result) => setModal({
                kind: "metric",
                layer: selectedLayer,
                metric,
                result,
              })}
            />
          );
        })}
      </div>

      {modal?.kind === "publication" && (
        <EvalModal
          title={publicationTitle}
          subtitle="C�c l?i du?i d�y l� nguy�n nh�n khi?n h? th?ng chua cho ph�p xu?t final export."
          onClose={() => setModal(null)}
        >
          <div className="explanation-block">
            <h3>V� sao b? ch?n?</h3>
            <p>
              Tr?ng th�i n�y l� tr?ng th�i c?p suite, kh�ng ph?i m?t metric ri�ng.
              H? th?ng d?t tr?ng th�i ch?n khi c�n P0 gate, artifact b?t bu?c, ho?c b?ng ch?ng ki?m d?nh chua d?t.
            </p>
          </div>
          {publicationIssues.length === 0 ? (
            <div className="explanation-block">
              <h3>Chua c� danh s�ch l?i chi ti?t</h3>
              <p>Evaluation packet hi?n t?i kh�ng g?i k�m blocking_issues ho?c metric blocking c? th?.</p>
            </div>
          ) : (
            <div className="publication-issues">
              {publicationIssues.map((issue, index) => (
                <article className="publication-issue" key={`${issue.artifact}-${issue.metricId}-${issue.reason}-${index}`}>
                  <header>
                    <div>
                      <h3>{issue.metricName}</h3>
                      <p>{issue.artifactName} � <code>{issue.artifact}</code></p>
                    </div>
                    <StatusPill status={resolveMetricStatus({
                      id: issue.metricId,
                      label: issue.metricName,
                      unit: "",
                      comparator: "lte",
                      threshold: 0,
                      technology: "publication_gate",
                      formula: issue.reason,
                    }, { value: null, status: issue.status ?? "fail" })} />
                  </header>
                  <dl>
                    <div><dt>L?i</dt><dd>{issue.reason}</dd></div>
                    <div><dt>Metric ID</dt><dd><code>{issue.metricId}</code></dd></div>
                    <div><dt>Severity</dt><dd>{displayRuntimeValue(issue.severity)}</dd></div>
                    <div><dt>Tr?ng th�i metric</dt><dd>{displayRuntimeValue(issue.status)}</dd></div>
                    <div><dt>K?t qu?</dt><dd>{displayRuntimeValue(issue.value)}</dd></div>
                    <div><dt>Ngu?ng d?t</dt><dd>{displayRuntimeValue(issue.threshold)}</dd></div>
                    <div><dt>Failed examples</dt><dd>{formatRoundedNumber(issue.failedExamples)}</dd></div>
                  </dl>
                </article>
              ))}
            </div>
          )}
        </EvalModal>
      )}

      {modal?.kind === "benchmark" && (
        <EvalModal
          title={`L?ch s? benchmark: ${modal.layer.title.replace(/^\d+ . /, "")}`}
          subtitle="Snapshot project-level ho?c run-scoped m?i nh?t du?c dashboard t?i v?."
          onClose={() => setModal(null)}
        >
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Ch? s?</th>
                <th>Lo?i</th>
                <th>Ngu?ng</th>
                <th>K?t qu?</th>
                <th>Tr?ng th�i</th>
                <th>Failed examples</th>
              </tr>
            </thead>
            <tbody>
              {modal.layer.metrics.map((metric) => {
                const values = valuesForLayer(packet, modal.layer);
                const results = resultsForLayer(packet, modal.layer);
                const result = results[metric.id];
                const status = resolveMetricStatus(metric, result, values[metric.id]);
                return (
                  <tr key={metric.id}>
                    <td><code>{packetRunId(packet, modal.layer)}</code></td>
                    <td>
                      <strong>{metric.label}</strong>
                      <span className="metric-technology">{metric.englishLabel ?? metric.technology}</span>
                    </td>
                    <td>{result?.metric_type ?? metric.metricType ?? metric.technology}</td>
                    <td className="num">{String(result?.threshold ?? formatPassCondition(metric))}</td>
                    <td className="num">{displayMetricValue(modal.layer, metric.id, result, values[metric.id])}</td>
                    <td><StatusPill status={status} /></td>
                    <td>{(result?.failed_examples ?? []).length || result?.detail || "Kh�ng c�"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </EvalModal>
      )}

      {modal?.kind === "explanation" && (
        <EvalModal
          title={`Gi?i th�ch: ${modal.layer.title.replace(/^\d+ . /, "")}`}
          subtitle={modal.layer.subtitle}
          onClose={() => setModal(null)}
        >
          <div className="explanation-block">
            <h3>Phuong ph�p d�nh gi�</h3>
            <ul>{modal.layer.methodology.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          {(() => {
            const artifact = artifactFor(packet, modal.layer);
            const values = valuesForLayer(packet, modal.layer);
            const results = resultsForLayer(packet, modal.layer);

            return (
              <div className="explanation-block">
                <h3>L?n ch?y benchmark dang hi?n th?</h3>
                <dl className="benchmark-run-details">
                  <div><dt>Run</dt><dd><code>{packetRunId(packet, modal.layer)}</code></dd></div>
                  <div><dt>Source</dt><dd>{packet?.source ?? "Chua c�"}</dd></div>
                  <div><dt>Artifact</dt><dd><code>{artifact?.artifact ?? modal.layer.artifact}</code></dd></div>
                  <div><dt>Tr?ng th�i artifact</dt><dd>{artifact?.status ?? "Chua c�"}</dd></div>
                  <div><dt>Generated at</dt><dd>{packet?.generated_at ?? "Chua c�"}</dd></div>
                </dl>
                <table>
                  <thead>
                    <tr>
                      <th>Ch? s?</th>
                      <th>Aggregation</th>
                      <th>T? s?</th>
                      <th>M?u s?</th>
                      <th>K?t qu?</th>
                      <th>Tr?ng th�i</th>
                      <th>Chi ti?t</th>
                    </tr>
                  </thead>
                  <tbody>
                    {modal.layer.metrics.map((metric) => {
                      const result = results[metric.id];
                      const calculation = result?.calculation;
                      const status = resolveMetricStatus(metric, result, values[metric.id]);
                      const failedCount = (result?.failed_examples ?? []).length;

                      return (
                        <tr key={metric.id}>
                          <td>
                            <strong>{metric.label}</strong>
                            <span className="metric-technology">{metric.englishLabel ?? metric.technology}</span>
                          </td>
                          <td>{displayRuntimeValue(calculation?.aggregation ?? result?.detail ?? "Chua c�")}</td>
                          <td className="num">{displayRuntimeValue(calculation?.numerator)}</td>
                          <td className="num">{displayRuntimeValue(calculation?.denominator)}</td>
                          <td className="num">{displayMetricValue(modal.layer, metric.id, result, values[metric.id])}</td>
                          <td><StatusPill status={status} /></td>
                          <td>
                            <span>sample={displayRuntimeValue(result?.sample_size)}</span>
                            <span className="metric-technology">failed_examples={formatRoundedNumber(failedCount)}</span>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            );
          })()}
          <table>
            <thead><tr><th>Ch? s?</th><th>Framework</th><th>C�ng th?c ho?c phuong ph�p</th><th>Chua d?t khi</th></tr></thead>
            <tbody>
              {modal.layer.metrics.map((metric) => (
                <tr key={metric.id}>
                  <td>
                    <strong>{metric.label}</strong>
                    <span className="metric-technology">{metric.englishLabel ?? metric.technology}</span>
                  </td>
                  <td>{metric.technology}</td>
                  <td>{metric.formula}</td>
                  <td className="num">{formatFailCondition(metric)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </EvalModal>
      )}

      {modal?.kind === "metric" && (
        <EvalModal
          title={`Gi?i tr�nh metric: ${modal.metric.label}`}
          subtitle={`${modal.layer.title.replace(/^\d+ . /, "")} � ${modal.metric.englishLabel ?? modal.metric.technology}`}
          onClose={() => setModal(null)}
        >
          <MetricExplanation def={modal.metric} result={modal.result} />
        </EvalModal>
      )}

    </section>
  );
}
