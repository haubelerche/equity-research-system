import { describe, it, expect } from "vitest";
import { ACCEPTANCE_EXPLANATION, EVAL_LAYERS, LAYER_VISIBLE_METRIC_IDS, PIPELINE_ORDER } from "./evalFramework";

describe("evalFramework", () => {
  it("contains the benchmark evaluation groups exposed by the dashboard", () => {
    expect(EVAL_LAYERS.length).toBe(6);
    expect(EVAL_LAYERS.some((layer) => layer.id === "rollout_ci")).toBe(false);
    expect(EVAL_LAYERS.some((layer) => layer.id === "citation")).toBe(false);
    expect(EVAL_LAYERS.some((layer) => layer.id === "report_quality")).toBe(true);
    expect(EVAL_LAYERS.some((layer) => layer.id === "publication_readiness")).toBe(false);
    expect(EVAL_LAYERS.find((layer) => layer.id === "report_quality")?.title)
      .toBe("5 · Chất lượng báo cáo");
    expect(EVAL_LAYERS.find((layer) => layer.id === "report_quality")?.artifactAliases)
      .toContain("report_quality_eval.json");
  });

  it("keeps visible layer numbering contiguous after removed dashboard groups", () => {
    expect(EVAL_LAYERS.map((layer) => layer.title.split(" ")[0])).toEqual(["1", "2", "3", "4", "5", "6"]);
    expect(EVAL_LAYERS.map((layer) => layer.id)).toEqual([
      "data_reliability",
      "rag_evidence",
      "financial",
      "agent",
      "report_quality",
      "observability",
    ]);
    expect(PIPELINE_ORDER).toEqual([
      "Chất lượng dữ liệu",
      "RAG",
      "Mô hình tài chính",
      "Agent và LLM Judge",
      "Chất lượng báo cáo",
      "Vận hành",
    ]);
  });

  it("defines one threshold, technology and formula for every metric", () => {
    for (const layer of EVAL_LAYERS) {
      expect(layer.metrics.length).toBeGreaterThan(0);
      expect(layer.artifact).toBeDefined();
      for (const metric of layer.metrics) {
        expect(typeof metric.threshold).toBe("number");
        expect(metric.technology.length).toBeGreaterThan(0);
        expect(metric.formula.length).toBeGreaterThan(0);
      }
    }
  });

  it("matches the executable evaluator threshold for RAG hit-rate", () => {
    const rag = EVAL_LAYERS.find((layer) => layer.id === "rag_evidence")!;
    expect(rag.metrics.find((metric) => metric.id === "hit_rate_at_5")!.threshold).toBe(0.9);
  });

  it("keeps the RAG dashboard contract aligned with core RAGAS and retrieval evaluators", () => {
    const rag = EVAL_LAYERS.find((layer) => layer.id === "rag_evidence")!;
    const metricIds = rag.metrics.map((metric) => metric.id);

    expect(metricIds).toEqual(expect.arrayContaining([
      "hit_rate_at_5",
      "mrr_at_5",
      "source_tier_hit_rate",
      "context_precision",
      "context_recall",
      "faithfulness",
      "response_relevancy",
    ]));
    expect(metricIds).not.toEqual(expect.arrayContaining([
      "ndcg_at_10",
      "metadata_filter_accuracy",
      "unanswerable_abstention_accuracy",
      "evidence_span_overlap",
      "retrieval_noise_rate",
    ]));
    expect(rag.metrics.find((metric) => metric.id === "context_recall")!.threshold).toBe(0.8);
    expect(rag.metrics.find((metric) => metric.id === "response_relevancy")!.threshold).toBe(0.75);
  });

  it("does not expose judge calibration diagnostics in the Agent dashboard group", () => {
    const agent = EVAL_LAYERS.find((layer) => layer.id === "agent")!;
    const metricIds = agent.metrics.map((metric) => metric.id);

    expect(metricIds).not.toContain("judge_calibration_agreement");
    expect(metricIds).not.toContain("judge_rationale_evidence_coverage");
  });

  it("exposes the curated dashboard visibility allowlist for every layer", () => {
    expect(Object.keys(LAYER_VISIBLE_METRIC_IDS)).toEqual([
      "data_reliability",
      "rag_evidence",
      "financial",
      "agent",
      "report_quality",
      "observability",
    ]);
    expect(LAYER_VISIBLE_METRIC_IDS.data_reliability).toEqual([
      "data_reliability_score",
      "core_metric_coverage",
      "material_ocr_error_count",
      "duplicate_fact_count",
      "dataframe_schema_validity",
      "raw_bctc_non_empty",
    ]);
    expect(LAYER_VISIBLE_METRIC_IDS.rag_evidence).toEqual([
      "rag.retrieval_difficulty_score",
      "hit_rate_at_5",
      "mrr_at_5",
      "context_precision",
      "context_recall",
      "faithfulness",
      "response_relevancy",
      "source_tier_hit_rate",
    ]);
    expect(LAYER_VISIBLE_METRIC_IDS.financial).toEqual([
      "finance.model_quality_score",
      "accounting_invariant_violations",
      "fcff",
      "target_price",
      "gordon_growth",
      "net_debt",
      "formula_trace",
    ]);
    expect(LAYER_VISIBLE_METRIC_IDS.agent).toEqual([
      "agent.workflow_quality_score",
      "tool_permission_compliance",
      "schema_validity",
      "no_unauthorized_calc",
      "stage_handoff_completeness",
      "tool_call_success_rate",
      "repair_loop_rate",
      "token_budget_adherence",
    ]);
    expect(LAYER_VISIBLE_METRIC_IDS.report_quality).toEqual([
      "report.quality_total",
      "report.completeness",
      "report.valuation_transparency",
    ]);
    expect(LAYER_VISIBLE_METRIC_IDS.observability).toEqual([
      "llm_retry_rate",
      "retrieval_fallback_rate",
      "final_ocr_error_count",
      "artifact_upload_failures",
      "pdf_render_failures",
      "warm_full_report_p95_latency",
      "cost_per_report",
      "full_run_duration",
    ]);
  });

  it("keeps every visible non-dynamic metric backed by a static definition", () => {
    const dynamicOnly = new Set([
      "dataframe_schema_validity",
      "raw_bctc_non_empty",
      "full_run_duration",
    ]);
    for (const layer of EVAL_LAYERS) {
      const staticIds = new Set(layer.metrics.map((metric) => metric.id));
      for (const id of LAYER_VISIBLE_METRIC_IDS[layer.id] ?? []) {
        if (dynamicOnly.has(id)) continue;
        expect(staticIds.has(id)).toBe(true);
      }
    }
  });

  it("keeps the evaluation pipeline and acceptance explanation in Vietnamese", () => {
    expect(PIPELINE_ORDER[0]).toMatch(/Chất lượng dữ liệu/i);
    expect(ACCEPTANCE_EXPLANATION.length).toBeGreaterThan(0);
    expect(ACCEPTANCE_EXPLANATION.join(" ")).toContain("Thiếu dữ liệu benchmark");
  });
});
