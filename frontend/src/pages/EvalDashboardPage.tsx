import { useState } from "react";
import { EVAL_LAYERS, CI_GATE_MATRIX, MATURITY_TABLE } from "../data/evalFramework";
import { mockValuesForLayer, MOCK_ARTIFACTS } from "../mock";
import type { Maturity } from "../lib/evalStatus";
import { LayerCard } from "../components/eval/LayerCard";
import { MaturityToggle } from "../components/eval/MaturityToggle";
import { PipelineFlow } from "../components/eval/PipelineFlow";

export function EvalDashboardPage() {
  const [maturity, setMaturity] = useState<Maturity>("P0");
  const pub = MOCK_ARTIFACTS.publication_readiness;

  return (
    <section>
      <header>
        <h1>Khung đánh giá mô hình</h1>
        <MaturityToggle value={maturity} onChange={setMaturity} />
      </header>

      <PipelineFlow />

      <div className={`pub-banner ${pub.passed ? "ok" : "blocked"}`} role="status">
        Publication readiness: {pub.passed ? "PASS" : "BLOCKED"}
        {pub.blocking_reasons.length > 0 && <span> — {pub.blocking_reasons.join(", ")}</span>}
      </div>

      <div className="layer-grid">
        {EVAL_LAYERS.map((layer) => (
          <LayerCard key={layer.id} layer={layer} values={mockValuesForLayer(layer.id)} maturity={maturity} />
        ))}
      </div>

      <section aria-label="ci-gate-matrix">
        <h2>CI gate matrix</h2>
        <table>
          <thead><tr><th>Job</th><th>Scope</th><th>Block merge</th></tr></thead>
          <tbody>
            {CI_GATE_MATRIX.map((g) => (
              <tr key={g.job}><td>{g.job}</td><td>{g.scope}</td><td>{g.blockMerge}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section aria-label="maturity-thresholds">
        <h2>Ngưỡng chấp nhận theo độ chín</h2>
        <table>
          <thead><tr><th>Layer</th><th>P0</th><th>P1</th><th>P2</th></tr></thead>
          <tbody>
            {MATURITY_TABLE.map((r) => (
              <tr key={r.layer}><td>{r.layer}</td><td>{r.P0}</td><td>{r.P1}</td><td>{r.P2}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
    </section>
  );
}
