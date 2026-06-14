import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EvalDashboardPage } from "./EvalDashboardPage";

describe("EvalDashboardPage", () => {
  it("renders binary evaluation groups without maturity levels or CI matrix", () => {
    render(<EvalDashboardPage />);
    expect(screen.getByText(/1 · Chất lượng và độ tin cậy dữ liệu/)).toBeInTheDocument();
    expect(screen.getByText(/2 · RAG$/)).toBeInTheDocument();
    expect(screen.getByText(/7 · Vận hành, chi phí và độ trễ/)).toBeInTheDocument();
    expect(screen.queryByText(/P0|P1|P2/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Ma trận cổng kiểm soát CI/i)).not.toBeInTheDocument();
    expect(screen.getAllByText(/chưa đạt/i).length).toBeGreaterThan(0);
  });

  it("opens benchmark history and explanation dialogs", async () => {
    render(<EvalDashboardPage />);
    await userEvent.click(screen.getAllByRole("button", { name: "Xem thêm" })[0]);
    expect(screen.getByRole("dialog", { name: /Lịch sử benchmark/i })).toBeInTheDocument();
    expect(screen.getAllByText("project-eval-20260614T033415Z").length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "Đóng cửa sổ" }));

    await userEvent.click(screen.getAllByRole("button", { name: "Giải thích" })[0]);
    expect(screen.getByRole("dialog", { name: /Giải thích:/i })).toBeInTheDocument();
    expect(screen.getByText(/Công thức hoặc phương pháp tính/i)).toBeInTheDocument();
  });
});
