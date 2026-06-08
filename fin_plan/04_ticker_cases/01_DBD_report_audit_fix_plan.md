# DBD Report Audit - lỗi còn tồn đọng và kế hoạch sửa cho Claude

**Ticker kiểm định:** DBD - Công ty CP Dược - Trang thiết bị Y tế Bình Định (Bidiphar)  
**File kiểm định:** `DBD_report.pdf`  
**Ngày kiểm định:** 2026-06-03  
**Vai trò kiểm định:** Senior Financial Analyst / Equity Research QA  
**Mục tiêu:** dùng DBD làm regression fixture để sửa lỗi chung cho toàn bộ report engine, không hard-code riêng cho DBD.  
**Kết luận:** bản hiện tại vẫn phải bị hạ trạng thái xuống `NEEDS_REVIEW` hoặc `BLOCKED`. Không được xuất `BÁN/MUA/GIỮ` như báo cáo final vì chưa pass source, numeric, valuation, forecast, sensitivity, layout và human-review gates.

---

## 0. Executive conclusion

Bản `DBD_report.pdf` đã có một số cải thiện so với các bản cũ: có sidebar, có target price, có forecast 2026F-2030F, có chart, có sensitivity và có danh sách nguồn cuối báo cáo. Tuy nhiên, báo cáo vẫn **không đủ tiêu chuẩn equity research final** vì các lỗi sau vẫn còn ở cấp hệ thống:

1. **Section bị gộp lung tung:** các phần business update, thesis, context, valuation, margin driver, event/risk bị trộn vào nhau; nhiều đoạn lặp lại; heading không khớp nội dung.
2. **Dữ liệu không cập nhật dù có nguồn công khai:** Q1/2026, kế hoạch 2026, cổ tức, phát hành riêng lẻ, ESOP và kế hoạch CAPEX 2026 bị bỏ trống hoặc không đưa vào mô hình.
3. **Sai logic P&L và EBIT/EBITDA:** bảng đang thiếu chi phí quản lý doanh nghiệp trong SG&A, làm EBITDA/EBIT margin bị thổi phồng; net income không reconcile với EBIT, interest và tax.
4. **EPS/shares không reconcile:** 2025 LNST 292 tỷ và 94 triệu cổ phiếu không thể ra EPS 2,674 VND; số này ngầm dùng mẫu số khoảng 109 triệu cổ phiếu nhưng bảng lại ghi 94 triệu.
5. **FCFF/FCFE chưa audit được:** không có valuation bridge, không có Re, WACC components, net debt bridge, terminal value weight, debt schedule, dividend schedule, share roll-forward.
6. **Sensitivity sai format và sai ý nghĩa:** bảng ghi `VND/cp` nhưng hiển thị `%`; base WACC 13.8% không nằm trong ma trận 8%-12%; bảng gọi là target price nhưng thực chất là FCFF sensitivity.
7. **Cổ tức và total return sai:** report ghi dividend yield `—` dù công ty công bố cổ tức tiền mặt 20%, tương đương 2,000 VND/cp; tổng return vì vậy bị tính bằng downside thuần.
8. **Corporate action bị bỏ qua:** kế hoạch phát hành riêng lẻ 23.3 triệu cổ phiếu và ESOP 1.5 triệu cổ phiếu không được mô hình hóa, làm sai diluted shares, EPS, BVPS, net cash và target price/cp.
9. **Citation vẫn chưa đạt chuẩn:** nguồn cuối báo cáo là nguồn chung chung `vnstock/VCI`; không có claim-level citation tới BCTC, tài liệu ĐHĐCĐ, VSDC, HOSE hoặc source manifest.
10. **Layout PDF lỗi:** có trang gần như trống, page 1 mâu thuẫn target, biểu đồ nhỏ/nhãn chồng, bảng tràn/cột dính, nhiều phần copy-paste và caption nguồn chung chung.

---

## 1. Nguồn kiểm chứng bên ngoài đã đối chiếu cho DBD

> Lưu ý cho Claude: các URL này phải được đưa vào `source_manifest` khi chạy lại pipeline. Không dùng các số dưới đây bằng cách hard-code; hãy ingest, normalize và reconcile thành canonical facts.

| Nhóm nguồn | Nội dung kiểm chứng chính | URL |
|---|---|---|
| Bidiphar IR - Financial statements | Có BCTC hợp nhất Q1/2026, BCTC riêng Q1/2026, BCTC hợp nhất 2025 sau kiểm toán, BCTC riêng 2025 sau kiểm toán. | https://bidiphar.com/category/quan-he-co-dong/bao-cao-tai-chinh/ |
| BCTC hợp nhất 2025 sau kiểm toán | Doanh thu bán hàng 2025: 1,946.613 tỷ; giảm trừ: 81.233 tỷ; doanh thu thuần: 1,865.380 tỷ; giá vốn: 981.001 tỷ; lợi nhuận gộp: 884.379 tỷ; chi phí bán hàng: 418.308 tỷ; chi phí quản lý: 139.794 tỷ; LNTT: 346.082 tỷ; LNST: 291.940 tỷ. | https://bidiphar.com/wp-content/uploads/2026/03/bao-cao-tai-chinh-hop-nhat-nam-2025-sau-kiem-toan-1774620839.pdf |
| BCTC hợp nhất Q1/2026 | Tổng tài sản 31/03/2026: 2,687.422 tỷ; vốn chủ sở hữu: 1,816.805 tỷ; doanh thu thuần Q1/2026: 448.087 tỷ; LNST Q1/2026: 80.298 tỷ. | https://bidiphar.com/wp-content/uploads/2026/04/bao-cao-tai-chinh-hop-nhat-quy-1-nam-2026-1777112034.pdf |
| Bidiphar - tin ĐHĐCĐ 2026 | 2025 tổng doanh thu 1,947 tỷ, LNTT 344 tỷ; cổ tức 20% tiền mặt = 2,000 VND/cp; mục tiêu 2026 doanh thu 2,090 tỷ, LNTT 375 tỷ; Q1/2026 doanh thu thuần khoảng 448 tỷ, LNST hơn 80.2 tỷ, tổng tài sản 2,687 tỷ, VCSH 1,816 tỷ; kế hoạch giải ngân đầu tư hơn 548 tỷ trong tổng kế hoạch 744 tỷ. | https://bidiphar.com/bidiphar-dbd-to-chuc-thanh-cong-dhdcd-2026/ |
| VSDC | DBD là cổ phiếu phổ thông giao dịch trên HOSE, mã ISIN VN000000DBD0, mệnh giá 10,000 đồng; ngày đăng ký cuối cùng họp ĐHĐCĐ 2026 là 20/03/2026. | https://www.vsd.vn/vi/ad/192315 |
| Bidiphar - niêm yết HOSE | DBD chính thức niêm yết 52.379 triệu cổ phiếu trên HOSE ngày 15/06/2018, mã DBD. | https://bidiphar.com/bidiphar-chinh-thuc-niem-yet-co-phieu-tai-hose/ |
| MekongASEAN / tài liệu ĐHĐCĐ 2026 | Dự trình phát hành riêng lẻ 23.3 triệu cổ phiếu, dự kiến thu 1,165 tỷ; cổ tức 2025 20% tiền mặt = 2,000 VND/cp; hơn 94.4 triệu cổ phiếu đang lưu hành; ESOP 1.5 triệu cp chia 2 đợt. | https://mekongasean.vn/bidiphar-muon-huy-dong-hon-1100-ty-dong-don-luc-cho-hai-nha-may-duoc-54225.html |
| CafeF market snapshot | Market price quanh 50,100 VND ngày 02/06/2026, vốn hóa khoảng 4,687 tỷ, shares outstanding khoảng 93.55 triệu theo trang CafeF; cần reconcile với official share capital/Q1 BCTC. | https://cafef.vn/du-lieu/hose/dbd-cong-ty-co-phan-duoc-trang-thiet-bi-y-te-binh-dinh.chn |

---

## 2. Những điểm trong report hiện tương đối đúng nhưng vẫn cần source/gate

1. **Sàn giao dịch:** report ghi `HOSE: DBD`, phù hợp nguồn VSDC/Bidiphar.
2. **Doanh thu thuần 2025 1,865 tỷ và LNST 292 tỷ:** khớp BCTC hợp nhất 2025 sau kiểm toán nếu hiểu đúng là **doanh thu thuần**, không phải tổng doanh thu bán hàng. Report cần ghi rõ `doanh thu thuần`, vì Bidiphar công bố tổng doanh thu 2025 khoảng 1,947 tỷ.
3. **Biên gộp 2025 47.4%:** khớp công thức 884.379 / 1,865.380.
4. **Target blend arithmetic:** `0.60 x 35,767 + 0.40 x 22,372 = 30,409` đúng về số học. Vấn đề là Price_FCFF và Price_FCFE chưa có bridge đủ để audit.
5. **Market cap 4,743 tỷ và shares 94 triệu:** có thể gần đúng nếu dùng giá 50,200 và khoảng 94.5 triệu cổ phiếu. Nhưng report phải ghi rõ timestamp giá và số cổ phiếu chính xác, không làm tròn quá mạnh.

---

## 3. Blocker cấp hệ thống cần sửa ngay

### BLOCKER-01 - Section assembly bị gộp lung tung, heading không khớp nội dung

**Hiện trạng quan sát trong PDF:**

- Page 1 chỉ có một dòng cover: `DBD | BÁN | Giá mục tiêu: — | Upside: —` và gần như trống.
- Page 2 vừa là snapshot, vừa company overview, vừa investment thesis, vừa business update, vừa current context.
- Page 3 tiếp tục `Bối cảnh hiện tại` rồi nhảy sang `Động lực tăng trưởng`, cuối trang lại chen `Tóm tắt tài chính`.
- Page 5 heading `Cập nhật hoạt động kinh doanh` nhưng chủ yếu là chart + `Triển vọng đầu tư`; heading `Động lực biên lợi nhuận` lại chứa đoạn valuation/DCF; heading `Sự kiện trọng yếu` lại là risk/catalyst narrative.
- Page 8 heading `Dự phóng và định giá` chứa cả valuation, sensitivity, cảnh báo terminal value và text lặp lại từ phần trước.
- Page cuối chỉ còn risk table sơ sài, disclaimer và source list chung chung.

**Vì sao sai:** report builder đang ghép các section bằng text block thay vì structured report contract. Heading không còn là semantic boundary; nội dung bị duplicated và mất logic analyst.

**Yêu cầu sửa:**

- Tạo `ReportSectionContract` với `section_id`, `section_title`, `allowed_content_types`, `required_artifacts`, `max_words`, `chart_slots`, `table_slots`.
- Không cho section lấy nhầm nội dung của section khác.
- Mỗi section phải được build từ đúng artifact:
  - `snapshot` -> market + valuation summary;
  - `company_overview` -> company profile + business model;
  - `financial_performance` -> historical facts + ratio trends;
  - `forecast` -> ForecastArtifact + driver assumptions;
  - `valuation` -> ValuationResult;
  - `sensitivity_peer` -> SensitivityArtifact + PeerArtifact;
  - `risk_catalyst` -> CatalystRiskArtifact.
- Add `section_coherence_gate`: reject nếu heading và content classification lệch nhau.

**Acceptance:** không còn đoạn valuation trong heading `Động lực biên lợi nhuận`; không còn risk narrative trong `Sự kiện trọng yếu`; không còn section lặp lại cùng đoạn driver-based.

---

### BLOCKER-02 - Report xuất rating `BÁN` dù vẫn là draft/needs review

**Hiện trạng:** PDF xuất `BÁN`, target price 30,409 VND, downside -39.4% như báo cáo final. Nhưng trong thân bài có nhiều câu như `cần soi kỹ`, `giả định trọng yếu cần chuyên viên phê duyệt`, `khi dữ liệu peer đủ tin cậy`, `kết quả định giá sơ bộ`.

**Vì sao sai:** nếu assumptions, debt schedule, dividend schedule, source/citation và valuation reproducibility chưa pass, report phải là `UNDER_REVIEW` hoặc `NEEDS_REVIEW`, không được xuất `BÁN/MUA/GIỮ`.

**Yêu cầu sửa:**

- Thêm hard gate trước recommendation:

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

- Nếu bất kỳ gate fail: `rating_model_output = UNDER_REVIEW`, `export_final_pdf = false`, chỉ cho phép `draft_review.pdf/html`.
- Không dùng wording `BÁN` trong sidebar khi final gate chưa pass.

**Acceptance:** DBD hiện tại phải bị block final export.

---

### BLOCKER-03 - Page 1 mâu thuẫn target price/upside với page 2

**Hiện trạng:** page 1 ghi `Giá mục tiêu: — | Upside: —`, page 2 lại ghi target price 30,409 và upside -39.4%.

**Vì sao sai:** các component đang đọc field khác nhau; `valuation_result` chưa phải single source of truth.

**Yêu cầu sửa:**

- Dùng duy nhất `valuation_result.target_price`, `valuation_result.current_price`, `valuation_result.upside_downside`.
- Add render consistency test: mọi occurrences của target/upside trong PDF/HTML phải khớp trong tolerance.
- Nếu một component thiếu target/upside thì block render final.

**Acceptance:** page title, sidebar, valuation section, conclusion và footer đều hiển thị cùng một target/upside hoặc cùng trạng thái `UNDER_REVIEW`.

---

### BLOCKER-04 - Source/citation vẫn không đạt chuẩn

**Hiện trạng:** cuối báo cáo chỉ có source list chung chung kiểu `Dữ liệu thị trường DBD - vnstock VCI`, `Bảng cân đối kế toán - dữ liệu thị trường VCI`, `Mô hình định giá - tính toán nội bộ`. Trong thân bài không có claim-level citations.

**Vì sao sai:** nguồn VCI/vnstock chỉ nên là market/provisional data. Financial facts chính phải được reconcile với official filings. Các claim về ETC/OTC, API, GMP-EU, cổ tức, phát hành riêng lẻ, ESOP, kế hoạch 2026 và Q1/2026 đều cần source cụ thể.

**Yêu cầu sửa:**

- Tạo bắt buộc `source_manifest.json`, `claim_ledger.json`, `evidence_pack.json` trước khi sinh narrative.
- Mỗi claim quan trọng phải map về `source_id`, `fact_id` hoặc `valuation_result.field_path`.
- PDF chỉ hiển thị citation tag ngắn như `[BCTC HN Q1/2026]`, `[BCTC HN 2025 audited]`, `[ĐHĐCĐ 2026]`, `[VSDC 2026]`.
- Không xuất claim nếu không có source hoặc source mismatch ticker/period.

**Acceptance:** `quantitative_claim_citation_coverage = 100%`, `fake_citation = 0`, `dangling_citation = 0`.

---

## 4. Lỗi dữ liệu và kiểm chứng DBD cụ thể

### DATA-01 - Q1/2026 bị bỏ trống dù official filing đã có

**Hiện trạng:** sidebar để `Tài sản Q1/2026 —`, `Vốn chủ sở hữu Q1/2026 —`. Report cũng không phân tích Q1/2026.

**Nguồn đối chiếu:** BCTC hợp nhất Q1/2026 công bố ngày 25/04/2026; Bidiphar cũng đăng tin ĐHĐCĐ 2026 nêu Q1/2026 doanh thu thuần khoảng 448 tỷ, LNST hơn 80.2 tỷ, tổng tài sản 2,687 tỷ, vốn chủ sở hữu 1,816 tỷ.

**Số đúng cần ingest:**

| Chỉ tiêu | Q1/2026 |
|---|---:|
| Doanh thu thuần | 448.087 tỷ VND |
| LNST | 80.298 tỷ VND |
| Tổng tài sản | 2,687.422 tỷ VND |
| Vốn chủ sở hữu | 1,816.805 tỷ VND |

**Yêu cầu sửa:** tạo `QuarterlySnapshotArtifact` và dùng trong sidebar + financial update. Nếu report date sau công bố Q1/2026, không được chỉ dùng FY2025.

---

### DATA-02 - Kế hoạch 2026 bị bỏ trống và forecast không so với guidance

**Hiện trạng:** sidebar để `Kế hoạch doanh thu 2026 —`, `Kế hoạch LNTT 2026 —`. Bảng forecast lại có 2026F doanh thu 1,982 tỷ nhưng không giải thích chênh lệch với kế hoạch công ty.

**Nguồn đối chiếu:** Bidiphar công bố mục tiêu 2026 doanh thu 2,090 tỷ và LNTT 375 tỷ.

**Vấn đề:**

- Report forecast 2026F net revenue 1,982 tỷ, thấp hơn guidance doanh thu 2,090 tỷ khoảng 5.2% nếu so trực tiếp.
- Report không nói forecast dùng net revenue hay total revenue.
- P&L forecast không trình bày PBT nên không so sánh được với kế hoạch LNTT.

**Yêu cầu sửa:**

- Tạo `ManagementGuidanceArtifact`.
- Phân biệt `gross sales/total revenue`, `net revenue`, `PBT`, `PAT`.
- Forecast section phải có bảng:

```text
2026 management guidance vs model forecast
revenue basis reconciliation: gross sales -> deductions -> net revenue
PBT guidance vs model PBT
```

**Acceptance:** không để blank nếu guidance đã có; nếu model forecast lệch guidance, narrative phải giải thích bằng driver.

---

### DATA-03 - Cổ tức bị bỏ trống dù công ty đã công bố

**Hiện trạng:** `Suất sinh lời cổ tức —`; bảng forecast dòng `Cổ tức/cp` và `Suất sinh lợi cổ tức` toàn `—`; narrative nói `suất cổ tức hiện chưa đủ dữ liệu công bố`.

**Nguồn đối chiếu:** Bidiphar công bố duy trì cổ tức 20% bằng tiền mặt năm 2025, tương đương 2,000 VND/cp. Với giá 50,200 VND, dividend yield xấp xỉ:

```text
2,000 / 50,200 = 3.98%
```

**Vì sao sai:** total return đang bằng downside thuần -39.4%, trong khi nếu tính dividend yield 12 tháng thì total return phải gần -35.4% trước các điều chỉnh khác.

**Yêu cầu sửa:**

- Ingest `DPS`, `dividend_policy`, `dividend_yield`, `cash_dividend`.
- Tính `total_return = price_return + expected_dividend_yield`.
- Cổ tức phải đi qua dividend schedule và equity roll-forward.
- Không mặc định zero dividend nếu công ty có lịch sử/định hướng trả cổ tức.

**Acceptance:** DBD phải hiển thị DPS 2,000 VND, dividend yield khoảng 4.0%, payout/cash dividend và impact lên total return.

---

### DATA-04 - Corporate actions trọng yếu bị bỏ qua: phát hành riêng lẻ và ESOP

**Hiện trạng:** forecast giữ `Số lượng cổ phiếu` = 94 triệu từ 2022 đến 2030; không có dilution/cash inflow/share issuance.

**Nguồn đối chiếu:** tài liệu ĐHĐCĐ 2026 và tin công bố cho biết:

- phát hành riêng lẻ 23.3 triệu cổ phiếu, giá không thấp hơn 50,000 VND/cp, dự kiến thu 1,165 tỷ;
- ESOP 1.5 triệu cổ phiếu chia 2 đợt;
- điều kiện ESOP gắn với GMP-EU nhà máy thuốc điều trị ung thư và nhà máy SVI.

**Vì sao sai:** đây là biến số cực lớn với DBD. Nó tác động trực tiếp tới diluted shares, EPS, BVPS, net cash, CAPEX funding, debt schedule, dividend capacity, WACC và target price/cp.

**Yêu cầu sửa:**

- Tạo `CorporateActionArtifact` gồm `private_placement`, `ESOP`, `cash_dividend`, `stock_dividend/bonus` nếu có.
- Forecast shares theo roll-forward:

```text
Beginning shares
+ private placement shares
+ ESOP shares
+ bonus/stock dividend shares
- treasury shares
= diluted ending shares
```

- Forecast cash:

```text
Cash inflow from private placement = issued shares x issue price
```

- Scenario hóa timing phát hành và dilution.

**Acceptance:** nếu có corporate action active, không được giữ shares constant toàn kỳ forecast.

---

### DATA-05 - CAPEX forecast 2026 thấp hơn kế hoạch đầu tư công bố, không có giải thích

**Hiện trạng:** report giả định `Capex / doanh thu = 8.3%`, 2026F CAPEX = 166 tỷ.

**Nguồn đối chiếu:** Bidiphar công bố kế hoạch đầu tư 2026 tổng 744 tỷ, dự kiến giải ngân hơn 548 tỷ.

**Vấn đề:** 2026F CAPEX 166 tỷ thấp hơn rất nhiều so với mức giải ngân đầu tư công bố. Nếu một phần là đầu tư tài chính, thiết bị, xây dựng cơ bản hoặc không phải CAPEX theo CFS thì phải reconcile. Hiện không có reconcile.

**Yêu cầu sửa:**

- Tạo `CapexPlanArtifact` từ tài liệu ĐHĐCĐ/IR.
- Phân biệt:
  - maintenance CAPEX;
  - growth CAPEX;
  - construction-in-progress;
  - investment budget/disbursement;
  - cash CAPEX in CFS.
- Forecast phải giải thích vì sao dùng 166 tỷ thay vì plan disbursement 548 tỷ.

**Acceptance:** CAPEX forecast có source, method và reconciliation với investment plan.

---

## 5. Lỗi numeric consistency và financial modeling

### NUMERIC-01 - EPS không reconcile với LNST và số cổ phiếu

**Hiện trạng:** 2025 LNST = 292 tỷ, shares = 94 triệu, EPS = 2,674 VND.

**Kiểm tra nhanh:**

```text
292,000 tỷ VND / 94 triệu cp ≈ 3,106 VND/cp
292,000 tỷ VND / 94.529 triệu cp ≈ 3,088 VND/cp
EPS 2,674 VND hàm ý shares ≈ 109.2 triệu cp
```

**Vì sao sai:** bảng hiển thị ending shares nhưng EPS có thể đang dùng weighted average/diluted shares khác. Report không nói rõ nên P/E, EPS growth và valuation per share không audit được.

**Yêu cầu sửa:**

- Tách rõ `ending_shares`, `weighted_avg_shares`, `diluted_shares`.
- Add gate:

```text
abs(EPS - NetIncomeToParent / WeightedAvgShares) <= tolerance
```

- Nếu không có weighted average shares, không tính EPS/P/E final.

**Acceptance:** mọi năm EPS/P/E reconcile với đúng share count.

---

### NUMERIC-02 - SG&A bị mapping sai: chi phí quản lý doanh nghiệp bị bỏ khỏi EBITDA/EBIT

**Hiện trạng:** bảng 2025 ghi `Chi phí bán hàng và quản lý = -418 tỷ`, trong khi BCTC hợp nhất 2025 có:

```text
Chi phí bán hàng: 418.308 tỷ
Chi phí quản lý doanh nghiệp: 139.794 tỷ
SG&A đúng = 558.102 tỷ
```

**Dấu hiệu sai trong report:**

- 2025 revenue = 1,865 tỷ.
- Report SG&A/revenue = 22.9%, gần đúng với selling expense/revenue, không phải SG&A/revenue.
- SG&A đúng phải xấp xỉ 29.9% doanh thu thuần.
- Report EBITDA 517 tỷ, EBIT 466 tỷ, EBIT margin 25.0%; nhưng nếu tính từ BCTC, operating profit 2025 là 349.128 tỷ, PBT 346.082 tỷ.

**Vì sao sai:** `selling_expense` bị gán nhãn thành `SG&A`, còn `general_admin_expense` bị bỏ khỏi operating forecast. Kết quả EBIT/EBITDA bị thổi phồng, làm FCFF sai.

**Yêu cầu sửa:**

- Sửa taxonomy:

```text
selling_expense.total
admin_expense.total
ga_expense.total
sga_total = selling_expense + admin_expense
```

- `EBIT` phải reconcile với official operating profit hoặc tính theo P&L đầy đủ.
- Add gate:

```text
Revenue - COGS - SellingExpense - AdminExpense + FinancialIncome - FinancialExpense + ShareOfAssociateProfit +/- Other = PBT before tax path
```

**Acceptance:** 2025 SG&A phải khoảng 558 tỷ nếu dùng BCTC hợp nhất; EBIT/operating profit phải không lệch material so với official P&L.

---

### NUMERIC-03 - Net income không reconcile với EBIT, interest và tax trong bảng forecast

**Hiện trạng:** 2026F report ghi:

```text
EBIT = 504
Interest = -4
Tax = -60
Net income = 320
```

Nếu chỉ lấy các dòng hiển thị thì:

```text
504 - 4 - 60 = 440, không phải 320
```

Năm 2025 cũng lệch: EBIT 466, interest -4, tax -54 nhưng LNST 292. Có dòng missing lớn không được trình bày.

**Vì sao sai:** P&L schedule không closed-form; các dòng bị thiếu/mapping sai nhưng report vẫn dùng để valuation.

**Yêu cầu sửa:**

- Bảng P&L phải có đầy đủ:
  - gross profit;
  - selling expense;
  - admin expense;
  - financial income;
  - financial expense;
  - share of associates/JV;
  - other income/expense;
  - PBT;
  - current tax;
  - deferred tax;
  - minority interest;
  - NPATMI.
- Add `pnl_reconciliation_gate` trước valuation.

**Acceptance:** PBT, tax và net income recompute được từ table.

---

### NUMERIC-04 - Net debt sai hoặc không theo chuẩn vì bỏ short-term investments

**Hiện trạng:** report 2025 net debt = -160 tỷ; 2026F net debt chuyển thành +36 tỷ. Không có bridge.

**Đối chiếu Q1/2026 balance sheet:**

- Đầu năm 2026: cash & equivalents khoảng 202.784 tỷ; short-term financial investments khoảng 409.201 tỷ; short-term borrowings khoảng 43.215 tỷ; long-term debt khoảng 132 tỷ.
- Net debt theo chuẩn nên là:

```text
Debt - Cash - Short-term investments
= (43.215 + 132.000) - 202.784 - 409.201
≈ -436.770 tỷ VND
```

Report -160 tỷ không reconcile với chuẩn net debt nếu short-term investments được xem là cash-like.

**Yêu cầu sửa:**

- Chuẩn hóa:

```text
interest_bearing_debt = short_term_borrowings + current_portion_ltd + long_term_debt + lease_liabilities
cash_like_assets = cash_and_equivalents + short_term_deposits + liquid_short_term_investments
net_debt = interest_bearing_debt - cash_like_assets
```

- Nếu không đưa short-term investments vào cash-like assets, phải ghi rõ và giải thích.
- Add net debt bridge từ balance sheet.

**Acceptance:** net debt reported phải reconcile với balance sheet và source.

---

### NUMERIC-05 - FCFF/FCFE chưa phải code-first valuation có thể tái lập

**Hiện trạng:** báo cáo chỉ nêu Price_FCFF = 35,767 và Price_FCFE = 22,372. Không có:

- FCFF schedule;
- FCFE schedule;
- NOPAT;
- D&A;
- CAPEX;
- ΔNWC;
- Net borrowing;
- Re / cost of equity;
- WACC components;
- PV explicit forecast;
- terminal value;
- terminal value weight;
- EV to equity bridge;
- net debt bridge;
- diluted shares bridge.

**Vì sao sai:** target price không reproducible từ report hoặc `valuation_result` visible. Không thể audit.

**Yêu cầu sửa:**

- `valuation_result.json` phải là single source of truth.
- FCFF schedule:

```text
FCFF = EBIT x (1 - tax) + D&A - CAPEX - ΔNWC
EV = PV(FCFF) + PV(TV)
Equity value = EV - net debt - minority interest + non-operating assets
Price_FCFF = equity value / diluted shares
```

- FCFE schedule:

```text
FCFE = Net income + D&A - CAPEX - ΔNWC + Net borrowing
Equity value = PV(FCFE) + PV(TV)
Price_FCFE = equity value / diluted shares
```

- Blend:

```text
Target = 60% x Price_FCFF + 40% x Price_FCFE
```

**Acceptance:** target price recompute được byte-for-byte hoặc trong tolerance từ `valuation_result.json`.

---

### NUMERIC-06 - FCFF/FCFE gap quá lớn nhưng vẫn publish rating

**Hiện trạng:** Price_FCFF 35,767 và Price_FCFE 22,372.

**Kiểm tra:**

```text
Valuation gap = 35,767 / 22,372 - 1 ≈ 59.9%
```

**Vì sao sai:** theo policy định giá, nếu gap FCFF/FCFE > 25%, mô hình cần audit net borrowing, CAPEX, NWC, debt schedule và terminal FCFE trước khi publish. Report có nói `cần soi kỹ`, nhưng vẫn xuất rating `BÁN`.

**Yêu cầu sửa:**

- Add `valuation_gap_gate`.
- Nếu gap > 25%: downgrade `rating_model_output = UNDER_REVIEW` trừ khi analyst approve và có bridge giải thích.

**Acceptance:** DBD hiện tại không được xuất final recommendation cho đến khi gap được giải trình.

---

### NUMERIC-07 - Sensitivity matrix sai format, sai range và sai ý nghĩa

**Hiện trạng:** bảng ghi `Đơn vị: VND/cp`, nhưng hiển thị như `6542200.0%`, `3967900.0%`.

**Các lỗi:**

1. Giá trị bị format thành phần trăm thay vì VND/cp.
2. Text nói vùng giá 39,679-91,113 VND, nhưng bảng hiển thị 3,967,900%-9,111,300%.
3. Base WACC trong report là 13.8%, nhưng sensitivity chỉ chạy WACC 8%-12%. Base case không nằm trong matrix.
4. Bảng gọi là `Độ nhạy giá mục tiêu`, nhưng subtitle nói `định giá FCFF DCF`. Nếu là FCFF matrix thì không được dùng làm target price blend.
5. Target blend 30,409 thấp hơn vùng FCFF 39,679-91,113; text đang gây hiểu lầm.

**Yêu cầu sửa:**

- Tách 3 bảng:
  - `FCFF sensitivity: WACC x g`;
  - `FCFE sensitivity: Re x g`;
  - `Blended target sensitivity` nếu cần.
- Center/base cell phải khớp base assumptions.
- WACC range phải bao quanh base 13.8%, ví dụ 11.8%, 12.8%, 13.8%, 14.8%, 15.8%.
- Format currency: `39,679`, không `%`.
- Add `sensitivity_recompute_gate`.

**Acceptance:** no `%` in VND matrix; base cell equals model implied price within tolerance.

---

### NUMERIC-08 - Cash conversion 2025 bị dùng như driver bền vững mà không normalize

**Hiện trạng:** report nêu `Cash conversion 2025 = 210.7%` và diễn giải như chất lượng dòng tiền tốt.

**Vấn đề:** CFO/PAT một năm cao có thể do giải phóng vốn lưu động, timing phải thu/hàng tồn kho hoặc dòng bất thường. Không thể dùng làm bằng chứng bền vững nếu không phân tích working capital.

**Yêu cầu sửa:**

- Bổ sung bảng CFO bridge:

```text
PAT + D&A +/- working capital changes +/- other = CFO
```

- Tách `cash_conversion_reported` và `normalized_cash_conversion`.
- Nếu CFO/PAT > 150% hoặc < 50%, bắt buộc có abnormal movement explanation.

**Acceptance:** cash conversion không được dùng làm positive thesis nếu không có CFO bridge.

---

## 6. Lỗi forecast/debt/dividend/share schedules

### FORECAST-01 - Forecast đang kéo CAGR đơn giản, chưa phải driver-based thật

**Hiện trạng:** revenue growth 2026F-2030F đều 6.3%; margin, tax, WACC, debt gần như cố định; ΔNWC rất nhỏ; không thấy DSO/DIO/DPO.

**Vì sao sai:** driver-based forecast phải nối business driver -> financial line item -> assumption -> valuation impact. Hiện mới là extrapolation.

**Yêu cầu sửa:**

- Historical driver calculation:
  - revenue growth by segment/channel if available;
  - gross margin;
  - selling expense/revenue;
  - admin expense/revenue;
  - D&A/revenue;
  - CAPEX/revenue;
  - DSO, DIO, DPO;
  - debt/EBITDA;
  - cost of debt;
  - payout ratio.
- Scenario builder Bear/Base/Bull cho từng driver.
- Mỗi assumption có method, source/confidence, warning.

**Acceptance:** forecast table phải nêu `method` và `source` cho mỗi driver, không chỉ một con số.

---

### FORECAST-02 - Debt schedule và cash sweep chưa tồn tại

**Hiện trạng:** bảng chỉ có `Thay đổi nợ ròng` và `Nợ ròng cuối năm`, không có debt roll-forward, cash movement, borrowing/repayment.

**Yêu cầu sửa:**

- Add debt schedule:

```text
Beginning debt
+ New borrowing
- Debt repayment
= Ending debt
Average debt x cost of debt = interest expense
```

- Add cash sweep:

```text
Beginning cash + CFO - CAPEX - dividends + debt issuance - debt repayment + equity issuance +/- other = ending cash
```

- Net borrowing phải feed vào FCFE.

**Acceptance:** net debt movement reconcile với cash/debt schedule.

---

### FORECAST-03 - Dividend schedule chưa tồn tại và equity bị overstated

**Hiện trạng:** cổ tức bằng `—`; equity forecast tăng đúng bằng net income qua từng năm, không trừ dividend.

Ví dụ:

```text
2025 VCSH = 1,736
2026F LNST = 320
2026F VCSH = 2,056 = 1,736 + 320
```

Điều này hàm ý payout = 0, trái với chính sách cổ tức 20%.

**Yêu cầu sửa:**

- Add dividend schedule:

```text
DPS_t
Cash dividend_t = DPS_t x shares_t
Payout ratio_t = cash dividend / NPATMI
Retained earnings addition = NPATMI - cash dividend
Equity_t = Equity_t-1 + retained earnings addition + equity issuance - buyback +/- OCI
```

**Acceptance:** equity roll-forward phải trừ dividend; BVPS/PB/ROE phải cập nhật theo equity đúng.

---

### FORECAST-04 - Share roll-forward chưa tồn tại

**Hiện trạng:** shares giữ 94 triệu từ 2022 đến 2030, trong khi DBD có cổ phiếu thưởng lịch sử, cổ phiếu quỹ, kế hoạch ESOP và phát hành riêng lẻ.

**Yêu cầu sửa:**

- Add share schedule:

```text
beginning_shares
+ bonus_shares
+ private_placement_shares
+ ESOP_shares
- treasury_shares
= ending_basic_shares
weighted_avg_shares
fully_diluted_shares
```

- EPS/P/E/target price phải dùng đúng share basis.

**Acceptance:** no constant shares if corporate action active.

---

## 7. Lỗi narrative và chất lượng phân tích

### NARRATIVE-01 - Nhận định quá chung, chưa chứng minh bằng sự kiện thật của DBD

**Hiện trạng:** lặp lại nhiều lần các ý chung như API, ETC, OTC, GMP-EU, working capital, đấu thầu nhưng không gắn số liệu cụ thể.

**Thiếu:**

- Q1/2026 performance;
- 2026 guidance;
- plan investment 744/548 tỷ;
- private placement 1,165 tỷ;
- ESOP 1.5 triệu cp;
- dividend 2,000 VND/cp;
- SVI plant / oncology GMP-EU progress;
- gross margin drop Q1/2026 so với Q1/2025 nếu dùng official Q1 P&L;
- SG&A/admin expense drivers.

**Yêu cầu sửa:** mỗi phần chính phải theo logic:

```text
fact -> driver explanation -> valuation implication -> risk/catalyst monitor
```

**Acceptance:** không còn đoạn phân tích chung chung nếu không có số/source.

---

### NARRATIVE-02 - Kết luận `BÁN` không được giải thích bằng valuation story thuyết phục

**Hiện trạng:** báo cáo nói doanh thu tăng đều, ROE cao, net cash, cổ tức chưa tính, có dự án tăng trưởng; nhưng lại đưa target thấp hơn thị giá 39.4% mà không bridge vì sao value thấp.

**Yêu cầu sửa:** valuation narrative phải giải thích:

- driver nào kéo target xuống;
- FCFE thấp vì net borrowing/capex/working capital nào;
- WACC 13.8% có nguồn và components;
- tại sao DBD xứng đáng multiple thấp/hay DCF thấp hơn thị trường;
- cổ tức và phát hành có làm thay đổi target/rating không.

**Acceptance:** rating phải đọc được như một investment conclusion, không phải output số học không giải thích.

---

### NARRATIVE-03 - Rủi ro/catalyst quá sơ sài

**Hiện trạng:** cuối report chỉ có 3 dòng risk: áp lực giá thầu, API/tỷ giá, cạnh tranh generic. Không có catalyst table.

**Yêu cầu sửa:** risk/catalyst phải có table:

```text
Risk/Catalyst | Evidence | Financial driver | Direction | Monitoring metric | Valuation impact | Source
```

Với DBD tối thiểu:

- giá thầu ETC;
- API/tỷ giá;
- gross margin Q1/2026;
- tiến độ GMP-EU oncology/SVI;
- kế hoạch CAPEX 2026;
- phát hành riêng lẻ/dilution;
- ESOP;
- dividend policy;
- working capital from receivables/inventory.

**Acceptance:** risks gắn trực tiếp với revenue, margin, CAPEX, NWC, shares, WACC hoặc terminal value.

---

## 8. Lỗi chart/layout/rendering

### LAYOUT-01 - Page layout fail: trang trống và nội dung không phân bổ đúng

**Hiện trạng:** PDF có 11 trang, trong đó page 1 gần trống, page 4 và page 7 gần như chỉ header. Nội dung không theo page budget 8 trang.

**Yêu cầu sửa:**

- Sử dụng HTML as single source of truth, PDF render sau khi QA.
- Add `visual_page_budget_gate`:
  - no page with content coverage < threshold;
  - no orphan header-only page;
  - no section starts/ends causing blank pages.
- Template đề xuất:
  - Page 1: snapshot + thesis + price chart;
  - Page 2: company overview + business model;
  - Page 3: financial performance + 2 charts;
  - Page 4: forecast drivers + forecast table;
  - Page 5: FCFF/FCFE valuation + bridge;
  - Page 6: sensitivity + scenario + peer check;
  - Page 7: catalysts & risks;
  - Page 8: conclusion + quality summary + sources + disclaimer.

**Acceptance:** không còn blank/header-only pages.

---

### LAYOUT-02 - Biểu đồ sai/khó đọc và không client-facing

**Hiện trạng:**

- Chart page 5 dùng title tiếng Anh, legend tiếng Anh, text nhỏ.
- Revenue/EBITDA chart có trục/scale khó hiểu, không rõ đơn vị.
- Price chart sidebar có label x-axis chồng kín, không thể đọc.
- Dưới chart chỉ có caption chung chung, không có source_id.

**Yêu cầu sửa:**

- Chart artifact phải có schema:

```text
chart_id, title_vi, period, unit, series, source_id, data_hash, rendered_path
```

- Price chart phải base 100 với VNINDEX, tối đa 12 tick labels, no overlap.
- Financial chart phải ghi `tỷ VND`, `%`, actual/forecast marker.
- Không dùng chart nếu data không pass numeric gate.

**Acceptance:** charts đọc được khi render PDF A4; caption có source tag cụ thể.

---

### LAYOUT-03 - Table formatting lỗi

**Hiện trạng:**

- Header năm bị dính: `2026F2027F2028F...`.
- Sensitivity currency bị format thành `%`.
- Nhiều bảng quá nhiều cột, font nhỏ, khó đọc.
- Nhiều dòng `—` dù có thể tính/lấy dữ liệu.

**Yêu cầu sửa:**

- Table renderer phải dùng column width fixed và min font size.
- Max 8-10 cột trong PDF; nếu quá rộng, chuyển appendix hoặc tách historical/forecast.
- Mỗi metric có `format_type`: currency, percent, multiple, ratio, shares, text.
- Không render `—` nếu metric có thể lấy hoặc tính từ available facts; nếu missing thật, để `N/A` kèm internal missing reason trong eval artifact, không làm rối client-facing PDF.

**Acceptance:** no overlapped year headers; no `%` for VND/cp; no avoidable blanks.

---

## 9. Implementation tasks cho Claude

### Phase 1 - Source and fact ingestion gate

- [ ] Ingest official DBD BCTC hợp nhất 2025 audited.
- [ ] Ingest official DBD BCTC hợp nhất Q1/2026.
- [ ] Ingest ĐHĐCĐ 2026 / Bidiphar IR news / VSDC corporate action metadata.
- [ ] Build `source_manifest.json` and `canonical_fact_table` with period/source/confidence.
- [ ] Reject final if critical facts only come from VCI/vnstock without official reconciliation.

### Phase 2 - P&L taxonomy fix

- [ ] Split `selling_expense` and `admin_expense`.
- [ ] Compute `sga_total = selling + admin`.
- [ ] Recompute EBITDA/EBIT from full P&L.
- [ ] Add `pnl_reconciliation_gate` for historical and forecast periods.

### Phase 3 - Forecast artifact

- [ ] Build `ForecastArtifact` with operating, working capital, CAPEX, debt, interest, tax, dividend, equity, cash and share schedules.
- [ ] Add management guidance reconciliation.
- [ ] Add Q1/TTM update if report date is after Q1 filing.
- [ ] Add scenario assumptions Bear/Base/Bull.

### Phase 4 - Corporate action and dividend module

- [ ] Add `CorporateActionArtifact` for private placement, ESOP, cash dividend.
- [ ] Add share roll-forward and diluted shares.
- [ ] Add dividend schedule with DPS/payout/cash dividend/equity impact.
- [ ] Add issuance cash inflow and dilution impact to valuation.

### Phase 5 - Valuation reproducibility

- [ ] Produce `valuation_result.json` as single source of truth.
- [ ] Include FCFF schedule, FCFE schedule, WACC components, Re components, terminal value, TV weight, net debt bridge, share basis.
- [ ] Add `valuation_gap_gate` if FCFF/FCFE gap > 25%.
- [ ] Add `target_price_recompute_gate`.

### Phase 6 - Sensitivity and scenario

- [ ] Separate FCFF WACC x g, FCFE Re x g, blended target sensitivity.
- [ ] Range must center around base WACC/Re/g.
- [ ] Format VND/cp as currency, never percent.
- [ ] Add scenario table Bear/Base/Bull with target price, upside, rating implication.

### Phase 7 - Report section assembly

- [ ] Implement `ReportSectionContract` and `section_coherence_gate`.
- [ ] Remove duplicated paragraphs.
- [ ] Stop mixing valuation content into business/margin/event sections.
- [ ] Use page-level templates and slot-based rendering.

### Phase 8 - Layout QA

- [ ] Render PDF to PNG after generation.
- [ ] Detect blank/header-only pages.
- [ ] Detect overlapping headers/tables.
- [ ] Detect chart label overlap.
- [ ] Detect wrong format tokens, especially `%` in currency tables.

---

## 10. Definition of Done

Một DBD report mới chỉ được coi là đạt khi:

1. `report_status = FINAL_EXPORTABLE` chỉ sau khi all gates pass.
2. Page 1 không mâu thuẫn target/upside.
3. Sidebar có current price, target price, upside/downside, dividend yield, total return, market cap, shares, Q1/2026 assets/equity, 2026 guidance.
4. Dữ liệu 2025 và Q1/2026 reconcile với official filings.
5. SG&A gồm cả selling và admin expense; EBIT/EBITDA/PBT/PAT reconcile.
6. EPS reconcile với weighted average/diluted shares.
7. Dividend, private placement và ESOP được mô hình hóa trong share/cash/equity schedules.
8. Forecast có operating, working capital, CAPEX, debt, interest, tax, dividend, equity và shares schedules.
9. FCFF/FCFE có bridge đầy đủ và target price tái lập được từ `valuation_result.json`.
10. Sensitivity hiển thị đúng VND/cp, base cell đúng với base assumptions.
11. Không còn source chung chung; claim định lượng có citation/source_id.
12. Không còn trang trống, header-only page, chart label overlap, year header dính nhau.
13. Section đúng ngữ nghĩa; không gộp lẫn business update, valuation, risk và events.
14. Nếu bất kỳ data/valuation/citation gate fail, report chỉ xuất `draft_review`, không xuất final recommendation.

---

## 11. Prompt ngắn để đưa cho Claude Code

```text
Audit và sửa toàn bộ pipeline sinh DBD_report theo file 01_DBD_report_audit_fix_plan.md. DBD chỉ là regression fixture; mọi fix phải ticker-agnostic.

Ưu tiên sửa theo thứ tự:
1. source_manifest + official financial fact ingestion/reconciliation;
2. P&L taxonomy: split selling/admin expense, fix EBIT/EBITDA/PBT/PAT reconciliation;
3. ForecastArtifact đầy đủ: operating, working capital, CAPEX, debt, interest, tax, dividend, equity, cash, shares;
4. CorporateActionArtifact: private placement 23.3m shares, ESOP 1.5m, dividend 2,000 VND/cp for DBD via source, not hard-code;
5. FCFF/FCFE valuation_result reproducibility, WACC/Re/TV/net debt/share bridges;
6. sensitivity formatting/range/meaning;
7. ReportSectionContract to stop merging sections incorrectly;
8. PDF/HTML layout QA to remove blank pages, broken charts and table overlaps.

Hard rules:
- Không xuất BUY/HOLD/SELL nếu any gate fail.
- Không dùng vnstock/VCI làm nguồn duy nhất cho financial facts critical.
- Không render claim định lượng nếu không có source_id/fact_id/valuation_result path.
- Không để shares constant nếu corporate actions active.
- Không format VND/cp as percent.
- Không trộn section content vào sai heading.
```
