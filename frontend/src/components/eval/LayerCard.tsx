import type { EvalLayer } from "../../data/evalFramework";
import type { BenchmarkMetricResult } from "../../api/types";
import { MetricRow } from "./MetricRow";

interface Props {
  layer: EvalLayer;
  values: Record<string, number | null>;
  results?: Record<string, BenchmarkMetricResult>;
  onViewBenchmark: (layer: EvalLayer) => void;
  onExplain: (layer: EvalLayer) => void;
}

export function LayerCard({ layer, values, results = {}, onViewBenchmark, onExplain }: Props) {
  return (
    <article className="layer-card">
      <header>
        <h3>{layer.title}</h3>
        <p>{layer.subtitle}</p>
        <div className="layer-card__actions">
          <button type="button" data-variant="primary" onClick={() => onViewBenchmark(layer)}>Xem thêm</button>
          <button type="button" onClick={() => onExplain(layer)}>Giải thích</button>
        </div>
      </header>
      <table>
        <thead><tr><th>Chỉ số và công cụ đánh giá</th><th>Đạt khi</th><th>Kết quả</th><th>Trạng thái</th></tr></thead>
        <tbody>
          {layer.metrics.map((m) => (
            <MetricRow key={m.id} def={m} value={values[m.id]} result={results[m.id]} />
          ))}
        </tbody>
      </table>
    </article>
  );
}
