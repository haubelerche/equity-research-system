import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReportsPage } from "./ReportsPage";
import * as client from "../api/client";

beforeEach(() => vi.restoreAllMocks());

describe("ReportsPage", () => {
  it("renders the full universe (incl. tickers absent from the API), then filters", async () => {
    vi.spyOn(client, "fetchReports").mockResolvedValue({
      items: [
        { ticker: "DHG", company_name: "Duoc Hau Giang", exchange: "HOSE", segment: "pharma", is_mvp: true, has_report: true, has_explanation: true, preview_pages: [1], report_size: 1, updated_at: "x" },
      ],
    });
    render(<ReportsPage />);
    await screen.findByText("DHG");
    // DMC is in the static universe but NOT in the API response — must still render
    expect(screen.getByText("DMC")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("search"), "IMP");
    expect(screen.queryByText("DHG")).toBeNull();
    expect(screen.getByText("IMP")).toBeInTheDocument();
  });

  it("still lists tickers when the backend is unreachable (graceful fallback)", async () => {
    vi.spyOn(client, "fetchReports").mockRejectedValue(new Error("network down"));
    render(<ReportsPage />);
    expect(await screen.findByText("DHG")).toBeInTheDocument();
    expect(screen.getByText("IMP")).toBeInTheDocument();
  });
});
