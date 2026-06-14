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
    expect(mockValuesForLayer("rag_evidence").context_precision).toBeNull();
  });
  it("unknown layer yields empty map", () => {
    expect(mockValuesForLayer("nope")).toEqual({});
  });
});
