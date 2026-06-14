import { describe, it, expect, vi, beforeEach } from "vitest";
import { fetchReports, startRun, fetchRunStatus, fileUrl, previewUrl } from "./client";

beforeEach(() => { vi.restoreAllMocks(); });

describe("api client", () => {
  it("fetchReports hits /reports and returns items", async () => {
    const items = [{ ticker: "DHG" }];
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ items }), { status: 200 })));
    const res = await fetchReports();
    expect((globalThis.fetch as any).mock.calls[0][0]).toBe("/reports");
    expect(res.items).toEqual(items);
  });

  it("startRun posts full_report run_type and templated objective", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ run_id: "r1", status: "INIT" }), { status: 200 })));
    const res = await startRun("DHG");
    const [url, opts] = (globalThis.fetch as any).mock.calls[0];
    expect(url).toBe("/research/start");
    const body = JSON.parse(opts.body);
    expect(body.ticker).toBe("DHG");
    expect(body.run_type).toBe("full_report");
    expect(body.objective).toBe("Generate full equity research report for DHG");
    expect(res.run_id).toBe("r1");
  });

  it("fetchRunStatus hits status route", async () => {
    vi.stubGlobal("fetch", vi.fn(async () =>
      new Response(JSON.stringify({ run_id: "r1", status: "ANALYZING" }), { status: 200 })));
    await fetchRunStatus("r1");
    expect((globalThis.fetch as any).mock.calls[0][0]).toBe("/research/r1/status");
  });

  it("builds file and preview urls", () => {
    expect(fileUrl("DHG", "report")).toBe("/reports/DHG/file/report");
    expect(previewUrl("DHG", 3)).toBe("/reports/DHG/preview/3");
  });

  it("throws on non-ok", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("nope", { status: 500 })));
    await expect(fetchReports()).rejects.toThrow();
  });
});
