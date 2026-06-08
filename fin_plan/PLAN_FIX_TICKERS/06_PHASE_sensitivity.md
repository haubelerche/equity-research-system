# Phase 06 — Sensitivity & scenario có target price thật

**PLAN gốc:** §1.8, §2 Phase 6, §4.7.
**Đọc trước:** `00_AUDIT.md`, `05_PHASE_valuation_blend.md`.

## Mục tiêu
Sensitivity ra giá mục tiêu định lượng, không phải bảng giả định ±15%.

## Hiện trạng code
- `backend/analytics/sensitivity.py` ĐÃ có (WACC × terminal growth — theo EXECUTION_STATE).
- `client_report_view_model._table_driver_sensitivity` (dòng ~816): hiện dùng `target_base × 0.85/1.15` (±15% giả lập) + stress driver thủ công ⇒ "minh họa", không phải recompute thật.

## Việc cần làm
1. **Recompute thật** thay vì ±15%: gọi `backend/analytics/sensitivity.py` để mỗi ô là target price tính lại từ DCF.
   - FCFF: WACC × terminal growth matrix.
   - FCFE: Re × terminal growth matrix.
   - Operating: revenue CAGR × EBIT/gross margin.
   - Scenario Bear/Base/Bull: target price + upside/downside + rating implication.
   - Peer: EPS × target P/E hoặc EBITDA × EV/EBITDA (nếu đủ peer).
2. **terminal_value_weight:** tính; nếu >70% EV ⇒ flag internal + diễn giải ở valuation risk (PLAN §1.8).
3. **Không render** sensitivity nếu ô target price vẫn `_DASH` (gate sensitivity, nối Phase 01).

## Acceptance
- Không còn dòng `Target price —` trong bảng sensitivity.
- Mỗi scenario có target price + upside + rating implication.

## Test
- `tests/unit/test_sensitivity.py` (mở rộng): matrix WACC×g ra giá khác nhau, monotonic theo hướng kỳ vọng.
- `tests/unit/test_sensitivity_table_render.py`: blend có target ⇒ bảng không `_DASH`.

## Rủi ro
- Matrix lớn ⇒ layout (PLAN §4.10): sensitivity/valuation matrix được phép full-width; các chart khác thì không.
