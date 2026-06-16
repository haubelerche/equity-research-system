# 03 - Financial Benchmarks

Purpose: validate code-first financial calculation, valuation bridges, formula
trace availability, accounting invariants, sensitivity grids, and valuation
publishability as deterministic release gates.

## Primary Data

- `golden_ratios.csv`: derived financial ratios from golden facts.
- `golden_valuation/valuation_cases.jsonl`: V2 DCF regression cases with formula trace and expected outputs.
- `golden_valuation/finance_cases_v3.jsonl`: V3 publishable and seeded negative finance cases.
- `golden_valuation/sensitivity_grid.csv`: WACC/terminal-growth sensitivity grid for V2 DCF cases.
- `financial_anomaly_expected_flags.csv`: expected warning or anomaly flags, for example EPS reconciliation.
- `strict_metrics.yaml`: P0/P1 metric contract for artifact presence, schema validity, case coverage, invariant errors, formula reproduction, golden drift, sensitivity grids, publishability, seeded issue detection, and LLM/tool governance.

## Critical Invariants

- `wacc > terminal_growth`.
- `shares_outstanding > 0`.
- Net debt equals interest-bearing debt minus cash minus short-term investments.
- Target price must be reproducible from equity value and share count.
- A valuation must not be publishable when material inputs are null, unresolved, or missing required formula traces.

## Anti-Overfit Controls

- V2 DCF cases and V3 finance cases are separate truth sets and must not be merged as one target source.
- V3 publishable base cases vary cash, debt, short-term investments, WACC, terminal growth, and cost of equity by ticker while preserving deterministic net debt reconciliation.
- Seeded negative cases must be evaluated by expected blocker semantics; public `case_id` or `case_type` must not be sufficient to pass.
