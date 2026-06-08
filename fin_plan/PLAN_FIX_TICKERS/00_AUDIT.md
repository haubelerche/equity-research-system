# 00 — AUDIT & ROOT CAUSE (ticker-agnostic)

> Nguồn gốc: `PLAN_FIX_ALL_TICKERS_REPORT_OUTPUT_FOR_CLAUDE.md`.
> File này là kết quả audit code thực tế, map 12 nhóm lỗi vào file/module cụ thể.
> Đọc file này TRƯỚC khi mở bất kỳ file phase nào.

## 0. Kết luận audit (quan trọng nhất)

Phần lớn module trong kế hoạch **ĐÃ tồn tại**. Lỗi report cuối **KHÔNG phải do thiếu engine**, mà do:

1. **Hai pipeline song song gây nhầm output:**
   - `scripts/run_full_pipeline.py` → **DEPRECATED**, render-only, `_write_artifacts()` ghi **placeholder rỗng** (`rating="UNDER_REVIEW"`, mọi giá trị `0.0`). PDF DHG "ĐANG HOÀN THIỆN" nhiều khả năng đến từ path này hoặc 1 harness run dở dang.
   - `scripts/run_research.py` → submit harness (`backend/harness/`) = production thật. Harness ĐÃ thiết kế sinh forecast/fcff/fcfe/blend/valuation_result + gates (`backend/harness/tools.py:200,305`; `backend/harness/gates.py:80`).

2. **Artifact production chưa được sinh đầy đủ:**
   - `artifacts/valuation_results/` **RỖNG** → đây là nguồn `current_price/target_price/upside_downside/is_publishable` cho mode `client_final` (`client_report_view_model.py:_valuation_result`, `_market_price_inputs`). Rỗng ⇒ `client_final` LUÔN bị block ⇒ chỉ ra được `analyst_draft` với rating `ĐANG HOÀN THIỆN`.
   - `artifacts/charts/` **RỖNG** ⇒ không có biểu đồ.
   - `artifacts/forecast/` CÓ blend/fcff/fcfe/forecast (DBD) ⇒ engine chạy được; vấn đề là chưa chạy đủ + chưa ghi valuation_result.

3. **Bug render thật trong view model** (độc lập dữ liệu):
   - `_derive_periods()` (`client_report_view_model.py:109`) chỉ giữ period kết thúc `FY`/`A`, **loại bỏ toàn bộ period forecast kết thúc `F`** khi facts có dữ liệu. ⇒ Bảng không bao giờ có cột 2026F–2030F dù forecast artifact có. Đây là lý do "forecast chưa phải forecast".

4. **Nội dung hardcode generic trong view model:**
   - `investment_thesis`, `latest_business_update`, `key_growth_drivers`, `key_margin_drivers`, `material_events`, `current_context` là **chuỗi cố định**, không bám fact/nguồn ⇒ narrative mỏng, chung chung.
   - `market_statistics` hardcode `_DASH` cho 52w/KLGD/tỷ giá; `trading_performance_table` toàn `_DASH`; `ownership_table` toàn `_DASH`; `dividend_yield=None`; `peer_table=None`; `catalyst_table=None`.
   - `source_captions` generic ("Nguồn: Dữ liệu thị trường") ⇒ không có citation cụ thể, "Nguồn tham khảo chính" trống.

## 1. Map 12 nhóm lỗi → file/phase

| # | Lỗi (PLAN §1) | Root cause / File | Phase |
|---|---|---|---|
| 1.1 | Status `ĐANG HOÀN THIỆN`, không rating | `_recommendation()` trả "ĐANG HOÀN THIỆN" khi upside None; gate `assert_client_final_ready` chỉ chặn `client_final`, không chặn `analyst_draft` xuất PDF | 01 |
| 1.2 | Market data trống | Không có `MarketSnapshotArtifact`; `market_statistics`/`trading_performance_table` hardcode `_DASH` | 02 |
| 1.3 | Không citation | `source_captions` generic; client view không nạp source evidence; "Nguồn tham khảo chính" trống | 08 |
| 1.4 | Narrative mỏng | 6 chuỗi narrative hardcode trong `build_client_report_view_model` | 07 |
| 1.5 | Driver 0.0% | `_table_key_forecast_drivers` đọc `forecast["drivers"]`, fallback `or 0.0`; forecast artifact drivers rỗng/không resolve | 03 |
| 1.6 | Forecast không có năm F | **BUG** `_derive_periods` loại period `F` | 03 |
| 1.7 | DCF/target price thiếu | `valuation_results/` rỗng ⇒ blend/valuation_result không tới view model | 05 |
| 1.8 | Sensitivity rỗng | `_table_driver_sensitivity` dùng ±15% giả lập + phụ thuộc blend; chưa phải WACC×g matrix | 06 |
| 1.9 | Bảng số lỗi logic (shares=0, P/E trống) | `_derive_shares_mn` trả 0 khi fact thiếu; `NumericConsistencyGate` chưa wire vào render | 01 |
| 1.10 | Không biểu đồ | `artifacts/charts/` rỗng; `_charts()` chỉ tìm C1/C2/C4 | 09 |
| 1.11 | Layout chưa giống IMP | `backend/reporting/html_renderer.py`, `pdf_renderer.py`, CSS | 09 |
| 1.12 | Font tiếng Việt | `scripts/setup_fonts.py` có sẵn; cần QA render PNG | 09 |

## 2. Module đã có sẵn (KHÔNG build lại — chỉ wire/sửa)

```
backend/analytics/  fcff.py fcfe.py blend.py forecasting.py sensitivity.py
                    debt_schedule.py dividend_schedule.py cash_sweep.py
                    capex.py shares.py tax_policy.py multiples.py
                    valuation_confidence.py approval_gate.py
backend/reporting/  client_report_view_model.py  client_section_builder.py
                    section_builder.py html_renderer.py pdf_renderer.py
                    chart_generator.py report_data_loader.py artifact_writer.py
backend/evaluation/ numeric_consistency.py citation_coverage.py source_provenance_gates.py
backend/harness/    runner.py graph.py tools.py gates.py state.py evidence_packet.py
backend/citations/  citation_map.py validator.py event_linker.py driver_evidence.py
```

## 3. Module CÒN THIẾU (cần tạo mới)

- `backend/reporting/market_snapshot.py` + artifact `artifacts/market_snapshot/{ticker}_*.json` (Phase 02).
- Source-evidence binding cho client view (Phase 08) — có `backend/sources/` nhưng chưa nối vào `ClientReportViewModel`.

## 4. Nguyên tắc bắt buộc khi thực thi mọi phase

- **Ticker-agnostic**: không `if ticker == "DHG"`. Ngoại lệ doanh nghiệp ⇒ `ticker_metadata`/`company_profile`/`source_manifest`/`approved_assumptions`.
- **Code-first**: số do Python tính; LLM chỉ diễn giải (CLAUDE.md §5.2).
- **HTML là single source of truth**, PDF render từ HTML đã QA.
- **Production path = `run_research.py` (harness)**. Không dùng `run_full_pipeline.py` để xuất final. Cân nhắc xóa/hard-deprecate placeholder writer ở Phase 01.
- Mỗi phase: sửa nhỏ nhất, thêm/cập nhật test, chạy `pytest tests/` subset liên quan, cập nhật `.claude/EXECUTION_STATE.md`.

## 5. Thứ tự thực thi đề xuất

```
03 (forecast periods + drivers, bug render)  ← sửa trước, gỡ được nhiều lỗi nhất
05 (valuation_result + blend wiring)         ← mở khóa target price/rating
01 (export gate)                             ← chặn xuất sai sau khi đã có dữ liệu
02 (market snapshot)                         ← lấp sidebar
06 (sensitivity)  04 (schedules)             ← hoàn thiện số
07 (narrative)  08 (citations)               ← chất lượng nội dung
09 (charts + layout + font QA)               ← bề mặt cuối
```

Lý do đảo thứ tự so với PLAN gốc: 03 và 05 là nguồn của ~6 nhóm lỗi; sửa chúng trước cho ROI cao nhất và để các gate (01) có dữ liệu thật để kiểm.

## 6. Việc kiểm chứng còn nợ (TODO trước khi code)

- [ ] Đọc `backend/harness/tools.py:160-320` xác nhận điều kiện ghi `valuation_results/*.json` và vì sao đang rỗng.
- [ ] Đọc 1 file `artifacts/forecast/DBD_*_forecast.json` xác nhận `drivers` có giá trị thật hay 0.
- [ ] Chạy `python scripts/run_research.py --ticker DHG` end-to-end, soi artifact sinh ra.
- [ ] Xác nhận `_derive_periods` là nguồn mất cột forecast (viết test đỏ trước khi sửa).
