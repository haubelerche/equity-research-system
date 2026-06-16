import { describe, it, expect } from "vitest";
import {
  evalMetricStatus,
  formatFailCondition,
  formatMetricNumber,
  formatPassCondition,
  formatRoundedNumber,
  inferRuntimeComparator,
  normalizeMetricStatus,
  parseRuntimeThreshold,
  resolveMetricStatus,
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

  it("rounds dashboard numbers without changing metric scale", () => {
    expect(formatMetricNumber(gte, 0.3333333333333333)).toBe("33.3%");
    expect(formatRoundedNumber(0.3333333333333333)).toBe("0.333");
  });

  it("parses runtime thresholds and comparators emitted as strings", () => {
    expect(parseRuntimeThreshold(">= 95%")).toBe(0.95);
    expect(parseRuntimeThreshold("<= 5%")).toBe(0.05);
    expect(parseRuntimeThreshold(">= 0.70")).toBe(0.7);
    expect(inferRuntimeComparator("<= 5%", undefined, "error_rate", "llm_retry_rate")).toBe("lte");
    expect(inferRuntimeComparator(">= 0.70", undefined, "score", "quality_score")).toBe("gte");
    expect(inferRuntimeComparator("= 0", undefined, "error_count", "artifact_upload_failures")).toBe("lte");
  });

  it("recomputes pass/fail from value and threshold before trusting stale backend status", () => {
    expect(resolveMetricStatus(gte, { value: 0.90, threshold: ">= 95%", status: "pass" })).toBe("fail");
    expect(resolveMetricStatus(gte, { value: 0.96, threshold: ">= 95%", status: "fail" })).toBe("pass");
    expect(resolveMetricStatus(lte, { value: 0.10, threshold: "<= 5%", status: "pass" })).toBe("fail");
    expect(resolveMetricStatus(lte, { value: 0.01, threshold: "<= 5%", status: "fail" })).toBe("pass");
  });

  it("trusts backend status for non-numeric runtime threshold contracts", () => {
    expect(resolveMetricStatus(gte, { value: 0, threshold: "pass", status: "fail" })).toBe("fail");
    expect(resolveMetricStatus(gte, { value: 0, threshold: "present", status: "blocked" })).toBe("blocked");
  });
});
