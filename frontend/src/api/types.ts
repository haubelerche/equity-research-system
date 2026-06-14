export interface ReportItem {
  ticker: string;
  company_name: string;
  exchange: string;
  segment: string;
  is_mvp: boolean;
  has_report: boolean;
  has_explanation: boolean;
  preview_pages: number[];
  report_size: number | null;
  updated_at: string | null;
}

export interface ReportsResponse {
  items: ReportItem[];
}

// Mirrors backend RunStatus public enum (backend/schemas.py + to_public_status)
export type RunStatus =
  | "INIT" | "INGESTING" | "ANALYZING" | "VALUATING"
  | "SYNTHESIZING" | "AUDITING" | "PUBLISHED" | "PUBLISHED_DRAFT"
  | "BLOCKED" | "FAILED";

export interface StartRunResponse { run_id: string; status: RunStatus; }
export interface RunStatusResponse {
  run_id: string;
  ticker: string;
  status: RunStatus;
  current_stage: string;
  updated_at: string;
  finished_at: string | null;
}
