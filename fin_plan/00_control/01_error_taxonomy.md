# Error Taxonomy

## Context

Tài liệu này chuẩn hóa các nhóm lỗi trong pipeline equity research để agent không xử lý từng triệu chứng riêng lẻ như các lỗi độc lập. Mỗi lỗi phải được map vào một failure class, artifact bị ảnh hưởng, gate chặn xuất bản, và file canonical liên quan.

## Problem Statement

Các audit hiện tại mô tả nhiều lỗi chồng lấn: thiếu citation, sai FCFE, thiếu debt schedule, sensitivity mỏng, narrative chung chung, layout PDF lỗi, và report vẫn publish recommendation khi chưa đủ dữ liệu. Nếu không phân loại, agent sẽ sửa từng màn hình hoặc từng ticker nhưng không xử lý invariant cấp hệ thống.

## Technical Deep-Dive

| Error class | Triệu chứng | Artifact chịu trách nhiệm | Gate bắt buộc | Canonical reference |
| --- | --- | --- | --- | --- |
| `SOURCE_GAP` | Thiếu official filing, thiếu market price, citation rỗng, Tier-3 source vượt gate | `SourceArtifact`, `CitationMap`, `ClaimLedger` | Không export final nếu numeric claim không có source đạt chuẩn | `02_fix_plans/01_fix_all_tickers_report_output.md` |
| `NUMERIC_RECONCILIATION` | EPS không khớp LNST/share count, EBIT/interest/tax không reconcile, net debt sai | `FinancialFactArtifact`, `ReconciliationReport` | Blocking nếu công thức kế toán không cân bằng | `03_audits/01_analytics_dcf_audit.md` |
| `FORECAST_DRIVER_GAP` | Forecast kéo CAGR cơ học, thiếu driver revenue/margin/WC/CAPEX | `ForecastArtifact` | Forecast không publishable nếu không có driver assumption và sanity check | `01_standards/02_forecast_pipeline_before_valuation.md` |
| `DEBT_FCFE_INVALID` | Net borrowing suy ra từ median debt, FCFE double count hoặc thiếu debt schedule | `DebtScheduleArtifact`, `CashSweepArtifact`, `FCFEArtifact` | Không có approved debt schedule thì không có FCFE/blend publishable | `02_fix_plans/02_fix_debt_net_borrowing_fcfe_gate.md` |
| `VALUATION_INVALID` | WACC <= terminal growth, FCFF/FCFE gap lớn, terminal value quá áp đảo | `DCFArtifact`, `BlendValuationArtifact` | Target price phải blocked nếu valuation status invalid | `01_standards/01_valuation_60_fcff_40_fcfe.md` |
| `SENSITIVITY_WEAK` | Matrix sai range, thiếu WACC x g hoặc Re x g, không có downside interpretation | `SensitivityArtifact` | Không cho client-facing valuation nếu sensitivity không bao phủ biến trọng yếu | `01_standards/04_sensitivity_analysis.md` |
| `NARRATIVE_THIN` | Luận điểm đầu tư chung chung, không link tới driver, catalyst, risk, valuation bridge | `NarrativeArtifact`, `SectionArtifact` | Report section phải có evidence-backed claim hoặc bị hạ confidence | `02_fix_plans/01_fix_all_tickers_report_output.md` |
| `REPORT_ASSEMBLY_LAYOUT` | Heading gộp sai nội dung, bảng tràn, trang trống, chart thiếu hoặc khó đọc | `ReportArtifact`, `LayoutAuditArtifact` | PDF/HTML không được final nếu layout audit fail | `02_fix_plans/01_fix_all_tickers_report_output.md` |
| `HARNESS_STATE_DRIFT` | Agent stage chạy sai thứ tự, state thiếu manifest, error không được ghi nhận | `HarnessState`, `EvidencePacket`, `RunManifest` | Stage transition phải validate contract và known failure state | `02_fix_plans/03_fix_err_harness_engineering.md` |

## Strategic Recommendations

1. Khi có lỗi mới, cập nhật taxonomy trước khi tạo file plan mới.
2. Nếu một lỗi thuộc class đã có, bổ sung acceptance test vào plan hiện hữu thay vì tạo tài liệu song song.
3. Nếu lỗi xuất hiện ở một ticker cụ thể, ghi vào `04_ticker_cases` nhưng chỉ promote lên `01_standards` khi nó là invariant chung.
