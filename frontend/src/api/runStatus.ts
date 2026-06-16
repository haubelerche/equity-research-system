import type { RunStatus } from "./types";

export type RunPhase = "running" | "success" | "failed";

const SUCCESS = new Set<string>(["PUBLISHED", "PUBLISHED_DRAFT"]);
const FAILED = new Set<string>(["BLOCKED", "FAILED"]);

export function classifyRunStatus(status: RunStatus | string): RunPhase {
  if (SUCCESS.has(status)) return "success";
  if (FAILED.has(status)) return "failed";
  return "running";
}

// The 9 backend pipeline stages, in order, for the live progress stepper.
export const PIPELINE_STAGES = [
  "PREFLIGHT",
  "PLAN",
  "INGEST_AND_VALIDATE",
  "ANALYZE",
  "FORECAST_AND_VALUE",
  "WRITE_REPORT",
  "REVIEW",
  "EXPORT_GATES",
  "PUBLISH",
] as const;

const STAGE_LABELS: Record<string, string> = {
  PREFLIGHT: "Ki?m tra di?u ki?n d?u v�o",
  PLAN: "L?p k? ho?ch ph�n t�ch",
  INGEST_AND_VALIDATE: "Thu th?p & ki?m d?nh d? li?u t�i ch�nh",
  ANALYZE: "Ph�n t�ch t�i ch�nh",
  FORECAST_AND_VALUE: "D? ph�ng & d?nh gi�",
  WRITE_REPORT: "So?n b�o c�o",
  REVIEW: "R� so�t ch?t lu?ng",
  EXPORT_GATES: "Ki?m tra c?ng xu?t b?n",
  PUBLISH: "D?ng file PDF",
};

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

const INGEST_SUBLABELS: Record<string, string> = {
  cafef: "�ang t�m d? li?u tr�n CafeF�",
  official_pdf: "�ang t?i BCTC t? HOSE/HNX/SSC�",
  vnstock: "�ang l?y d? li?u vnstock�",
  validate: "�ang ki?m d?nh & d?i chi?u s? li?u�",
  rendering: "�ang d?ng file b�o c�o�",
};

/** Vietnamese label for an ingestion/render sub-step, or null if unknown. */
export function ingestSubLabel(substep?: string | null): string | null {
  if (!substep) return null;
  return INGEST_SUBLABELS[substep] ?? null;
}

/** Index of a stage in the pipeline order, or -1. Drives stepper highlighting. */
export function stageIndex(stage: string): number {
  return (PIPELINE_STAGES as readonly string[]).indexOf(stage);
}
