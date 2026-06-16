import { useEffect } from "react";
import { PIPELINE_STAGES, ingestSubLabel, stageIndex, stageLabel } from "../../api/runStatus";
import type { GenerationRun } from "../../generation/types";

interface Props {
  run: GenerationRun;
  onHide: () => void;
}

const SUBSTEP_STAGES = new Set(["INGEST_AND_VALIDATE", "PUBLISH"]);

export function ProgressModal({ run, onHide }: Props) {
  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape") onHide();
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [onHide]);

  const failed = run.phase === "failed";
  const done = run.phase === "success";
  const activeIdx = Math.max(0, stageIndex(run.stage));
  const subLabel = SUBSTEP_STAGES.has(run.stage) ? ingestSubLabel(run.substep) : null;
  const heading = done
    ? `Đã hoàn tất báo cáo ${run.ticker}`
    : failed
      ? `Không tạo được báo cáo ${run.ticker}`
      : `Đang tạo báo cáo ${run.ticker}`;

  return (
    <div className="gen-modal-backdrop" role="presentation" onMouseDown={onHide}>
      <section
        className="gen-modal"
        role="dialog"
        aria-modal="true"
        aria-label={`Tiến trình tạo báo cáo ${run.ticker}`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        <header className="gen-modal__head">
          <h2>{heading}</h2>
          <button type="button" className="gen-modal__hide" onClick={onHide} aria-label="Ẩn cửa sổ tiến trình">
            Ẩn
          </button>
        </header>

        {failed ? (
          <p className="gen-modal__error" role="alert">
            {run.blockingReason ?? `Không tạo được báo cáo ${run.ticker}.`}
          </p>
        ) : (
          <ol className="gen-stepper">
            {PIPELINE_STAGES.map((stage, idx) => {
              const state = done || idx < activeIdx ? "done" : idx === activeIdx ? "active" : "todo";
              return (
                <li key={stage} className={`gen-step gen-step--${state}`}>
                  <span className="gen-step__mark" aria-hidden="true">
                    {state === "done" ? "✓" : state === "active" ? "•" : "·"}
                  </span>
                  <span className="gen-step__label">{stageLabel(stage)}</span>
                  {state === "active" && subLabel && <span className="gen-step__sub">{subLabel}</span>}
                </li>
              );
            })}
          </ol>
        )}

        <footer className="gen-modal__foot">
          <p className="gen-modal__hint">Có thể nhấn Ẩn; quá trình vẫn tiếp tục chạy nền.</p>
        </footer>
      </section>
    </div>
  );
}
