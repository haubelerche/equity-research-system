import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EvalDashboardPage } from "./EvalDashboardPage";

const packet = {
  run_id: "project-eval-test",
  ticker: "DHG",
  benchmark_suite_version: "benchmark_standards_v1",
  publication_status: "BLOCKED_BY_P0",
  artifacts: [{
    plan_id: "01",
    name: "Data reliability",
    artifact: "data_quality.json",
    status: "fail",
    metric_results: [{
      metric_id: "core_metric_coverage",
      metric_name: "Core metric coverage",
      metric_type: "coverage",
      scope: "report_run",
      severity: "P0",
      blocks_publish: true,
      value: 0.5,
      threshold: ">= 95%",
      status: "fail",
      sample_size: 10,
      owner: "data",
      source: "fixture",
      failed_examples: [{ reason: "missing_source" }],
      remediation_hint: "Repair source provenance.",
      evaluator: {
        framework: "pandera",
        framework_version: "0.24.0",
        execution_status: "executed",
      },
      calculation: {
        formula: "valid / required",
        numerator: 5,
        denominator: 10,
        aggregation: "coverage",
        per_sample_results: [{ id: "revenue", passed: false }],
      },
      threshold_policy: {
        profile: "mvp",
        rationale: "MVP coverage threshold.",
      },
    }],
  }, {
    plan_id: "03",
    name: "Financial calculation",
    artifact: "financial_eval.json",
    status: "fail",
    metric_results: [{
      metric_id: "fcff",
      metric_name: "FCFF formula",
      metric_type: "coverage",
      value: 10,
      threshold: "pass",
      status: "pass",
      unit: "count",
      evaluator: { framework: "deterministic_finance_gates" },
    }, {
      metric_id: "valuation_publishable",
      metric_name: "Valuation publishability policy",
      metric_type: "coverage",
      value: 0,
      threshold: "pass",
      status: "fail",
      unit: "count",
      evaluator: { framework: "valuation_publishability_policy" },
    }, {
      metric_id: "new_backend_metric",
      metric_name: "New backend metric",
      metric_type: "score",
      value: 0.73,
      threshold: ">= 0.70",
      status: "pass",
      evaluator: { framework: "future_evaluator" },
    }],
  }, {
    plan_id: "07",
    name: "Observability, cost, and latency",
    artifact: "observability_eval.json",
    status: "pass",
    metric_results: [{
      metric_id: "llm_retry_rate",
      metric_name: "LLM retry rate",
      value: 0,
      threshold: "<= 5%",
      status: "pass",
    }, {
      metric_id: "artifact_upload_failures",
      metric_name: "Artifact upload failures",
      value: 0,
      threshold: "= 0",
      status: "pass",
    }],
  }],
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(packet), {
    status: 200,
    headers: { "content-type": "application/json" },
  })));
});

describe("EvalDashboardPage", () => {
  it("renders the live benchmark packet with publication status", async () => {
    render(<EvalDashboardPage />);
    expect(await screen.findByText(/BLOCKED_BY_P0/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/eval/framework", { cache: "no-store" });
    expect(screen.getAllByText("Core metric coverage").length).toBeGreaterThan(0);
    expect(screen.getAllByText("50.0%").length).toBeGreaterThan(0);
    expect(screen.getByText("Số mã đạt công thức FCFF")).toBeInTheDocument();
    expect(screen.getByText("Số mã đủ điều kiện publish valuation")).toBeInTheDocument();
    expect(screen.getAllByText("New backend metric").length).toBeGreaterThan(0);
  });

  it("opens a layer benchmark dialog", async () => {
    render(<EvalDashboardPage />);
    await screen.findByText(/BLOCKED_BY_P0/);
    await userEvent.click(screen.getAllByRole("button")[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByText("project-eval-test").length).toBeGreaterThan(0);
  });

  it("opens calculation evidence when a metric row is clicked", async () => {
    render(<EvalDashboardPage />);
    await screen.findByText(/BLOCKED_BY_P0/);
    await userEvent.click(screen.getAllByText("Core metric coverage")[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("pandera")).toBeInTheDocument();
    expect(screen.getByText("0.24.0")).toBeInTheDocument();
    expect(screen.getByText(/MVP coverage threshold/)).toBeInTheDocument();
    expect(screen.queryByText("Scope")).not.toBeInTheDocument();
    expect(screen.queryByText("Severity")).not.toBeInTheDocument();
    expect(screen.queryByText("Owner")).not.toBeInTheDocument();
    expect(screen.queryByText("Chặn xuất bản")).not.toBeInTheDocument();
  });
});
