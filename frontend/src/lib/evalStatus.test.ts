import { describe, it, expect } from "vitest";
import {
  evalMetricStatus,
  formatFailCondition,
  formatMetricNumber,
  formatMetricScope,
  formatPassCondition,
  formatRoundedNumber,
  formatRuntimeMetricResult,
  formatRuntimeThreshold,
  inferRuntimeComparator,
  normalizeMetricStatus,
  metricSemanticType,
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
const coverageMetric: MetricDef = {
  id: "fcff", label: "FCFF formula pass count", unit: "%", comparator: "gte", threshold: 10,
  technology: "Test framework", formula: "fcff formula pass",
  metricType: "coverage",
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
    expect(parseRuntimeThreshold(">= 90/100")).toBe(0.9);
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

  it("preserves fail-closed status for partially observed aggregate metrics", () => {
    expect(resolveMetricStatus(lte, {
      value: 0.378,
      threshold: "<= 10",
      status: "not_evaluable",
      metric_type: "latency_percentile",
      unit: "minutes",
      sample_size: 45,
      calculation: { aggregation: "cohort_mean_observed", numerator: 0.378, denominator: 17 },
    })).toBe("not_evaluable");
  });

  it("classifies boolean-gate runtime metrics as boolean by aggregation", () => {
    const runtimeType = metricSemanticType(coverageMetric, {
      metric_id: "fcff",
      metric_type: "error_count",
      threshold: "pass",
      unit: "count",
      calculation: { aggregation: "boolean_gate", numerator: 1, denominator: 1 },
      value: 1,
    });

    expect(runtimeType).toBe("boolean_gate");
  });

  it("keeps runtime error_count metrics as error_count when threshold is pass", () => {
    const runtimeType = metricSemanticType(coverageMetric, {
      metric_id: "final_ocr_error_count",
      metric_type: "error_count",
      threshold: "pass",
      unit: "count",
      calculation: { aggregation: "error_count", numerator: 0, denominator: 1 },
      value: 0,
    });

    expect(runtimeType).toBe("error_count");
  });

  it("describes observed numeric cohort means by observed sample count", () => {
    expect(formatMetricScope(gte, {
      metric_id: "warm_full_report_p95_latency",
      metric_type: "latency_percentile",
      unit: "minutes",
      value: 9.35,
      sample_size: 45,
      calculation: { aggregation: "cohort_mean_observed", numerator: 9.35, denominator: 17 },
    })).toBe("17/45 samples");
  });

  it("does not render a numerator formula when the ratio disagrees with value", () => {
    expect(formatRuntimeMetricResult(coverageMetric, {
      metric_id: "hit_rate_at_5",
      metric_type: "coverage",
      unit: "percent",
      value: 0.966,
      threshold: ">= 90%",
      calculation: { aggregation: "cohort_pass_rate", numerator: 14, denominator: 14 },
    })).toBe("96.6%");
  });

  it("shows the missing-data reason when a metric is not evaluable", () => {
    expect(formatRuntimeMetricResult(coverageMetric, {
      metric_id: "fcfe",
      metric_type: "coverage",
      unit: "percent",
      value: null,
      status: "not_evaluable",
      detail: "valuation_trace_missing",
      evaluator: { execution_status: "not_executed" },
    })).toBe("Thiếu dữ liệu: valuation_trace_missing");
  });

  it("renders pooled coverage formulas only when numerator and denominator match value", () => {
    expect(metricSemanticType(coverageMetric, {
      metric_id: "hit_rate_at_5",
      metric_type: "coverage",
      unit: "percent",
      value: 13 / 14,
      threshold: ">= 90%",
      calculation: { aggregation: "cohort_pooled_coverage", numerator: 13, denominator: 14 },
    })).toBe("pass_rate");
    expect(formatRuntimeMetricResult(coverageMetric, {
      metric_id: "hit_rate_at_5",
      metric_type: "coverage",
      unit: "percent",
      value: 13 / 14,
      threshold: ">= 90%",
      calculation: { aggregation: "cohort_pooled_coverage", numerator: 13, denominator: 14 },
    })).toBe("13/14 = 92.9%");
    expect(formatMetricScope(coverageMetric, {
      metric_id: "hit_rate_at_5",
      metric_type: "coverage",
      unit: "percent",
      value: 13 / 14,
      threshold: ">= 90%",
      calculation: { aggregation: "cohort_pooled_coverage", numerator: 13, denominator: 14 },
    })).toBe("14 eligible samples");
  });

  it("classifies cohort means as score-like metrics instead of pass rates", () => {
    expect(metricSemanticType(coverageMetric, {
      metric_id: "hit_rate_at_5",
      metric_type: "coverage",
      unit: "percent",
      value: 0.966,
      threshold: ">= 90%",
      calculation: { aggregation: "cohort_mean", numerator: 43.47, denominator: 45 },
    })).toBe("score");
    expect(formatRuntimeMetricResult(coverageMetric, {
      metric_id: "hit_rate_at_5",
      metric_type: "coverage",
      unit: "percent",
      value: 0.966,
      threshold: ">= 90%",
      calculation: { aggregation: "cohort_mean", numerator: 43.47, denominator: 45 },
    })).toBe("96.6%");
  });

  it("formats normalized score metrics as percentages without changing threshold semantics", () => {
    const score: MetricDef = {
      id: "data_reliability_score",
      label: "Data reliability score",
      unit: "%",
      comparator: "gte",
      threshold: 0.9,
      technology: "weighted score",
      formula: "weighted score",
      metricType: "score",
    };

    expect(formatRuntimeMetricResult(score, {
      metric_id: "data_reliability_score",
      metric_type: "score",
      unit: "score",
      value: 0.992,
      threshold: ">= 90/100",
    })).toBe("99.2%");
    expect(formatRuntimeThreshold(score, {
      metric_id: "data_reliability_score",
      metric_type: "score",
      unit: "score",
      threshold: ">= 90/100",
    })).toBe("≥ 90%");
  });

  it("formats rubric scores and exact percentage gates consistently", () => {
    const rubric: MetricDef = {
      id: "report.quality_total",
      label: "Report quality total",
      unit: "",
      comparator: "gte",
      threshold: 85,
      technology: "rubric",
      formula: "rubric score",
      metricType: "score",
    };

    expect(formatRuntimeMetricResult(rubric, {
      metric_id: "report.quality_total",
      metric_type: "score",
      unit: "score",
      value: 85,
      threshold: ">= 85/100",
    })).toBe("85%");
    expect(formatRuntimeThreshold(gte, {
      metric_id: "schema_validity",
      metric_type: "coverage",
      unit: "percent",
      threshold: "= 100%",
      threshold_operator: "=",
    })).toBe("= 100%");
  });

  it("does not convert cost or ratio score metrics into percentages", () => {
    const cost: MetricDef = {
      id: "cost_per_report",
      label: "Cost per report",
      unit: "usd",
      comparator: "lte",
      threshold: 2,
      technology: "cost ledger",
      formula: "usd",
      metricType: "score",
    };

    expect(formatRuntimeMetricResult(cost, {
      metric_id: "cost_per_report",
      metric_type: "score",
      unit: "usd",
      value: 1.25,
      threshold: "<= 2",
    })).toBe("1.25");
    expect(formatRuntimeThreshold(cost, {
      metric_id: "latency_regression_ratio",
      metric_type: "score",
      unit: "ratio",
      threshold: "<= 1.25",
    })).toBe("<= 1.25");
  });
});
