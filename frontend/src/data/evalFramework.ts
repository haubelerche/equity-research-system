import type { MetricDef } from "../lib/evalStatus";

export interface EvalLayer {
  id: string;
  title: string;
  subtitle: string;
  artifact: string;            // e.g. "data_quality.json"
  metrics?: MetricDef[];       // metric-driven layers
  invariants?: string[];       // Layer 3 critical invariants (display)
  rubricDimensions?: string[]; // Layer 5 judge rubric (display)
  blockingConditions?: string[]; // Layer 6 (display)
}

const t = (P0: number | null, P1: number | null, P2: number | null) => ({ P0, P1, P2 });

export const EVAL_LAYERS: EvalLayer[] = [
  {
    id: "data_reliability",
    title: "1 · Data reliability",
    subtitle: "Fact ingestion, provenance, reconciliation, freshness",
    artifact: "data_quality.json",
    metrics: [
      { id: "core_metric_coverage", label: "Core metric coverage", unit: "%", comparator: "gte", thresholds: t(0.95, 0.95, 0.95) },
      { id: "period_completeness", label: "Period completeness", unit: "%", comparator: "gte", thresholds: t(1, 1, 1) },
      { id: "provenance_coverage", label: "Source provenance coverage", unit: "%", comparator: "gte", thresholds: t(1, 1, 1) },
      { id: "official_reconciliation_rate", label: "Official reconciliation rate", unit: "%", comparator: "gte", thresholds: t(0.95, 0.95, 0.95) },
      { id: "ocr_unresolved_rate", label: "OCR unresolved rate", unit: "%", comparator: "lte", thresholds: t(0, 0, 0) },
      { id: "duplicate_fact_rate", label: "Duplicate fact rate", unit: "%", comparator: "lte", thresholds: t(0, 0, 0) },
    ],
  },
  {
    id: "rag_evidence",
    title: "2 · RAG & evidence",
    subtitle: "Retrieval, citation evidence, Ragas metrics",
    artifact: "retrieval_eval.json",
    metrics: [
      { id: "hit_rate_at_5", label: "Hit-rate@5", unit: "%", comparator: "gte", thresholds: t(null, 0.9, 0.95) },
      { id: "mrr_at_5", label: "MRR@5", unit: "", comparator: "gte", thresholds: t(null, 0.8, 0.8) },
      { id: "context_precision", label: "Context precision", unit: "", comparator: "gte", thresholds: t(null, 0.85, 0.85) },
      { id: "context_recall", label: "Context recall", unit: "", comparator: "gte", thresholds: t(null, 0.85, 0.85) },
      { id: "faithfulness", label: "Faithfulness", unit: "", comparator: "gte", thresholds: t(null, 0.85, 0.9) },
      { id: "response_relevancy", label: "Response relevancy", unit: "", comparator: "gte", thresholds: t(null, 0.85, 0.85) },
    ],
  },
  {
    id: "financial",
    title: "3 · Financial calculation",
    subtitle: "Deterministic invariants — LLM must not compute these",
    artifact: "financial_eval.json",
    metrics: [
      { id: "critical_failures", label: "Critical invariant failures", unit: "", comparator: "lte", thresholds: t(0, 0, 0) },
      { id: "golden_drift_out_of_tolerance", label: "Golden valuation drift out of tolerance", unit: "", comparator: "lte", thresholds: t(0, 0, 0) },
    ],
    invariants: [
      "Net debt = interest_bearing_debt − cash − short_term_investments",
      "EPS = net_income × 1000 / diluted_shares_mn",
      "BS balance: assets = equity + debt + other_liabilities",
      "FCFF = EBIT(1−tax) + D&A − CAPEX − ΔNWC",
      "FCFE = NI + D&A − CAPEX − ΔNWC + net_borrowing",
      "EV-to-equity bridge",
      "Target price = equity_value / diluted_shares",
      "Gordon growth: discount_rate > terminal_growth",
      "Sensitivity matrix varies (≥2 distinct values)",
      "Sensitivity base cell matches target price",
      "Recommendation matches upside policy",
    ],
  },
  {
    id: "citation",
    title: "4 · Citation & provenance",
    subtitle: "Claim-level coverage, source tier, official source requirement",
    artifact: "citation_eval.json",
    metrics: [
      { id: "quant_citation_coverage", label: "Quantitative citation coverage", unit: "%", comparator: "gte", thresholds: t(1, 1, 1) },
      { id: "citation_key_resolution", label: "Citation key resolution", unit: "%", comparator: "gte", thresholds: t(1, 1, 1) },
      { id: "source_id_validity", label: "Source ID validity", unit: "%", comparator: "gte", thresholds: t(1, 1, 1) },
      { id: "official_source_coverage", label: "Official source coverage (material quant.)", unit: "%", comparator: "gte", thresholds: t(1, 1, 1) },
      { id: "numeric_mismatch_rate", label: "Numeric mismatch rate (> tol.)", unit: "%", comparator: "lte", thresholds: t(0, 0, 0) },
      { id: "tier3_only_material_claims", label: "Tier-3-only material claims", unit: "", comparator: "lte", thresholds: t(0, 0, 0) },
      { id: "generic_citations", label: "Generic citation labels", unit: "", comparator: "lte", thresholds: t(0, 0, 0) },
      { id: "catalyst_without_evidence", label: "Catalyst events without evidence span", unit: "", comparator: "lte", thresholds: t(0, 0, 0) },
    ],
  },
  {
    id: "agent",
    title: "5 · Agent workflow & LLM judge",
    subtitle: "Tool permission, role adherence, groundedness, judge rubric",
    artifact: "agent_eval.json",
    metrics: [
      { id: "tool_permission_compliance", label: "Tool permission compliance", unit: "%", comparator: "gte", thresholds: t(1, 1, 1) },
      { id: "schema_validity", label: "Output schema validity", unit: "%", comparator: "gte", thresholds: t(1, 1, 1) },
      { id: "no_unauthorized_calc", label: "No unauthorized financial calculation", unit: "%", comparator: "gte", thresholds: t(1, 1, 1) },
      { id: "role_adherence", label: "Role adherence", unit: "", comparator: "gte", thresholds: t(null, 0.85, 0.9) },
      { id: "groundedness", label: "Groundedness (final narrative)", unit: "", comparator: "gte", thresholds: t(null, 0.85, 0.9) },
      { id: "task_completion", label: "Task completion", unit: "", comparator: "gte", thresholds: t(null, 0.85, 0.85) },
      { id: "plan_adherence", label: "Plan adherence", unit: "", comparator: "gte", thresholds: t(null, 0.85, 0.85) },
      { id: "critic_issue_recall", label: "Critic issue recall (seeded)", unit: "%", comparator: "gte", thresholds: t(null, 0.9, 0.9) },
    ],
    rubricDimensions: [
      "Evidence discipline", "Financial restraint", "Company specificity",
      "Materiality", "Risk balance", "Citation integrity", "Professional tone",
    ],
  },
  {
    id: "report_quality",
    title: "6 · Report quality",
    subtitle: "Institutional report quality, export gating, publication readiness",
    artifact: "report_eval.json",
    metrics: [
      { id: "report_quality_score", label: "Report quality score", unit: "", comparator: "gte", thresholds: t(85, 85, 90) },
    ],
    blockingConditions: [
      "Report quality score < 85", "Any failed deterministic finance gate",
      "Recommendation visible before approval", "Target price from blocked valuation",
      "Report/valuation snapshot mismatch", "Missing evidence packet or formula trace",
      "PDF rendered from candidate model as final", "Missing final approval for client render",
      "publishable_final_report_model not locked", "Report-quality warning treated as final pass",
      "Post-render client-final audit failed",
    ],
  },
  {
    id: "observability",
    title: "7 · Observability, cost & latency",
    subtitle: "Duration, tokens, cost, retries, fallback, render failures",
    artifact: "observability_eval.json",
    metrics: [
      { id: "llm_retry_rate", label: "LLM retry rate", unit: "%", comparator: "lte", thresholds: t(0.05, 0.05, 0.05) },
      { id: "retrieval_fallback_rate", label: "Retrieval fallback rate", unit: "%", comparator: "lte", thresholds: t(0.2, 0.2, 0.2) },
      { id: "ocr_failure_rate", label: "OCR failure rate (material)", unit: "%", comparator: "lte", thresholds: t(0.05, 0.05, 0.05) },
      { id: "artifact_upload_failures", label: "Artifact upload failures (final)", unit: "", comparator: "lte", thresholds: t(0, 0, 0) },
      { id: "pdf_render_failures", label: "PDF render failures (final)", unit: "", comparator: "lte", thresholds: t(0, 0, 0) },
    ],
  },
  {
    id: "rollout_ci",
    title: "8 · Rollout & CI",
    subtitle: "CI gate matrix and acceptance thresholds by maturity",
    artifact: "—",
  },
];

export const PIPELINE_ORDER: string[] = [
  "Data reliability",
  "Fact reconciliation",
  "Retrieval & source provenance",
  "Financial calculation invariants",
  "Agent & narrative",
  "Report quality",
  "Package validation & auto-exported draft",
  "Human final approval",
  "Client-final render authorization",
];

export interface CiGate { job: string; scope: string; blockMerge: string; }
export const CI_GATE_MATRIX: CiGate[] = [
  { job: "unit-core", scope: "tests/unit/ core deterministic", blockMerge: "Yes" },
  { job: "evaluation-gates", scope: "evaluation/citations/reconciliation + package/publication", blockMerge: "Yes" },
  { job: "finance-regression", scope: "DCF, ratios, debt, dividend, sensitivity, governance invariants", blockMerge: "Yes" },
  { job: "report-render-smoke", scope: "HTML/PDF smoke, post-render audit, authorization-required render", blockMerge: "Yes (if renderer required)" },
  { job: "rag-golden", scope: "Golden retrieval set", blockMerge: "Warn P1 → block P2" },
  { job: "llm-judge-offline", scope: "Calibrated report/agent dataset", blockMerge: "Warn → block after calibration" },
  { job: "integration-db", scope: "Supabase/PostgreSQL live tests", blockMerge: "Scheduled/protected" },
];

export interface MaturityRow { layer: string; P0: string; P1: string; P2: string; }
export const MATURITY_TABLE: MaturityRow[] = [
  { layer: "Data critical failures", P0: "0", P1: "0", P2: "0" },
  { layer: "Finance critical failures", P0: "0", P1: "0", P2: "0" },
  { layer: "Citation coverage (final)", P0: "100%", P1: "100%", P2: "100%" },
  { layer: "Report quality score", P0: "≥ 85", P1: "≥ 85", P2: "≥ 90 (published)" },
  { layer: "RAG hit-rate@5", P0: "Measured", P1: "≥ 90%", P2: "≥ 95%" },
  { layer: "Ragas faithfulness", P0: "Measured", P1: "≥ 0.85", P2: "≥ 0.90" },
  { layer: "Agent role adherence", P0: "Measured", P1: "≥ 0.85", P2: "≥ 0.90" },
  { layer: "Cost per report", P0: "Baseline", P1: "≤ +15%", P2: "Budgeted" },
];
