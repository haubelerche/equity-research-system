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
  PREFLIGHT: "Kiểm tra điều kiện đầu vào",
  PLAN: "Lập kế hoạch phân tích",
  INGEST_AND_VALIDATE: "Thu thập & kiểm định dữ liệu tài chính",
  ANALYZE: "Phân tích tài chính",
  FORECAST_AND_VALUE: "Dự phóng & định giá",
  WRITE_REPORT: "Soạn báo cáo",
  REVIEW: "Rà soát chất lượng",
  EXPORT_GATES: "Kiểm tra cổng xuất bản",
  PUBLISH: "Dựng file PDF",
};

export function stageLabel(stage: string): string {
  return STAGE_LABELS[stage] ?? stage;
}

const INGEST_SUBLABELS: Record<string, string> = {
  cafef: "Đang tìm dữ liệu trên CafeF…",
  official_pdf: "Đang tải BCTC từ HOSE/HNX/SSC…",
  vnstock: "Đang lấy dữ liệu vnstock…",
  validate: "Đang kiểm định & đối chiếu số liệu…",
  rendering: "Đang dựng file báo cáo…",
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
