import type { ReportsResponse, StartRunResponse, RunStatusResponse } from "./types";

const API_BASE = import.meta.env.VITE_API_BASE ?? "";

async function getJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return (await res.json()) as T;
}

export async function fetchReports(): Promise<ReportsResponse> {
  return getJSON<ReportsResponse>("/reports");
}

export async function startRun(ticker: string): Promise<StartRunResponse> {
  const res = await fetch(`${API_BASE}/research/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ticker,
      run_type: "full_report",
      objective: `Generate full equity research report for ${ticker}`,
    }),
  });
  if (!res.ok) throw new Error(`startRun failed: ${res.status}`);
  return (await res.json()) as StartRunResponse;
}

export async function fetchRunStatus(runId: string): Promise<RunStatusResponse> {
  return getJSON<RunStatusResponse>(`/research/${runId}/status`);
}

export const fileUrl = (ticker: string, kind: "report" | "explanation") =>
  `${API_BASE}/reports/${ticker}/file/${kind}`;

export const previewUrl = (ticker: string, page: number) =>
  `${API_BASE}/reports/${ticker}/preview/${page}`;
