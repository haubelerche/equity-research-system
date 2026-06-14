import type { RunStatus } from "./types";

export type RunPhase = "running" | "success" | "failed";

const SUCCESS = new Set<string>(["PUBLISHED", "PUBLISHED_DRAFT"]);
const FAILED = new Set<string>(["BLOCKED", "FAILED"]);

export function classifyRunStatus(status: RunStatus | string): RunPhase {
  if (SUCCESS.has(status)) return "success";
  if (FAILED.has(status)) return "failed";
  return "running";
}
