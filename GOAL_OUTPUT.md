# OUTPUT_REPORT_SPEC.md — Chuẩn đầu ra báo cáo định giá cổ phiếu

**Project:** Vietnam Pharma Multi-Agent Equity Research Agent  
**Output artifact:** Vietnamese professional equity research report, PDF-ready, tối đa khoảng 8 trang A4  
**Primary audience:** analyst/reviewer/giảng viên/nhà đầu tư có kiến thức cơ bản  
**Report language:** Tiếng Việt chuyên nghiệp, ngắn gọn, có nguồn, không viết kiểu quảng cáo  
**Version:** v1.0  

---

## 1. Mục tiêu của tài liệu

Tài liệu này định nghĩa chuẩn đầu ra cuối cùng cho agent khi sinh **báo cáo định giá cổ phiếu ngành dược/y tế Việt Nam**.

Đầu ra cần giống tinh thần của một báo cáo equity research chuyên nghiệp: có trang bìa/tóm tắt, luận điểm đầu tư, tổng quan doanh nghiệp, phân tích tài chính, dự phóng, định giá FCFF, sensitivity, rủi ro, kết luận và disclaimer. Tuy nhiên, báo cáo phải được **nén còn khoảng 8 trang**, tránh dài dòng, tránh copy nguyên văn nguồn, ưu tiên bảng và biểu đồ có khả năng ra quyết định.

Agent phải hiểu đây không phải là chatbot viết tự do. Báo cáo chỉ được sinh từ:

1. `canonical financial facts` đã qua kiểm định;
2. `valuation_result.json` do deterministic Python engine tạo;
3. `source_manifest.json` và `claim_ledger.json`;
4. các evidence pack có nguồn, ngày, kỳ dữ liệu, độ tin cậy;
5. assumptions đã được reviewer phê duyệt hoặc đánh dấu `pending_review`.

---

## 2. Nguyên tắc bắt buộc

### 2.1. Facts before narrative

Không được viết nhận định tài chính trước khi có số liệu, nguồn và phép tính. Mọi số như doanh thu, lợi nhuận, EPS, WACC, FCFF, target price, upside/downside, market cap, P/E, P/B, ROE, ROA, biên lợi nhuận phải truy vết được về một trong ba loại artifact:

```text
canonical_fact
computed_metric
valuation_result
```

Nếu một số không truy vết được, số đó không được xuất hiện trong báo cáo final.

### 2.2. Code-first valuation

LLM không được tự tính DCF, FCFF, EPS, CAGR, P/E, P/B, EV/EBITDA, ROE, ROA hoặc target price bằng văn bản. LLM chỉ được diễn giải kết quả do Python engine trả về.

### 2.3. Citation-first reporting

Mọi claim định lượng và mọi claim định tính quan trọng phải có nguồn. Các claim bắt buộc có citation:

| Loại claim | Ví dụ | Citation bắt buộc |
|---|---|---|
| Số liệu tài chính | Doanh thu 2024 đạt X tỷ đồng | Có |
| Dự phóng | Doanh thu 2026F tăng X% | Có, trỏ về valuation artifact/assumption |
| Thông tin doanh nghiệp | Công ty sở hữu nhà máy GMP-WHO | Có |
| Catalyst | Kết quả đấu thầu, BHYT, đăng ký thuốc | Có |
| Rủi ro | Phụ thuộc sản phẩm chính, áp lực giá thầu | Có |
| So sánh peer | P/E thấp hơn trung vị ngành | Có |
| Nhận định chung | “vị thế tốt”, “tăng trưởng ổn định” | Có evidence hoặc phải viết thận trọng |

### 2.4. Không đưa lời khuyên cá nhân hóa

Báo cáo có thể có **rating cấp độ báo cáo** như `BUY`, `HOLD`, `SELL`, nhưng phải diễn đạt là **kết luận định giá dựa trên mô hình và giả định hiện tại**, không phải lời khuyên đầu tư cá nhân hóa.

Câu chuẩn:

> Rating trong báo cáo là kết luận mô hình dựa trên dữ liệu, giả định và mức sinh lời kỳ vọng tại thời điểm lập báo cáo; không phải khuyến nghị đầu tư cá nhân hóa.

### 2.5. Human approval gate

Báo cáo chỉ được chuyển sang `final_exportable` khi pass toàn bộ gate:

```text
source_gate = pass
numeric_consistency_gate = pass
valuation_reproducibility_gate = pass
citation_gate = pass
risk_language_gate = pass
human_assumption_approval = pass
human_final_review = pass
```

---

## 3. Định dạng đầu ra cuối cùng

### 3.1. File đầu ra bắt buộc

Mỗi research run phải tạo tối thiểu các file sau:

```text
artifacts/
├── reports/{run_id}_{ticker}_report.md
├── reports_html/{run_id}_{ticker}_report.html
├── reports_pdf/{run_id}_{ticker}_report.pdf
├── valuation_results/{run_id}_{ticker}_valuation_result.json
├── claim_ledgers/{run_id}_{ticker}_claim_ledger.json
├── source_manifests/{run_id}_{ticker}_source_manifest.json
├── eval_results/{run_id}_{ticker}_eval_result.json
└── run_logs/{run_id}_{ticker}_run_log.json
```

### 3.2. Yêu cầu PDF-ready

| Thuộc tính | Chuẩn |
|---|---|
| Khổ giấy | A4 portrait |
| Độ dài | Tối đa khoảng 8 trang |
| Ngôn ngữ | Tiếng Việt |
| Tông giọng | Chuyên nghiệp, phân tích, trung lập |
| Bảng | Gọn, không quá 10 cột nếu đưa vào PDF |
| Biểu đồ | 5-7 biểu đồ chính, không lạm dụng |
| Citation | Hiển thị dạng footnote/endnote hoặc source tag ngắn |
| Disclaimer | Bắt buộc ở cuối báo cáo |
| Executive summary | Bắt buộc ở trang 1 |
| Valuation assumptions | Bắt buộc ở phần định giá |
| Sensitivity | Bắt buộc nếu có target price |

### 3.3. Quy tắc nén nội dung 8 trang

Báo cáo không được cố đưa toàn bộ bảng dự phóng chi tiết vào thân PDF. Phần PDF chỉ hiển thị bảng tóm tắt; chi tiết có thể nằm trong appendix hoặc Excel/JSON artifact.

| Nội dung | Cách xử lý trong PDF 8 trang |
|---|---|
| Bảng KQKD 10 năm | Chỉ hiển thị 5-7 dòng chính: doanh thu thuần, lợi nhuận gộp, EBIT/EBITDA, LNST, EPS, biên gộp, biên ròng |
| Bảng cân đối kế toán | Chỉ hiển thị tài sản, nợ vay, VCSH, tiền, hàng tồn kho, phải thu nếu liên quan thesis |
| Bảng lưu chuyển tiền tệ | Chỉ hiển thị CFO, CAPEX, FCF/FCFF, working capital |
| Ratio table | Chọn 10-14 chỉ số chính |
| Industry overview | Không viết thành section riêng trong MVP; chỉ lồng vào catalyst/risk nếu có evidence |
| News list | Không liệt kê quá nhiều; chỉ chọn catalyst material |
| Peer comparison | Chỉ hiển thị peer median và 3-5 peer liên quan |

---

## 4. Cấu trúc báo cáo 8 trang

### Page 1 — Cover + Investment Snapshot

**Mục tiêu:** Người đọc hiểu ngay rating, target price, upside/downside, luận điểm chính và rủi ro chính.

**Bố cục bắt buộc:**

1. Header:
   - Tên báo cáo: `Equity Research Report`
   - Ticker
   - Tên doanh nghiệp
   - Sàn giao dịch
   - Ngành: Dược/Y tế
   - Ngày lập báo cáo
   - Kỳ dữ liệu gần nhất

2. Rating block:
   - `Rating`: BUY / HOLD / SELL / UNDER REVIEW
   - `Current Price`
   - `Target Price`
   - `Upside/Downside`
   - `Investment Horizon`: 12 tháng hoặc cấu hình khác
   - `Risk Level`: Low / Medium / High
   - `Data Confidence`: High / Medium / Low

3. Key metrics snapshot:
   - Market Cap
   - Net Revenue TTM hoặc FY gần nhất
   - Revenue Growth YoY
   - Gross Margin
   - Net Margin
   - ROE
   - ROA
   - EPS
   - P/E
   - P/B
   - EV/EBITDA nếu có
   - Dividend Yield nếu có

4. Investment thesis:
   - 5-7 dòng.
   - Phải bao gồm: động lực tăng trưởng, triển vọng lợi nhuận, định giá, rủi ro chính.
   - Không được viết quá 180-220 từ.

5. Chart 1:
   - So sánh diễn biến giá cổ phiếu với VNINDEX trong 1Y hoặc 3Y.
   - Chuẩn hóa về base 100 tại ngày đầu kỳ.
   - Có chú thích nguồn và kỳ dữ liệu.

**Template:**

```markdown
# {TICKER} — {COMPANY_NAME}
## Equity Research Report | Ngành Dược/Y tế Việt Nam

| Rating | Current Price | Target Price | Upside/Downside | Horizon | Risk |
|---|---:|---:|---:|---|---|
| {BUY/HOLD/SELL/UNDER_REVIEW} | {current_price} VND | {target_price} VND | {upside_pct}% | 12M | {risk_level} |

### Key Metrics Snapshot
| Metric | Value |
|---|---:|
| Market Cap | {market_cap} tỷ VND |
| Revenue FY{year} | {revenue} tỷ VND |
| Revenue Growth | {revenue_growth}% |
| Net Profit | {net_profit} tỷ VND |
| EPS | {eps} VND |
| P/E | {pe}x |
| P/B | {pb}x |
| ROE | {roe}% |

### Investment Thesis
{5-7 dòng ngắn, có citation hoặc trỏ về claim ledger.}

![Stock vs VNINDEX](charts/{ticker}_price_vs_vnindex.png)
```

---

### Page 2 — Company Overview + Business Model

**Mục tiêu:** Giải thích doanh nghiệp kiếm tiền từ đâu, sản phẩm nào đóng góp chính và chiến lược tăng trưởng là gì.

**Nội dung bắt buộc:**

| Block | Nội dung |
|---|---|
| Company profile | Tên đầy đủ, năm thành lập, sàn, lĩnh vực chính |
| Business model | Sản xuất, phân phối, ETC/OTC, thiết bị y tế, bệnh viện, dịch vụ y tế tùy doanh nghiệp |
| Product/revenue mix | Sản phẩm/nhóm sản phẩm chính nếu có dữ liệu |
| Competitive position | GMP, hệ thống phân phối, thương hiệu, danh mục thuốc, năng lực đấu thầu nếu có evidence |
| Growth strategy | Mở rộng nhà máy, sản phẩm mới, kênh ETC/OTC, M&A, xuất khẩu |
| Key operating drivers | Giá bán, sản lượng, biên gộp, đấu thầu, BHYT, tồn kho, working capital |

**Độ dài:** 450-650 từ.

**Không được:**

- Viết lịch sử doanh nghiệp quá dài.
- Tuyên bố “dẫn đầu ngành” nếu không có nguồn.
- Copy nguyên văn báo cáo thường niên.

**Chart/Table đề xuất:**

- Biểu đồ cơ cấu doanh thu theo mảng, nếu có.
- Bảng key business drivers.

---

### Page 3 — Financial Performance

**Mục tiêu:** Cho thấy xu hướng tài chính lịch sử và chất lượng tăng trưởng.

**Nội dung bắt buộc:**

1. Revenue & Profitability:
   - Doanh thu thuần 3-5 năm.
   - Lợi nhuận gộp, EBIT/EBITDA, LNST.
   - Biên gộp, biên EBIT/EBITDA, biên ròng.

2. Growth analysis:
   - CAGR doanh thu.
   - CAGR LNST.
   - Giải thích các năm bất thường.

3. Operating efficiency:
   - Vòng quay hàng tồn kho, phải thu, phải trả hoặc cash conversion cycle nếu dữ liệu đủ.
   - Chỉ giải thích nếu có biến động đáng kể.

**Charts bắt buộc:**

| Chart | Loại | Nội dung |
|---|---|---|
| Chart 2 | Bar + line | Revenue + EBITDA/EBIT margin |
| Chart 3 | Line | EPS + P/E hoặc LNST + biên ròng |
| Chart 4 | Line/bar | Gross margin, net margin, ROE |

**Bảng tóm tắt financials:**

```markdown
| Chỉ tiêu | 2021A | 2022A | 2023A | 2024A | 2025A/TTM |
|---|---:|---:|---:|---:|---:|
| Doanh thu thuần | | | | | |
| Lợi nhuận gộp | | | | | |
| EBITDA/EBIT | | | | | |
| LNST CĐ mẹ | | | | | |
| EPS | | | | | |
| Biên gộp | | | | | |
| Biên ròng | | | | | |
| ROE | | | | | |
```

**Narrative chuẩn:**

- Nêu xu hướng chính trước.
- Sau đó giải thích nguyên nhân bằng evidence.
- Chỉ ra điểm bất thường nếu biến động YoY > ngưỡng cấu hình, ví dụ 15-20%.
- Không nói “tốt/xấu” chung chung; phải nói biến động ảnh hưởng thế nào tới valuation.

---

### Page 4 — Forecast & Key Assumptions

**Mục tiêu:** Trình bày dự phóng 5 năm một cách có logic, không chỉ đưa bảng số.

**Nội dung bắt buộc:**

1. Forecast horizon:
   - Tối thiểu 3 năm, khuyến nghị 5 năm: 2026F-2030F hoặc theo config.

2. Forecast logic:
   - Revenue growth driver.
   - Gross margin assumption.
   - SG&A/sales assumption.
   - Tax rate.
   - Working capital assumption.
   - CAPEX/depreciation assumption.
   - Terminal growth hoặc exit multiple nếu dùng.

3. Forecast table:
   - Không đưa bảng KQKD đầy đủ 20 dòng trong PDF.
   - Chỉ đưa bảng key line items.

**Bảng forecast tóm tắt:**

```markdown
| Chỉ tiêu | 2025A/TTM | 2026F | 2027F | 2028F | 2029F | 2030F |
|---|---:|---:|---:|---:|---:|---:|
| Doanh thu thuần | | | | | | |
| Tăng trưởng DT | | | | | | |
| Lợi nhuận gộp | | | | | | |
| Biên gộp | | | | | | |
| EBIT/EBITDA | | | | | | |
| Biên EBIT/EBITDA | | | | | | |
| LNST CĐ mẹ | | | | | | |
| EPS | | | | | | |
| FCFF | | | | | | |
```

**Assumptions table:**

```markdown
| Assumption | Base Case | Rationale | Source/Artifact |
|---|---:|---|---|
| Revenue CAGR 2026F-2030F | {x}% | {rationale} | {source_id/artifact_id} |
| Gross margin | {x}% | {rationale} | {source_id/artifact_id} |
| Tax rate | {x}% | {rationale} | {source_id/artifact_id} |
| WACC | {x}% | {rationale} | valuation_result |
| Terminal growth | {x}% | {rationale} | valuation_result |
```

**Quy tắc giải thích số dự phóng:**

Agent phải giải thích ít nhất 3 driver lớn nhất làm thay đổi forecast:

```text
driver_name
affected_line_item
direction: positive | negative | neutral
magnitude_estimate
evidence
assumption_status: approved | pending_review
```

---

### Page 5 — Valuation: FCFF DCF + Relative Multiples

**Mục tiêu:** Chốt giá mục tiêu bằng mô hình định giá có thể tái lập.

**Phương pháp bắt buộc:**

1. DCF theo FCFF là phương pháp chính.
2. P/E, P/B, EV/EBITDA là phương pháp kiểm tra chéo.
3. EV/Sales chỉ dùng nếu doanh nghiệp đặc thù và có giải thích.

**Công thức FCFF:**

```text
FCFF = EBIT × (1 - Tax Rate) + Depreciation - CAPEX - ΔNWC
```

**Công thức enterprise value:**

```text
EV = Σ PV(FCFF_t) + PV(Terminal Value)
```

**Công thức equity value:**

```text
Equity Value = EV + Cash & Equivalents - Debt - Minority Interest
```

**Công thức target price:**

```text
Target Price = Equity Value / Diluted Shares Outstanding
```

**Bảng định giá DCF tóm tắt:**

```markdown
| Valuation Item | 2026F | 2027F | 2028F | 2029F | 2030F |
|---|---:|---:|---:|---:|---:|
| EBIT | | | | | |
| Tax Rate | | | | | |
| EBIT(1-T) | | | | | |
| Depreciation | | | | | |
| CAPEX | | | | | |
| ΔNWC | | | | | |
| FCFF | | | | | |
| Discount Factor | | | | | |
| PV of FCFF | | | | | |
```

**Valuation summary table:**

```markdown
| Method | Implied Equity Value | Implied Price | Weight | Weighted Price |
|---|---:|---:|---:|---:|
| DCF - FCFF | | | | |
| P/E | | | | |
| P/B | | | | |
| EV/EBITDA | | | | |
| Final Target Price | | | 100% | |
```

**Valuation assumptions:**

```markdown
| Parameter | Value |
|---|---:|
| Risk-free rate | |
| Beta | |
| Equity risk premium | |
| Cost of equity | |
| Cost of debt | |
| Tax rate | |
| WACC | |
| Terminal growth | |
| Net debt / cash | |
| Shares outstanding | |
```

**Narrative chuẩn:**

- Nêu phương pháp chính và lý do phù hợp.
- Giải thích target price đến từ đâu.
- So sánh target price với current price.
- Nêu mô hình nhạy với assumption nào nhất.
- Không kết luận chắc chắn; phải nói theo điều kiện assumptions.

---

### Page 6 — Sensitivity, Scenario & Peer Check

**Mục tiêu:** Cho reviewer thấy mô hình có bền không khi giả định thay đổi.

**Sensitivity bắt buộc:**

1. Sensitivity target price theo `WACC` và `terminal growth`.
2. Hoặc sensitivity theo `revenue CAGR` và `EBIT/EBITDA margin` nếu terminal assumptions không phù hợp.

**Sensitivity matrix:**

```markdown
| Target Price Sensitivity | WACC -1.0% | WACC -0.5% | Base WACC | WACC +0.5% | WACC +1.0% |
|---|---:|---:|---:|---:|---:|
| g -0.5% | | | | | |
| Base g | | | | | |
| g +0.5% | | | | | |
```

**Scenario table:**

```markdown
| Scenario | Revenue CAGR | Margin Assumption | WACC | Target Price | Upside/Downside | Rating Implication |
|---|---:|---:|---:|---:|---:|---|
| Bear | | | | | | |
| Base | | | | | | |
| Bull | | | | | | |
```

**Peer comparison table:**

```markdown
| Ticker | Business Type | Market Cap | P/E | P/B | EV/EBITDA | ROE | Net Margin |
|---|---|---:|---:|---:|---:|---:|---:|
| {ticker} | | | | | | | |
| Peer Median | | | | | | | |
```

**Quy tắc peer:**

- Peer phải thuộc ngành dược/y tế Việt Nam hoặc có lý do tương đồng rõ.
- Nếu không có peer đủ tương đồng, ghi `peer comparison limited` thay vì ép so sánh.
- Không dùng peer global nếu không điều chỉnh khác biệt thị trường và quy mô.

---

### Page 7 — Catalysts & Investment Risks

**Mục tiêu:** Trình bày điều gì có thể làm thesis đúng/sai trong 6-12 tháng tới.

**Positive catalysts:**

```markdown
| Catalyst | Expected Timing | Impact | Probability | Evidence |
|---|---|---|---|---|
| | | Low/Medium/High | | |
```

**Downside risks:**

```markdown
| Risk | Affected Driver | Impact | Mitigation/Monitor | Evidence |
|---|---|---|---|---|
| Áp lực giảm giá thầu | Gross margin/revenue | High | Theo dõi kết quả đấu thầu | |
| Phụ thuộc sản phẩm chính | Revenue stability | Medium | Theo dõi product mix | |
| Tồn kho/phải thu tăng | Working capital/FCFF | Medium | Theo dõi CCC | |
```

**Rủi ro đặc thù ngành dược/y tế Việt Nam cần kiểm tra:**

- rủi ro đấu thầu thuốc;
- BHYT/reimbursement;
- thay đổi quy định đăng ký/lưu hành thuốc;
- GMP/nhà máy/chất lượng sản xuất;
- cạnh tranh generic;
- phụ thuộc kênh ETC hoặc OTC;
- biến động nguyên liệu nhập khẩu;
- rủi ro hàng tồn kho, phải thu bệnh viện/nhà thuốc;
- rủi ro tỷ giá nếu nhập nguyên liệu;
- rủi ro cổ tức/thanh khoản/free float.

**Quy tắc viết rủi ro:**

- Mỗi rủi ro phải gắn với một financial driver.
- Không viết rủi ro chung chung như “thị trường biến động”.
- Phải nói rủi ro ảnh hưởng tới doanh thu, margin, working capital, WACC, valuation multiple hoặc target price như thế nào.

---

### Page 8 — Conclusion, Quality Checks, Sources & Disclaimer

**Mục tiêu:** Chốt lại báo cáo, hiển thị mức tin cậy, trạng thái audit và disclaimer.

**Nội dung bắt buộc:**

1. Key takeaways:
   - 3-5 bullet.
   - Mỗi bullet phải là kết luận có căn cứ.

2. Final valuation conclusion:
   - Rating.
   - Target price.
   - Upside/downside.
   - Điều kiện để rating thay đổi.

3. Quality & audit summary:
   - Citation coverage.
   - Numeric consistency.
   - Valuation reproducibility.
   - Data freshness.
   - Human approval status.

4. Source summary:
   - Không cần liệt kê toàn bộ source nếu quá dài.
   - Hiển thị 5-10 nguồn quan trọng nhất.
   - Toàn bộ nguồn nằm trong `source_manifest.json`.

5. Disclaimer.

**Quality summary table:**

```markdown
| Gate | Status | Notes |
|---|---|---|
| Source Gate | PASS/FAIL | |
| Numeric Consistency | PASS/FAIL | |
| Valuation Reproducibility | PASS/FAIL | |
| Citation Coverage | {x}% | |
| Data Freshness | PASS/STALE | |
| Human Assumption Approval | PASS/PENDING | |
| Final Review | PASS/PENDING | |
```

**Disclaimer chuẩn:**

```text
Báo cáo này chỉ nhằm mục đích nghiên cứu và tham khảo học thuật/sản phẩm. Nội dung không phải là khuyến nghị đầu tư cá nhân hóa, không phải lời mời mua/bán chứng khoán, và không thay thế tư vấn từ chuyên gia được cấp phép. Kết quả định giá phụ thuộc vào dữ liệu đầu vào, giả định mô hình và điều kiện thị trường tại thời điểm lập báo cáo. Hiệu suất quá khứ không đảm bảo kết quả tương lai. Người đọc chịu trách nhiệm độc lập khi sử dụng thông tin.
```

---

## 5. Quy tắc rating

Rating phải dựa trên upside/downside so với current price, nhưng phải có reviewer approval.

### 5.1. Default threshold

```yaml
rating_thresholds:
  buy:
    min_upside: 0.15
    required_confidence: 0.70
  hold:
    min_downside: -0.10
    max_upside: 0.15
    required_confidence: 0.60
  sell:
    max_upside: -0.10
    required_confidence: 0.70
  under_review:
    trigger:
      - insufficient_sources
      - failed_numeric_gate
      - missing_human_approval
      - valuation_extreme_sensitivity
      - source_conflict
```

### 5.2. Không được đưa BUY/SELL/HOLD nếu

- Không có current price đáng tin cậy.
- Không có shares outstanding hợp lệ.
- Valuation không tái lập được.
- Target price thay đổi quá mạnh theo sensitivity.
- Dữ liệu tài chính stale hoặc chưa đủ kỳ.
- Claim định lượng chính thiếu citation.
- Reviewer chưa approve assumptions.

---

## 6. Danh mục biểu đồ chuẩn

Báo cáo 8 trang nên có tối đa 5-7 biểu đồ.

| Chart ID | Tên | Loại | Trang | Bắt buộc |
|---|---|---|---|---|
| C1 | Stock vs VNINDEX | Line, base 100 | Page 1 | Có |
| C2 | Revenue & EBITDA/EBIT Trend | Bar + line | Page 3 | Có |
| C3 | EPS & P/E Trend | Dual-axis line/bar | Page 3 | Có |
| C4 | Margin & ROE Trend | Multi-line | Page 3 | Có |
| C5 | Forecast Revenue/Profit | Bar + line | Page 4 | Có |
| C6 | DCF Value Bridge | Waterfall | Page 5 | Khuyến nghị |
| C7 | Sensitivity Heatmap | Heatmap/table | Page 6 | Có |

### 6.1. Chart generation rules

- Chart phải có title, period, unit, source.
- Không dùng màu quá nhiều.
- Trục phải ghi rõ đơn vị: tỷ VND, %, x, VND/share.
- Không dùng biểu đồ nếu dữ liệu thiếu hoặc sai kỳ.
- Nếu là forecast, phải ký hiệu rõ `F`.
- Nếu là actual, ký hiệu rõ `A`.
- Nếu dùng TTM, ghi rõ `TTM`.

---

## 7. Financial metric checklist

### 7.1. Metrics bắt buộc

| Nhóm | Chỉ số |
|---|---|
| Growth | Revenue growth, net profit growth, revenue CAGR, net profit CAGR |
| Profitability | Gross margin, EBIT/EBITDA margin, net margin, ROE, ROA |
| Valuation | EPS, BVPS, P/E, P/B, EV/EBITDA, dividend yield nếu có |
| Balance sheet | Debt/equity, net debt/cash, current ratio nếu có |
| Working capital | Inventory days, receivable days, payable days, cash conversion cycle nếu đủ dữ liệu |
| Cash flow | CFO, CAPEX, FCFF, FCF conversion nếu đủ dữ liệu |

### 7.2. Formula registry

```yaml
formulas:
  revenue_growth:
    formula: "(revenue_t / revenue_t_minus_1) - 1"
    unit: "%"
  gross_margin:
    formula: "gross_profit / net_revenue"
    unit: "%"
  net_margin:
    formula: "net_profit_after_tax / net_revenue"
    unit: "%"
  roe:
    formula: "net_profit_after_tax / average_equity"
    unit: "%"
  roa:
    formula: "net_profit_after_tax / average_assets"
    unit: "%"
  eps:
    formula: "net_profit_attributable_to_parent / weighted_average_shares"
    unit: "VND/share"
  pe:
    formula: "market_price / eps"
    unit: "x"
  pb:
    formula: "market_price / bvps"
    unit: "x"
  ev_ebitda:
    formula: "enterprise_value / ebitda"
    unit: "x"
  fcff:
    formula: "ebit * (1 - tax_rate) + depreciation - capex - change_in_nwc"
    unit: "VND"
```

---

## 8. Claim ledger contract

Mỗi claim trong report phải được ghi vào `claim_ledger.json`.

```json
{
  "claim_id": "CLM-001",
  "section": "investment_thesis",
  "claim_text": "Doanh thu thuần 2024 tăng 12.3% so với cùng kỳ.",
  "claim_type": "quantitative",
  "ticker": "DHG",
  "period": "2024A",
  "metric": "net_revenue_growth",
  "value": 0.123,
  "unit": "%",
  "source_refs": ["SRC-001", "FACT-2024-DHG-IS-001"],
  "artifact_refs": ["valuation_result:base_case"],
  "support_status": "supported",
  "confidence": 0.92,
  "review_status": "approved"
}
```

### 8.1. Claim types

```yaml
claim_types:
  - quantitative
  - qualitative_business
  - valuation
  - forecast
  - risk
  - catalyst
  - peer_comparison
  - conclusion
```

### 8.2. Support status

```yaml
support_status:
  supported: "Có đủ nguồn hoặc artifact"
  partially_supported: "Có nguồn nhưng thiếu một phần logic"
  unsupported: "Không được phép xuất hiện trong final report"
  conflicting: "Nguồn mâu thuẫn, cần review"
```

---

## 9. Source manifest contract

```json
{
  "source_id": "SRC-001",
  "ticker": "DHG",
  "source_type": "annual_report",
  "source_name": "Báo cáo thường niên 2024",
  "publisher": "Company",
  "published_date": "2025-03-30",
  "retrieval_timestamp": "2026-05-07T10:00:00+07:00",
  "period": "2024A",
  "url_or_path": "sources/DHG/annual_report_2024.pdf",
  "reliability_tier": "official",
  "checksum": "sha256:...",
  "parser_version": "v1.0",
  "used_sections": ["financial_statements", "business_overview", "management_discussion"]
}
```

---

## 10. Evaluation gates

### 10.1. Gate thresholds

```yaml
evaluation_thresholds:
  quantitative_claim_citation_coverage: 1.00
  numeric_consistency_min: 0.99
  valuation_reproducibility: 1.00
  unsupported_claims_allowed: 0
  stale_financial_data_allowed: false
  fake_citation_allowed: false
  final_confidence_min: 0.70
```

### 10.2. Numeric consistency check

Agent phải kiểm tra:

- số trong report khớp với `canonical facts` hoặc `valuation_result`;
- đơn vị không bị sai: VND, tỷ VND, triệu VND, %, x;
- năm/kỳ không bị nhầm;
- forecast và actual được ký hiệu đúng;
- tổng tài sản = tổng nguồn vốn nếu hiển thị bảng cân đối kế toán;
- FCFF có thể recompute từ các thành phần;
- target price có thể recompute từ equity value và shares outstanding.

### 10.3. Report quality rubric

| Dimension | Score 1 | Score 3 | Score 5 |
|---|---|---|---|
| Accuracy | Nhiều lỗi số/nguồn | Có lỗi nhỏ | Số và nguồn nhất quán |
| Logicality | Luận điểm rời rạc | Có logic nhưng thiếu driver | Driver -> forecast -> valuation -> risk rõ |
| Storytelling | Dài, khó đọc | Đọc được | Ngắn gọn, chuyên nghiệp, có insight |
| Grounding | Thiếu citation | Citation chưa đều | Claim quan trọng đều có source |
| Valuation transparency | Assumption mơ hồ | Có bảng assumption | Reproducible, có sensitivity |
| Risk balance | Thiên lệch | Có rủi ro nhưng chung | Rủi ro cụ thể, gắn financial driver |

---

## 11. Markdown skeleton cho report final

Agent có thể dùng skeleton sau để sinh `report.md`.

```markdown
---
report_type: equity_research
ticker: "{TICKER}"
company_name: "{COMPANY_NAME}"
exchange: "{EXCHANGE}"
sector: "Dược/Y tế"
report_date: "{REPORT_DATE}"
data_cutoff: "{DATA_CUTOFF}"
rating: "{RATING}"
current_price: "{CURRENT_PRICE}"
target_price: "{TARGET_PRICE}"
upside_downside: "{UPSIDE_DOWNSIDE}"
status: "{DRAFT|NEEDS_REVIEW|APPROVED}"
---

# {TICKER} — {COMPANY_NAME}
## Equity Research Report | {REPORT_DATE}

### Investment Snapshot

| Rating | Current Price | Target Price | Upside/Downside | Risk Level | Data Confidence |
|---|---:|---:|---:|---|---|
| {RATING} | {CURRENT_PRICE} | {TARGET_PRICE} | {UPSIDE_DOWNSIDE} | {RISK_LEVEL} | {DATA_CONFIDENCE} |

### Key Metrics Snapshot

{KEY_METRICS_TABLE}

### Investment Thesis

{INVESTMENT_THESIS}

![Stock vs VNINDEX](charts/{TICKER}_price_vs_vnindex.png)

\pagebreak

## Company Overview

{COMPANY_OVERVIEW}

{BUSINESS_DRIVER_TABLE_OR_REVENUE_MIX_CHART}

\pagebreak

## Financial Performance

{FINANCIAL_PERFORMANCE_NARRATIVE}

{FINANCIAL_SUMMARY_TABLE}

![Revenue & EBITDA Trend](charts/{TICKER}_revenue_ebitda.png)

![EPS & P/E Trend](charts/{TICKER}_eps_pe.png)

\pagebreak

## Forecast & Key Assumptions

{FORECAST_NARRATIVE}

{FORECAST_TABLE}

{ASSUMPTIONS_TABLE}

![Forecast Revenue and Profit](charts/{TICKER}_forecast.png)

\pagebreak

## Valuation

{VALUATION_NARRATIVE}

{DCF_TABLE}

{VALUATION_SUMMARY_TABLE}

{VALUATION_ASSUMPTIONS_TABLE}

![DCF Value Bridge](charts/{TICKER}_dcf_bridge.png)

\pagebreak

## Sensitivity & Peer Check

{SENSITIVITY_NARRATIVE}

{SENSITIVITY_MATRIX}

{SCENARIO_TABLE}

{PEER_COMPARISON_TABLE}

\pagebreak

## Catalysts & Risks

{CATALYSTS_TABLE}

{RISKS_TABLE}

{RISK_NARRATIVE}

\pagebreak

## Conclusion, Audit Summary & Disclaimer

### Key Takeaways

{KEY_TAKEAWAYS}

### Final Valuation Conclusion

{FINAL_CONCLUSION}

### Quality & Audit Summary

{QUALITY_GATE_TABLE}

### Key Sources

{KEY_SOURCES_TABLE}

### Disclaimer

{DISCLAIMER}
```

---

## 12. Agent execution instruction

Khi được yêu cầu sinh báo cáo, agent phải tuân thủ thứ tự sau:

```text
1. Load run state and ticker metadata.
2. Validate source_manifest and data freshness.
3. Load canonical facts.
4. Run deterministic financial metric computation.
5. Run deterministic valuation engine.
6. Generate chart data from computed artifacts.
7. Ask/verify human approval for assumptions if required.
8. Draft section-by-section report narrative.
9. Build claim_ledger.
10. Run citation audit.
11. Run numeric consistency audit.
12. Run valuation reproducibility audit.
13. Run risk language audit.
14. If all gates pass, export report.md/html/pdf.
15. If any gate fails, mark report as NEEDS_REVIEW and explain failure.
```

### 12.1. Section writing constraints

| Section | Allowed source | Prohibited |
|---|---|---|
| Investment Thesis | facts + valuation_result + claim ledger | Unsupported growth story |
| Company Overview | official filings + company source + verified news | Generic company praise |
| Financial Performance | canonical facts + computed metrics | LLM-calculated ratios |
| Forecast | approved assumptions + valuation artifact | Invented assumptions |
| Valuation | valuation_result only | Manual target price in text |
| Risks | evidence + domain risk taxonomy | Generic risk list |
| Conclusion | passed gates + valuation summary | Personalized investment advice |

---

## 13. Failure handling

Nếu thiếu dữ liệu hoặc kiểm định không pass, báo cáo không được giả vờ hoàn chỉnh.

### 13.1. Failure messages

| Failure | Report Status | Required Message |
|---|---|---|
| Missing financial facts | `NEEDS_REVIEW` | Thiếu dữ liệu tài chính cho kỳ X; không thể hoàn tất valuation |
| Source conflict | `NEEDS_REVIEW` | Nguồn A và B mâu thuẫn tại chỉ tiêu X |
| Failed numeric audit | `BLOCKED` | Số trong report không khớp artifact |
| Failed citation audit | `BLOCKED` | Có claim quan trọng thiếu nguồn |
| Extreme sensitivity | `NEEDS_REVIEW` | Target price quá nhạy với WACC/growth |
| Missing human approval | `PENDING_APPROVAL` | Assumptions/final report chưa được duyệt |

### 13.2. Không được dùng các câu sau

- “Có thể công ty sẽ tăng trưởng mạnh” nếu không có driver và nguồn.
- “Cổ phiếu chắc chắn hấp dẫn”.
- “Nên mua ngay”.
- “Theo dữ liệu thị trường” nhưng không nêu nguồn.
- “Target price được tính toán” nhưng không có valuation artifact.
- “Rủi ro thấp” nếu chưa có risk scoring.

---

## 14. Definition of Done

Một báo cáo được coi là đạt chuẩn nếu thỏa toàn bộ tiêu chí:

| Category | Requirement |
|---|---|
| Structure | Đủ 8 section chính, PDF khoảng 8 trang |
| Data | Có source manifest và data cutoff |
| Financials | Có bảng financial summary và forecast summary |
| Valuation | Có FCFF DCF, assumptions, target price, sensitivity |
| Rating | BUY/HOLD/SELL/UNDER_REVIEW theo threshold và đã review |
| Charts | Có tối thiểu 5 chart chính nếu dữ liệu đủ |
| Citation | 100% claim định lượng có citation hoặc artifact reference |
| Numeric | >=99% numeric consistency |
| Reproducibility | Target price recompute được từ valuation_result |
| Risk | Rủi ro cụ thể, gắn financial driver |
| Disclaimer | Có disclaimer chuẩn |
| Audit | Có eval_result, claim_ledger, run_log |
| Human Review | Có approval record trước final export |

---

## 15. Minimal viable report cho demo 6 tuần

Nếu không đủ thời gian làm bản full 8 trang, demo tối thiểu phải có:

1. Page 1: Investment snapshot + thesis + price chart.
2. Page 2: Company overview.
3. Page 3: Financial performance + 2 charts.
4. Page 4: Forecast assumptions + forecast table.
5. Page 5: FCFF DCF + target price.
6. Page 6: Sensitivity + risks.
7. Appendix artifact: `claim_ledger`, `source_manifest`, `valuation_result`, `eval_result`.

Không được cắt bỏ valuation audit, citation audit hoặc numeric audit, vì đây là lõi tin cậy của dự án.

---

## 16. Final instruction for report-generating agent

Sinh báo cáo như một analyst chuyên nghiệp, nhưng vận hành như một hệ thống kiểm định dữ liệu nghiêm ngặt.

Ưu tiên theo thứ tự:

```text
Correctness > Traceability > Valuation Reproducibility > Risk Balance > Readability > Visual Design
```

Không được đánh đổi độ đúng số liệu để lấy văn phong hay. Một báo cáo ngắn nhưng đúng nguồn, đúng số, đúng valuation tốt hơn một báo cáo dài, đẹp nhưng không thể kiểm chứng.
