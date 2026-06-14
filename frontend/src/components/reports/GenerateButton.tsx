import { useEffect, useRef, useState } from "react";
import { startRun, fetchRunStatus } from "../../api/client";
import { classifyRunStatus, type RunPhase } from "../../api/runStatus";

interface Props {
  ticker: string;
  onComplete: () => void;
  pollMs?: number;
  /** Idle-state button label. "Sinh báo cáo" for new, "Cập nhật" for refresh. */
  label?: string;
}

type UiState = "idle" | "running" | "success" | "failed";

export function GenerateButton({ ticker, onComplete, pollMs = 4000, label = "Sinh báo cáo" }: Props) {
  const [state, setState] = useState<UiState>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  async function poll(runId: string) {
    const res = await fetchRunStatus(runId);
    const phase: RunPhase = classifyRunStatus(res.status);
    if (phase === "success") { setState("success"); onComplete(); return; }
    if (phase === "failed") { setState("failed"); return; }
    timer.current = setTimeout(() => void poll(runId), pollMs);
  }

  async function handleClick() {
    setState("running");
    try {
      const res = await startRun(ticker);
      // Defer first poll so React can flush the "running" render first
      timer.current = setTimeout(
        () => void poll(res.run_id),
        Math.max(25, Math.min(pollMs, 250)),
      );
    } catch {
      setState("failed");
    }
  }

  if (state === "running") return <span role="status" className="run-state run-state--running">Đang chạy…</span>;
  if (state === "success") return <span role="status" className="run-state run-state--success">Xong</span>;
  if (state === "failed") return <span role="status" className="run-state run-state--failed">Thất bại</span>;
  return <button className="btn-generate" onClick={handleClick}>{label}</button>;
}
