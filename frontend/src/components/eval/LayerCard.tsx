import type { EvalLayer } from "../../data/evalFramework";
import type { BenchmarkMetricResult } from "../../api/types";
import type { MetricDef } from "../../lib/evalStatus";
import { MetricRow } from "./MetricRow";

interface Props {
  layer: EvalLayer;
  values: Record<string, number | null>;
  results?: Record<string, BenchmarkMetricResult>;
  onViewBenchmark: (layer: EvalLayer) => void;
  onExplain: (layer: EvalLayer) => void;
  onSelectMetric: (layer: EvalLayer, metric: MetricDef, result?: BenchmarkMetricResult) => void;
}

export function LayerCard({ layer, values, results = {}, onViewBenchmark, onExplain, onSelectMetric }: Props) {
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
      <div className="layer-card__table-scroll">
        <table>
          <thead>
            <tr>
              <th>Chỉ số và công cụ đánh giá</th>
              <th>Ngưỡng đạt</th>
              <th>Kết quả</th>
              <th>Trạng thái</th>
            </tr>
          </thead>
          <tbody>
            {layer.metrics.map((metric) => (
              <MetricRow
                key={metric.id}
                def={metric}
                value={values[metric.id]}
                result={results[metric.id]}
                onSelect={(selectedMetric, result) => onSelectMetric(layer, selectedMetric, result)}
              />
            ))}
          </tbody>
        </table>
      </div>
    </article>
  );
}
