import { describe, it, expect } from "vitest";
import { mockValuesForLayer } from "./index";

describe("mock values", () => {
  it("returns a numeric map for data_reliability metric ids", () => {
    const v = mockValuesForLayer("data_reliability");
    expect(typeof v.core_metric_coverage).toBe("number");
    expect(typeof v.duplicate_fact_rate).toBe("number");
  });
  it("returns report_quality_score for report_quality", () => {
    expect(typeof mockValuesForLayer("report_quality").report_quality_score).toBe("number");
  });
  it("unknown layer yields empty map", () => {
    expect(mockValuesForLayer("nope")).toEqual({});
  });
});
