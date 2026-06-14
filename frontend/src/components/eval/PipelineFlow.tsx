import { PIPELINE_ORDER } from "../../data/evalFramework";

export function PipelineFlow() {
  return (
    <figure aria-labelledby="pipeline-title" className="pipeline-flowchart">
      <div className="pipeline-flowchart__heading">
        <h2 id="pipeline-title">Luồng đánh giá tổng quan</h2>
      </div>
      <ol className="pipeline-flowchart__steps">
        {PIPELINE_ORDER.map((stage, index) => (
          <li
            key={stage}
            className={index === PIPELINE_ORDER.length - 1 ? "pipeline-flowchart__step pipeline-flowchart__step--final" : "pipeline-flowchart__step"}
          >
            <span className="pipeline-flowchart__number">{index + 1}</span>
            <span>{stage}</span>
          </li>
        ))}
      </ol>
    </figure>
  );
}
