import type { EvalLayer } from "../../data/evalFramework";
import type { Maturity } from "../../lib/evalStatus";
import { MetricRow } from "./MetricRow";

interface Props { layer: EvalLayer; values: Record<string, number>; maturity: Maturity; }

export function LayerCard({ layer, values, maturity }: Props) {
  return (
    <article className="layer-card">
      <header>
        <h3>{layer.title}</h3>
        <p>{layer.subtitle}</p>
        {layer.artifact !== "—" && <code>{layer.artifact}</code>}
      </header>
      {layer.metrics && (
        <table>
          <thead><tr><th>Metric</th><th>Ngưỡng</th><th>Giá trị</th><th>Trạng thái</th></tr></thead>
          <tbody>
            {layer.metrics.map((m) => (
              <MetricRow key={m.id} def={m} value={values[m.id]} maturity={maturity} />
            ))}
          </tbody>
        </table>
      )}
      {layer.invariants && (
        <ul className="invariants">{layer.invariants.map((i) => <li key={i}>{i}</li>)}</ul>
      )}
      {layer.rubricDimensions && (
        <ul className="rubric">{layer.rubricDimensions.map((d) => <li key={d}>{d}</li>)}</ul>
      )}
      {layer.blockingConditions && (
        <ul className="blocking">{layer.blockingConditions.map((b) => <li key={b}>{b}</li>)}</ul>
      )}
    </article>
  );
}
