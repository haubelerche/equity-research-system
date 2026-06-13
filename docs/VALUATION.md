# Forecast và valuation

Cập nhật: 2026-06-13

## Context

Valuation là lớp deterministic finance của dự án. LLM không được dùng như calculator cho target price, WACC, FCFF, FCFE, sensitivity hoặc recommendation reconciliation. Các module trong `backend/analytics/` chịu trách nhiệm tính toán và tạo artifact có formula trace.

## Problem Statement

Báo cáo equity research có rủi ro nghiêm trọng nếu model ngôn ngữ tự tính số tài chính trong prose. Sai số nhỏ trong debt bridge, share count, terminal value hoặc working capital có thể đổi hoàn toàn khuyến nghị. Vì vậy hệ thống phải tách narrative khỏi math, đồng thời tạo gate để phát hiện thiếu bridge, thiếu assumption hoặc recommendation không khớp upside.

## Technical Deep-Dive

### 1. Module chính

| Module | Trách nhiệm |
|---|---|
| `backend/analytics/ratios.py` | Tính financial ratios từ canonical facts |
| `backend/analytics/forecasting.py` | Forecast theo driver và FY period |
| `backend/analytics/fcff.py` | FCFF DCF, WACC, enterprise value, EV-to-equity bridge |
| `backend/analytics/fcfe.py` | FCFE DCF, cost of equity, net borrowing, equity value |
| `backend/analytics/blend.py` | Blend FCFF/FCFE, gap check, terminal value checks |
| `backend/analytics/multiples.py` | P/E, EV/EBITDA và relative valuation cross-check |
| `backend/analytics/sensitivity.py` | WACC/g, Re/g, blend, multiples sensitivity |
| `backend/analytics/debt_schedule.py` | Debt schedule và net debt assumptions |
| `backend/analytics/dividend_schedule.py` | Dividend assumptions và payout/yield consistency |
| `backend/analytics/working_capital_schedule.py` | DSO/DIO/DPO và NWC assumptions |
| `backend/analytics/share_rollforward.py` | Share count, dilution, EPS consistency |

### 2. Stage execution

Trong `FORECAST_AND_VALUE`, runner thực hiện:

| Bước | Tool/logic | Output |
|---|---|---|
| Forecast | `run_forecast` | `forecast_model` |
| Forecast narrative | LLM hoặc deterministic fast draft path | `forecast_narrative` |
| Forecast gate | `forecast_quality_gate` | Pass/block theo driver coverage |
| Valuation | `run_valuation` | `valuation` |
| Read-back | `read_valuation_artifact` | `valuation_read` |
| Valuation gates | `valuation_gate`, `valuation_reconciliation_gate` | Kiểm tra component và reconciliation |
| Lock | `research_lock` | Danh sách artifact đã khóa |

### 3. Gate trọng yếu

| Gate | Điều kiện block tiêu biểu |
|---|---|
| `FORECAST_QUALITY_GATE` | Thiếu revenue by channel/product, gross margin assumptions, opex assumptions, working capital days, capex/depreciation, debt/cash/interest, EPS, quality checks |
| `VALUATION_GATE` | Thiếu FCFF, blend, sensitivity, formula version, assumption version, unit policy, currency, period scope, assumptions |
| `VALUATION_RECONCILIATION_GATE` | FCFF bridge không khớp, value per share không reconcile, terminal growth >= WACC, thiếu current price, upside/recommendation không khớp |
| `FORMULA_TRACE_GATE` | Thiếu formula trace hoặc trace thiếu formula id/version/calculation steps |
| `FPTS_GRADE_GATE` | Score dưới ngưỡng hoặc fail financial model integrity/valuation completeness |

### 4. Recommendation logic

`valuation_reconciliation_gate` kỳ vọng recommendation khớp upside:

| Upside expected | Recommendation |
|---|---|
| `> 15%` | `BUY` |
| `< -20%` | `SELL` |
| Còn lại | `HOLD` |

Ngưỡng này là policy trong code hiện tại, không phải khuyến nghị đầu tư độc lập. Nếu product policy đổi, cần sửa gate và tests tương ứng.

### 5. Unit và currency discipline

Valuation artifact cần thể hiện `unit_policy`, `currency`, `period_scope`, `formula_version`, `assumption_version` và `approved_assumption_refs`. Financial facts thường xử lý theo VND bn hoặc shares mn tùy module; reconciliation gate có logic kiểm tra per-share để phát hiện mismatch đơn vị.

## Strategic Recommendations

| Ưu tiên | Khuyến nghị |
|---|---|
| P0 | Mọi thay đổi valuation phải có unit tests cho formula và gate |
| P0 | Không cho prompt tạo số target price khi artifact thiếu |
| P1 | Mở rộng formula trace để reviewer đọc được từng driver lớn |
| P1 | Tách rõ assumption approval cho development draft và client-final |
| P2 | Khi batch nhiều ticker, chuẩn hóa peer group và market data freshness trước khi scale valuation |
