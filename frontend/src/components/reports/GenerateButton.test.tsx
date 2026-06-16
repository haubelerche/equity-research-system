import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { GenerationProvider } from "../../generation/GenerationContext";
import { GenerateButton } from "./GenerateButton";
import * as client from "../../api/client";
import type { RunStatus, RunStatusResponse } from "../../api/types";

beforeEach(() => vi.restoreAllMocks());

function renderButton(onComplete = vi.fn()) {
  render(
    <GenerationProvider pollMs={1}>
      <GenerateButton ticker="DHG" onComplete={onComplete} />
    </GenerationProvider>,
  );
  return onComplete;
}

const status = (over: Partial<RunStatusResponse> = {}) =>
  ({
    run_id: "r", ticker: "DHG", status: "ANALYZING", current_stage: "ANALYZE",
    progress: {}, blocking_reason: null, updated_at: "", finished_at: null, ...over,
  }) as any;

describe("GenerateButton + GenerationProvider", () => {
  it("starts a run, shows the progress modal, then a success toast and calls onComplete", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r1", mode: "full_pipeline" });
    const seq: RunStatus[] = ["ANALYZING", "PUBLISHED"];
    let i = 0;
    vi.spyOn(client, "fetchRunStatus").mockImplementation(async () =>
      status({ status: seq[Math.min(i++, seq.length - 1)] }),
    );
    const onComplete = renderButton();

    await userEvent.click(screen.getByRole("button", { name: /sinh báo cáo/i }));
    expect(client.startRun).toHaveBeenCalledWith("DHG");
    await screen.findByRole("button", { name: /ẩn cửa sổ tiến trình/i });
    await screen.findByText(/đã sinh xong báo cáo DHG/i);
    expect(onComplete).toHaveBeenCalled();
  });

  it("hiding the modal keeps the run going", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r2", mode: "full_pipeline" });
    vi.spyOn(client, "fetchRunStatus").mockResolvedValue(status());
    renderButton();

    await userEvent.click(screen.getByRole("button", { name: /sinh báo cáo/i }));
    await screen.findByText(/đang tạo báo cáo DHG/i);
    await userEvent.click(screen.getByRole("button", { name: /ẩn cửa sổ tiến trình/i }));

    expect(screen.queryByText(/đang tạo báo cáo DHG/i)).not.toBeInTheDocument();
    await screen.findByRole("button", { name: /đang chạy/i });
  });

  it("shows a failure toast with the Vietnamese blocking reason on BLOCKED", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r3", mode: "full_pipeline" });
    const reason = "Không đủ dữ liệu tài chính để tạo báo cáo cho DHG.";
    vi.spyOn(client, "fetchRunStatus").mockResolvedValue(
      status({ status: "BLOCKED", current_stage: "INGEST_AND_VALIDATE", blocking_reason: reason, progress: { blocking_reason: reason } }),
    );
    renderButton();

    await userEvent.click(screen.getByRole("button", { name: /sinh báo cáo/i }));
    const matches = await screen.findAllByText(/Không đủ dữ liệu tài chính/i);
    expect(matches.length).toBeGreaterThan(0);
  });
});
