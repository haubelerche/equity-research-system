import { describe, it, expect } from "vitest";
import { classifyRunStatus } from "./runStatus";

describe("classifyRunStatus", () => {
  it("maps in-progress statuses", () => {
    for (const s of ["INIT", "INGESTING", "ANALYZING", "VALUATING", "SYNTHESIZING", "AUDITING"]) {
      expect(classifyRunStatus(s)).toBe("running");
    }
  });
  it("maps terminal success", () => {
    expect(classifyRunStatus("PUBLISHED")).toBe("success");
    expect(classifyRunStatus("PUBLISHED_DRAFT")).toBe("success");
  });
  it("maps terminal failure", () => {
    expect(classifyRunStatus("BLOCKED")).toBe("failed");
    expect(classifyRunStatus("FAILED")).toBe("failed");
  });
  it("treats unknown as running (defensive)", () => {
    expect(classifyRunStatus("WAT")).toBe("running");
  });
});
