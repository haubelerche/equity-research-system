import { PIPELINE_ORDER } from "../../data/evalFramework";

export function PipelineFlow() {
  return (
    <nav aria-label="fail-closed pipeline" className="pipeline">
      {PIPELINE_ORDER.map((stage, i) => (
        <span key={stage} className="pipeline__stage">
          {stage}{i < PIPELINE_ORDER.length - 1 ? " →" : ""}
        </span>
      ))}
      <p className="pipeline__rule">
        Một lớp deterministic critical fail không được LLM-judge ghi đè bằng điểm cao.
      </p>
    </nav>
  );
}
