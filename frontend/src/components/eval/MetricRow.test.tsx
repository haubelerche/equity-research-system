import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MetricRow } from "./MetricRow";
import type { MetricDef } from "../../lib/evalStatus";

const def: MetricDef = {
  id: "cov", label: "Coverage", unit: "%", comparator: "gte",
  thresholds: { P0: 0.95, P1: 0.95, P2: 0.95 },
};

describe("MetricRow", () => {
  it("shows pass pill when value meets threshold at maturity", () => {
    render(<table><tbody><MetricRow def={def} value={0.97} maturity="P0" /></tbody></table>);
    expect(screen.getByText("Coverage")).toBeInTheDocument();
    expect(screen.getByText(/pass/i)).toBeInTheDocument();
  });
  it("shows fail pill when below threshold", () => {
    render(<table><tbody><MetricRow def={def} value={0.5} maturity="P0" /></tbody></table>);
    expect(screen.getByText(/fail/i)).toBeInTheDocument();
  });
  it("shows measured-only when threshold null at maturity", () => {
    const m: MetricDef = { ...def, thresholds: { P0: null, P1: 0.9, P2: 0.9 } };
    render(<table><tbody><MetricRow def={m} value={0.5} maturity="P0" /></tbody></table>);
    expect(screen.getByText(/measured/i)).toBeInTheDocument();
  });
});
