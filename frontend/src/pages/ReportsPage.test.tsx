import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ReportsPage } from "./ReportsPage";
import { GenerationProvider } from "../generation/GenerationContext";
import * as client from "../api/client";

beforeEach(() => {
  vi.restoreAllMocks();
  window.localStorage.clear();
});

describe("ReportsPage", () => {
  it("renders the full universe (incl. tickers absent from the API), then filters", async () => {
    vi.spyOn(client, "fetchReports").mockResolvedValue({
      items: [
        { ticker: "DHG", company_name: "Duoc Hau Giang", exchange: "HOSE", segment: "pharma", is_mvp: true, has_report: true, has_explanation: true, preview_pages: [1], report_size: 1, updated_at: "x" },
      ],
    });
    render(<GenerationProvider><ReportsPage /></GenerationProvider>);
    await screen.findByText("DHG");
    // DMC is in the static universe but NOT in the API response — must still render
    expect(screen.getByText("DMC")).toBeInTheDocument();

    await userEvent.selectOptions(screen.getByLabelText("search"), "IMP");
    expect(screen.queryByText("DHG")).toBeNull();
    expect(screen.getByText("IMP")).toBeInTheDocument();
  });

  it("still lists tickers when the backend is unreachable (graceful fallback)", async () => {
    vi.spyOn(client, "fetchReports").mockRejectedValue(new Error("network down"));
    render(<GenerationProvider><ReportsPage /></GenerationProvider>);
    expect(await screen.findByText("DHG")).toBeInTheDocument();
    expect(screen.getByText("IMP")).toBeInTheDocument();
    expect(await screen.findByRole("status")).toHaveTextContent("VITE_API_BASE");
  });

  it("keeps the last known report status across a page refresh while the API is loading or down", async () => {
    window.localStorage.setItem(
      "reports.inventory.v1",
      JSON.stringify({
        items: [
          {
            ticker: "DHG",
            company_name: "Duoc Hau Giang",
            exchange: "HOSE",
            segment: "pharma",
            is_mvp: true,
            has_report: true,
            has_explanation: true,
            preview_pages: [1],
            report_size: 1,
            updated_at: "2026-06-15T00:00:00Z",
          },
        ],
      }),
    );
    vi.spyOn(client, "fetchReports").mockRejectedValue(new Error("network down"));

    render(<GenerationProvider><ReportsPage /></GenerationProvider>);

    expect(await screen.findByRole("link", { name: /Tải báo cáo/i })).toBeInTheDocument();
    expect(screen.getByText("DHG")).toBeInTheDocument();
  });

  it("shows the selected ticker row when the API has no completed reports", async () => {
    vi.spyOn(client, "fetchReports").mockResolvedValue({ items: [] });
    render(<GenerationProvider><ReportsPage /></GenerationProvider>);

    await screen.findByText("DHG");
    await userEvent.selectOptions(screen.getByLabelText("search"), "DHG");

    expect(screen.getByText("DHG")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Sinh/ })).toBeInTheDocument();
    expect(screen.queryByText("IMP")).toBeNull();
  });

  it("renders DHG first and pushes DBD to the end of the reports table", async () => {
    vi.spyOn(client, "fetchReports").mockResolvedValue({ items: [] });
    render(<GenerationProvider><ReportsPage /></GenerationProvider>);

    await screen.findByText("DHG");
    const dataRows = screen.getAllByRole("row").slice(1);

    expect(dataRows[0]).toHaveTextContent(/^DHG/);
    expect(dataRows[dataRows.length - 1]).toHaveTextContent(/^DBD/);
  });
});
