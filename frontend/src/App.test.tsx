import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import App from "./App";

// Prevent ReportsPage from firing a real fetch in jsdom
vi.mock("./api/client", () => ({
  fetchReports: vi.fn().mockResolvedValue({ items: [] }),
  fileUrl: vi.fn(),
  previewUrl: vi.fn(),
}));

describe("App", () => {
  it("renders nav with both routes", () => {
    render(<MemoryRouter initialEntries={["/"]}><App /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /báo cáo|reports/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /đánh giá|dashboard/i })).toBeInTheDocument();
  });
});
