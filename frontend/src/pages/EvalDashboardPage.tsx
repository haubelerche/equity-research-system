import { useEffect, useMemo, useState } from "react";
import type { BenchmarkMetricResult, EvaluationPacket } from "../api/types";
import { fetchEvaluationPacket } from "../api/client";
import { EVAL_LAYERS, type EvalLayer } from "../data/evalFramework";
import { mockRunIdForLayer, mockValuesForLayer } from "../mock";
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
import { StatusPill } from "../components/eval/StatusPill";

type ModalState =
  | { kind: "benchmark"; layer: EvalLayer }
  | { kind: "explanation"; layer: EvalLayer }
  | null;

type MetricResultMap = Record<string, BenchmarkMetricResult>;

function artifactFor(packet: EvaluationPacket | null, layer: EvalLayer) {
  return packet?.artifacts?.find((artifact) => artifact.artifact === layer.artifact);
}

function resultKey(result: BenchmarkMetricResult): string {
  return String(result.metric_id ?? result.id ?? "");
}

function resultsForLayer(packet: EvaluationPacket | null, layer: EvalLayer): MetricResultMap {
  const artifact = artifactFor(packet, layer);
  const entries = (artifact?.metric_results ?? [])
    .map((result) => [resultKey(result), result] as const)
    .filter(([key]) => key.length > 0);
  return Object.fromEntries(entries);
}

function valuesForLayer(packet: EvaluationPacket | null, layer: EvalLayer): Record<string, number | null> {
  const values = { ...mockValuesForLayer(layer.id) };
  const results = resultsForLayer(packet, layer);
  for (const metric of layer.metrics) {
    const value = results[metric.id]?.value;
    if (typeof value === "number") values[metric.id] = value;
    if (typeof value === "boolean") values[metric.id] = value ? 1 : 0;
  }
  return values;
}

function layerMetricsPassed(packet: EvaluationPacket | null, layer: EvalLayer): boolean {
  const values = valuesForLayer(packet, layer);
  const results = resultsForLayer(packet, layer);
  return layer.metrics.every((metric) => {
    const result = results[metric.id];
    if (result?.status) return normalizeMetricStatus(String(result.status)) === "pass";
    return evalMetricStatus(metric, values[metric.id]) === "pass";
  });
}

function topBlockers(packet: EvaluationPacket | null): string[] {
  const blockers = new Set<string>();
  for (const artifact of packet?.artifacts ?? []) {
    for (const issue of artifact.blocking_issues ?? []) {
      blockers.add(`${artifact.name}: ${issue}`);
    }
    for (const metric of artifact.metric_results ?? []) {
      const status = normalizeMetricStatus(String(metric.status ?? ""));
      if (status === "fail" || status === "not_evaluable") {
        blockers.add(`${artifact.name}: ${metric.metric_name ?? metric.label ?? resultKey(metric)}`);
      }
    }
  }
  return Array.from(blockers).slice(0, 5);
}

function packetRunId(packet: EvaluationPacket | null, layer: EvalLayer): string {
  return packet?.run_id ?? mockRunIdForLayer(layer.id);
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

  const allMetricsPassed = useMemo(
    () => EVAL_LAYERS.every((layer) => layerMetricsPassed(packet, layer)),
    [packet],
  );
  const blockers = topBlockers(packet);
  const publicationStatus = packet?.publication_status ?? (allMetricsPassed ? "DRAFT_PUBLISHABLE" : "NOT_EVALUATED");

  return (
    <section>
      <header>
        <h1>Khung đánh giá chất lượng hệ thống</h1>
        <p>
          Run <code>{packet?.run_id ?? "local-mock"}</code>
          {packet?.ticker ? `, ticker ${packet.ticker}` : ""}
          {packet?.benchmark_suite_version ? `, suite ${packet.benchmark_suite_version}` : ""}
        </p>
      </header>

      <PipelineFlow />

      <div className={`pub-banner ${allMetricsPassed ? "ok" : "blocked"}`} role="status">
        Trạng thái xuất bản: {publicationStatus}
        {!allMetricsPassed && <span> Cổng deterministic hoặc bằng chứng bắt buộc vẫn đang chặn bản final export.</span>}
      </div>
      {loadError && (
        <div className="eval-note" role="note">
          Chưa tải được evaluation packet trực tiếp; dashboard đang hiển thị snapshot benchmark nội bộ. Chi tiết: {loadError}
        </div>
      )}

      <section className="top-blockers" aria-label="Top Blockers">
        <div className="section-title-row">
          <h2>Top Blockers</h2>
        </div>
        {blockers.length > 0 ? (
          <ol>{blockers.map((blocker) => <li key={blocker}>{blocker}</li>)}</ol>
        ) : (
          <p>Không có blocker trong packet hiện tại.</p>
        )}
      </section>

      <div className="layer-grid">
        {EVAL_LAYERS.map((layer) => (
          <LayerCard
            key={layer.id}
            layer={layer}
            values={valuesForLayer(packet, layer)}
            results={resultsForLayer(packet, layer)}
            onViewBenchmark={(selected) => setModal({ kind: "benchmark", layer: selected })}
            onExplain={(selected) => setModal({ kind: "explanation", layer: selected })}
          />
        ))}
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
                    <td>{result?.metric_name ?? result?.label ?? metric.label}</td>
                    <td>{result?.metric_type ?? metric.technology}</td>
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
                  <td>{metric.label}</td>
                  <td>{metric.technology}</td>
                  <td>{metric.formula}</td>
                  <td className="num">{formatFailCondition(metric)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </EvalModal>
      )}

    </section>
  );
}
