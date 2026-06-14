import { describe, it, expect } from "vitest";
import { EVAL_LAYERS, PIPELINE_ORDER, CI_GATE_MATRIX, MATURITY_TABLE } from "./evalFramework";

describe("evalFramework", () => {
  it("has 8 layers in fail-closed order", () => {
    expect(EVAL_LAYERS.length).toBe(8);
    expect(EVAL_LAYERS[0].id).toBe("data_reliability");
    expect(EVAL_LAYERS[5].id).toBe("report_quality");
  });
  it("each layer references its artifact and has metrics or rows", () => {
    for (const l of EVAL_LAYERS) {
      expect(l.title.length).toBeGreaterThan(0);
      expect(l.artifact).toBeDefined();
    }
  });
  it("RAG hit-rate is measured_only at P0", () => {
    const rag = EVAL_LAYERS.find((l) => l.id === "rag_evidence")!;
    const hit = rag.metrics!.find((m) => m.id === "hit_rate_at_5")!;
    expect(hit.thresholds.P0).toBeNull();
    expect(hit.thresholds.P1).toBe(0.9);
  });
  it("pipeline order starts at data and ends at client-final authorization", () => {
    expect(PIPELINE_ORDER[0]).toMatch(/Data reliability/i);
    expect(PIPELINE_ORDER[PIPELINE_ORDER.length - 1]).toMatch(/Client-final/i);
  });
  it("CI matrix and maturity table are non-empty", () => {
    expect(CI_GATE_MATRIX.length).toBeGreaterThan(0);
    expect(MATURITY_TABLE.length).toBeGreaterThan(0);
  });
});
