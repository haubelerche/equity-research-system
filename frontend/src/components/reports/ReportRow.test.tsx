import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReportRow } from "./ReportRow";
import { GenerationProvider } from "../../generation/GenerationContext";
import type { ReportItem } from "../../api/types";

const withReport: ReportItem = {
  ticker: "DHG",
  company_name: "Duoc Hau Giang",
  exchange: "HOSE",
  segment: "pharma",
  is_mvp: true,
  has_report: true,
  has_explanation: false,
  preview_pages: [1, 2],
  report_size: 100,
  updated_at: "2026-06-14T00:00:00Z",
};

const noReport: ReportItem = {
  ...withReport,
  ticker: "IMP",
  has_report: false,
  has_explanation: false,
};

describe("ReportRow", () => {
  it("with a report: shows download + refresh, hides explanation when missing", () => {
    render(
      <GenerationProvider>
        <table>
          <tbody>
            <ReportRow item={withReport} onPreview={vi.fn()} onGenerated={vi.fn()} />
          </tbody>
        </table>
      </GenerationProvider>,
    );
    expect(screen.getByText("DHG")).toBeInTheDocument();
    const dl = screen.getByRole("link", { name: /Tải báo cáo/i });
    expect(dl).toHaveAttribute("href", "/reports/DHG/file/report?v=2026-06-14T00%3A00%3A00Z");
    expect(screen.queryByRole("link", { name: /Tải giải thích/i })).toBeNull();
    expect(screen.getByRole("button", { name: /Cập nhật/i })).toBeInTheDocument();
  });

  it("without a report: shows only the generate button", () => {
    render(
      <GenerationProvider>
        <table>
          <tbody>
            <ReportRow item={noReport} onPreview={vi.fn()} onGenerated={vi.fn()} />
          </tbody>
        </table>
      </GenerationProvider>,
    );
    expect(screen.getByRole("button", { name: /Sinh báo cáo/i })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Tải báo cáo/i })).toBeNull();
  });
});
