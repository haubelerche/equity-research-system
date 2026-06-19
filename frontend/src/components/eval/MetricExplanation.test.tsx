import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MetricExplanation } from "./MetricExplanation";
import type { BenchmarkMetricResult } from "../../api/types";
import type { MetricDef } from "../../lib/evalStatus";

const def: MetricDef = {
  id: "report.valuation_transparency",
  label: "Tính minh bạch định giá",
  englishLabel: "Valuation transparency",
  unit: "",
  comparator: "gte",
  threshold: 85,
  thresholdLabel: ">= 85/100",
  technology: "Report Quality Rubric",
  formula: "Điểm rubric cho method selection, assumptions, WACC, bridge và sensitivity",
  metricType: "score",
  scope: "benchmark_suite",
  severity: "P1",
  blocksPublish: true,
};

const result: BenchmarkMetricResult = {
  metric_id: "report.valuation_transparency",
  metric_name: "Valuation transparency",
  metric_type: "score",
  value: 100,
  threshold: ">= 85/100",
  threshold_operator: ">=",
  status: "pass",
  sample_size: 45,
  calculation: {
    aggregation: "cohort_mean_observed",
    numerator: 4500,
    denominator: 45,
    per_sample_results: [],
  },
  threshold_policy: {
    profile: "mvp",
    rationale: "Ngưỡng bảo vệ luận văn yêu cầu điểm minh bạch định giá tối thiểu 85/100.",
  },
};

const passRateDef: MetricDef = {
  id: "fcff",
  label: "Công thức FCFF",
  englishLabel: "FCFF formula",
  unit: "%",
  comparator: "gte",
  threshold: 0.85,
  thresholdLabel: ">= 85/100",
  technology: "Financial Deterministic Gates",
  formula: "pass_rate = count(pass) / count(eligible)",
  metricType: "coverage",
  scope: "benchmark_suite",
  severity: "P0",
  blocksPublish: true,
};

const cappedPassRateResult: BenchmarkMetricResult = {
  metric_id: "fcff",
  metric_name: "FCFF formula",
  metric_type: "coverage",
  unit: "percent",
  value: 0.94,
  threshold: ">= 85/100",
  threshold_operator: ">=",
  status: "pass",
  sample_size: 45,
  calculation: {
    aggregation: "cohort_pass_rate",
    numerator: 45,
    denominator: 45,
    per_sample_results: [],
  },
  threshold_policy: {
    profile: "mvp",
    rationale: "Dashboard presentation threshold for thesis defense.",
  },
};

describe("MetricExplanation", () => {
  it("shows the theoretical formula and concrete substitution for cohort mean metrics", () => {
    render(<MetricExplanation def={def} result={result} />);

    expect(screen.getByText("Công thức lý thuyết")).toBeInTheDocument();
    expect(screen.getByText(/mean_score = sum\(score_i\) \/ n/)).toBeInTheDocument();
    expect(screen.getByText(/4,500 \/ 45 = 100/)).toBeInTheDocument();
    expect(screen.getByText(/Metric đạt khi giá trị quan sát tối thiểu ≥ 85%/)).toBeInTheDocument();
    expect(screen.getByText(/Metric này cho biết chất lượng trung bình của toàn bộ tập đánh giá/)).toBeInTheDocument();
  });

  it("uses numerator and denominator for raw pass-rate substitutions when dashboard value is capped", () => {
    render(<MetricExplanation def={passRateDef} result={cappedPassRateResult} />);

    expect(screen.getByText(/Tỷ lệ đạt = 45 \/ 45 = 100%; giá trị dashboard = 94%\./)).toBeInTheDocument();
  });
});
