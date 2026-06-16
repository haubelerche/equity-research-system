import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
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
      value: 0.3333333333333333,
      threshold: ">= 95%",
      status: "fail",
      sample_size: 3,
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
        numerator: 1,
        denominator: 3,
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
      value: 1,
      threshold: "= 100%",
      status: "pass",
      unit: "percent",
      evaluator: { framework: "deterministic_finance_gates" },
      calculation: { numerator: 10, denominator: 10, aggregation: "cohort_pass_rate" },
    }, {
      metric_id: "valuation_publishable",
      metric_name: "Valuation publishability policy",
      metric_type: "coverage",
      value: 0,
      threshold: "= 100%",
      status: "fail",
      unit: "percent",
      evaluator: { framework: "valuation_publishability_policy" },
      calculation: { numerator: 0, denominator: 10, aggregation: "cohort_pass_rate" },
    }, {
      metric_id: "new_backend_metric",
      metric_name: "New backend metric",
      metric_type: "score",
      value: 0.73,
      threshold: ">= 0.70",
      status: "fail",
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
      value: 0.10,
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
    expect(await screen.findByText(/B�o c�o dang b? ch?n b?i l?i P0/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/eval/framework", { cache: "no-store" });
    expect(screen.getAllByText("Core metric coverage").length).toBeGreaterThan(0);
    expect(screen.getAllByText("33.3%").length).toBeGreaterThan(0);
    expect(screen.queryByText("1/3 = 33.3%")).not.toBeInTheDocument();
    expect(screen.queryByText("0.3333333333333333")).not.toBeInTheDocument();
    expect(screen.getByText("S? m� d?t c�ng th?c FCFF")).toBeInTheDocument();
    expect(screen.getByText("S? m� d? di?u ki?n publish valuation")).toBeInTheDocument();
    expect(screen.getAllByText("New backend metric").length).toBeGreaterThan(0);
  });

  it("opens publication blocking details from the suite status banner", async () => {
    render(<EvalDashboardPage />);
    await userEvent.click(await screen.findByRole("button", { name: /P0/ }));

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByText(/final export/).length).toBeGreaterThan(1);
    expect(screen.getAllByText("Core metric coverage").length).toBeGreaterThan(0);
    expect(screen.getByText(/Metric P0\/P1/)).toBeInTheDocument();
  });

  it("recomputes dashboard pass/fail from metric thresholds instead of stale backend statuses", async () => {
    render(<EvalDashboardPage />);
    await screen.findByText(/P0/);

    const dynamicMetricRow = screen.getAllByText("New backend metric")[0].closest("tr");
    expect(dynamicMetricRow).not.toBeNull();
    expect(within(dynamicMetricRow!).getByText("�?t")).toBeInTheDocument();

    const retryRow = screen.getByText("T? l? g?i LLM ph?i th? l?i").closest("tr");
    expect(retryRow).not.toBeNull();
    expect(within(retryRow!).getByText("Chua d?t")).toBeInTheDocument();
  });

  it("opens a layer benchmark dialog", async () => {
    render(<EvalDashboardPage />);
    await screen.findByText(/P0/);
    await userEvent.click(screen.getAllByRole("button", { name: "Xem th�m" })[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getAllByText("project-eval-test").length).toBeGreaterThan(0);
  });

  it("opens calculation evidence when a metric row is clicked", async () => {
    render(<EvalDashboardPage />);
    await screen.findByText(/P0/);
    await userEvent.click(screen.getAllByText("Core metric coverage")[0]);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("pandera")).toBeInTheDocument();
    expect(screen.getByText("0.24.0")).toBeInTheDocument();
    expect(screen.getByText(/MVP coverage threshold/)).toBeInTheDocument();
    expect(screen.queryByText("Scope")).not.toBeInTheDocument();
    expect(screen.queryByText("Severity")).not.toBeInTheDocument();
    expect(screen.queryByText("Owner")).not.toBeInTheDocument();
    expect(screen.queryByText("Ch?n xu?t b?n")).not.toBeInTheDocument();
  });

  it("shows runtime calculation details in the layer explanation dialog", async () => {
    render(<EvalDashboardPage />);
    await screen.findByText(/P0/);
    await userEvent.click(screen.getAllByRole("button", { name: "Gi?i th�ch" })[0]);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("L?n ch?y benchmark dang hi?n th?")).toBeInTheDocument();
    expect(screen.getAllByText("data_quality.json").length).toBeGreaterThan(0);
    expect(screen.getAllByText("coverage").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
    expect(screen.getAllByText("33.3%").length).toBeGreaterThan(0);
  });

  it("does not fall back to mock benchmark values when the packet cannot load", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("missing", { status: 404 })));

    render(<EvalDashboardPage />);

    expect(await screen.findByText(/khong hien thi so lieu thay the/i)).toBeInTheDocument();
    expect(screen.getByText(/Chua c� k?t qu? d�nh gi�/)).toBeInTheDocument();
    expect(screen.queryByText("70.0%")).not.toBeInTheDocument();
  });
});
