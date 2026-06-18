import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MetricRow } from "./MetricRow";
import type { MetricDef } from "../../lib/evalStatus";

const def: MetricDef = {
  id: "cov",
  label: "Coverage",
  unit: "%",
  comparator: "gte",
  threshold: 0.95,
  technology: "Ragas",
  formula: "covered / total",
};

describe("MetricRow", () => {
  it("shows pass when value meets the acceptance threshold", () => {
    render(<table><tbody><MetricRow def={def} value={0.97} /></tbody></table>);
    expect(screen.getByText("Coverage")).toBeInTheDocument();
    expect(screen.getByText("Ragas")).toBeInTheDocument();
    expect(screen.getByText("97%")).toBeInTheDocument();
  });

  it("shows fail when benchmark data is missing", () => {
    render(<table><tbody><MetricRow def={def} value={undefined} /></tbody></table>);
    expect(screen.getByText("Coverage")).toBeInTheDocument();
    expect(document.querySelector('[data-status="fail"]')).toBeInTheDocument();
  });

  it("shows fail when no numeric benchmark value is available", () => {
    render(
      <table><tbody><MetricRow def={def} value={1} result={{
        metric_id: "cov",
        metric_name: "Coverage",
        status: "not_evaluable",
        threshold: ">= 95%",
        value: null,
      }} /></tbody></table>,
    );
    expect(document.querySelector('[data-status="fail"]')).toBeInTheDocument();
  });

  it("recomputes status from numeric thresholds when backend pass/fail is stale", () => {
    render(
      <table><tbody><MetricRow def={def} value={0.90} result={{
        metric_id: "cov",
        metric_name: "Coverage",
        status: "pass",
        threshold: ">= 95%",
        value: 0.90,
      }} /></tbody></table>,
    );
    expect(document.querySelector('[data-status="fail"]')).toBeInTheDocument();
  });

  it("handles lower-is-better runtime thresholds", () => {
    render(
      <table><tbody><MetricRow
        def={{ ...def, id: "retry_rate", comparator: "lte", threshold: 0.05 }}
        value={0.10}
        result={{
          metric_id: "retry_rate",
          metric_name: "Retry rate",
          status: "pass",
          threshold: "<= 5%",
          value: 0.10,
        }}
      /></tbody></table>,
    );
    expect(document.querySelector('[data-status="fail"]')).toBeInTheDocument();
  });

  it("normalizes a bare-ratio backend threshold onto the 0-100% scale", () => {
    render(
      <table><tbody><MetricRow
        def={{ ...def, id: "context_precision", threshold: 0.8 }}
        value={0.314}
        result={{
          metric_id: "context_precision",
          metric_name: "Context Precision",
          status: "fail",
          threshold: ">= 0.80",
          value: 0.314,
        }}
      /></tbody></table>,
    );
    expect(screen.getByText("31.4%")).toBeInTheDocument();
    expect(screen.getByText("≥ 80%")).toBeInTheDocument();
  });

  it("keeps a backend threshold that is already a percentage condition", () => {
    render(
      <table><tbody><MetricRow def={def} value={0.97} result={{
        metric_id: "cov",
        metric_name: "Coverage",
        status: "pass",
        threshold: "= 100%",
        value: 0.97,
      }} /></tbody></table>,
    );
    expect(screen.getByText("= 100%")).toBeInTheDocument();
  });

  it("does not convert a non-numeric runtime threshold into a fake pass", () => {
    render(
      <table><tbody><MetricRow
        def={{ ...def, id: "valuation_publishable", unit: "", threshold: 10 }}
        value={0}
        result={{
          metric_id: "valuation_publishable",
          metric_name: "Valuation publishability",
          metric_type: "coverage",
          unit: "count",
          threshold: "pass",
          status: "fail",
          value: 0,
        }}
      /></tbody></table>,
    );
    expect(document.querySelector('[data-status="fail"]')).toBeInTheDocument();
  });

  it("renders pass-rate semantics with numerator and denominator", () => {
    render(
      <table><tbody><MetricRow
        def={{ ...def, id: "fcfe", unit: "%", threshold: 1 }}
        value={0.2}
        result={{
          metric_id: "fcfe",
          metric_name: "FCFE formula",
          metric_type: "coverage",
          unit: "percent",
          threshold: "= 100%",
          status: "fail",
          value: 0.2,
          calculation: { numerator: 2, denominator: 10, aggregation: "cohort_pass_rate" },
        }}
      /></tbody></table>,
    );
    expect(screen.getByText("pass_rate · 10 case đủ điều kiện")).toBeInTheDocument();
    expect(screen.getByText("20%")).toBeInTheDocument();
    expect(screen.queryByText("2/10 = 20%")).not.toBeInTheDocument();
    expect(document.querySelector('[data-status="fail"]')).toBeInTheDocument();
  });

  it("opens metric evidence through the row callback", async () => {
    const onSelect = vi.fn();
    render(<table><tbody><MetricRow def={def} value={0.97} onSelect={onSelect} /></tbody></table>);
    await userEvent.click(screen.getByText("Coverage"));
    expect(onSelect).toHaveBeenCalledWith(def, undefined);
  });
});
