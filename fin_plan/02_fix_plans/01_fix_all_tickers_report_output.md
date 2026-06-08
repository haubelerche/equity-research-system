# Kế hoạch sửa lỗi output báo cáo PDF/HTML cho toàn bộ ticker

## 0. Kết luận kiểm định nhanh

Output hiện tại lấy `DHG_report.html` và `DHG_report.pdf` làm ví dụ kiểm định chưa đạt chuẩn báo cáo equity research chuyên nghiệp theo mẫu `IMP_by_ACBS_Update_22.pdf`. Lỗi không nằm riêng ở ticker DHG mà là lỗi hệ thống trong pipeline sinh báo cáo: thiếu dữ liệu thị trường, thiếu target price, thiếu khuyến nghị chính thức, thiếu citation, thiếu biểu đồ, chưa có forecast thật sau năm hiện tại, nhiều bảng để dấu `—`, driver-based modeling chỉ là mô tả hình thức, DCF/FCFF/FCFE chưa được tính đủ, sensitivity chưa ra kết quả định lượng và phần phân tích quá ngắn.

PDF hiện chỉ có 5 trang, khoảng 1.600 từ, không có biểu đồ, không có nguồn tham khảo cụ thể, không có target price và vẫn ghi `ĐANG HOÀN THIỆN`. Trong khi mẫu IMP có bố cục research report hoàn chỉnh: sidebar có giá mục tiêu/giá hiện tại/upside, biểu đồ giá nhỏ ở cột trái, phần luận điểm nhiều đoạn phân tích sâu, bảng tài chính có năm forecast, nhiều biểu đồ minh họa driver, phần khuyến nghị rõ ràng và disclaimer đầy đủ.

Mục tiêu sửa: biến output HTML/PDF thành bản báo cáo client-facing hoàn chỉnh, có dữ liệu, insight, định giá, khuyến nghị, citation và layout đúng chuẩn; không để thuật ngữ backend, không để warning thừa, không xuất final nếu các gate định lượng/citation/valuation chưa đạt.

**Phạm vi áp dụng:** kế hoạch này phải được triển khai ở cấp **pipeline/report engine/artifact contract**, không hard-code cho DHG. DHG chỉ là ticker mẫu để soi lỗi. Mọi rule, gate, schema, renderer, chart, citation, valuation và narrative contract phải chạy được cho toàn bộ universe dược/y tế Việt Nam như DHG, IMP, DBD, DMC, TRA, DP3 và các ticker tiếp theo. Không được viết logic dạng `if ticker == "DHG"`; mọi ngoại lệ theo doanh nghiệp phải nằm trong `ticker_metadata`, `company_profile`, `source_manifest` hoặc `approved_assumptions`.

---

## 1. Lỗi nghiêm trọng đang thấy trực tiếp trên PDF/HTML hiện tại

### 1.1. Trạng thái báo cáo và khuyến nghị sai chuẩn

- Header và sidebar đang ghi `ĐANG HOÀN THIỆN`, nhưng vẫn render thành báo cáo PDF như một output hoàn chỉnh.
- Không có rating `BUY / HOLD / SELL / TRUNG LẬP` theo chính sách khuyến nghị.
- Không có giá mục tiêu, giá hiện tại, upside/downside, tổng tỷ suất lợi nhuận, dividend yield.
- Phần `Khuyến cáo` lại viết như disclaimer pháp lý chung, không phải kết luận đầu tư.

**Yêu cầu sửa:**

- Nếu chưa có target price hoặc gate chưa pass, chỉ được xuất `draft_review.html/pdf`, không được xuất final.
- Nếu đủ dữ liệu, bắt buộc tính `target_price`, `current_price`, `upside`, `dividend_yield`, `total_return`, sau đó map rating theo policy.
- Sidebar phải hiển thị rating thật, ví dụ `MUA`, `TRUNG LẬP`, `BÁN`, không dùng `ĐANG HOÀN THIỆN` trong bản final.

---

### 1.2. Dữ liệu thị trường gần như trống

Các trường sau đang để `—` dù về nguyên tắc phải lấy được từ nguồn giá/thị trường hoặc tính được:

- Giá hiện tại.
- Giá mục tiêu.
- Upside/downside.
- Vốn hóa.
- Số lượng cổ phiếu.
- P/E, P/B, EV/EBITDA, EV/FCF, P/S.
- Cổ tức/cp, suất sinh lợi cổ tức.
- Diễn biến giá YTD/1T/3T/12T.
- Biểu đồ giao dịch.
- Kế hoạch doanh thu/LNTT 2026.
- Tài sản và vốn chủ sở hữu Q1/2026.

**Yêu cầu sửa:**

- Tạo `MarketSnapshotArtifact` trước khi render report.
- Bắt buộc có: `last_price`, `as_of_date`, `market_cap`, `shares_outstanding`, `free_float/foreign_room nếu có`, `52w high/low`, `price_return_ytd_1m_3m_12m`, `volume`, `index comparison`.
- Nếu nguồn chính không có dữ liệu, fallback theo thứ tự: HOSE/HNX/disclosure → StoxPlus/FiinTrade nếu có → CafeF/Vietstock → vnstock chỉ làm nguồn phụ.
- Trường chỉ được để trống nếu thật sự công ty không có số liệu đó hoặc tất cả nguồn đều thiếu; khi thiếu phải ghi ở internal audit, không hiển thị dấu `—` tràn lan trong client-facing report.

---

### 1.3. Không có citation và nguồn tham khảo cụ thể

- PDF có mục `Nguồn tham khảo chính` nhưng để trống.
- HTML không chứa citation/source tag rõ ràng.
- Các nhận định như áp lực API, tỷ giá, ETC/OTC, GMP-EU, generic, đấu thầu thuốc không gắn với bài báo, báo cáo thường niên, nghị quyết, BCTC hoặc disclosure cụ thể.
- Báo cáo không chứng minh dữ liệu đến từ đâu, không có evidence table client-facing.

**Yêu cầu sửa:**

- Tạo `SourceEvidenceArtifact` bắt buộc trước khi viết report.
- Mỗi factual claim quan trọng phải gắn `source_id`, `source_type`, `publisher`, `date`, `url/file`, `excerpt`, `confidence`.
- Với báo cáo PDF client-facing: dùng citation ngắn dạng `[BCTN 2025]`, `[BCTC Q1/2026]`, `[HOSE, ngày ...]`, `[CafeF, ngày ...]`.
- Full source manifest để ở artifact JSON/appendix, không nhồi thuật ngữ backend vào thân báo cáo.
- Không được dùng citation chung chung kiểu `vnstock` hoặc `Vietnam Pharma Equity Research`.

---

### 1.4. Narrative quá mỏng, chưa đạt chuẩn chuyên viên phân tích

- Nhiều mục chỉ có 1-3 câu, chưa đủ 300 chữ/phần theo mục tiêu.
- Phần `Triển vọng đầu tư`, `Động lực biên lợi nhuận`, `Sự kiện trọng yếu`, `Rủi ro` đều chung chung, không kể câu chuyện của số liệu.
- Không có phân tích chuyên sâu về vì sao doanh thu 2024 giảm, vì sao 2025 phục hồi, chất lượng lợi nhuận, cash conversion, working capital, tồn kho, kênh ETC/OTC, chính sách đấu thầu, API/tỷ giá, danh mục sản phẩm, GMP-EU.
- Không có liên kết rõ giữa sự kiện kinh doanh và tác động lên revenue, margin, CAPEX, NWC, FCFF, FCFE, multiple.

**Yêu cầu sửa:**

- Các phần phân tích chính phải có tối thiểu 300 chữ tiếng Việt/phần:
  - Investment thesis.
  - Business update/company overview.
  - Financial performance.
  - Forecast & driver-based assumptions.
  - Valuation.
  - Risks & catalysts.
- Mỗi phần phải có ít nhất 3 lớp: dữ kiện định lượng → nguyên nhân/driver → tác động định giá.
- Không viết câu chung chung nếu chưa có số liệu hoặc nguồn.

---

### 1.5. Driver-based modeling hiện chỉ là hình thức

Bảng `ĐỘNG LỰC DỰ PHÓNG CHÍNH` hiện có nhiều dòng 0.0%:

- Tăng trưởng doanh thu: 0.0%.
- Biên lợi nhuận gộp: 0.0%.
- SG&A/doanh thu: 0.0%.
- Khấu hao/doanh thu: 0.0%.
- Capex/doanh thu: 0.0%.

Trong khi narrative lại nói mô hình dựa trên driver. Đây là mâu thuẫn nghiêm trọng.

**Yêu cầu sửa:**

- Tạo `DriverAssumptionArtifact` thật, gồm:
  - historical median/min/max;
  - analyst/base assumption;
  - bear/base/bull;
  - source/evidence;
  - linked financial line item;
  - valuation impact.
- Không cho phép driver quan trọng bằng 0.0% nếu historical data có thể tính được.
- Các driver tối thiểu: revenue growth, gross margin, SG&A/revenue, EBIT margin, D&A/revenue, CAPEX/revenue, DSO, DIO, DPO, NWC/revenue, tax rate, debt/EBITDA, net borrowing, payout ratio.

---

### 1.6. Forecast chưa phải forecast

- Bảng hiện chỉ có 2021FY-2025FY, không có 2026F-2030F.
- Không có forecast horizon 5 năm như yêu cầu DCF.
- Không có bảng doanh thu, EBIT, NOPAT, D&A, CAPEX, ΔNWC, FCFF, FCFE dự phóng.
- Không có working capital schedule.
- Không có debt schedule.
- Không có dividend schedule.
- Không có cash sweep/equity roll-forward.

**Yêu cầu sửa:**

- Forecast phải chạy theo thứ tự:
  1. Chuẩn hóa dữ liệu lịch sử.
  2. Tính driver lịch sử.
  3. Lập bear/base/bull assumptions.
  4. Forecast revenue, gross profit, SG&A, EBIT, EBITDA.
  5. Forecast D&A, CAPEX.
  6. Forecast working capital: DSO/DIO/DPO, NWC, ΔNWC.
  7. Forecast debt schedule và net borrowing.
  8. Forecast interest expense.
  9. Forecast tax và net income.
  10. Forecast dividend schedule.
  11. Build cash/equity roll-forward.
  12. Build FCFF và FCFE.
  13. Run valuation 60% FCFF / 40% FCFE.
  14. Run sensitivity và gates.

---

### 1.7. DCF/valuation chưa đủ điều kiện xuất target price

Hiện báo cáo nói dùng FCFF và kiểm tra bằng P/E/P/B/EV/EBITDA/EV/FCF nhưng không có:

- FCFF DCF summary.
- FCFE DCF summary.
- Cost of equity/Re.
- WACC components.
- Terminal growth rationale.
- Terminal value weight.
- EV to equity bridge.
- Net debt bridge.
- Price_FCFF.
- Price_FCFE.
- Blend 60% FCFF / 40% FCFE.
- Multiples peer group.
- Target price.

**Yêu cầu sửa:**

- Tách rõ FCFF và FCFE:
  - `FCFF = EBIT x (1 - tax) + D&A - CAPEX - ΔNWC`, chiết khấu bằng WACC.
  - `FCFE = NI + D&A - CAPEX - ΔNWC + Net Borrowing`, chiết khấu bằng Re.
- Target price chính:
  - `Target Price = 60% x Price_FCFF + 40% x Price_FCFE`.
- Bắt buộc có valuation bridge:
  - PV explicit FCFF/FCFE.
  - PV terminal value.
  - Enterprise value.
  - Net debt/cash/short-term investments.
  - Equity value.
  - Diluted shares.
  - Value per share.
- Nếu thiếu shares outstanding hoặc current price, block rating.

---

### 1.8. Sensitivity analysis chưa có giá trị thực

Bảng sensitivity hiện chỉ có stress giả định nhưng `Target price` và `Upside/downside` đều là `—`.

**Yêu cầu sửa:**

- Bắt buộc có tối thiểu:
  - WACC x terminal growth matrix cho FCFF.
  - Re x terminal growth matrix cho FCFE.
  - Revenue CAGR x EBIT/gross margin sensitivity.
  - Scenario table Bear/Base/Bull có target price và rating implication.
  - Peer multiple sensitivity: EPS x target P/E hoặc EBITDA x EV/EBITDA.
- Tính `terminal_value_weight`; nếu >70% EV thì flag internal và diễn giải trong valuation risk.
- Không render sensitivity table nếu không có kết quả định lượng.

---

### 1.9. Bảng số liệu có lỗi logic và thiếu tính toán

Các lỗi cụ thể quan sát từ output mẫu DHG nhưng phải sửa ở cấp pipeline chung:

- `Số lượng cổ phiếu (triệu)` đang bằng 0 cho toàn bộ 2021-2025, nhưng EPS vẫn có số. Đây là lỗi nghiêm trọng.
- P/E, P/B, EV/EBITDA, EV/FCF, P/S đều trống dù có thể tính nếu có giá và market cap.
- WACC trong bảng ratio trống nhưng bảng driver lại có WACC 13.8%.
- Nợ ròng/EBITDA trống dù có nợ ròng và EBITDA ở nhiều năm.
- Change in working capital trống toàn bộ, nhưng FCF vẫn được tính.
- Cổ tức trống toàn bộ, dividend yield trống.
- Doanh thu tài chính trống dù chi phí tài chính có số.
- `Capex` đang hiển thị số dương nhưng chưa rõ đây là CAPEX positive hay CAPEX signed từ CFS.

**Yêu cầu sửa:**

- Tạo `NumericConsistencyGate` trước render:
  - EPS ≈ Net income / shares.
  - FCF/FCFF reconcile với CFO/CAPEX/interest/tax.
  - Nợ ròng = interest-bearing debt - cash - short-term investments.
  - P/E = price / EPS.
  - P/B = price / BVPS.
  - EV/EBITDA = EV / EBITDA.
  - Dividend yield = DPS / price.
- Nếu shares = 0 hoặc missing nhưng EPS có số, gate phải fail.
- Không được âm thầm render dấu `—` nếu metric có thể tính từ dữ liệu có sẵn.

---

### 1.10. Không có biểu đồ trong HTML/PDF

HTML hiện không có `img`, `svg`, hoặc `canvas`; PDF vì vậy không có biểu đồ. Điều này lệch chuẩn IMP, trong đó có biểu đồ giao dịch, biểu đồ doanh thu/LNST, cơ cấu doanh thu, tăng trưởng theo kênh.

**Yêu cầu sửa:**

- Tạo chart artifact trước render, lưu PNG/SVG cố định.
- Biểu đồ bắt buộc:
  - Giá cổ phiếu + volume trong sidebar trang 1.
  - Revenue & net profit hoặc revenue & EBIT margin.
  - Gross margin/EBIT margin trend.
  - Forecast revenue/EBIT/FCFF.
  - Sensitivity heatmap hoặc matrix table.
- Quy tắc layout:
  - Biểu đồ nhỏ, width 40-55% content area.
  - Đặt float left/right hoặc trong 2-column grid.
  - Không bao giờ phóng to full-width ở giữa nếu không phải sensitivity/valuation matrix.
  - Caption phải có nguồn.

---

### 1.11. Layout chưa giống mẫu IMP

- PDF hiện nhiều khoảng trắng lớn, đặc biệt trang 2 và trang 5.
- Header/cấu trúc đơn giản, chưa có branding/màu sắc/nhịp trình bày như IMP.
- Sidebar trang 1 thiếu biểu đồ, thiếu thống kê đầy đủ, thiếu analyst info/source.
- Các bảng rộng full-width liên tục, ít điểm nhấn thị giác.
- Không có footer chuyên nghiệp theo từng trang như mẫu IMP.
- Không có cover hoặc trang cuối disclaimer đầy đủ.

**Yêu cầu sửa:**

- Sử dụng HTML là single source of truth, PDF chỉ render từ HTML đã QA.
- Tạo layout theo page template:
  - Page 1: investment snapshot + sidebar + chart giá + financial summary.
  - Page 2: business update/company overview.
  - Page 3: financial performance + 2 biểu đồ nhỏ.
  - Page 4: forecast & driver assumptions.
  - Page 5: valuation FCFF/FCFE + bridge.
  - Page 6: sensitivity + scenario + peer check.
  - Page 7: catalysts & risks.
  - Page 8: conclusion + quality summary + sources + disclaimer.
- Dùng CSS page-break rõ, tránh trang trắng/thừa khoảng trống.
- Footer/header thống nhất: ticker, date, project name, page number.

---

### 1.12. Font tiếng Việt hiện chưa lỗi nhưng vẫn chưa có cơ chế bảo đảm

PDF mẫu hiện render được tiếng Việt, nhưng CSS đang phụ thuộc font stack. Nếu chạy trên môi trường khác, nguy cơ lỗi dấu vẫn còn.

**Yêu cầu sửa:**

- Embed hoặc kiểm soát font hỗ trợ tiếng Việt ổn định: Noto Sans/DejaVu Sans.
- Thêm visual QA render test: xuất PNG từng trang và kiểm tra không có tofu/ô vuông/mất dấu.
- Không dùng font không chắc hỗ trợ tiếng Việt.

---

## 2. Kế hoạch sửa theo phase cho Claude Code

### Phase 1 — Chặn xuất báo cáo final khi thiếu dữ liệu lõi

**Mục tiêu:** Không cho pipeline xuất một PDF có vẻ hoàn chỉnh nhưng thực tế thiếu valuation/rating/citation.

**Việc cần làm:**

- Thêm `ReportExportGate` trước bước HTML/PDF export.
- Điều kiện final:
  - Có current price.
  - Có target price.
  - Có upside/downside.
  - Có rating.
  - Có shares outstanding hợp lệ.
  - Có valuation result reproducible.
  - Có citation coverage đạt ngưỡng.
  - Numeric consistency pass.
- Nếu fail, output phải là draft review, không dùng template client-facing final.

**Acceptance:** Không còn PDF final nào ghi `ĐANG HOÀN THIỆN` nhưng vẫn trông như báo cáo hoàn chỉnh.

---

### Phase 2 — Bổ sung MarketSnapshotArtifact và dữ liệu giá

**Mục tiêu:** Lấp toàn bộ khoảng trống sidebar và metric định giá thị trường.

**Việc cần làm:**

- Build `market_snapshot.py`:
  - lấy giá gần nhất;
  - market cap;
  - shares outstanding;
  - 52-week range;
  - YTD/1M/3M/12M return;
  - volume;
  - benchmark return nếu có.
- Tạo price chart artifact dạng PNG/SVG nhỏ.
- Thêm cache và provenance cho từng field.

**Acceptance:** Sidebar không còn các dòng `Giá hiện tại`, `Vốn hóa`, `Số lượng cổ phiếu`, `Diễn biến giá` bị trống nếu nguồn có thể lấy được.

---

### Phase 3 — Chuẩn hóa forecast driver-based thật

**Mục tiêu:** Biến phần driver từ text trang trí thành forecast engine có số liệu.

**Việc cần làm:**

- Tạo `ForecastArtifact` gồm historical + forecast 5 năm.
- Tính historical drivers: revenue growth, gross margin, SG&A/revenue, EBIT margin, tax rate, D&A/revenue, CAPEX/revenue, DSO/DIO/DPO, NWC/revenue, payout ratio, net borrowing.
- Sinh Bear/Base/Bull assumptions có nguồn và lý do.
- Không cho phép default 0.0% ở các driver quan trọng.

**Acceptance:** Bảng `ĐỘNG LỰC DỰ PHÓNG CHÍNH` có số thật, có Bear/Base/Bull, có link tới dòng tài chính và valuation impact.

---

### Phase 4 — Thêm working capital, debt, dividend, cash sweep

**Mục tiêu:** Làm forecast đủ điều kiện tính FCFF/FCFE.

**Việc cần làm:**

- Build `working_capital_schedule.py`:
  - DSO, DIO, DPO, NWC, ΔNWC.
- Build `debt_schedule.py`:
  - beginning debt, new borrowing, repayment, ending debt, net borrowing, interest expense.
- Build `dividend_schedule.py`:
  - DPS, payout ratio, dividends paid, retained earnings impact.
- Build `cash_sweep.py`:
  - beginning cash + CFO - CAPEX - dividends + net borrowing + equity issuance +/- other = ending cash.

**Acceptance:** Không còn `Thay đổi vốn lưu động`, `Cổ tức`, `Thay đổi nợ ròng` trống hàng loạt nếu có đủ dữ liệu lịch sử hoặc proxy hợp lệ.

---

### Phase 5 — Viết lại valuation engine theo FCFF/FCFE 60/40

**Mục tiêu:** Tính được target price chính thức và giải thích được.

**Việc cần làm:**

- Tách module:
  - `fcff_valuation.py`.
  - `fcfe_valuation.py`.
  - `valuation_blend.py`.
- FCFF dùng WACC; FCFE dùng Re.
- Không tự cap terminal growth nếu `WACC <= g` hoặc `Re <= g`; phải báo invalid.
- Tính terminal value weight.
- Tính EV-to-equity bridge.
- Tính target price 60/40.
- Tính relative valuation peer check.

**Acceptance:** Report có target price, upside/downside, rating, valuation bridge và lý do rating.

---

### Phase 6 — Bổ sung sensitivity và scenario đúng nghĩa

**Mục tiêu:** Sensitivity phải ra giá mục tiêu, không chỉ là bảng giả định.

**Việc cần làm:**

- FCFF sensitivity: WACC x terminal growth.
- FCFE sensitivity: Re x terminal growth.
- Operating sensitivity: revenue CAGR x EBIT/gross margin.
- Scenario table: Bear/Base/Bull với target price, upside/downside, rating implication.
- Peer sensitivity: EPS x P/E hoặc EBITDA x EV/EBITDA.

**Acceptance:** Không còn dòng `Target price —` trong bảng sensitivity.

---

### Phase 7 — Viết lại report narrative như analyst thật

**Mục tiêu:** Báo cáo phải có insight, không chỉ liệt kê số liệu.

**Việc cần làm:**

- Cập nhật prompt/report writer contract:
  - mỗi phần chính tối thiểu 300 chữ;
  - phải có số liệu cụ thể;
  - phải giải thích nguyên nhân;
  - phải nêu tác động lên forecast/valuation;
  - phải có citation.
- Với mỗi phần, writer nhận `section_context` gồm:
  - 5-8 số liệu chính;
  - driver quan trọng;
  - source list;
  - valuation impact;
  - risk/catalyst liên quan.
- Không cho writer tự bịa dữ liệu; chỉ diễn giải artifact.

**Acceptance:** Các mục `Triển vọng đầu tư`, `Động lực biên lợi nhuận`, `Forecast`, `Valuation`, `Risk` không còn 1-3 câu chung chung.

---

### Phase 8 — Thêm citation/source rendering gọn trong PDF

**Mục tiêu:** Có nguồn rõ nhưng không làm rối báo cáo.

**Việc cần làm:**

- Render citation ngắn trong đoạn: `[BCTC 2025]`, `[HOSE]`, `[BCTN]`, `[Tin doanh nghiệp]`.
- Cuối báo cáo có bảng `Nguồn tham khảo chính` gồm 5-10 nguồn quan trọng.
- Full source manifest để ở JSON artifact.
- Citation gate kiểm tra:
  - factual claim có citation;
  - numeric claim map tới fact_id;
  - source không stale;
  - URL/file tồn tại.

**Acceptance:** `Nguồn tham khảo chính` không còn trống; không có citation chung chung kiểu backend.

---

### Phase 9 — Sửa layout HTML/PDF theo mẫu IMP

**Mục tiêu:** PDF chuyên nghiệp, nhiều dữ liệu, không phóng biểu đồ to ở giữa.

**Việc cần làm:**

- Tạo component CSS:
  - `two-column-grid`.
  - `sidebar-chart-card`.
  - `small-chart-left/right`.
  - `metric-card`.
  - `valuation-bridge-table`.
  - `source-caption`.
- Chart rule:
  - chart width 40-55%; float left/right;
  - page-break-inside avoid;
  - max height cố định;
  - không center full page trừ sensitivity matrix.
- Table rule:
  - tối đa 8-10 cột;
  - nếu quá rộng, chuyển appendix hoặc chia bảng.
- Render QA:
  - render PDF thành PNG;
  - kiểm tra font tiếng Việt;
  - kiểm tra không có chart quá to;
  - kiểm tra không có trang quá trống.

**Acceptance:** Output nhìn gần chuẩn IMP: sidebar có chart, phần chính có phân tích dài, chart nhỏ, bảng gọn, footer/header rõ.

---

## 3. Gate kiểm định bắt buộc trước khi xuất final

```text
source_gate == PASS
citation_gate == PASS
numeric_consistency_gate == PASS
forecast_artifact_gate == PASS
valuation_reproducibility_gate == PASS
sensitivity_gate == PASS
layout_render_gate == PASS
human_review_gate == APPROVED
```

Nếu một gate fail:

```text
report_status = NEEDS_REVIEW hoặc BLOCKED
export_final_pdf = false
export_final_html = false
allow_draft_export = true
```

Không được dùng warning backend trong PDF client-facing. Warning chi tiết nằm trong `eval_result.json`; PDF chỉ hiển thị quality summary ngắn nếu cần.

---

## 4. Checklist sửa lỗi áp dụng cho mọi ticker

Checklist này phải được triển khai theo hướng ticker-agnostic. DHG chỉ là ví dụ đầu vào để chứng minh lỗi; mọi item bên dưới phải pass cho bất kỳ ticker nào trong universe.

### 4.1. Report status và khuyến nghị

- [ ] Không xuất `final_report.html/pdf` nếu còn trạng thái `ĐANG HOÀN THIỆN`, `UNDER REVIEW`, `NEEDS_REVIEW` hoặc thiếu valuation chính.
- [ ] Với mọi ticker, rating chỉ được render khi có `current_price`, `target_price`, `upside/downside`, `dividend_yield` nếu có và `valuation_confidence`.
- [ ] Rating policy phải dùng chung: `BUY / HOLD / SELL / TRUNG LẬP / UNDER REVIEW`, map theo upside, tổng tỷ suất lợi nhuận, risk level và confidence.
- [ ] Không hard-code tên công ty, sàn, ngành, analyst, ngày báo cáo hoặc rating theo ticker.

### 4.2. Market snapshot và dữ liệu thị trường

- [ ] Tạo `MarketSnapshotArtifact` cho từng ticker trước render.
- [ ] Lấy/tính `last_price`, `as_of_date`, `market_cap`, `shares_outstanding`, `free_float` nếu có, `foreign_room` nếu có, `52w high/low`, `YTD/1M/3M/12M return`, `average_volume`, `benchmark_return`.
- [ ] Không để `—` ở các trường có thể lấy hoặc tính từ nguồn hợp lệ.
- [ ] Nếu thiếu thật, ghi vào `eval_result.json`; PDF client-facing chỉ ghi gọn “chưa đủ dữ liệu công bố” khi cần, không rải dấu `—` hàng loạt.
- [ ] Luôn kiểm tra consistency: `market_cap ≈ last_price × shares_outstanding`.

### 4.3. Financial facts và numeric consistency

- [ ] Không cho `shares_outstanding = 0` nếu EPS, market cap hoặc giá/cp có số.
- [ ] Tính được EPS, BVPS, P/E, P/B, EV/EBITDA, EV/FCF, net debt/EBITDA, ROE, ROA khi đủ dữ liệu.
- [ ] Chuẩn hóa đơn vị: tỷ VND, triệu cổ phiếu, VND/cp, %, lần. Presentation layer mới format, core không nhân/đổi đơn vị tùy tiện.
- [ ] Kiểm tra dấu CAPEX, debt, interest expense, dividend paid, COGS, SG&A trước forecast.
- [ ] Gate phải fail nếu số liệu nguồn mâu thuẫn lớn hoặc metric quan trọng bị tính từ dữ liệu thiếu.

### 4.4. Driver-based forecast

- [ ] Tạo `ForecastArtifact` 5 năm cho từng ticker, tối thiểu từ năm gần nhất đến `Y+5`.
- [ ] Tính driver lịch sử: revenue growth, gross margin, SG&A/revenue, EBIT margin, EBITDA margin, tax rate, D&A/revenue, CAPEX/revenue, DSO, DIO, DPO, NWC/revenue, payout ratio, debt/EBITDA, net borrowing.
- [ ] Sinh Bear/Base/Bull assumptions từ dữ liệu lịch sử, evidence mới và approved assumptions.
- [ ] Không render driver quan trọng bằng `0.0%` trừ khi thực sự hợp lý và có giải thích.
- [ ] Mỗi driver phải map vào financial line item và valuation impact.

### 4.5. Working capital, debt, dividend và cash sweep

- [ ] Dự phóng working capital bằng DSO/DIO/DPO, không dùng proxy mơ hồ nếu đủ dữ liệu bảng cân đối.
- [ ] Dự phóng nợ vay bằng debt roll-forward: beginning debt, new borrowing, repayment, net borrowing, ending debt.
- [ ] Chi phí lãi vay phải tính từ average debt × cost of debt, không tính theo doanh thu.
- [ ] Dự phóng cổ tức bằng payout/DPS/residual policy; không mặc định zero dividend khi thiếu dữ liệu.
- [ ] Equity roll-forward phải trừ cổ tức khỏi retained earnings.
- [ ] Cash sweep phải reconcile CFO, CAPEX, dividends, net borrowing, equity issuance và ending cash.

### 4.6. Valuation FCFF/FCFE 60/40

- [ ] Tính FCFF riêng và FCFE riêng cho từng ticker.
- [ ] FCFF chiết khấu bằng WACC; FCFE chiết khấu bằng Re. Không dùng lẫn dòng tiền và suất chiết khấu.
- [ ] Tính `Price_FCFF`, `Price_FCFE`, `Target_Price = 60% × Price_FCFF + 40% × Price_FCFE`.
- [ ] Có EV-to-equity bridge: EV, net debt/cash, short-term investments, minority interest nếu có, non-operating assets nếu có, diluted shares.
- [ ] Nếu `WACC <= g` hoặc `Re <= g`, valuation invalid và không xuất rating.
- [ ] Có relative valuation peer check theo taxonomy ngành dược/y tế Việt Nam, không so peer sai nhóm.

### 4.7. Sensitivity, scenario và peer check

- [ ] Có WACC × terminal growth matrix cho FCFF.
- [ ] Có Re × terminal growth matrix cho FCFE.
- [ ] Có Bear/Base/Bull với target price, upside/downside và rating implication.
- [ ] Có sensitivity operating driver: revenue growth, gross/EBIT margin, CAPEX/NWC.
- [ ] Có peer sensitivity: EPS × target P/E hoặc EBITDA × EV/EBITDA nếu dữ liệu peer đủ.
- [ ] Không render sensitivity nếu các ô giá mục tiêu vẫn là `—`.

### 4.8. Narrative analyst-grade

- [ ] Mỗi phần chính tối thiểu 300 chữ: investment thesis, business/company update, financial performance, forecast & assumptions, valuation, risks & catalysts.
- [ ] Mỗi phần phải theo logic: dữ kiện định lượng → nguyên nhân/driver → tác động forecast/valuation → rủi ro cần theo dõi.
- [ ] Narrative phải dùng thông tin mới từ nhiều nguồn: BCTC/BCTN, công bố sở giao dịch, nghị quyết, tin doanh nghiệp, dữ liệu thị trường, ngành/đấu thầu/quy định nếu liên quan.
- [ ] Không viết chung chung kiểu “nền tảng ổn định”, “triển vọng tích cực” nếu không có số liệu và nguồn.
- [ ] Không để nội dung backend như `Tier`, `database`, `artifact`, `gate warning` trong PDF client-facing.

### 4.9. Citation và source rendering

- [ ] Mỗi claim định lượng phải map tới `canonical_fact`, `computed_metric`, `valuation_result` hoặc `approved_assumption`.
- [ ] Mỗi claim định tính quan trọng phải có source cụ thể: BCTN, BCTC, HOSE/HNX/UPCOM, nghị quyết, tin doanh nghiệp, nguồn ngành.
- [ ] PDF chỉ hiển thị citation ngắn gọn; full source nằm trong `source_manifest.json`.
- [ ] Mục `Nguồn tham khảo chính` phải có 5-10 nguồn quan trọng, không được để trống.
- [ ] Không dùng source chung chung kiểu `vnstock`, `database`, `market data` nếu không truy ngược được.

### 4.10. Chart và layout PDF/HTML

- [ ] Tạo chart artifact cho từng ticker: price + volume, revenue/net profit, margin trend, forecast/FCFF, sensitivity matrix.
- [ ] Biểu đồ phải nhỏ, đặt trong sidebar hoặc cột trái/phải; width khoảng 40-55% vùng nội dung, trừ sensitivity/valuation matrix.
- [ ] Không phóng to chart full-width ở giữa nếu không cần thiết.
- [ ] Layout theo tinh thần IMP: sidebar rõ, bảng tài chính cô đọng, nhiều đoạn phân tích sâu, chart nhỏ có caption nguồn.
- [ ] Render PDF thành PNG để QA: font tiếng Việt, chart không vỡ, bảng không tràn, không có trang trống lớn.

## 5. Definition of Done

Một output cho bất kỳ ticker nào được coi là đạt khi:

1. PDF/HTML có rating rõ ràng và target price tính được.
2. Không còn trường định lượng quan trọng bị `—` nếu có thể lấy/tính.
3. Forecast có đủ 5 năm và dựa trên driver thật.
4. Valuation có FCFF, FCFE và blend 60/40.
5. Sensitivity có kết quả target price, không phải bảng giả định rỗng.
6. Mỗi phần phân tích chính có insight tối thiểu 300 chữ, có số liệu và citation.
7. Biểu đồ được render nhỏ, đúng vị trí trái/phải, có nguồn.
8. Font tiếng Việt hiển thị đúng trong PDF.
9. Client-facing report không chứa thuật ngữ backend, warning kỹ thuật hoặc citation rối.
10. Nếu gate fail, hệ thống chỉ xuất draft review, không xuất final.
