import { describe, it, expect } from "vitest";
import {
  evalMetricStatus,
  formatFailCondition,
  formatPassCondition,
  normalizeMetricStatus,
  type MetricDef,
} from "./evalStatus";

const gte: MetricDef = {
  id: "coverage", label: "Coverage", unit: "%", comparator: "gte", threshold: 0.95,
  technology: "Test framework", formula: "covered / total",
};
const lte: MetricDef = {
  id: "dupes", label: "Duplicates", unit: "%", comparator: "lte", threshold: 0,
  technology: "Test framework", formula: "duplicates / total",
};

describe("evalMetricStatus", () => {
  it("evaluates threshold comparators", () => {
    expect(evalMetricStatus(gte, 0.96)).toBe("pass");
    expect(evalMetricStatus(gte, 0.90)).toBe("fail");
    expect(evalMetricStatus(lte, 0)).toBe("pass");
    expect(evalMetricStatus(lte, 0.01)).toBe("fail");
  });

  it("treats missing values as not evaluated", () => {
    expect(evalMetricStatus(gte, null)).toBe("not_evaluable");
  });

  it("preserves fail-closed runtime statuses", () => {
    expect(normalizeMetricStatus("blocked")).toBe("blocked");
    expect(normalizeMetricStatus("not_measured")).toBe("not_measured");
    expect(normalizeMetricStatus("not_evaluable")).toBe("not_evaluable");
  });

  it("formats pass and fail conditions explicitly", () => {
    expect(formatPassCondition(gte)).toContain("95%");
    expect(formatFailCondition(gte)).toBe("< 95%");
    expect(formatFailCondition(lte)).toBe("> 0%");
  });
});
