import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EvalDashboardPage } from "./EvalDashboardPage";

const packet = {
  run_id: "project-eval-test",
  ticker: "DHG",
  benchmark_suite_version: "benchmark_standards_v1",
  publication_status: "BLOCKED_BY_P0",
  artifacts: [
    {
      plan_id: "01",
      name: "Data reliability",
      artifact: "data_quality.json",
      status: "fail",
      blocking_issues: ["missing_runtime_evidence:data_quality.json"],
      metric_results: [
        {
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
        },
      ],
    },
  ],
};

beforeEach(() => {
  vi.restoreAllMocks();
  vi.stubGlobal(
    "fetch",
    vi.fn(async () =>
      new Response(JSON.stringify(packet), {
        status: 200,
        headers: { "content-type": "application/json" },
      }),
    ),
  );
});

describe("EvalDashboardPage", () => {
  it("renders the live benchmark packet with publication status and blockers", async () => {
    render(<EvalDashboardPage />);
    expect(await screen.findByText(/Trạng thái xuất bản: BLOCKED_BY_P0/)).toBeInTheDocument();
    expect(screen.getByText(/project-eval-test/)).toBeInTheDocument();
    expect(screen.getByText(/Data reliability: missing_runtime_evidence:data_quality.json/)).toBeInTheDocument();
    expect(screen.queryByText("Benchmark Metric Contract")).not.toBeInTheDocument();
    expect(screen.getAllByText("Core metric coverage").length).toBeGreaterThan(0);
  });

  it("opens benchmark history and explanation dialogs", async () => {
    render(<EvalDashboardPage />);
    await screen.findByText(/Trạng thái xuất bản:/);

    await userEvent.click(screen.getAllByRole("button", { name: /Xem/ })[0]);
    expect(screen.getByRole("dialog", { name: /Lịch sử benchmark/i })).toBeInTheDocument();
    expect(screen.getAllByText("project-eval-test").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: /ng/ }));

    await userEvent.click(screen.getAllByRole("button", { name: /Gi/ })[0]);
    expect(screen.getByRole("dialog", { name: /Giải thích:/i })).toBeInTheDocument();
    expect(screen.getByText(/Công thức hoặc phương pháp/i)).toBeInTheDocument();
  });
});
