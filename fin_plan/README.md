# fin_data Knowledge Base

## Context

`fin_data` là khu vực điều phối tri thức cho dự án multi-agent equity research, không phải nơi chứa mã nguồn thực thi. Mục tiêu của thư mục này là gom các chuẩn định giá, audit lỗi, kế hoạch sửa lỗi, và case ticker thành một hệ thống tham chiếu có thứ tự, tránh tình trạng nhiều file cùng mô tả một vấn đề nhưng không rõ file nào là nguồn chuẩn.

## Problem Statement

Trước khi sắp xếp, thư mục này ở dạng phẳng, trộn lẫn handbook, audit, implementation plan, prompt cho agent, và case ticker cụ thể. Cấu trúc đó tạo ba rủi ro vận hành:

| Rủi ro | Hệ quả kỹ thuật | Biện pháp tổ chức hiện tại |
| --- | --- | --- |
| Trùng kế hoạch sửa lỗi | Agent có thể lấy nhầm bản ngắn/cũ và lặp lại remediation logic | Chỉ giữ plan canonical trong `02_fix_plans`; bản rút gọn chuyển vào `99_archive` |
| Trộn chuẩn mô hình với audit lỗi | Khó phân biệt invariant dài hạn với lỗi phát hiện theo report | Chuẩn dài hạn đặt trong `01_standards`; audit đặt trong `03_audits` |
| Case ticker lẫn với kế hoạch toàn hệ thống | Fix có thể overfit vào DBD/DP3 thay vì áp dụng cho toàn pipeline | Case ticker đặt riêng trong `04_ticker_cases`; chỉ promote invariant chung vào `00_control` hoặc `01_standards` |

## Technical Deep-Dive

### Folder Contract

| Folder | Vai trò | Quy tắc sử dụng |
| --- | --- | --- |
| `00_control/` | Bản đồ điều hành, taxonomy lỗi, thứ tự xử lý | Đọc trước khi giao việc cho agent hoặc tạo kế hoạch sprint |
| `01_standards/` | Chuẩn nghiệp vụ và kỹ thuật có giá trị dài hạn | Dùng làm nguồn sự thật cho valuation, sensitivity, forecasting, formula library |
| `02_fix_plans/` | Kế hoạch sửa lỗi có thể triển khai bằng code/test | Dùng để lập issue, PR, hoặc prompt cho coding agent |
| `03_audits/` | Bằng chứng lỗi, đánh giá chất lượng, phân tích failure mode | Dùng để truy vết nguyên nhân và xác minh rằng fix đã xử lý đúng lỗi gốc |
| `04_ticker_cases/` | Case study theo ticker cụ thể | Dùng làm regression scenario, không tự động biến thành rule toàn hệ thống |
| `99_archive/` | Bản trùng, bản rút gọn, hoặc tài liệu đã bị thay thế | Không dùng cho implementation trừ khi cần truy vết lịch sử |

### Canonical Files

| Chủ đề | File canonical |
| --- | --- |
| Định giá 60% FCFF / 40% FCFE | `01_standards/01_valuation_60_fcff_40_fcfe.md` |
| Forecast trước valuation | `01_standards/02_forecast_pipeline_before_valuation.md` |
| Debt/dividend driver-based forecast | `01_standards/03_driver_based_debt_dividend.md` |
| Sensitivity analysis | `01_standards/04_sensitivity_analysis.md` |
| Formula library cho agent | `01_standards/05_formula_finance_library.md` |
| Output report cho toàn bộ ticker | `02_fix_plans/01_fix_all_tickers_report_output.md` |
| Debt schedule, net borrowing, FCFE gate | `02_fix_plans/02_fix_debt_net_borrowing_fcfe_gate.md` |
| ERR harness engineering | `02_fix_plans/03_fix_err_harness_engineering.md` |
| DCF audit | `03_audits/01_analytics_dcf_audit.md` |
| Report quality progress audit | `03_audits/02_current_report_quality_progress.md` |
| DBD report case | `04_ticker_cases/01_DBD_report_audit_fix_plan.md` |
| DP3 debt/dividend case | `04_ticker_cases/02_DP3_debt_dividend_forecast.md` |

## Strategic Recommendations

1. Mọi task sửa lỗi nên bắt đầu từ `00_control/02_implementation_queue.md`, sau đó mở đúng file canonical trong `02_fix_plans` và chỉ dùng `03_audits` để kiểm chứng nguyên nhân.
2. Mọi chuẩn nghiệp vụ dùng lại nhiều lần phải được promote vào `01_standards`; không để chuẩn chung bị khóa trong case DBD hoặc DP3.
3. Mọi lỗi mới cần được ghi vào `00_control/01_error_taxonomy.md` trước khi viết plan mới, để tránh tạo thêm một file kế hoạch song song cho cùng failure mode.
4. `99_archive` chỉ là vùng truy vết; agent không được dùng nội dung archive làm nguồn triển khai mặc định.
