# 03 — Financial Benchmarks

Mục tiêu: kiểm định code-first finance, valuation, formula trace và accounting invariants.

## Dữ liệu chính

- `golden_ratios.csv`: ratios derived từ golden facts.
- `golden_valuation/valuation_cases.jsonl`: DCF regression cases với formula trace.
- `golden_valuation/sensitivity_grid.csv`: sensitivity matrix theo WACC/g.
- `financial_anomaly_expected_flags.csv`: các warning/anomaly kỳ vọng, ví dụ EPS reconciliation.

## Critical invariants

- `wacc > terminal_growth`.
- `shares_outstanding > 0`.
- Net debt = short debt + long debt - cash - short-term investments.
- Target price tái lập được từ equity value và shares.
- Không dùng model nếu input trọng yếu là null/unresolved.
