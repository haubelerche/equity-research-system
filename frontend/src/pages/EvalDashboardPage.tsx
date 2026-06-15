import { useEffect, useMemo, useState } from "react";
import type { BenchmarkMetricResult, EvaluationPacket } from "../api/types";
import { fetchEvaluationPacket } from "../api/client";
import { EVAL_LAYERS, type EvalLayer } from "../data/evalFramework";
import {
  evalMetricStatus,
  formatFailCondition,
  formatMetricNumber,
  formatPassCondition,
  normalizeMetricStatus,
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
  | { kind: "metric"; layer: EvalLayer; metric: MetricDef; result?: BenchmarkMetricResult }
  | null;

type MetricResultMap = Record<string, BenchmarkMetricResult>;

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
  const threshold = typeof result.threshold === "number" ? result.threshold : 0;
  const operator = String(result.threshold_operator ?? result.threshold ?? "");
  const unit = result.unit === "%" || result.unit === "percent" ? "%" : "";
  return {
    id,
    label: String(result.metric_name ?? result.label ?? id),
    englishLabel: String(result.metric_name ?? result.label ?? id),
    unit,
    comparator: operator.includes("<=") || operator.trim() === "<" ? "lte" : "gte",
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
    .filter(([id]) => id && !configuredIds.has(id))
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

function displayMetricValue(layer: EvalLayer, metricId: string, result: BenchmarkMetricResult | undefined, value: number | null | undefined): string {
  const def = layer.metrics.find((metric) => metric.id === metricId);
  if (typeof result?.value === "number" && def) return formatMetricNumber(def, result.value);
  if (typeof result?.value === "boolean") return result.value ? "true" : "false";
  if (typeof result?.value === "string") return result.value;
  if (value === undefined || value === null || !def) return "Thiếu dữ liệu";
  return formatMetricNumber(def, value);
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
  const publicationStatus = packet?.publication_status ?? "NOT_EVALUATED";

  return (
    <section>
      <header>
        <h1>Khung đánh giá chất lượng hệ thống</h1>
      </header>

      <PipelineFlow />

      <div className={`pub-banner ${allMetricsPassed ? "ok" : "blocked"}`} role="status">
        Trạng thái xuất bản: {publicationStatus}
        {!allMetricsPassed && <span> Cổng deterministic hoặc bằng chứng bắt buộc vẫn đang chặn bản final export.</span>}
      </div>
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

      {modal?.kind === "benchmark" && (
        <EvalModal
          title={`Lịch sử benchmark: ${modal.layer.title.replace(/^\d+ . /, "")}`}
          subtitle="Snapshot project-level hoặc run-scoped mới nhất được dashboard tải về."
          onClose={() => setModal(null)}
        >
          <table>
            <thead>
              <tr>
                <th>Run</th>
                <th>Chỉ số</th>
                <th>Loại</th>
                <th>Ngưỡng</th>
                <th>Kết quả</th>
                <th>Trạng thái</th>
                <th>Failed examples</th>
              </tr>
            </thead>
            <tbody>
              {modal.layer.metrics.map((metric) => {
                const values = valuesForLayer(packet, modal.layer);
                const results = resultsForLayer(packet, modal.layer);
                const result = results[metric.id];
                const status = result?.status
                  ? normalizeMetricStatus(String(result.status))
                  : evalMetricStatus(metric, values[metric.id]);
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
                    <td>{(result?.failed_examples ?? []).length || result?.detail || "Không có"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </EvalModal>
      )}

      {modal?.kind === "explanation" && (
        <EvalModal
          title={`Giải thích: ${modal.layer.title.replace(/^\d+ . /, "")}`}
          subtitle={modal.layer.subtitle}
          onClose={() => setModal(null)}
        >
          <div className="explanation-block">
            <h3>Phương pháp đánh giá</h3>
            <ul>{modal.layer.methodology.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          <table>
            <thead><tr><th>Chỉ số</th><th>Framework</th><th>Công thức hoặc phương pháp</th><th>Chưa đạt khi</th></tr></thead>
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
          title={`Giải trình metric: ${modal.metric.label}`}
          subtitle={`${modal.layer.title.replace(/^\d+ . /, "")} · ${modal.metric.englishLabel ?? modal.metric.technology}`}
          onClose={() => setModal(null)}
        >
          <MetricExplanation def={modal.metric} result={modal.result} />
        </EvalModal>
      )}

    </section>
  );
}
