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
  renderable_run_ids?: string[];
  lineage_source?: "manifest" | "local_files" | string;
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

// POST /reports/{ticker}/generate
export interface GenerateReportResponse {
  run_id: string;
  mode: "fast_render" | "full_pipeline" | string;
}

export interface RunProgress {
  substep?: string;
  detail?: string;
  blocking_reason?: string;
}

export interface RunStatusResponse {
  run_id: string;
  ticker: string;
  status: RunStatus;
  current_stage: string;
  progress?: RunProgress;
  blocking_reason?: string | null;
  updated_at: string;
  finished_at: string | null;
}

export type BenchmarkMetricStatus =
  | "pass"
  | "fail"
  | "warning"
  | "not_evaluable"
  | "blocked"
  | "measured_only";

export interface BenchmarkMetricResult {
  id?: string;
  label?: string;
  metric_id?: string;
  metric_name?: string;
  category?: string;
  layer?: string;
  metric_type?: string;
  scope?: string;
  severity?: "P0" | "P1" | "P2" | "P3" | string;
  blocks_publish?: boolean;
  value?: number | string | boolean | null;
  threshold?: number | string | boolean | null;
  threshold_operator?: string;
  unit?: string;
  status?: BenchmarkMetricStatus | string;
  sample_size?: number;
  artifact_id?: string | null;
  artifact_version?: string | null;
  dataset_version?: string | null;
  owner?: string;
  source?: string;
  detail?: string;
  failed_examples?: unknown[];
  remediation_hint?: string;
  metric_registry_version?: string | null;
  evaluator?: {
    id?: string;
    framework?: string;
    framework_version?: string | null;
    implementation_version?: string | null;
    execution_status?: string;
  };
  calculation?: {
    formula?: string | null;
    inputs?: Record<string, unknown>;
    parameters?: Record<string, unknown>;
    aggregation?: string | null;
    numerator?: number | null;
    denominator?: number | null;
    per_sample_results?: unknown[];
  };
  threshold_policy?: {
    profile?: string;
    rationale?: string | null;
    registry_version?: string | null;
  };
  evidence?: {
    artifact_ids?: string[];
    dataset_version?: string | null;
    trace_url?: string | null;
  };
}

export interface EvaluationArtifactSummary {
  plan_id: string;
  name: string;
  artifact: string;
  status: string;
  metrics?: Record<string, unknown> | BenchmarkMetricResult[];
  metric_results?: BenchmarkMetricResult[];
  blocking_issues?: string[];
}

export interface EvaluationPacket {
  schema_version?: string;
  benchmark_suite_version?: string;
  source?: string;
  run_id?: string;
  ticker?: string;
  generated_at?: string;
  fail_closed?: boolean;
  overall_status?: string;
  publication_status?: string;
  client_final_authorized?: boolean | null;
  artifacts?: EvaluationArtifactSummary[];
  summary?: Record<string, number>;
  message?: string;
}
