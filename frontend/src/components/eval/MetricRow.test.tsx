import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { MetricRow } from "./MetricRow";
import type { MetricDef } from "../../lib/evalStatus";

const def: MetricDef = {
  id: "cov", label: "Coverage", unit: "%", comparator: "gte", threshold: 0.95,
  technology: "Ragas", formula: "covered / total",
};

describe("MetricRow", () => {
  it("shows pass when value meets the single acceptance threshold", () => {
    render(<table><tbody><MetricRow def={def} value={0.97} /></tbody></table>);
    expect(screen.getByText("Coverage")).toBeInTheDocument();
    expect(screen.getByText("Ragas")).toBeInTheDocument();
    expect(screen.getByText(/^Đạt$/i)).toBeInTheDocument();
  });

  it("shows not passed when below threshold", () => {
    render(<table><tbody><MetricRow def={def} value={0.5} /></tbody></table>);
    expect(screen.getByText(/Chưa đạt/i)).toBeInTheDocument();
  });

  it("shows not passed when benchmark data is missing", () => {
    render(<table><tbody><MetricRow def={def} value={undefined} /></tbody></table>);
    expect(screen.getByText(/Thiếu dữ liệu/i)).toBeInTheDocument();
    expect(screen.getByText(/Chưa đạt/i)).toBeInTheDocument();
  });

  it("uses normalized backend benchmark status when provided", () => {
    render(
      <table>
        <tbody>
          <MetricRow
            def={def}
            value={1}
            result={{
              metric_id: "cov",
              metric_name: "Coverage",
              status: "not_evaluable",
              threshold: ">= 95%",
              value: null,
            }}
          />
        </tbody>
      </table>,
    );
    expect(screen.getByText(/Chưa đánh giá/i)).toBeInTheDocument();
  });
});
