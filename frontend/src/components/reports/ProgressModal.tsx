import { useEffect } from "react";
import { PIPELINE_STAGES, ingestSubLabel, stageIndex, stageLabel } from "../../api/runStatus";
import type { GenerationRun } from "../../generation/types";

interface Props {
  run: GenerationRun;
  onHide: () => void;
}

const SUBSTEP_STAGES = new Set(["INGEST_AND_VALIDATE", "PUBLISH"]);
const FAST_RENDER_STALE_MS = 45_000;
const FULL_PIPELINE_STALE_MS = 90_000;

function formatElapsed(seconds?: number | null): string | null {
  if (seconds === null || seconds === undefined) return null;
  const safe = Math.max(0, Math.floor(seconds));
  const minutes = Math.floor(safe / 60);
  const rest = safe % 60;
  if (minutes === 0) return `${rest}s`;
  return `${minutes}m ${rest.toString().padStart(2, "0")}s`;
}

function formatLastUpdated(raw?: string | null): string | null {
  if (!raw) return null;
  const timestamp = Date.parse(raw);
  if (!Number.isFinite(timestamp)) return null;
  const seconds = Math.max(0, Math.floor((Date.now() - timestamp) / 1000));
  if (seconds < 60) return `${seconds}s trước`;
  return `${Math.floor(seconds / 60)}m ${String(seconds % 60).padStart(2, "0")}s trước`;
}

function modeLabel(mode?: string | null): string {
  if (mode === "fast_render") return "Dựng lại PDF";
  if (mode === "full_pipeline") return "Chạy lại phân tích đầy đủ";
  return "Đang xác định chế độ";
}

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
  const subLabel = (SUBSTEP_STAGES.has(run.stage) ? ingestSubLabel(run.substep) : null) ?? run.detail ?? null;
  const elapsed = formatElapsed(run.elapsedSeconds);
  const lastUpdated = formatLastUpdated(run.lastHeartbeatAt ?? run.updatedAt);
  const staleThreshold = run.mode === "fast_render" ? FAST_RENDER_STALE_MS : FULL_PIPELINE_STALE_MS;
  const lastHeartbeatMs = Date.parse(run.lastHeartbeatAt ?? run.updatedAt ?? "");
  const isStale = (
    run.phase === "running"
    && Number.isFinite(lastHeartbeatMs)
    && Date.now() - lastHeartbeatMs > staleThreshold
  );
  const hasPollWarning = (run.pollErrorCount ?? 0) >= 2;
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

        <div className="gen-modal__meta" aria-label="Chẩn đoán tiến trình">
          <span>{modeLabel(run.mode)}</span>
          {elapsed && <span>Đã chạy {elapsed}</span>}
          {run.executorState && <span>Worker: {run.executorState}</span>}
          {lastUpdated && <span>Cập nhật {lastUpdated}</span>}
          {run.sourceRunId && <span>Nguồn: {run.sourceRunId.slice(0, 12)}</span>}
        </div>

        {hasPollWarning && (
          <p className="gen-modal__warning" role="status">
            Kết nối trạng thái đang chập chờn; hệ thống vẫn tiếp tục kiểm tra lại.
          </p>
        )}
        {isStale && !failed && !done && (
          <p className="gen-modal__warning" role="status">
            Chưa thấy heartbeat mới từ backend. Nếu worker bị khởi động lại, báo cáo hiện có sẽ không bị ghi đè.
          </p>
        )}

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
