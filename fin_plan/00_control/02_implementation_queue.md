# Implementation Queue

## Context

Queue này chuyển các tài liệu trong `fin_data` thành trình tự triển khai có kiểm soát. Thứ tự ưu tiên dựa trên Iron Triangle: reliability trước, scalability tiếp theo, latency/cost-to-serve sau cùng, vì pipeline định giá sai nhưng chạy nhanh vẫn tạo rủi ro sản phẩm cao hơn pipeline bị chặn đúng cách.

## Problem Statement

Hiện tại các kế hoạch sửa lỗi có mức độ chi tiết cao nhưng phân tán theo chủ đề. Agent cần một hàng đợi duy nhất để tránh sửa narrative/layout trước khi các gate định lượng và source provenance được khóa.

## Technical Deep-Dive

| Priority | Workstream | Failure classes | Primary file | Exit criteria |
| --- | --- | --- | --- | --- |
| P0 | Export gate và source provenance | `SOURCE_GAP`, `VALUATION_INVALID` | `02_fix_plans/01_fix_all_tickers_report_output.md` | Không có report final/recommendation khi thiếu source, market snapshot, hoặc valuation status invalid |
| P0 | Debt schedule, cash sweep, net borrowing | `DEBT_FCFE_INVALID`, `NUMERIC_RECONCILIATION` | `02_fix_plans/02_fix_debt_net_borrowing_fcfe_gate.md` | FCFE chỉ publishable khi `DebtScheduleArtifact` và `CashSweepArtifact` pass gate |
| P1 | Driver-based forecast | `FORECAST_DRIVER_GAP` | `01_standards/02_forecast_pipeline_before_valuation.md` | Forecast có driver, scenario, WC, CAPEX, debt, dividend, equity roll-forward, và sanity checks |
| P1 | DCF hardening | `VALUATION_INVALID`, `SENSITIVITY_WEAK` | `03_audits/01_analytics_dcf_audit.md` | WACC/g invalid bị block, terminal value weight được cảnh báo, sensitivity matrix đạt chuẩn |
| P1 | Report narrative and section assembly | `NARRATIVE_THIN`, `REPORT_ASSEMBLY_LAYOUT` | `02_fix_plans/01_fix_all_tickers_report_output.md` | Section không gộp sai, narrative có claim-source-driver linkage, chart/table render ổn định |
| P2 | Harness engineering reliability | `HARNESS_STATE_DRIFT` | `02_fix_plans/03_fix_err_harness_engineering.md` | Stage order, manifest, evidence packet, known failure registry hoạt động deterministic |
| P2 | Formula library productization | `NUMERIC_RECONCILIATION` | `01_standards/05_formula_finance_library.md` | Formula registry có typed input, explicit warnings, golden tests, và agent wrapper |

## Strategic Recommendations

1. Không triển khai P1 narrative/layout trước khi P0 gate đã chặn được report sai; nếu không, sản phẩm sẽ đẹp hơn nhưng vẫn sai về mặt kiểm soát rủi ro.
2. Không dùng case DBD hoặc DP3 làm rule mặc định; hãy dùng chúng như regression fixtures sau khi invariant đã được định nghĩa trong artifact/gate chung.
3. Mỗi workstream phải kết thúc bằng test hoặc gate có thể chạy tự động, không chỉ bằng checklist thủ công.
