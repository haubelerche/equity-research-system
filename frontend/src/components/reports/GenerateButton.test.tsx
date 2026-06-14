import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GenerateButton } from "./GenerateButton";
import * as client from "../../api/client";

beforeEach(() => vi.restoreAllMocks());

describe("GenerateButton", () => {
  it("starts a run then shows running, then success and calls onComplete", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r1", status: "INIT" });
    const statuses = ["ANALYZING", "PUBLISHED"];
    let i = 0;
    vi.spyOn(client, "fetchRunStatus").mockImplementation(async () => ({
      run_id: "r1", ticker: "DHG", status: statuses[Math.min(i++, statuses.length - 1)] as any,
      current_stage: "", updated_at: "", finished_at: null,
    }));
    const onComplete = vi.fn();
    render(<GenerateButton ticker="DHG" pollMs={1} onComplete={onComplete} />);

    await userEvent.click(screen.getByRole("button", { name: /sinh báo cáo|generate/i }));
    expect(client.startRun).toHaveBeenCalledWith("DHG");
    await screen.findByText(/đang chạy|running/i);
    await screen.findByText(/xong|done|success/i);
    expect(onComplete).toHaveBeenCalled();
  });

  it("shows failure on BLOCKED and stops", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r2", status: "INIT" });
    vi.spyOn(client, "fetchRunStatus").mockResolvedValue({
      run_id: "r2", ticker: "DHG", status: "BLOCKED",
      current_stage: "", updated_at: "", finished_at: null,
    });
    render(<GenerateButton ticker="DHG" pollMs={1} onComplete={vi.fn()} />);
    await userEvent.click(screen.getByRole("button", { name: /sinh báo cáo|generate/i }));
    await screen.findByText(/lỗi|thất bại|failed|blocked/i);
  });
});
