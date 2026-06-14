import { describe, it, expect } from "vitest";
import { mockValuesForLayer } from "./index";

describe("mock values", () => {
  it("returns a numeric map for data_reliability metric ids", () => {
    const v = mockValuesForLayer("data_reliability");
    expect(typeof v.core_metric_coverage).toBe("number");
    expect(typeof v.duplicate_fact_rate).toBe("number");
  });
  it("returns fpts_score for report_fpts", () => {
    expect(typeof mockValuesForLayer("report_fpts").fpts_score).toBe("number");
  });
  it("unknown layer yields empty map", () => {
    expect(mockValuesForLayer("nope")).toEqual({});
  });
});
