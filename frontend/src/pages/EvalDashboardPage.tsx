import { useState } from "react";
import { ACCEPTANCE_EXPLANATION, EVAL_LAYERS, type EvalLayer } from "../data/evalFramework";
import { mockRunIdForLayer, mockValuesForLayer } from "../mock";
import {
  evalMetricStatus,
  formatFailCondition,
  formatMetricNumber,
  formatPassCondition,
} from "../lib/evalStatus";
import { LayerCard } from "../components/eval/LayerCard";
import { PipelineFlow } from "../components/eval/PipelineFlow";
import { EvalModal } from "../components/eval/EvalModal";
import { StatusPill } from "../components/eval/StatusPill";

type ModalState =
  | { kind: "benchmark"; layer: EvalLayer }
  | { kind: "explanation"; layer: EvalLayer }
  | { kind: "acceptance" }
  | null;

export function EvalDashboardPage() {
  const [modal, setModal] = useState<ModalState>(null);
  const allMetricsPassed = EVAL_LAYERS.every((layer) => {
    const values = mockValuesForLayer(layer.id);
    return layer.metrics.every((metric) => evalMetricStatus(metric, values[metric.id]) === "pass");
  });

  return (
    <section>
      <header>
        <h1>Khung đánh giá chất lượng hệ thống</h1>
      </header>

      <PipelineFlow />

      <div className={`pub-banner ${allMetricsPassed ? "ok" : "blocked"}`} role="status">
        Mức sẵn sàng xuất bản: {allMetricsPassed ? "ĐẠT" : "CHƯA ĐẠT"}
        {!allMetricsPassed && <span> — Có ít nhất một chỉ số chưa đạt ngưỡng vận hành chính thức.</span>}
      </div>

      <div className="layer-grid">
        {EVAL_LAYERS.map((layer) => (
          <LayerCard
            key={layer.id}
            layer={layer}
            values={mockValuesForLayer(layer.id)}
            onViewBenchmark={(selected) => setModal({ kind: "benchmark", layer: selected })}
            onExplain={(selected) => setModal({ kind: "explanation", layer: selected })}
          />
        ))}
      </div>

      <section className="acceptance-standards" aria-label="Tiêu chuẩn đánh giá">
        <div className="section-title-row">
          <h2>Tiêu chuẩn đánh giá và điều kiện Chưa đạt</h2>
          <button type="button" onClick={() => setModal({ kind: "acceptance" })}>Giải thích</button>
        </div>
        <table>
          <thead>
            <tr><th>Nhóm đánh giá</th><th>Chỉ số</th><th>Công nghệ / Framework</th><th>Đạt khi</th><th>Chưa đạt khi</th></tr>
          </thead>
          <tbody>
            {EVAL_LAYERS.flatMap((layer) =>
              layer.metrics.map((metric) => (
                <tr key={`${layer.id}-${metric.id}`}>
                  <td>{layer.title.replace(/^\d+ · /, "")}</td>
                  <td>{metric.label}</td>
                  <td>{metric.technology}</td>
                  <td className="num">{formatPassCondition(metric)}</td>
                  <td className="num">{formatFailCondition(metric)}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      </section>

      {modal?.kind === "benchmark" && (
        <EvalModal
          title={`Lịch sử benchmark: ${modal.layer.title.replace(/^\d+ · /, "")}`}
          subtitle="Hiển thị snapshot benchmark gần nhất đã được hệ thống ghi nhận."
          onClose={() => setModal(null)}
        >
          <table>
            <thead>
              <tr><th>Lần chạy</th><th>Chỉ số</th><th>Framework</th><th>Ngưỡng đạt</th><th>Kết quả</th><th>Trạng thái</th></tr>
            </thead>
            <tbody>
              {modal.layer.metrics.map((metric) => {
                const value = mockValuesForLayer(modal.layer.id)[metric.id];
                const status = evalMetricStatus(metric, value);
                return (
                  <tr key={metric.id}>
                    <td><code>{mockRunIdForLayer(modal.layer.id)}</code></td>
                    <td>{metric.label}</td>
                    <td>{metric.technology}</td>
                    <td className="num">{formatPassCondition(metric)}</td>
                    <td className="num">{value === undefined || value === null ? "Thiếu dữ liệu" : formatMetricNumber(metric, value)}</td>
                    <td><StatusPill status={status} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </EvalModal>
      )}

      {modal?.kind === "explanation" && (
        <EvalModal
          title={`Giải thích: ${modal.layer.title.replace(/^\d+ · /, "")}`}
          subtitle={modal.layer.subtitle}
          onClose={() => setModal(null)}
        >
          <div className="explanation-block">
            <h3>Phương pháp đánh giá</h3>
            <ul>{modal.layer.methodology.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
          <table>
            <thead><tr><th>Chỉ số</th><th>Công nghệ / Framework</th><th>Công thức hoặc phương pháp tính</th><th>Chưa đạt khi</th></tr></thead>
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

      {modal?.kind === "acceptance" && (
        <EvalModal
          title="Cách đọc tiêu chuẩn đánh giá"
          subtitle="Ý nghĩa ngưỡng, trạng thái và cách hệ thống ra quyết định."
          onClose={() => setModal(null)}
        >
          <div className="explanation-block">
            <ul>{ACCEPTANCE_EXPLANATION.map((item) => <li key={item}>{item}</li>)}</ul>
          </div>
        </EvalModal>
      )}
    </section>
  );
}
