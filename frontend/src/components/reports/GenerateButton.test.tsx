import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
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

function hideProgressModal() {
  const button = screen.getAllByRole("button").find((el) =>
    String(el.getAttribute("class") ?? "").includes("gen-modal__hide")
  );
  if (!button) throw new Error("hide button not found");
  return userEvent.click(button);
}

const status = (over: Partial<RunStatusResponse> = {}) =>
  ({
    run_id: "r",
    ticker: "DHG",
    status: "ANALYZING",
    current_stage: "ANALYZE",
    progress: {},
    blocking_reason: null,
    created_at: "2026-06-19T00:00:00Z",
    updated_at: new Date().toISOString(),
    finished_at: null,
    ...over,
  }) as RunStatusResponse;

describe("GenerateButton + GenerationProvider", () => {
  it("starts a run, shows the progress modal, then a success toast and calls onComplete", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r1", mode: "full_pipeline" });
    const seq: RunStatus[] = ["ANALYZING", "PUBLISHED"];
    let i = 0;
    vi.spyOn(client, "fetchRunStatus").mockImplementation(async () =>
      status({ status: seq[Math.min(i++, seq.length - 1)] }),
    );
    const onComplete = renderButton();

    await userEvent.click(screen.getByRole("button", { name: /sinh/i }));

    expect(client.startRun).toHaveBeenCalledWith("DHG", { forceFull: false });
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await waitFor(() => expect(onComplete).toHaveBeenCalled());
  });

  it("passes forceFull for refresh buttons", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "refresh-1", mode: "full_pipeline" });
    vi.spyOn(client, "fetchRunStatus").mockResolvedValue(status());
    render(
      <GenerationProvider pollMs={1}>
        <GenerateButton ticker="DHG" onComplete={vi.fn()} label="Cập nhật" forceFull />
      </GenerationProvider>,
    );

    await userEvent.click(screen.getByRole("button", { name: /Cập nhật/i }));

    expect(client.startRun).toHaveBeenCalledWith("DHG", { forceFull: true });
  });

  it("hiding the modal keeps the run going", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r2", mode: "full_pipeline" });
    vi.spyOn(client, "fetchRunStatus").mockResolvedValue(status());
    renderButton();

    await userEvent.click(screen.getByRole("button", { name: /sinh/i }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await hideProgressModal();

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await screen.findByRole("button", { name: /ch.y/i });
  });

  it("shows a failure toast with the blocking reason on BLOCKED", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r3", mode: "full_pipeline" });
    const reason = "API blocked DHG.";
    vi.spyOn(client, "fetchRunStatus").mockResolvedValue(
      status({
        status: "BLOCKED",
        current_stage: "INGEST_AND_VALIDATE",
        blocking_reason: reason,
        progress: { blocking_reason: reason },
      }),
    );
    renderButton();

    await userEvent.click(screen.getByRole("button", { name: /sinh/i }));

    expect(await screen.findAllByText(/API blocked DHG/i)).not.toHaveLength(0);
  });

  it("shows generation mode and backend diagnostics in the modal", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r4", mode: "fast_render" });
    vi.spyOn(client, "fetchRunStatus").mockResolvedValue(
      status({
        mode: "fast_render",
        source_run_id: "source-run-123456",
        executor_state: "running",
        elapsed_seconds: 12,
        last_heartbeat_at: new Date().toISOString(),
      }),
    );
    renderButton();

    await userEvent.click(screen.getByRole("button", { name: /sinh/i }));

    expect((await screen.findAllByText(/PDF/i)).length).toBeGreaterThan(0);
    expect(await screen.findByText(/12s/i)).toBeInTheDocument();
    expect(await screen.findByText(/Worker: running/i)).toBeInTheDocument();
    expect(await screen.findByText(/source-run-1/i)).toBeInTheDocument();
  });

  it("warns when backend heartbeat is stale", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r5", mode: "full_pipeline" });
    vi.spyOn(client, "fetchRunStatus").mockResolvedValue(
      status({
        mode: "full_pipeline",
        updated_at: "2026-06-19T00:00:00Z",
        last_heartbeat_at: "2026-06-19T00:00:00Z",
        elapsed_seconds: 240,
      }),
    );
    renderButton();

    await userEvent.click(screen.getByRole("button", { name: /sinh/i }));

    expect(await screen.findByText(/heartbeat/i)).toBeInTheDocument();
  });

  it("warns after repeated status polling failures", async () => {
    vi.spyOn(client, "startRun").mockResolvedValue({ run_id: "r6", mode: "full_pipeline" });
    vi.spyOn(client, "fetchRunStatus").mockRejectedValue(new Error("network"));
    renderButton();

    await userEvent.click(screen.getByRole("button", { name: /sinh/i }));

    expect(await screen.findByText(/ti.p t.c ki.m tra l.i/i)).toBeInTheDocument();
  });
});
