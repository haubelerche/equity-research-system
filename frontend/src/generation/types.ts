import type { RunPhase } from "../api/runStatus";
import type { RunStatus } from "../api/types";

export interface GenerationRun {
  ticker: string;
  label: string;
  runId: string | null;
  status: RunStatus | "INIT";
  phase: RunPhase;
  stage: string;
  substep?: string;
  blockingReason?: string | null;
}

export interface Toast {
  id: number;
  kind: "success" | "error";
  message: string;
}

export interface GenerationContextValue {
  /** In-flight + finished generation runs, keyed by ticker. */
  runs: Record<string, GenerationRun>;
  /** Ticker whose progress modal is currently shown, or null when hidden. */
  activeTicker: string | null;
  toasts: Toast[];
  /** Begin (or restart) generation for a ticker and open its progress modal. */
  start: (ticker: string, label: string, onComplete?: () => void) => void;
  openModal: (ticker: string) => void;
  /** Hide the modal WITHOUT stopping generation (polling continues). */
  hideModal: () => void;
  dismissToast: (id: number) => void;
}
