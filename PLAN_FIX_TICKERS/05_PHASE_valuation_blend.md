# Phase 05 — Valuation FCFF/FCFE 60/40 + valuation_result wiring ⭐ ƯU TIÊN 2

**PLAN gốc:** §1.7, §2 Phase 5, §4.6.
**Đọc trước:** `00_AUDIT.md`. Mở khóa target price/rating.

## Mục tiêu
Sinh `valuation_result` đầy đủ ⇒ view model có current_price/target_price/upside/rating; có valuation bridge.

## Root cause
- `artifacts/valuation_results/` **RỖNG**. `client_report_view_model._valuation_result` đọc `artifacts/valuation_results/*_{ticker}_valuation_result.json` ⇒ rỗng ⇒ `_market_price_inputs` (client_final) trả None ⇒ rating "CHƯA XUẤT BẢN"/"ĐANG HOÀN THIỆN".
- Harness ĐÃ có code ghi `valuation_result_json` (`backend/harness/tools.py:200,305`) — cần xác minh vì sao không chạy/không ghi ra thư mục đó.

## Hiện trạng code (đã có)
- `backend/analytics/fcff.py`, `fcfe.py`, `blend.py`, `multiples.py`, `valuation_confidence.py`, `approval_gate.py`.
- `_market_price_inputs` (view model dòng ~530): client_final đọc valuation_result; analyst_draft đọc blend (`target_price_dcf_vnd`, `current_price_vnd`, `upside_pct`).
- `_recommendation` (dòng ~543): >0.20 MUA, <−0.20 BÁN, else GIỮ.

## Việc cần làm
1. **Sửa harness để THỰC SỰ ghi `artifacts/valuation_results/{run_id}_{ticker}_valuation_result.json`** với: current_price, target_price, upside_downside, is_publishable, price_fcff, price_fcfe, blend 60/40, wacc, Re, terminal_growth, terminal_value_weight, EV→equity bridge (EV, net debt, STI, minority, non-op assets, diluted shares, value/share).
2. **Blend chuẩn (PLAN §4.6):** `Target = 0.6×Price_FCFF + 0.4×Price_FCFE`. FCFF chiết khấu WACC, FCFE chiết khấu Re. Không lẫn dòng tiền/suất chiết khấu.
3. **Validity guard:** nếu `WACC ≤ g` hoặc `Re ≤ g` ⇒ valuation invalid, `is_publishable=false`, KHÔNG xuất rating (đừng tự cap g).
4. **Relative valuation peer check** theo taxonomy dược/y tế VN (đừng so sai nhóm).
5. **Nếu thiếu shares/current_price ⇒ block rating** (nối Phase 01).

## Acceptance
- `artifacts/valuation_results/` có file cho DHG + mọi ticker chạy.
- Report có target price, upside/downside, rating, valuation bridge, lý do rating.
- `WACC ≤ g` ⇒ invalid, không ra rating (test).

## Test
- `tests/unit/test_fcff.py`/`test_fcfe.py`/`test_blend.py` (mở rộng): blend 60/40 đúng; guard WACC≤g.
- `tests/unit/test_valuation_result_artifact.py` (mới): harness ghi đủ field bridge.

## Rủi ro
- Đây là phase đụng harness — chạy `scripts/run_research.py --ticker DHG` end-to-end để verify, không chỉ unit test.
