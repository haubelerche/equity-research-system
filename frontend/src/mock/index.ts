import dataQuality from "./data_quality.json";
import retrieval from "./retrieval_eval.json";
import financial from "./financial_eval.json";
import citation from "./citation_eval.json";
import agent from "./agent_eval.json";
import report from "./report_eval.json";
import publication from "./publication_readiness.json";
import observability from "./observability_eval.json";

export const MOCK_ARTIFACTS = {
  data_quality: dataQuality,
  retrieval_eval: retrieval,
  financial_eval: financial,
  citation_eval: citation,
  agent_eval: agent,
  report_eval: report,
  publication_readiness: publication,
  observability_eval: observability,
};

// Flatten the latest evaluation snapshot to metric-id -> nullable value.
// Null means the evaluator could not prove the metric from runtime evidence.
const LAYER_VALUE_MAP: Record<string, Record<string, number | null>> = {
  data_reliability: {
    data_reliability_score: (dataQuality as unknown as Record<string, number | undefined>).data_reliability_score ?? null,
    core_metric_coverage: dataQuality.core_metric_coverage,
    valuation_method_data_readiness: dataQuality.valuation_method_data_readiness ?? null,
    period_completeness: dataQuality.period_completeness,
    provenance_coverage: dataQuality.provenance_coverage,
    official_reconciliation_rate: dataQuality.official_reconciliation_rate,
    ocr_unresolved_rate: dataQuality.ocr_unresolved_rate,
    duplicate_fact_rate: dataQuality.duplicate_fact_rate,
  },
  rag_evidence: {
    hit_rate_at_5: retrieval.golden_scores.hit_rate_at_5,
    mrr_at_5: retrieval.golden_scores.mrr_at_5,
    context_precision: retrieval.ragas_scores.context_precision,
    context_recall: retrieval.ragas_scores.context_recall,
    faithfulness: retrieval.ragas_scores.faithfulness,
    response_relevancy: retrieval.ragas_scores.response_relevancy,
  },
  financial: {
    critical_failures: financial.critical_failures,
    golden_drift_out_of_tolerance: financial.golden_drift_out_of_tolerance,
  },
  citation: {
    quant_citation_coverage: citation.quant_citation_coverage,
    citation_key_resolution: citation.citation_key_resolution,
    source_id_validity: citation.source_id_validity,
    official_source_coverage: citation.official_source_coverage,
    numeric_mismatch_rate: citation.numeric_mismatch_rate,
    tier3_only_material_claims: citation.tier3_only_material_claims,
    generic_citations: citation.generic_citations,
    catalyst_without_evidence: citation.catalyst_without_evidence,
  },
  agent: {
    tool_permission_compliance: agent.tool_permission_compliance,
    schema_validity: agent.schema_validity,
    no_unauthorized_calc: agent.no_unauthorized_calc,
    role_adherence: agent.role_adherence,
    groundedness: agent.groundedness,
    task_completion: agent.task_completion,
    plan_adherence: agent.plan_adherence,
    critic_issue_recall: agent.critic_issue_recall,
  },
  report_quality: { report_quality_score: report.report_quality_score },
  observability: {
    llm_retry_rate: observability.llm.retry_rate,
    retrieval_fallback_rate: observability.retrieval.fallback_rate,
    ocr_failure_rate: observability.ocr_failure_rate,
    artifact_upload_failures: observability.artifact_upload_failures,
    pdf_render_failures: observability.pdf_render_failures,
  },
};

export function mockValuesForLayer(layerId: string): Record<string, number | null> {
  return LAYER_VALUE_MAP[layerId] ?? {};
}

export function mockRunIdForLayer(layerId: string): string {
  const runIds: Record<string, string> = {
    data_reliability: dataQuality.run_id,
    rag_evidence: retrieval.run_id,
    financial: financial.run_id,
    citation: citation.run_id,
    agent: agent.run_id,
    report_quality: report.run_id,
    observability: observability.run_id,
  };
  return runIds[layerId] ?? "unknown";
}
