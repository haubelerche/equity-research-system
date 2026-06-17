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
    }, {
      metric_id: "valuation_method_data_readiness",
      metric_name: "Valuation method data readiness",
      metric_type: "coverage",
      value: 0.023,
      threshold: ">= 80%",
      status: "fail",
    }, {
      metric_id: "official_reconciliation_rate",
      metric_name: "Material official reconciliation rate",
      metric_type: "coverage",
      value: 0.023,
      threshold: ">= 95%",
      status: "fail",
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
    expect(await screen.findByText(/Báo cáo đang bị chặn bởi lỗi P0/)).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/eval/framework", { cache: "no-store" });
    expect(screen.getAllByText("Core metric coverage").length).toBeGreaterThan(0);
    expect(screen.getAllByText("33.3%").length).toBeGreaterThan(0);
    expect(screen.queryByText("1/3 = 33.3%")).not.toBeInTheDocument();
    expect(screen.queryByText("0.3333333333333333")).not.toBeInTheDocument();
    expect(screen.queryByText("Valuation method data readiness")).not.toBeInTheDocument();
    expect(screen.queryByText("Material official reconciliation rate")).not.toBeInTheDocument();
    expect(screen.getByText("Số mã đạt công thức FCFF")).toBeInTheDocument();
    // valuation_publishable is no longer a benchmark-03 framework row (moved to the
    // governance/publishability gate); when present it renders as a dynamic backend
    // metric under its backend metric_name rather than the old framework label.
    expect(screen.getAllByText("Valuation publishability policy").length).toBeGreaterThan(0);
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
    expect(within(dynamicMetricRow!).getByText("Đạt")).toBeInTheDocument();

    const retryRow = screen.getByText("Tỷ lệ gọi LLM phải thử lại").closest("tr");
    expect(retryRow).not.toBeNull();
    expect(within(retryRow!).getByText("Chưa đạt")).toBeInTheDocument();
  });

  it("opens a layer benchmark dialog", async () => {
    render(<EvalDashboardPage />);
    await screen.findByText(/P0/);
    await userEvent.click(screen.getAllByRole("button", { name: "Xem thêm" })[0]);
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
    expect(screen.queryByText("Chặn xuất bản")).not.toBeInTheDocument();
  });

  it("shows runtime calculation details in the layer explanation dialog", async () => {
    render(<EvalDashboardPage />);
    await screen.findByText(/P0/);
    await userEvent.click(screen.getAllByRole("button", { name: "Giải thích" })[0]);

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("Lần chạy benchmark đang hiển thị")).toBeInTheDocument();
    expect(screen.getAllByText("data_quality.json").length).toBeGreaterThan(0);
    expect(screen.getAllByText("coverage").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1").length).toBeGreaterThan(0);
    expect(screen.getAllByText("3").length).toBeGreaterThan(0);
    expect(screen.getAllByText("33.3%").length).toBeGreaterThan(0);
  });

  it("does not fall back to mock benchmark values when the packet cannot load", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("missing", { status: 404 })));

    render(<EvalDashboardPage />);

    expect(await screen.findByText(/không hiển thị số liệu thay thế/i)).toBeInTheDocument();
    expect(screen.getByText(/Chưa có kết quả đánh giá/)).toBeInTheDocument();
    expect(screen.queryByText("70.0%")).not.toBeInTheDocument();
  });
});
