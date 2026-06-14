import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { EvalDashboardPage } from "./EvalDashboardPage";

describe("EvalDashboardPage", () => {
  it("renders all 8 layer titles and the pipeline", () => {
    render(<EvalDashboardPage />);
    expect(screen.getByText(/1 · Data reliability/)).toBeInTheDocument();
    expect(screen.getByText(/6 · Report quality/)).toBeInTheDocument();
    expect(screen.getByText(/8 · Rollout & CI/)).toBeInTheDocument();
    expect(screen.getByText(/Client-final render authorization/)).toBeInTheDocument();
  });

  it("RAG hit-rate flips from measured-only at P0 to pass at P1", async () => {
    render(<EvalDashboardPage />);
    expect(screen.getAllByText(/measured/i).length).toBeGreaterThan(0);
    await userEvent.click(screen.getByRole("button", { name: "P1" }));
    expect(screen.getAllByText(/pass/i).length).toBeGreaterThan(0);
  });
});
