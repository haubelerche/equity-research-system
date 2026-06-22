import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { fetchRunStatus, startRun } from "../api/client";
import { classifyRunStatus } from "../api/runStatus";
import { ProgressModal } from "../components/reports/ProgressModal";
import { ToastContainer } from "../components/common/Toast";
import type { GenerationContextValue, Toast } from "./types";

const GenerationContext = createContext<GenerationContextValue | null>(null);

export function useGeneration(): GenerationContextValue {
  const ctx = useContext(GenerationContext);
  if (!ctx) throw new Error("useGeneration must be used within a GenerationProvider");
  return ctx;
}

const TOAST_TTL_MS = 6000;

export function GenerationProvider({ children, pollMs = 4000 }: { children: ReactNode; pollMs?: number }) {
  const [runs, setRuns] = useState<GenerationContextValue["runs"]>({});
  const [activeTicker, setActiveTicker] = useState<string | null>(null);
  const [toasts, setToasts] = useState<Toast[]>([]);

  // Timers + onComplete callbacks live in refs so polling survives modal hide
  // and component re-renders. Polling is owned here (app level), never by the
  // modal or button; hiding the modal cannot stop a run.
  const timers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});
  const onCompletes = useRef<Record<string, (() => void) | undefined>>({});
  const toastSeq = useRef(0);

  const dismissToast = useCallback((id: number) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const pushToast = useCallback((kind: Toast["kind"], message: string) => {
    const id = ++toastSeq.current;
    setToasts((list) => [...list, { id, kind, message }]);
    setTimeout(() => dismissToast(id), TOAST_TTL_MS);
  }, [dismissToast]);

  const clearTimer = (ticker: string) => {
    const t = timers.current[ticker];
    if (t) {
      clearTimeout(t);
      delete timers.current[ticker];
    }
  };

  const poll = useCallback(async (ticker: string, runId: string) => {
    let res;
    try {
      res = await fetchRunStatus(runId);
    } catch {
      setRuns((prev) => ({
        ...prev,
        [ticker]: {
          ...prev[ticker],
          runId,
          pollErrorCount: (prev[ticker]?.pollErrorCount ?? 0) + 1,
        },
      }));
      // Transient error; keep polling rather than failing the run.
      timers.current[ticker] = setTimeout(() => void poll(ticker, runId), pollMs);
      return;
    }
    const phase = classifyRunStatus(res.status);
    const blockingReason = res.blocking_reason ?? res.progress?.blocking_reason ?? null;
    setRuns((prev) => ({
      ...prev,
      [ticker]: {
        ...prev[ticker],
        runId,
        status: res.status,
        phase,
        stage: res.current_stage ?? "",
        mode: res.mode ?? res.progress?.mode ?? prev[ticker]?.mode ?? null,
        sourceRunId: res.source_run_id ?? res.progress?.source_run_id ?? prev[ticker]?.sourceRunId ?? null,
        executorState: res.executor_state ?? null,
        substep: res.progress?.substep,
        detail: res.progress?.detail,
        blockingReason,
        createdAt: res.created_at ?? prev[ticker]?.createdAt,
        updatedAt: res.updated_at,
        stageStartedAt: res.stage_started_at ?? res.progress?.stage_started_at ?? null,
        lastHeartbeatAt: res.last_heartbeat_at ?? res.progress?.last_heartbeat_at ?? res.updated_at,
        elapsedSeconds: res.elapsed_seconds ?? null,
        pollErrorCount: 0,
      },
    }));

    if (phase === "success") {
      clearTimer(ticker);
      pushToast("success", `Đã sinh xong báo cáo ${ticker}`);
      onCompletes.current[ticker]?.();
      return;
    }
    if (phase === "failed") {
      clearTimer(ticker);
      pushToast("error", blockingReason ?? `Không tạo được báo cáo ${ticker}.`);
      return;
    }
    timers.current[ticker] = setTimeout(() => void poll(ticker, runId), pollMs);
  }, [pollMs, pushToast]);

  const start = useCallback((ticker: string, label: string, onComplete?: () => void, options?: { forceFull?: boolean }) => {
    clearTimer(ticker);
    onCompletes.current[ticker] = onComplete;
    setRuns((prev) => ({
      ...prev,
      [ticker]: { ticker, label, runId: null, status: "INIT", phase: "running", stage: "", pollErrorCount: 0 },
    }));
    setActiveTicker(ticker);

    startRun(ticker, { forceFull: options?.forceFull })
      .then((res) => {
        setRuns((prev) => ({
          ...prev,
          [ticker]: { ...prev[ticker], runId: res.run_id, mode: res.mode },
        }));
        timers.current[ticker] = setTimeout(() => void poll(ticker, res.run_id), Math.min(pollMs, 250));
      })
      .catch(() => {
        setRuns((prev) => ({
          ...prev,
          [ticker]: { ...prev[ticker], phase: "failed", blockingReason: "Không kết nối được API." },
        }));
        pushToast("error", `Không bắt đầu được quá trình sinh báo cáo ${ticker}.`);
      });
  }, [poll, pollMs, pushToast]);

  const openModal = useCallback((ticker: string) => setActiveTicker(ticker), []);
  const hideModal = useCallback(() => setActiveTicker(null), []);

  // Clean up any outstanding timers on unmount.
  useEffect(() => {
    const active = timers.current;
    return () => {
      Object.values(active).forEach(clearTimeout);
    };
  }, []);

  const value = useMemo<GenerationContextValue>(
    () => ({ runs, activeTicker, toasts, start, openModal, hideModal, dismissToast }),
    [runs, activeTicker, toasts, start, openModal, hideModal, dismissToast],
  );

  const activeRun = activeTicker ? runs[activeTicker] : null;

  return (
    <GenerationContext.Provider value={value}>
      {children}
      {activeRun && <ProgressModal run={activeRun} onHide={hideModal} />}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </GenerationContext.Provider>
  );
}
