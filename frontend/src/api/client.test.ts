import { describe, it, expect, vi, beforeEach } from "vitest";
import {
  fetchEvaluationPacket,
  fetchReports,
  startRun,
  fetchRunStatus,
  fileUrl,
  previewUrl,
} from "./client";

beforeEach(() => { vi.restoreAllMocks(); });

const jsonResponse = (body: unknown, init: ResponseInit = {}) =>
  new Response(JSON.stringify(body), {
    ...init,
    headers: { "content-type": "application/json", ...init.headers },
  });

describe("api client", () => {
  it("fetchReports hits /reports and returns items", async () => {
    const items = [{ ticker: "DHG" }];
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ items }, { status: 200 })));
    const res = await fetchReports();
    const [url, opts] = (globalThis.fetch as any).mock.calls[0];
    expect(url).toBe("/reports");
    expect(opts.cache).toBe("no-store");
    expect(res.items).toEqual(items);
  });

  it("startRun POSTs to the ticker generate endpoint", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      jsonResponse({ run_id: "r1", mode: "full_pipeline" }, { status: 200 })));
    const res = await startRun("DHG");
    const [url, opts] = (globalThis.fetch as any).mock.calls[0];
    expect(url).toBe("/reports/DHG/generate");
    expect(opts.method).toBe("POST");
    expect(opts.cache).toBe("no-store");
    expect(res.run_id).toBe("r1");
    expect(res.mode).toBe("full_pipeline");
  });

  it("fetchRunStatus hits status route", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      jsonResponse({ run_id: "r1", status: "ANALYZING" }, { status: 200 })));
    await fetchRunStatus("r1");
    expect((globalThis.fetch as any).mock.calls[0][0]).toBe("/research/r1/status");
  });

  it("fetchEvaluationPacket uses project or run scoped endpoints", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      jsonResponse({ publication_status: "DRAFT_PUBLISHABLE" }, { status: 200 })));
    await fetchEvaluationPacket();
    await fetchEvaluationPacket("run-1");
    expect((globalThis.fetch as any).mock.calls[0][0]).toBe("/eval/framework");
    expect((globalThis.fetch as any).mock.calls[1][0]).toBe("/research/run-1/evaluation");
  });

  it("falls back to the project benchmark packet when run scoped evaluation is missing", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      if (url === "/research/run-1/evaluation") {
        return new Response("missing", { status: 404 });
      }
      return jsonResponse({ source: "benchmark_suite", artifacts: [{ artifact: "data_quality.json" }] }, { status: 200 });
    }));

    const packet = await fetchEvaluationPacket("run-1");

    expect((globalThis.fetch as any).mock.calls[0][0]).toBe("/research/run-1/evaluation");
    expect((globalThis.fetch as any).mock.calls[1][0]).toBe("/eval/framework");
    expect(packet.source).toBe("benchmark_suite");
    expect(packet.artifacts?.[0]?.artifact).toBe("data_quality.json");
  });

  it("builds file and preview urls", () => {
    expect(fileUrl("DHG", "report")).toBe("/reports/DHG/file/report");
    expect(fileUrl("DHG", "report", "2026-06-15T00:00:00Z")).toBe("/reports/DHG/file/report?v=2026-06-15T00%3A00%3A00Z");
    expect(previewUrl("DHG", 3)).toBe("/reports/DHG/preview/3");
    expect(previewUrl("DHG", 3, "2026-06-15T00:00:00Z")).toBe("/reports/DHG/preview/3?v=2026-06-15T00%3A00%3A00Z");
  });

  it("throws on non-ok", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 500 })));
    await expect(fetchReports()).rejects.toThrow();
  });
});
