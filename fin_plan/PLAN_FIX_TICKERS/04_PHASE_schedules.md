# Phase 04 — Working capital / debt / dividend / cash sweep

**PLAN gốc:** §1.6, §1.9, §2 Phase 4, §4.5.
**Đọc trước:** `00_AUDIT.md`, `03_PHASE_forecast_periods_drivers.md`.

## Mục tiêu
Lấp các dòng `Thay đổi vốn lưu động`, `Cổ tức`, `Thay đổi nợ ròng` đang `_DASH` để forecast đủ điều kiện FCFF/FCFE.

## Hiện trạng code
- ĐÃ có: `backend/analytics/debt_schedule.py`, `dividend_schedule.py`, `cash_sweep.py`, `capex.py`, `tax_policy.py`.
- `client_report_view_model.py:_table_bs_cf` (dòng ~639): nhiều dòng hardcode `_DASH` ("Thay đổi nợ ròng", "Phát hành cổ phiếu", "Nợ ròng/EBITDA"); delta_nwc/cash/dividend chỉ điền forecast period.

## Việc cần làm
1. **Xác nhận harness gọi đủ schedule** (`backend/harness/tools.py`) và ghi vào forecast artifact: working_capital (DSO/DIO/DPO/NWC/ΔNWC), debt roll-forward (beginning/new/repay/ending/net borrowing/interest), dividend (DPS/payout/paid), cash sweep (begin cash + CFO − CAPEX − div + net borrowing ± other = end cash).
2. **Wire vào `_table_bs_cf` / `_table_valuation_model`:**
   - "Thay đổi nợ ròng" = Δ(debt − cash) từ debt schedule.
   - "Cổ tức" lịch sử từ fact `dividends_per_share.cash` × shares (đang `_DASH` cho actual).
   - "Nợ ròng/EBITDA" tính khi có net debt + EBITDA (đang `_DASH` × n).
   - "Doanh thu tài chính" (`_table_valuation_model` dòng ~618 `_DASH`) — dùng `_finance_income_values` đã có (dòng ~503) thay vì `_DASH`.
3. **Sign discipline** (PLAN §4.3): kiểm CAPEX/debt/interest/dividend/COGS/SG&A trước forecast. Interest = average debt × cost of debt (không theo doanh thu).
4. Equity roll-forward trừ cổ tức khỏi retained earnings; cash sweep reconcile.

## Acceptance
- Không còn `Thay đổi vốn lưu động`/`Cổ tức`/`Thay đổi nợ ròng`/`Doanh thu tài chính`/`Nợ ròng/EBITDA` trống hàng loạt khi đủ dữ liệu.

## Test
- `tests/unit/test_debt_schedule.py`, `test_dividend_schedule.py`, `test_cash_sweep.py` (kiểm tra tồn tại; bổ sung reconciliation assertion).
- `tests/unit/test_bs_cf_table.py`: forecast đủ ⇒ các dòng trên có số.

## Rủi ro
- Cash bridge hiện tại trong `_cash_values` (dòng ~461) cố tình bảo thủ (`0.0 * capex`) — review lại khi cash sweep thật vào.
