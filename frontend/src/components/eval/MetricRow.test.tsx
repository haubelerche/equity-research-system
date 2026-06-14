import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MetricRow } from "./MetricRow";
import type { MetricDef } from "../../lib/evalStatus";

const def: MetricDef = {
  id: "cov", label: "Coverage", unit: "%", comparator: "gte", threshold: 0.95,
  technology: "Ragas", formula: "covered / total",
};

describe("MetricRow", () => {
  it("shows pass when value meets the acceptance threshold", () => {
    render(<table><tbody><MetricRow def={def} value={0.97} /></tbody></table>);
    expect(screen.getByText("Coverage")).toBeInTheDocument();
    expect(screen.getByText("Ragas")).toBeInTheDocument();
    expect(screen.getByText("97.0%")).toBeInTheDocument();
  });

  it("shows not evaluated when benchmark data is missing", () => {
    render(<table><tbody><MetricRow def={def} value={undefined} /></tbody></table>);
    expect(screen.getByText("Coverage")).toBeInTheDocument();
    expect(document.querySelector('[data-status="not_evaluable"]')).toBeInTheDocument();
  });

  it("uses normalized backend benchmark status when provided", () => {
    render(
      <table><tbody><MetricRow def={def} value={1} result={{
        metric_id: "cov", metric_name: "Coverage", status: "not_evaluable",
        threshold: ">= 95%", value: null,
      }} /></tbody></table>,
    );
    expect(document.querySelector('[data-status="not_evaluable"]')).toBeInTheDocument();
  });

  it("opens metric evidence through the row callback", async () => {
    const onSelect = vi.fn();
    render(<table><tbody><MetricRow def={def} value={0.97} onSelect={onSelect} /></tbody></table>);
    await userEvent.click(screen.getByText("Coverage"));
    expect(onSelect).toHaveBeenCalledWith(def, undefined);
  });
});
