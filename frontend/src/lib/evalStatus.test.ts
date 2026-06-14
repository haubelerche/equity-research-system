import { describe, it, expect } from "vitest";
import { evalMetricStatus, type MetricDef } from "./evalStatus";

const gte: MetricDef = {
  id: "coverage", label: "Coverage", unit: "%", comparator: "gte",
  thresholds: { P0: 0.95, P1: 0.95, P2: 0.95 },
};
const lte: MetricDef = {
  id: "dupes", label: "Duplicates", unit: "%", comparator: "lte",
  thresholds: { P0: 0, P1: 0, P2: 0 },
};
const measuredAtP0: MetricDef = {
  id: "hit", label: "Hit-rate@5", unit: "", comparator: "gte",
  thresholds: { P0: null, P1: 0.9, P2: 0.95 },
};

describe("evalMetricStatus", () => {
  it("gte pass/fail", () => {
    expect(evalMetricStatus(gte, 0.96, "P0")).toBe("pass");
    expect(evalMetricStatus(gte, 0.90, "P0")).toBe("fail");
  });
  it("lte pass/fail", () => {
    expect(evalMetricStatus(lte, 0, "P0")).toBe("pass");
    expect(evalMetricStatus(lte, 0.01, "P0")).toBe("fail");
  });
  it("null threshold at maturity is measured_only", () => {
    expect(evalMetricStatus(measuredAtP0, 0.5, "P0")).toBe("measured_only");
    expect(evalMetricStatus(measuredAtP0, 0.95, "P1")).toBe("pass");
    expect(evalMetricStatus(measuredAtP0, 0.5, "P1")).toBe("fail");
  });
  it("missing value is measured_only", () => {
    expect(evalMetricStatus(gte, null, "P0")).toBe("measured_only");
  });
});
