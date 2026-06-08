# Phase 03 — Forecast periods (bug) + driver thật ⭐ ƯU TIÊN 1

**PLAN gốc:** §1.5, §1.6, §2 Phase 3, §4.4.
**Đọc trước:** `00_AUDIT.md`. Đây là phase gỡ nhiều lỗi nhất — làm TRƯỚC.

## Mục tiêu
(a) Bảng có cột forecast 2026F–2030F. (b) Driver table có số thật, không 0.0%.

## Root cause đã xác định
1. **BUG render:** `_derive_periods()` (`client_report_view_model.py:109-118`) chỉ giữ period `endswith(("FY","A"))` ⇒ **loại bỏ mọi period forecast `*F`**. Khi facts có dữ liệu, fallback `_PERIODS_FALLBACK` (có năm F) không chạy ⇒ bảng mất hẳn cột forecast.
2. **Driver 0.0%:** `_table_key_forecast_drivers()` (dòng ~753) đọc `forecast.get("drivers", {})` rồi `_driver_pct(...) or 0.0`. Nếu forecast artifact `drivers` rỗng/không resolve ⇒ 0.0%.

## Việc cần làm
1. **Sửa `_derive_periods`** (TDD — viết test đỏ trước):
   - Trả về **actuals (FY/A) + forecast (F)** đã sort đúng thứ tự thời gian.
   - Lấy forecast periods từ `forecast["forecast_years"][].label` (đã có `_forecast_by_label`).
   - Giữ số cột hợp lý cho layout (PLAN §4.10: bảng ≤8–10 cột) — ví dụ 2 actual gần nhất + 5 forecast, phần còn lại để appendix.
2. **Đảm bảo forecast artifact có `drivers` thật:**
   - Xác nhận `backend/analytics/forecasting.py` ghi `drivers` với historical median/min/max + base assumption. Nếu chưa, bổ sung.
   - `DriverAssumptionArtifact` (PLAN §1.5): historical median/min/max, base, bear/base/bull, source/evidence, linked line item, valuation impact.
   - Driver tối thiểu (PLAN §4.4): revenue growth, gross margin, SG&A/rev, EBIT margin, EBITDA margin, tax rate, D&A/rev, CAPEX/rev, DSO, DIO, DPO, NWC/rev, payout, debt/EBITDA, net borrowing.
3. **Chặn driver 0.0% vô lý:** trong `_table_key_forecast_drivers`, nếu driver quan trọng = 0 nhưng historical tính được ⇒ dùng historical median; nếu thực sự thiếu ⇒ đánh dấu missing cho gate (Phase 01), không render 0.0%.

## Acceptance
- Bảng `MÔ HÌNH ĐỊNH GIÁ`/`TÓM TẮT TÀI CHÍNH` có cột 2026F–2030F.
- `ĐỘNG LỰC DỰ PHÓNG CHÍNH` có số thật + bear/base/bull + link line item + valuation impact.
- Không driver quan trọng nào 0.0% khi historical tính được.

## Test
- `tests/unit/test_client_view_model_periods.py` (mới): facts có 2021–2025FY + forecast 2026–2030F ⇒ `_derive_periods` trả 7 cột đúng thứ tự.
- `tests/unit/test_driver_table.py`: forecast có drivers ⇒ không có 0.0% ở revenue_growth/gross_margin/sga/capex.

## Rủi ro
- Đổi `_derive_periods` ảnh hưởng nhiều bảng (financial_summary, valuation_model, bs_cf, profitability) — chạy full `tests/unit` sau khi sửa.
