import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReportsPage } from "./ReportsPage";
import * as client from "../api/client";

beforeEach(() => vi.restoreAllMocks());

describe("ReportsPage", () => {
  it("loads /reports and renders rows, then filters", async () => {
    vi.spyOn(client, "fetchReports").mockResolvedValue({
      items: [
        { ticker: "DHG", company_name: "Duoc Hau Giang", exchange: "HOSE", segment: "pharma", is_mvp: true, has_report: true, has_explanation: true, preview_pages: [1], report_size: 1, updated_at: "x" },
        { ticker: "IMP", company_name: "Imexpharm", exchange: "HOSE", segment: "pharma", is_mvp: true, has_report: false, has_explanation: false, preview_pages: [], report_size: null, updated_at: null },
      ],
    });
    render(<ReportsPage />);
    await screen.findByText("DHG");
    expect(screen.getByText("IMP")).toBeInTheDocument();
    await userEvent.type(screen.getByLabelText("search"), "imex");
    expect(screen.queryByText("DHG")).toBeNull();
    expect(screen.getByText("IMP")).toBeInTheDocument();
  });
});
