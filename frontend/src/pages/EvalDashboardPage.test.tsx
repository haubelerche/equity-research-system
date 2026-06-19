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
        per_sample_results: [{
          artifact_id: "DHG/data_quality.json",
          source_metric_id: "core_metric_coverage",
          status: "fail",
          value: 0.3333333333333333,
          sample_size: 2,
          failed_examples: [{ reason: "missing_source" }],
          evidence: {
            artifact_ids: ["storage/runs/DHG/evidence_packet.json"],
            trace_url: "storage/runs/DHG/trace.json",
          },
          source_samples: [{
            id: "revenue",
            passed: false,
            value: false,
            reason: "missing_source",
          }, {
            id: "gross_margin",
            passed: true,
            value: true,
          }, {
            sample_origin: "data_reliability_score_component",
            component: "provenance_coverage",
            component_score: 1,
            weight: 0.15,
          }, {
            tool_name: "READ_SNAPSHOT",
            permission: {
              tool_id: "read_snapshot",
              agent_id: "financial_analysis",
              permission_level: "read_only",
            },
          }, {
            source_metric_id: "report.valuation_transparency",
            scores: {
              valuation_transparency: 70,
            },
          }],
        }],
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
    plan_id: "02",
    name: "RAG retrieval",
    artifact: "retrieval_eval.json",
    status: "pass",
    metric_results: [{
      metric_id: "hit_rate_at_5",
      metric_name: "Hit-rate@5",
      metric_type: "coverage",
      unit: "percent",
      value: 0.95,
      threshold: ">= 90%",
      status: "pass",
      sample_size: 20,
      evaluator: { framework: "golden_retrieval_set", execution_status: "executed" },
      calculation: { aggregation: "coverage", per_sample_results: [{ status: "pass", value: true }] },
    }, {
      metric_id: "mrr_at_5",
      metric_name: "MRR@5",
      metric_type: "score",
      unit: "percent",
      value: 0.82,
      threshold: ">= 75%",
      status: "pass",
      sample_size: 20,
      evaluator: { framework: "golden_retrieval_set", execution_status: "executed" },
      calculation: { aggregation: "mean", per_sample_results: [{ status: "pass", value: 1 }] },
    }, {
      metric_id: "source_tier_hit_rate",
      metric_name: "Source-tier hit rate",
      metric_type: "coverage",
      unit: "percent",
      value: 0.92,
      threshold: ">= 90%",
      status: "pass",
      sample_size: 20,
      evaluator: { framework: "source_tier_retrieval_audit", execution_status: "executed" },
      calculation: { aggregation: "coverage", per_sample_results: [{ status: "pass", value: true }] },
    }, {
      metric_id: "context_precision",
      metric_name: "Context Precision",
      metric_type: "score",
      unit: "percent",
      value: 0.84,
      threshold: ">= 80%",
      status: "pass",
      sample_size: 20,
      evaluator: { framework: "ragas", execution_status: "executed" },
      calculation: { aggregation: "mean", per_sample_results: [{ status: "pass", value: 0.84 }] },
    }, {
      metric_id: "context_recall",
      metric_name: "Context Recall",
      metric_type: "score",
      unit: "percent",
      value: 0.82,
      threshold: ">= 80%",
      status: "pass",
      sample_size: 20,
      evaluator: { framework: "ragas", execution_status: "executed" },
      calculation: { aggregation: "mean", per_sample_results: [{ status: "pass", value: 0.82 }] },
    }, {
      metric_id: "faithfulness",
      metric_name: "Faithfulness",
      metric_type: "score",
      unit: "percent",
      value: 0.9,
      threshold: ">= 85%",
      status: "pass",
      sample_size: 20,
      evaluator: { framework: "ragas", execution_status: "executed" },
      calculation: { aggregation: "mean", per_sample_results: [{ status: "pass", value: 0.9 }] },
    }, {
      metric_id: "response_relevancy",
      metric_name: "Response Relevancy",
      metric_type: "score",
      unit: "percent",
      value: 0.8,
      threshold: ">= 75%",
      status: "pass",
      sample_size: 20,
      evaluator: { framework: "ragas", execution_status: "executed" },
      calculation: { aggregation: "mean", per_sample_results: [{ status: "pass", value: 0.8 }] },
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
      metric_id: "fcfe",
      metric_name: "FCFE formula",
      metric_type: "coverage",
      value: null,
      threshold: "= 100%",
      status: "not_evaluable",
      unit: "percent",
      evaluator: { framework: "deterministic_finance_gates", execution_status: "not_executed" },
      calculation: { numerator: 0, denominator: 0, aggregation: "cohort_pass_rate" },
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
    plan_id: "05",
    name: "Agent and judge",
    artifact: "agent_eval.json",
    status: "pass",
    metric_results: [{
      metric_id: "schema_validity",
      metric_name: "Output schema validity",
      metric_type: "coverage",
      unit: "percent",
      value: 1,
      threshold: "100%",
      status: "pass",
      sample_size: 2,
      evaluator: { framework: "json_schema_required_contract", execution_status: "executed" },
      calculation: {
        numerator: 2,
        denominator: 2,
        aggregation: "coverage",
        per_sample_results: [{
          artifact_id: "DHG/agent_eval.json",
          source_metric_id: "schema_validity",
          status: "pass",
          value: 1,
          source_samples: [{
            artifact: "evidence_packet",
            status: "pass",
            path: "storage/runs/DHG/evidence_packet.json",
          }, {
            artifact: "agent_effectiveness_audit",
            status: "fail",
            path: "storage/runs/DHG/agent_effectiveness_audit.json",
          }],
        }],
      },
    }, {
      metric_id: "agent.judge_calibration_agreement",
      metric_name: "Judge calibration agreement",
      metric_type: "score",
      value: null,
      threshold: ">= 85%",
      status: "not_evaluable",
    }, {
      metric_id: "agent.judge_rationale_evidence_coverage",
      metric_name: "Judge rationale evidence coverage",
      metric_type: "coverage",
      value: null,
      threshold: ">= 90%",
      status: "not_evaluable",
    }],
  }, {
    plan_id: "06",
    name: "Report quality",
    artifact: "report_eval.json",
    status: "pass",
    metric_results: [{
      metric_id: "report.quality_total",
      metric_name: "Report quality total",
      metric_type: "score",
      value: 88,
      threshold: ">= 85/100",
      status: "pass",
    }, {
      metric_id: "report.completeness",
      metric_name: "Report completeness",
      metric_type: "coverage",
      unit: "percent",
      value: 0.93,
      threshold: ">= 90%",
      status: "pass",
    }, {
      metric_id: "report.valuation_transparency",
      metric_name: "Valuation transparency",
      metric_type: "score",
      value: 91,
      threshold: ">= 85/100",
      status: "pass",
    }, {
      metric_id: "report.thesis_specificity",
      metric_name: "Legacy thesis specificity",
      metric_type: "score",
      value: 94,
      threshold: ">= 85/100",
      status: "pass",
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
    expect(screen.getAllByText("MRR@5").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Context Precision").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Context Recall").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Faithfulness").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Response Relevancy").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Source-tier hit rate").length).toBeGreaterThan(0);
    expect(screen.queryByText("nDCG@10")).not.toBeInTheDocument();
    expect(screen.queryByText("Metadata filter accuracy")).not.toBeInTheDocument();
    expect(screen.queryByText("Unanswerable abstention accuracy")).not.toBeInTheDocument();
    expect(screen.queryByText("Evidence span overlap")).not.toBeInTheDocument();
    expect(screen.queryByText("Retrieval noise rate")).not.toBeInTheDocument();
    const contextRecallRow = screen.getAllByText("Context Recall")[0].closest("tr");
    expect(contextRecallRow).not.toBeNull();
    expect(within(contextRecallRow!).getByText(/80%/)).toBeInTheDocument();
    expect(within(contextRecallRow!).getByText("82%")).toBeInTheDocument();
    expect(screen.queryByText("1/3 = 33.3%")).not.toBeInTheDocument();
    expect(screen.queryByText("0.3333333333333333")).not.toBeInTheDocument();
    expect(screen.queryByText("Valuation method data readiness")).not.toBeInTheDocument();
    expect(screen.queryByText("Material official reconciliation rate")).not.toBeInTheDocument();
    expect(screen.getByText("Số mã đạt công thức FCFF")).toBeInTheDocument();
    expect(screen.queryByText("Số mã đạt công thức FCFE")).not.toBeInTheDocument();
    // valuation_publishable is no longer a benchmark-03 framework row (moved to the
    // governance/publishability gate); when present it renders as a dynamic backend
    // metric under its backend metric_name rather than the old framework label.
    expect(screen.getAllByText("Valuation publishability policy").length).toBeGreaterThan(0);
    expect(screen.getAllByText("New backend metric").length).toBeGreaterThan(0);
    expect(screen.queryByText("Judge calibration agreement")).not.toBeInTheDocument();
    expect(screen.queryByText("Judge rationale evidence coverage")).not.toBeInTheDocument();
    expect(screen.getAllByText("Report quality total").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Report completeness").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Valuation transparency").length).toBeGreaterThan(0);
    expect(screen.queryByText("Legacy thesis specificity")).not.toBeInTheDocument();
  });

  it("keeps report quality rows visible when the evaluator is not evaluable", async () => {
    const stalledPacket = JSON.parse(JSON.stringify(packet));
    const reportArtifact = stalledPacket.artifacts.find((artifact: any) => artifact.artifact === "report_eval.json");
    reportArtifact.status = "blocked";
    reportArtifact.metric_results = [
      {
        metric_id: "report.quality_total",
        metric_name: "Report quality total",
        metric_type: "score",
        value: null,
        threshold: ">= 85/100",
        status: "not_evaluable",
        sample_size: 0,
        detail: "structured_report_quality_evidence_missing",
        calculation: { denominator: 0, aggregation: "not_evaluable" },
      },
      {
        metric_id: "report.completeness",
        metric_name: "Report completeness",
        metric_type: "coverage",
        unit: "percent",
        value: null,
        threshold: ">= 90%",
        status: "not_evaluable",
        sample_size: 0,
        detail: "structured_report_quality_evidence_missing",
        calculation: { denominator: 0, aggregation: "not_evaluable" },
      },
      {
        metric_id: "report.valuation_transparency",
        metric_name: "Valuation transparency",
        metric_type: "score",
        value: null,
        threshold: ">= 85/100",
        status: "not_evaluable",
        sample_size: 0,
        detail: "structured_report_quality_evidence_missing",
        calculation: { denominator: 0, aggregation: "not_evaluable" },
      },
    ];
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(stalledPacket), {
      status: 200,
      headers: { "content-type": "application/json" },
    })));

    render(<EvalDashboardPage />);

    const totalRow = (await screen.findAllByText("Report quality total"))[0].closest("tr");
    const completenessRow = screen.getAllByText("Report completeness")[0].closest("tr");
    const transparencyRow = screen.getAllByText("Valuation transparency")[0].closest("tr");

    expect(totalRow).not.toBeNull();
    expect(completenessRow).not.toBeNull();
    expect(transparencyRow).not.toBeNull();
    expect(totalRow!.querySelector('[data-status="not_evaluable"]')).toBeInTheDocument();
    expect(completenessRow!.querySelector('[data-status="not_evaluable"]')).toBeInTheDocument();
    expect(transparencyRow!.querySelector('[data-status="not_evaluable"]')).toBeInTheDocument();
    expect(within(totalRow!).getByText(/structured_report_quality_evidence_missing/)).toBeInTheDocument();
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
    expect(screen.getByText(/đếm số sample đạt điều kiện/)).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /sample \(5\)/i })).toBeInTheDocument();
    expect(screen.getByText("gross_margin")).toBeInTheDocument();
    const componentRow = screen.getByText("provenance_coverage").closest("tr");
    expect(componentRow).not.toBeNull();
    expect(within(componentRow!).getByText("pass")).toBeInTheDocument();
    expect(within(componentRow!).getByText("100%")).toBeInTheDocument();
    const permissionCell = screen
      .getAllByText("READ_SNAPSHOT")
      .find((element) => element.tagName.toLowerCase() === "td");
    const permissionRow = permissionCell?.closest("tr");
    expect(permissionRow).not.toBeNull();
    expect(within(permissionRow!).getByText("pass")).toBeInTheDocument();
    expect(within(permissionRow!).getByText("read_only")).toBeInTheDocument();
    const reportScoreCell = screen
      .getAllByText("report.valuation_transparency")
      .find((element) => element.tagName.toLowerCase() === "td");
    const reportScoreRow = reportScoreCell?.closest("tr");
    expect(reportScoreRow).not.toBeNull();
    expect(within(reportScoreRow!).getByText("fail")).toBeInTheDocument();
    expect(within(reportScoreRow!).getByText("70")).toBeInTheDocument();
    expect(screen.getAllByText("Artifact ID").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Reason").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Evidence").length).toBeGreaterThan(0);
    expect(screen.getAllByText(/DHG\/data_quality\.json/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/core_metric_coverage/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/storage\/runs\/DHG\/evidence_packet\.json/).length).toBeGreaterThan(0);
    expect(screen.queryByText(/Metric result không có trace chi tiết/)).not.toBeInTheDocument();
    expect(screen.queryByText("Scope")).not.toBeInTheDocument();
    expect(screen.queryByText("Severity")).not.toBeInTheDocument();
    expect(screen.queryByText("Owner")).not.toBeInTheDocument();
    expect(screen.queryByText("Chặn xuất bản")).not.toBeInTheDocument();
  });

  it("shows boolean values for legacy schema validity source samples", async () => {
    render(<EvalDashboardPage />);
    await screen.findByText(/P0/);
    await userEvent.click(screen.getAllByText("JSON schema validity")[0]);

    expect(screen.getByRole("heading", { name: /sample \(2\)/i })).toBeInTheDocument();
    const evidencePacketRow = screen.getByText("evidence_packet").closest("tr");
    expect(evidencePacketRow).not.toBeNull();
    expect(within(evidencePacketRow!).getByText("pass")).toBeInTheDocument();
    expect(within(evidencePacketRow!).getByText("true")).toBeInTheDocument();

    const auditRow = screen.getByText("agent_effectiveness_audit").closest("tr");
    expect(auditRow).not.toBeNull();
    expect(within(auditRow!).getByText("fail")).toBeInTheDocument();
    expect(within(auditRow!).getByText("false")).toBeInTheDocument();
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
