import { describe, it, expect } from "vitest";
import { ACCEPTANCE_EXPLANATION, EVAL_LAYERS, PIPELINE_ORDER } from "./evalFramework";

describe("evalFramework", () => {
  it("contains only benchmarkable evaluation groups", () => {
    expect(EVAL_LAYERS.length).toBe(5);
    expect(EVAL_LAYERS.some((layer) => layer.id === "rollout_ci")).toBe(false);
    expect(EVAL_LAYERS.some((layer) => layer.id === "citation")).toBe(false);
    expect(EVAL_LAYERS.some((layer) => layer.id === "report_quality")).toBe(false);
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
  it("keeps the evaluation pipeline and acceptance explanation", () => {
    expect(PIPELINE_ORDER[0]).toMatch(/Chất lượng dữ liệu/i);
    expect(ACCEPTANCE_EXPLANATION.length).toBeGreaterThan(0);
  });
});
