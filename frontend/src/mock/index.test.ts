import { describe, it, expect } from "vitest";
import { mockValuesForLayer } from "./index";

describe("mock values", () => {
  it("returns a numeric map for data_reliability metric ids", () => {
    const v = mockValuesForLayer("data_reliability");
    expect(typeof v.core_metric_coverage).toBe("number");
    expect(typeof v.duplicate_fact_rate).toBe("number");
  });
  it("preserves missing runtime evidence as null", () => {
    expect(mockValuesForLayer("report_quality").report_quality_score).toBeNull();
  });
  it("exposes the live (pure-live) RAG/RAGAS values", () => {
    // Benchmark 02 is now pure-live (real pgvector + real ragas), so these are
    // measured numbers, not null.
    expect(typeof mockValuesForLayer("rag_evidence").hit_rate_at_5).toBe("number");
    expect(typeof mockValuesForLayer("rag_evidence").context_precision).toBe("number");
  });
  it("unknown layer yields empty map", () => {
    expect(mockValuesForLayer("nope")).toEqual({});
  });
});
