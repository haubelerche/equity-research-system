import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { ReportRow } from "./ReportRow";
import type { ReportItem } from "../../api/types";

const item: ReportItem = {
  ticker: "DHG", company_name: "Duoc Hau Giang", exchange: "HOSE", segment: "pharma",
  is_mvp: true, has_report: true, has_explanation: false, preview_pages: [1, 2],
  report_size: 100, updated_at: "2026-06-14T00:00:00Z",
};

describe("ReportRow", () => {
  it("enables report download, disables explanation when missing", () => {
    render(<table><tbody>
      <ReportRow item={item} onPreview={vi.fn()} onGenerated={vi.fn()} />
    </tbody></table>);
    expect(screen.getByText("DHG")).toBeInTheDocument();
    const dl = screen.getByRole("link", { name: /tải report|download report/i });
    expect(dl).toHaveAttribute("href", "/reports/DHG/file/report");
    expect(screen.queryByRole("link", { name: /explanation/i })).toBeNull();
  });
});
