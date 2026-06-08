# Phase 02 — MarketSnapshotArtifact + dữ liệu sidebar

**PLAN gốc:** §1.2, §2 Phase 2, §4.2.
**Đọc trước:** `00_AUDIT.md`.

## Mục tiêu
Lấp toàn bộ sidebar/market metric đang `_DASH`: giá hiện tại, vốn hóa, shares, 52w, YTD/1T/3T/12T, KLGD, dividend yield.

## Hiện trạng code
- KHÔNG có module market snapshot. `client_report_view_model.py`:
  - `market_statistics` (dòng ~1027) hardcode `_DASH` cho "Giá cao/thấp 52 tuần", "KLGD bình quân 3 tháng", "Tỷ giá VND/USD".
  - `trading_performance_table` (dòng ~1042) toàn `_DASH` (YTD/1T/3T/12T).
  - `dividend_yield=None` (dòng ~1025).
- Connector giá ĐÃ có: `scripts/connectors/vnstock_price_connector.py`, `scripts/connectors/vn_market_data_adapter.py`.
- `_market_price_inputs` lấy current_price từ `valuation_result`/`blend` (Phase 05).

## Việc cần làm
1. **Tạo `backend/reporting/market_snapshot.py`** → `MarketSnapshotArtifact`:
   - Fields: `last_price`, `as_of_date`, `market_cap`, `shares_outstanding`, `free_float`(opt), `foreign_room`(opt), `high_52w`, `low_52w`, `return_ytd/1m/3m/12m`, `avg_volume_3m`, `benchmark_return`(VNINDEX).
   - Provenance per field (source + as_of).
   - Fallback order (PLAN §1.2): HOSE/HNX/disclosure → StoxPlus/FiinTrade → CafeF/Vietstock → vnstock (phụ).
2. **Sinh artifact** `artifacts/market_snapshot/{ticker}_{run_id}.json` trong harness (`backend/harness/tools.py`) trước render.
3. **Wire vào view model:** thay `_DASH` hardcode bằng giá trị từ snapshot; `dividend_yield = DPS/last_price`; điền `trading_performance_table`.
4. **Consistency check:** `market_cap ≈ last_price × shares_outstanding` (Phase 01 numeric gate).
5. Trường thật sự thiếu ⇒ ghi `eval_result.json`, KHÔNG rải `_DASH` trong client report (PLAN §4.2).

## Acceptance
- Sidebar không còn `Giá hiện tại`/`Vốn hóa`/`Số lượng cổ phiếu`/`Diễn biến giá` trống khi nguồn lấy được.
- `market_cap ≈ last_price × shares` (sai số <1%).

## Test
- `tests/unit/test_market_snapshot.py`: mock connector → artifact đầy đủ field + consistency.
- Mở rộng `test_report_data_loader_*` để view model đọc snapshot.

## Rủi ro
- vnstock price unit ×1000 (đã ghi ở EXECUTION_STATE Known Issues) — chuẩn hóa VND ở core, format ở presentation.
- Ticker-agnostic: free_float/foreign_room qua `ticker_metadata`, không hardcode.
