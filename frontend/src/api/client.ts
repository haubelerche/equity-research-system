import type {
  EvaluationPacket,
  GenerateReportResponse,
  ReportsResponse,
  RunStatusResponse,
} from "./types";

// Strip a trailing slash so `${API_BASE}${path}` never produces a double slash.
const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/+$/, "");

// Guard against the most common deploy misconfiguration: pointing VITE_API_BASE
// at the Railway *dashboard* (railway.com/project/...) instead of the deployed
// backend service domain (https://<service>.up.railway.app). The dashboard is
// not an API and sends no CORS headers, so every request otherwise fails with an
// opaque "Failed to fetch" / CORS error. Surface a clear, actionable message.
function assertApiBaseConfigured(): void {
  if (/railway\.(com|app)\/project\//.test(API_BASE)) {
    throw new Error(
      "VITE_API_BASE points at the Railway dashboard URL (railway.com/project/...), " +
        "not your backend. Set it to the service domain, e.g. https://<service>.up.railway.app, then redeploy.",
    );
  }
}

async function getJSON<T>(path: string): Promise<T> {
  assertApiBaseConfigured();
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new Error(
      `GET ${path} returned ${contentType || "unknown content-type"} instead of JSON; check VITE_API_BASE`
    );
  }
  return (await res.json()) as T;
}

export async function fetchReports(): Promise<ReportsResponse> {
  return getJSON<ReportsResponse>("/reports");
}

export async function startRun(ticker: string): Promise<GenerateReportResponse> {
  assertApiBaseConfigured();
  const res = await fetch(`${API_BASE}/reports/${encodeURIComponent(ticker)}/generate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  if (!res.ok) throw new Error(`startRun failed: ${res.status}`);
  const contentType = res.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    throw new Error(
      `POST /reports/${ticker}/generate returned ${contentType || "unknown content-type"} instead of JSON; check VITE_API_BASE`
    );
  }
  return (await res.json()) as GenerateReportResponse;
}

export async function fetchRunStatus(runId: string): Promise<RunStatusResponse> {
  return getJSON<RunStatusResponse>(`/research/${runId}/status`);
}

export async function fetchEvaluationPacket(runId?: string): Promise<EvaluationPacket> {
  return getJSON<EvaluationPacket>(
    runId ? `/research/${runId}/evaluation` : "/eval/framework",
  );
}

export const fileUrl = (ticker: string, kind: "report" | "explanation") =>
  `${API_BASE}/reports/${ticker}/file/${kind}`;

export const previewUrl = (ticker: string, page: number) =>
  `${API_BASE}/reports/${ticker}/preview/${page}`;
