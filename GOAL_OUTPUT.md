# GOAL_OUTPUT.md — Chuẩn đầu ra báo cáo định giá cổ phiếu

**Project:** Vietnam Pharma Multi-Agent Equity Research Agent  
**Document type:** Final report output specification + artifact contract + export gates  
**Primary output artifact:** Vietnamese professional equity research report, PDF-ready, tối đa khoảng 8 trang A4  
**Primary audience:** analyst, reviewer, giảng viên, nhà đầu tư có kiến thức cơ bản  
**Report language:** Tiếng Việt chuyên nghiệp, trung lập, có nguồn, không viết kiểu quảng cáo  
**Reference style:** Báo cáo equity research chuyên nghiệp như mẫu LLY, nhưng được nâng cấp bằng citation, lineage, valuation reproducibility và human review  
**Version:** v2.0  
**Status:** Revised after output-spec audit  

---

## 0. Executive Summary

Tài liệu này định nghĩa chuẩn đầu ra cuối cùng cho hệ thống **Vietnam Pharma Multi-Agent Equity Research Agent** khi sinh báo cáo phân tích và định giá cổ phiếu ngành dược/y tế Việt Nam.

Chuẩn này dùng mẫu equity research như LLY làm tham chiếu về **nhịp đọc, bố cục, độ cô đọng và kiểu trình bày**, nhưng không copy nguyên mẫu. Báo cáo của dự án phải mạnh hơn mẫu tham chiếu ở các điểm sau:

1. Mỗi số liệu quan trọng phải truy vết được về `canonical_fact`, `computed_metric` hoặc `valuation_result`.
2. Mỗi claim định lượng phải có citation hoặc artifact reference hợp lệ.
3. Valuation phải chạy bằng deterministic Python engine, không để LLM tự tính toán trong văn bản.
4. Forecast phải dựa trên driver rõ ràng: business driver -> financial line item -> assumption -> valuation impact.
5. Report final chỉ được export khi pass các gate bắt buộc: source, numeric consistency, valuation reproducibility, citation, risk language và human review.
6. PDF phải đủ chuyên nghiệp về layout, bảng, biểu đồ, nguồn, disclaimer và page budget.

Tài liệu này là **single-file master spec** để tiện cho Claude/code agent triển khai. Tuy nhiên, về mặt kiến trúc, nội dung được chia logic thành ba lớp:

```text
Layer A — Report Output Spec
  Quy định nội dung, cấu trúc, page budget, chart, layout và văn phong của báo cáo PDF/Markdown.

Layer B — Artifact Contracts
  Quy định schema tối thiểu cho claim_ledger, source_manifest, valuation_result, eval_result và run_log.

Layer C — Generation Gates
  Quy định các điều kiện kiểm định trước khi report được export thành final.
```

---

## 1. Mục tiêu của tài liệu

### 1.1. Mục tiêu sản phẩm

Đầu ra cuối cùng của hệ thống là một **báo cáo equity research tiếng Việt** cho cổ phiếu ngành dược/y tế Việt Nam, có khả năng:

- trình bày thesis đầu tư rõ ràng;
- giải thích doanh nghiệp kiếm tiền từ đâu;
- phân tích xu hướng tài chính lịch sử;
- dự phóng dựa trên driver;
- định giá bằng FCFF DCF và kiểm tra chéo bằng multiples;
- trình bày sensitivity, scenario, peer comparison;
- nêu catalyst và rủi ro gắn với financial driver;
- có citation, audit summary và disclaimer;
- export được thành Markdown, HTML và PDF.

### 1.2. Mục tiêu kỹ thuật

Báo cáo không được là kết quả viết tự do của LLM. Báo cáo chỉ được sinh từ các artifact đã kiểm soát:

```text
canonical financial facts
computed financial metrics
valuation_result.json
source_manifest.json
claim_ledger.json
evidence packs
approved assumptions
eval_result.json
run_log.json
```

LLM chỉ đóng vai trò:

1. tổng hợp và diễn giải các artifact đã có;
2. viết narrative theo cấu trúc đã khóa;
3. giải thích logic driver, rủi ro và valuation bằng ngôn ngữ analyst;
4. không được tự tạo số liệu hoặc tự sửa kết quả valuation.

### 1.3. Mục tiêu trình bày

Báo cáo final cần đạt hai yêu cầu đồng thời:

| Yêu cầu | Ý nghĩa |
|---|---|
| Professional readability | Đọc giống một equity research report chuyên nghiệp, không giống log kỹ thuật. |
| Machine-auditable output | Mọi số, claim, chart và conclusion quan trọng có thể truy vết về artifact. |

Vì vậy, trong PDF client-facing chỉ hiển thị audit summary gọn. Chi tiết kỹ thuật như mismatch list, full claim ledger, full source manifest, trace và gate failure phải nằm trong appendix artifact hoặc JSON, không làm rối thân báo cáo.

---

## 2. Phạm vi đầu ra

### 2.1. In-scope

Báo cáo output chuẩn áp dụng cho:

- cổ phiếu dược/y tế Việt Nam trên HOSE, HNX, UPCOM;
- full equity research report;
- report bằng tiếng Việt;
- forecast tối thiểu 3 năm, khuyến nghị 5 năm;
- valuation bằng FCFF DCF làm phương pháp chính;
- P/E, P/B, EV/EBITDA làm kiểm tra chéo nếu dữ liệu đủ;
- sensitivity và scenario analysis;
- catalyst/risk đặc thù ngành dược Việt Nam;
- citation và audit trail.

### 2.2. Out-of-scope

Report final không được thể hiện như:

- hệ thống tự động khuyến nghị giao dịch;
- tín hiệu mua/bán ngắn hạn;
- báo cáo không nguồn;
- báo cáo chỉ dựa trên dữ liệu thị trường từ API mà không có kiểm chứng;
- báo cáo dùng LLM để tự tính financial facts hoặc valuation;
- báo cáo cá nhân hóa cho một nhà đầu tư cụ thể.

---

## 3. Nguyên tắc bắt buộc

### 3.1. Facts before narrative

Không được viết nhận định tài chính trước khi có số liệu, nguồn và phép tính. Mọi số như doanh thu, lợi nhuận, EPS, WACC, FCFF, target price, upside/downside, market cap, P/E, P/B, ROE, ROA, biên lợi nhuận phải truy vết được về một trong các artifact sau:

```text
canonical_fact
computed_metric
valuation_result
approved_assumption
```

Nếu một số không truy vết được, số đó không được xuất hiện trong báo cáo final.

### 3.2. Code-first valuation

LLM không được tự tính DCF, FCFF, EPS, CAGR, P/E, P/B, EV/EBITDA, ROE, ROA, WACC hoặc target price bằng văn bản. LLM chỉ được diễn giải kết quả do deterministic Python engine trả về.

Các phép tính bắt buộc phải do code thực hiện:

```text
financial ratio calculation
historical growth calculation
CAGR
working capital metrics
FCFF
DCF discounting
terminal value
equity value
target price
upside/downside
sensitivity matrix
scenario table
weighted valuation summary
```

### 3.3. Citation-first reporting

Mọi claim định lượng và mọi claim định tính quan trọng phải có nguồn.

| Loại claim | Ví dụ | Citation bắt buộc |
|---|---|---|
| Số liệu tài chính | Doanh thu 2024 đạt X tỷ đồng | Có |
| Dự phóng | Doanh thu 2026F tăng X% | Có, trỏ về valuation artifact hoặc approved assumption |
| Thông tin doanh nghiệp | Công ty sở hữu nhà máy GMP-WHO | Có |
| Catalyst | Kết quả đấu thầu, BHYT, đăng ký thuốc | Có |
| Rủi ro | Phụ thuộc sản phẩm chính, áp lực giá thầu | Có |
| Peer comparison | P/E thấp hơn trung vị ngành | Có |
| Nhận định chung | “vị thế tốt”, “tăng trưởng ổn định” | Có evidence hoặc viết thận trọng |

Không được dùng citation chung chung kiểu:

```text
Source: database
Source: vnstock
Source: market data
Source: company filings
```

Trừ khi source tag đó có thể click hoặc truy ngược về `source_manifest.source_id`, `fact_id`, document chunk, URL hoặc file path cụ thể.

### 3.4. Driver-based forecast

Forecast không được chỉ là kéo dài số quá khứ. Forecast phải thể hiện logic:

```text
business driver -> affected financial line item -> assumption -> forecast output -> valuation impact
```

Ví dụ:

```text
Đấu thầu thuốc -> doanh thu ETC / gross margin -> giả định giá bán giảm x bps -> EBIT giảm -> FCFF giảm
Tồn kho tăng -> net working capital -> ΔNWC tăng -> FCFF giảm
Mở rộng nhà máy -> sản lượng / CAPEX / depreciation -> revenue tăng nhưng FCFF ngắn hạn giảm
```

### 3.5. Không đưa lời khuyên cá nhân hóa

Báo cáo có thể có rating cấp độ báo cáo như `BUY`, `HOLD`, `SELL`, `UNDER REVIEW`, nhưng phải diễn đạt là **kết luận định giá dựa trên mô hình, dữ liệu và giả định hiện tại**, không phải lời khuyên đầu tư cá nhân hóa.

Câu chuẩn bắt buộc đưa vào disclaimer hoặc phần rating note:

```text
Rating trong báo cáo là kết luận mô hình dựa trên dữ liệu, giả định và mức sinh lời kỳ vọng tại thời điểm lập báo cáo; không phải khuyến nghị đầu tư cá nhân hóa.
```

### 3.6. Human approval gate

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

Nếu một trong các gate fail, hệ thống phải xuất `NEEDS_REVIEW`, `PENDING_APPROVAL` hoặc `BLOCKED`, không được giả vờ hoàn chỉnh.

---

## 4. File đầu ra bắt buộc

Mỗi research run phải tạo tối thiểu các file sau:

```text
artifacts/
├── reports/{run_id}_{ticker}_report.md
├── reports_html/{run_id}_{ticker}_report.html
├── reports_pdf/{run_id}_{ticker}_report.pdf
├── charts/{run_id}_{ticker}_{chart_id}.png
├── valuation_results/{run_id}_{ticker}_valuation_result.json
├── claim_ledgers/{run_id}_{ticker}_claim_ledger.json
├── source_manifests/{run_id}_{ticker}_source_manifest.json
├── eval_results/{run_id}_{ticker}_eval_result.json
└── run_logs/{run_id}_{ticker}_run_log.json
```

### 4.1. Report status

Mỗi report phải có trạng thái rõ ràng:

```yaml
report_status:
  - DRAFT
  - NEEDS_REVIEW
  - PENDING_APPROVAL
  - APPROVED
  - BLOCKED
  - FINAL_EXPORTABLE
```

Không được xuất PDF final nếu status chưa phải `FINAL_EXPORTABLE`.

### 4.2. Artifact immutability

Các artifact dùng để sinh final report phải được version hóa. Nếu số liệu, source, assumption hoặc valuation thay đổi, report phải tạo version mới thay vì ghi đè âm thầm.

```text
same_run_id + changed_artifact_hash = invalid final export
new_artifact_hash -> rerun affected stages -> regenerate report version
```

---

## 5. PDF-ready rendering specification

### 5.1. Page setup

| Thuộc tính | Chuẩn |
|---|---|
| Khổ giấy | A4 portrait |
| Độ dài | Tối đa khoảng 8 trang cho full report body |
| Margin | 16-20mm mỗi cạnh |
| Header | Ticker, company name, report type, report date |
| Footer | Page number, short source/disclaimer note |
| Ngôn ngữ | Tiếng Việt |
| Tông giọng | Chuyên nghiệp, phân tích, trung lập |
| Citation | Source tag ngắn trong thân bài; full source trong artifact |
| Disclaimer | Bắt buộc cuối báo cáo |
| Executive summary | Bắt buộc trang 1 |
| Valuation assumptions | Bắt buộc ở phần định giá |
| Sensitivity | Bắt buộc nếu có target price |

### 5.2. Typography

| Element | Recommended size | Rule |
|---|---:|---|
| Report title | 18-22pt | Không quá dài, ưu tiên ticker + company |
| Section heading | 13-15pt | Rõ cấp bậc, không dùng quá nhiều cấp |
| Body text | 8.5-10pt | Dễ đọc trên A4 |
| Table text | 7.5-9pt | Không nhồi quá nhiều cột |
| Chart title | 9-11pt | Phải có kỳ và đơn vị |
| Source caption | 6.5-8pt | Bắt buộc dưới chart/table nếu có nguồn |

### 5.3. Layout grid

| Page type | Layout khuyến nghị |
|---|---|
| Page 1 | Snapshot layout: rating block + key metrics + thesis + 1 chart |
| Analytical pages | 55/45 hoặc 60/40 text-chart split |
| Valuation page | Bảng lớn full-width + commentary ngắn |
| Sensitivity page | Matrix/table full-width, narrative ngắn |
| Risk page | Bảng catalysts và risks, ít prose |
| Final page | Key takeaways + client-facing quality summary + key sources + disclaimer |

### 5.4. Chart rendering rules

Mỗi chart phải có:

```text
title
period
unit
source_caption
actual_or_forecast_marker
```

Không được dùng chart nếu:

- dữ liệu thiếu kỳ;
- dữ liệu nhầm đơn vị;
- dữ liệu chưa pass numeric gate;
- chart không hỗ trợ decision-making;
- chart chỉ được thêm để làm đẹp.

### 5.5. Table rendering rules

| Rule | Mô tả |
|---|---|
| Max columns | Tối đa 10 cột trong PDF, trừ sensitivity matrix |
| Unit clarity | Phải ghi rõ tỷ VND, %, x, VND/share |
| Forecast marker | Actual dùng `A`, forecast dùng `F`, TTM ghi rõ `TTM` |
| Negative values | Phải hiển thị nhất quán, không mất dấu âm |
| Source | Bảng tài chính phải có source tag hoặc artifact reference |

---

## 6. Quy tắc nén nội dung 8 trang

Báo cáo không được cố đưa toàn bộ bảng dự phóng chi tiết vào thân PDF. PDF chỉ hiển thị bảng tóm tắt; chi tiết nằm trong appendix hoặc JSON artifact.

| Nội dung | Cách xử lý trong PDF 8 trang |
|---|---|
| Bảng KQKD 10 năm | Chỉ hiển thị 5-7 dòng chính: doanh thu thuần, lợi nhuận gộp, EBIT/EBITDA, LNST, EPS, biên gộp, biên ròng |
| Bảng cân đối kế toán | Chỉ hiển thị tài sản, nợ vay, VCSH, tiền, hàng tồn kho, phải thu nếu liên quan thesis |
| Bảng lưu chuyển tiền tệ | Chỉ hiển thị CFO, CAPEX, FCF/FCFF, working capital |
| Ratio table | Chọn 10-14 chỉ số chính |
| Industry overview | Không viết thành section riêng trong MVP; lồng vào catalyst/risk nếu có evidence |
| News list | Không liệt kê quá nhiều; chỉ chọn catalyst material |
| Peer comparison | Chỉ hiển thị peer median và 3-5 peer liên quan |
| Audit detail | Client-facing summary trong PDF; full detail trong `eval_result.json` |

### 6.1. Page budget bắt buộc

| Page | Nội dung | Budget |
|---|---|---|
| 1 | Cover + Investment Snapshot | 1 chart hoặc chart mini; thesis 180-220 từ |
| 2 | Company Overview + Business Model | 450-650 từ hoặc 1 bảng driver |
| 3 | Financial Performance | 1 bảng summary + tối đa 3 chart |
| 4 | Forecast & Key Assumptions | 1 forecast table + 1 driver table + 1 chart |
| 5 | Valuation | 1 DCF table + 1 valuation summary + 1 assumptions table |
| 6 | Sensitivity, Scenario & Peer Check | 1 sensitivity matrix + 1 scenario table + 1 peer table |
| 7 | Catalysts & Risks | 2 bảng chính, narrative tối đa 250 từ |
| 8 | Conclusion, Quality Summary, Sources & Disclaimer | Gọn, không biến thành technical log |

Nếu nội dung vượt quá budget, renderer phải ưu tiên:

```text
Correctness > Traceability > Valuation Reproducibility > Decision Utility > Visual Design > Completeness of prose
```

---

## 7. Cấu trúc báo cáo 8 trang

## Page 1 — Cover + Investment Snapshot

### 7.1.1. Mục tiêu

Người đọc phải hiểu ngay:

- mã cổ phiếu;
- rating;
- current price;
- target price;
- upside/downside;
- horizon;
- risk level;
- data confidence;
- thesis chính;
- rủi ro chính;
- dữ liệu được cập nhật đến ngày nào.

### 7.1.2. Input bắt buộc

```text
ticker_metadata
market_data
valuation_result
computed_metrics
claim_ledger
source_manifest
price_history
benchmark_price_history
```

### 7.1.3. Bố cục bắt buộc

1. Header:
   - `Equity Research Report`
   - Ticker
   - Tên doanh nghiệp
   - Sàn giao dịch
   - Ngành: Dược/Y tế
   - Ngày lập báo cáo
   - Data cutoff
   - Kỳ dữ liệu gần nhất

2. Rating block:
   - `Rating`: BUY / HOLD / SELL / UNDER REVIEW
   - `Current Price`
   - `Target Price`
   - `Upside/Downside`
   - `Investment Horizon`
   - `Risk Level`
   - `Data Confidence`

3. Key metrics snapshot:
   - Market Cap
   - Net Revenue FY gần nhất hoặc TTM
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
   - 180-220 từ.
   - Phải bao gồm: growth driver, profitability outlook, valuation view, key risk.
   - Mỗi claim chính phải map vào claim ledger.

5. Chart 1:
   - So sánh diễn biến giá cổ phiếu với VNINDEX trong 1Y hoặc 3Y.
   - Chuẩn hóa base 100 tại ngày đầu kỳ.
   - Có source caption.

### 7.1.4. Template

```markdown
# {TICKER} — {COMPANY_NAME}
## Equity Research Report | Ngành Dược/Y tế Việt Nam

| Rating | Current Price | Target Price | Upside/Downside | Horizon | Risk | Data Confidence |
|---|---:|---:|---:|---|---|---|
| {BUY/HOLD/SELL/UNDER_REVIEW} | {current_price} VND | {target_price} VND | {upside_pct}% | 12M | {risk_level} | {data_confidence} |

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

{5-7 dòng ngắn, có citation hoặc claim ledger reference.}

![Stock vs VNINDEX](charts/{ticker}_price_vs_vnindex.png)
```

### 7.1.5. Fallback

Nếu không có price history hoặc VNINDEX benchmark hợp lệ:

```text
Không vẽ Chart 1.
Thay bằng note: Dữ liệu diễn biến giá chưa đủ điều kiện kiểm định để hiển thị trong báo cáo final.
Report status tối thiểu là NEEDS_REVIEW nếu current price cũng không đáng tin cậy.
```

---

## Page 2 — Company Overview + Business Model

### 7.2.1. Mục tiêu

Giải thích doanh nghiệp kiếm tiền từ đâu, sản phẩm hoặc kênh nào đóng góp chính, và các driver vận hành nào ảnh hưởng đến forecast.

### 7.2.2. Nội dung bắt buộc

| Block | Nội dung |
|---|---|
| Company profile | Tên đầy đủ, năm thành lập, sàn, lĩnh vực chính |
| Business model | Sản xuất, phân phối, ETC/OTC, thiết bị y tế, bệnh viện, dịch vụ y tế tùy doanh nghiệp |
| Product/revenue mix | Sản phẩm/nhóm sản phẩm chính nếu có dữ liệu |
| Competitive position | GMP, hệ thống phân phối, thương hiệu, danh mục thuốc, năng lực đấu thầu nếu có evidence |
| Growth strategy | Mở rộng nhà máy, sản phẩm mới, kênh ETC/OTC, M&A, xuất khẩu |
| Key operating drivers | Giá bán, sản lượng, biên gộp, đấu thầu, BHYT, tồn kho, working capital |

### 7.2.3. Business driver table bắt buộc nếu có dữ liệu

```markdown
| Driver | Business Meaning | Financial Line Item | Direction | Evidence |
|---|---|---|---|---|
| Kênh ETC | Doanh thu bệnh viện/đấu thầu | Revenue, gross margin | Positive/Negative | SRC-... |
| Giá thầu thuốc | Áp lực giá bán | Revenue, gross margin | Negative | SRC-... |
| Nguyên liệu nhập khẩu | Chi phí đầu vào | COGS, gross margin | Negative/Neutral | SRC-... |
| Tồn kho/phải thu | Vốn lưu động | ΔNWC, FCFF | Negative if rising | FACT-... |
```

### 7.2.4. Writing constraints

Không được:

- viết lịch sử doanh nghiệp quá dài;
- tuyên bố “dẫn đầu ngành” nếu không có nguồn;
- copy nguyên văn báo cáo thường niên;
- đưa nhận định tăng trưởng nếu chưa gắn với driver và evidence;
- viết generic như “công ty có vị thế tốt” mà không giải thích bằng số hoặc source.

Độ dài: 450-650 từ.

---

## Page 3 — Financial Performance

### 7.3.1. Mục tiêu

Cho thấy xu hướng tài chính lịch sử, chất lượng tăng trưởng, biên lợi nhuận, hiệu quả sử dụng vốn và điểm bất thường.

### 7.3.2. Nội dung bắt buộc

1. Revenue & profitability:
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

4. Abnormal movement analysis:
   - Flag nếu biến động YoY vượt ngưỡng cấu hình.
   - Mỗi flag phải có reason và source.

### 7.3.3. Bảng financial summary

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

### 7.3.4. Charts bắt buộc nếu dữ liệu đủ

| Chart | Loại | Nội dung |
|---|---|---|
| C2 | Bar + line | Revenue + EBITDA/EBIT margin |
| C3 | Line/bar | EPS + P/E hoặc LNST + biên ròng |
| C4 | Multi-line | Gross margin, net margin, ROE |

### 7.3.5. Narrative chuẩn

Thứ tự viết bắt buộc:

```text
1. Nêu xu hướng chính.
2. Nêu driver hoặc nguyên nhân có evidence.
3. Chỉ ra điểm bất thường nếu có.
4. Giải thích tác động tới forecast hoặc valuation.
```

Không được nói “tốt/xấu” chung chung. Phải nói biến động ảnh hưởng thế nào đến revenue, margin, working capital, WACC, multiple hoặc FCFF.

---

## Page 4 — Forecast & Key Assumptions

### 7.4.1. Mục tiêu

Trình bày forecast một cách có logic, có driver, có assumption, có source và có trạng thái approval.

### 7.4.2. Forecast horizon

Khuyến nghị:

```text
Base actual year: FY gần nhất đã kiểm định hoặc TTM nếu đủ tin cậy
Forecast horizon: 2026F-2030F hoặc 5 năm tính từ năm base
Minimum horizon: 3 năm
Preferred horizon: 5 năm
```

### 7.4.3. Forecast logic bắt buộc

Forecast phải bao gồm tối thiểu:

- Revenue growth driver.
- Gross margin assumption.
- SG&A/sales assumption.
- Tax rate.
- Working capital assumption.
- CAPEX/depreciation assumption.
- Terminal growth hoặc exit multiple nếu dùng.

### 7.4.4. Driver-based planning table

Bảng này là bắt buộc, vì đây là cầu nối giữa business analysis và valuation.

```markdown
| Driver | Linked Line Item | Direction | Base Assumption | Evidence | Valuation Impact | Approval Status |
|---|---|---|---:|---|---|---|
| Sản lượng/kênh ETC | Revenue | Positive | +x% | SRC-... | Tăng FCFF | approved/pending_review |
| Giá thầu thuốc | Gross margin | Negative | -x bps | SRC-... | Giảm EBIT, giảm FCFF | approved/pending_review |
| Chi phí nguyên liệu | COGS | Negative | +x bps | SRC-... | Giảm gross margin | approved/pending_review |
| Tồn kho/phải thu | ΔNWC | Negative | +x ngày | FACT-... | Giảm FCFF | approved/pending_review |
```

### 7.4.5. Forecast table

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

### 7.4.6. Assumptions table

```markdown
| Assumption | Base Case | Rationale | Source/Artifact | Approval Status |
|---|---:|---|---|---|
| Revenue CAGR 2026F-2030F | {x}% | {rationale} | {source_id/artifact_id} | approved/pending_review |
| Gross margin | {x}% | {rationale} | {source_id/artifact_id} | approved/pending_review |
| SG&A / Revenue | {x}% | {rationale} | {source_id/artifact_id} | approved/pending_review |
| Tax rate | {x}% | {rationale} | {source_id/artifact_id} | approved/pending_review |
| WACC | {x}% | {rationale} | valuation_result | approved/pending_review |
| Terminal growth | {x}% | {rationale} | valuation_result | approved/pending_review |
```

### 7.4.7. Chart bắt buộc nếu dữ liệu đủ

| Chart | Loại | Nội dung |
|---|---|---|
| C5 | Bar + line | Forecast revenue and profit hoặc revenue and FCFF |

### 7.4.8. Forecast writing rules

Agent phải giải thích ít nhất 3 driver lớn nhất làm thay đổi forecast:

```yaml
driver_name:
affected_line_item:
direction: positive | negative | neutral
magnitude_estimate:
evidence:
assumption_status: approved | pending_review
valuation_impact:
```

Không được viết:

```text
Doanh thu được dự phóng tăng ổn định do triển vọng ngành tích cực.
```

Nếu không có driver và source, phải viết:

```text
Chưa đủ bằng chứng để gán nguyên nhân cụ thể cho giả định tăng trưởng; assumption cần reviewer phê duyệt trước khi export final.
```

---

## Page 5 — Valuation: FCFF DCF + Relative Multiples

### 7.5.1. Mục tiêu

Chốt giá mục tiêu bằng mô hình định giá có thể tái lập, minh bạch assumption và có kiểm tra chéo bằng multiples.

### 7.5.2. Phương pháp bắt buộc

1. FCFF DCF là phương pháp chính.
2. P/E, P/B, EV/EBITDA là phương pháp kiểm tra chéo nếu dữ liệu đủ.
3. EV/Sales chỉ dùng nếu doanh nghiệp đặc thù và có giải thích.
4. Không dùng multiples nếu peer không đủ tương đồng hoặc dữ liệu không đáng tin cậy.

### 7.5.3. Công thức chuẩn

```text
FCFF = EBIT × (1 - Tax Rate) + Depreciation - CAPEX - ΔNWC

EV = Σ PV(FCFF_t) + PV(Terminal Value)

Equity Value = EV + Cash & Equivalents - Debt - Minority Interest

Target Price = Equity Value / Diluted Shares Outstanding

Upside/Downside = (Target Price / Current Price) - 1
```

Các công thức phải được implement trong Python engine. Markdown report chỉ diễn giải kết quả.

### 7.5.4. Bảng DCF summary

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

### 7.5.5. Valuation summary table

```markdown
| Method | Implied Equity Value | Implied Price | Weight | Weighted Price | Status |
|---|---:|---:|---:|---:|---|
| DCF - FCFF | | | | | valid/limited |
| P/E | | | | | valid/limited |
| P/B | | | | | valid/limited |
| EV/EBITDA | | | | | valid/limited |
| Final Target Price | | | 100% | | |
```

### 7.5.6. Valuation assumptions table

```markdown
| Parameter | Value | Source/Method |
|---|---:|---|
| Risk-free rate | | valuation_result |
| Beta | | valuation_result/source |
| Equity risk premium | | valuation_result/source |
| Cost of equity | | valuation_result |
| Cost of debt | | valuation_result |
| Tax rate | | valuation_result/computed_metric |
| WACC | | valuation_result |
| Terminal growth | | valuation_result |
| Net debt / cash | | canonical_fact/computed_metric |
| Shares outstanding | | canonical_fact/source |
```

### 7.5.7. DCF value bridge

Khuyến nghị có chart C6 nếu dữ liệu đủ:

| Chart | Loại | Nội dung |
|---|---|---|
| C6 | Waterfall | Enterprise value -> net debt/cash -> equity value -> target price |

### 7.5.8. Narrative chuẩn

Thứ tự viết bắt buộc:

```text
1. Nêu phương pháp chính và lý do phù hợp.
2. Giải thích target price đến từ đâu.
3. So sánh target price với current price.
4. Nêu assumption nhạy nhất.
5. Nêu điều kiện khiến rating thay đổi.
```

Không được kết luận chắc chắn. Phải viết theo điều kiện assumptions.

Ví dụ đúng:

```text
Trong base case đã được phê duyệt, FCFF DCF cho ra giá trị hợp lý X VND/cp. Kết quả này nhạy nhất với WACC và terminal growth; khi WACC tăng 100 bps, target price giảm về Y VND/cp. Do đó, rating hiện tại phụ thuộc đáng kể vào khả năng duy trì biên EBIT và kiểm soát vốn lưu động.
```

---

## Page 6 — Sensitivity, Scenario & Peer Check

### 7.6.1. Mục tiêu

Cho reviewer thấy mô hình có bền không khi giả định thay đổi.

### 7.6.2. Sensitivity bắt buộc

Phải có ít nhất một trong hai dạng:

1. Sensitivity target price theo `WACC` và `terminal growth`.
2. Sensitivity theo `revenue CAGR` và `EBIT/EBITDA margin` nếu terminal assumptions không phù hợp.

### 7.6.3. Sensitivity matrix

```markdown
| Target Price Sensitivity | WACC -1.0% | WACC -0.5% | Base WACC | WACC +0.5% | WACC +1.0% |
|---|---:|---:|---:|---:|---:|
| g -0.5% | | | | | |
| Base g | | | | | |
| g +0.5% | | | | | |
```

### 7.6.4. Scenario table

```markdown
| Scenario | Revenue CAGR | Margin Assumption | WACC | Target Price | Upside/Downside | Rating Implication |
|---|---:|---:|---:|---:|---:|---|
| Bear | | | | | | |
| Base | | | | | | |
| Bull | | | | | | |
```

### 7.6.5. Peer comparison table

```markdown
| Ticker | Business Type | Market Cap | P/E | P/B | EV/EBITDA | ROE | Net Margin |
|---|---|---:|---:|---:|---:|---:|---:|
| {ticker} | | | | | | | |
| Peer Median | | | | | | | |
```

### 7.6.6. Peer rules

- Peer phải thuộc ngành dược/y tế Việt Nam hoặc có lý do tương đồng rõ.
- Nếu không có peer đủ tương đồng, ghi `peer comparison limited` thay vì ép so sánh.
- Không dùng peer global nếu không điều chỉnh khác biệt thị trường, quy mô và mô hình kinh doanh.
- Peer comparison không được tự động kéo rating nếu DCF và data confidence không đủ.

### 7.6.7. Sensitivity risk flag

Report phải flag `valuation_extreme_sensitivity` nếu một trong các điều kiện xảy ra:

```text
WACC +1.0% làm target price đổi rating từ BUY sang SELL hoặc từ SELL sang BUY
terminal growth +/-0.5% làm target price thay đổi quá ngưỡng cấu hình
base case target price nằm ngoài vùng hợp lý của peer check mà không có giải thích
```

Nếu flag này bật, rating tối đa là `UNDER REVIEW` cho đến khi reviewer approve.

---

## Page 7 — Catalysts & Investment Risks

### 7.7.1. Mục tiêu

Trình bày điều gì có thể làm thesis đúng hoặc sai trong 6-12 tháng tới.

### 7.7.2. Positive catalysts table

```markdown
| Catalyst | Expected Timing | Affected Driver | Impact | Probability | Evidence |
|---|---|---|---|---|---|
| | | Revenue/margin/WACC/multiple | Low/Medium/High | Low/Medium/High | SRC-... |
```

### 7.7.3. Downside risks table

```markdown
| Risk | Affected Driver | Financial Impact | Mitigation/Monitor | Evidence |
|---|---|---|---|---|
| Áp lực giảm giá thầu | Gross margin/revenue | High | Theo dõi kết quả đấu thầu | SRC-... |
| Phụ thuộc sản phẩm chính | Revenue stability | Medium | Theo dõi product mix | SRC-... |
| Tồn kho/phải thu tăng | Working capital/FCFF | Medium | Theo dõi CCC | FACT-... |
```

### 7.7.4. Rủi ro đặc thù ngành dược/y tế Việt Nam cần kiểm tra

- Rủi ro đấu thầu thuốc.
- BHYT/reimbursement.
- Thay đổi quy định đăng ký/lưu hành thuốc.
- GMP/nhà máy/chất lượng sản xuất.
- Cạnh tranh generic.
- Phụ thuộc kênh ETC hoặc OTC.
- Biến động nguyên liệu nhập khẩu.
- Hàng tồn kho, phải thu bệnh viện/nhà thuốc.
- Tỷ giá nếu nhập nguyên liệu.
- Cổ tức, thanh khoản, free float.
- Rủi ro tập trung sản phẩm.
- Rủi ro thu hồi thuốc hoặc chất lượng sản phẩm.

### 7.7.5. Quy tắc viết risk

Mỗi rủi ro phải gắn với một financial driver.

Không viết:

```text
Thị trường biến động có thể ảnh hưởng đến giá cổ phiếu.
```

Phải viết:

```text
Nếu giá trúng thầu giảm mạnh hơn giả định base case, gross margin có thể giảm x bps, làm EBIT và FCFF thấp hơn mô hình hiện tại.
```

---

## Page 8 — Conclusion, Quality Summary, Sources & Disclaimer

### 7.8.1. Mục tiêu

Chốt lại báo cáo, hiển thị kết luận định giá, mức tin cậy, trạng thái kiểm định và disclaimer.

### 7.8.2. Nội dung bắt buộc

1. Key takeaways:
   - 3-5 bullet.
   - Mỗi bullet phải là kết luận có căn cứ.

2. Final valuation conclusion:
   - Rating.
   - Target price.
   - Upside/downside.
   - Điều kiện để rating thay đổi.

3. Client-facing quality summary:
   - Data confidence.
   - Source coverage.
   - Numeric consistency.
   - Valuation reproducibility.
   - Data cutoff.
   - Human review status.

4. Key sources:
   - Không liệt kê toàn bộ source nếu quá dài.
   - Hiển thị 5-10 nguồn quan trọng nhất.
   - Toàn bộ nguồn nằm trong `source_manifest.json`.

5. Disclaimer.

### 7.8.3. Client-facing quality summary table

```markdown
| Quality Item | Status | Notes |
|---|---|---|
| Data Confidence | High/Medium/Low | |
| Source Coverage | {x}% | |
| Numeric Consistency | PASS/FAIL | |
| Valuation Reproducibility | PASS/FAIL | |
| Data Cutoff | {date} | |
| Human Review | PASS/PENDING | |
```

### 7.8.4. Internal gate summary

Bảng gate chi tiết không bắt buộc hiển thị đầy đủ trong PDF client-facing. Full detail phải nằm trong `eval_result.json`.

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

### 7.8.5. Disclaimer chuẩn

```text
Báo cáo này chỉ nhằm mục đích nghiên cứu và tham khảo học thuật/sản phẩm. Nội dung không phải là khuyến nghị đầu tư cá nhân hóa, không phải lời mời mua/bán chứng khoán, và không thay thế tư vấn từ chuyên gia được cấp phép. Rating trong báo cáo là kết luận mô hình dựa trên dữ liệu, giả định và mức sinh lời kỳ vọng tại thời điểm lập báo cáo; không phải khuyến nghị đầu tư cá nhân hóa. Kết quả định giá phụ thuộc vào dữ liệu đầu vào, giả định mô hình và điều kiện thị trường tại thời điểm lập báo cáo. Hiệu suất quá khứ không đảm bảo kết quả tương lai. Người đọc chịu trách nhiệm độc lập khi sử dụng thông tin.
```

---

## 8. Rating policy

### 8.1. Rating labels

```yaml
rating_labels:
  - BUY
  - HOLD
  - SELL
  - UNDER_REVIEW
```

### 8.2. Default upside/downside threshold

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
      - unreliable_current_price
      - invalid_shares_outstanding
```

### 8.3. Enhanced rating rule

Rating không chỉ dựa vào upside/downside. Rating phải là hàm của:

```text
rating = function(
  upside_downside,
  data_confidence,
  sensitivity_risk,
  liquidity_risk,
  business_risk,
  valuation_reproducibility,
  citation_coverage,
  reviewer_approval
)
```

### 8.4. Không được đưa BUY/SELL/HOLD nếu

- Không có current price đáng tin cậy.
- Không có shares outstanding hợp lệ.
- Valuation không tái lập được.
- Target price thay đổi quá mạnh theo sensitivity.
- Dữ liệu tài chính stale hoặc chưa đủ kỳ.
- Claim định lượng chính thiếu citation.
- Reviewer chưa approve assumptions.
- Source mâu thuẫn ở financial facts trọng yếu.
- Thanh khoản quá thấp nhưng chưa được flag trong risk.
- Data confidence thấp hơn ngưỡng cấu hình.

Trong các trường hợp trên, rating phải là `UNDER REVIEW`.

---

## 9. Chart registry

Báo cáo 8 trang nên có tối đa 5-7 biểu đồ.

| Chart ID | Tên | Loại | Trang | Bắt buộc nếu dữ liệu đủ |
|---|---|---|---|---|
| C1 | Stock vs VNINDEX | Line, base 100 | Page 1 | Có |
| C2 | Revenue & EBITDA/EBIT Trend | Bar + line | Page 3 | Có |
| C3 | EPS & P/E Trend | Dual-axis line/bar | Page 3 | Có |
| C4 | Margin & ROE Trend | Multi-line | Page 3 | Có |
| C5 | Forecast Revenue/Profit | Bar + line | Page 4 | Có |
| C6 | DCF Value Bridge | Waterfall | Page 5 | Khuyến nghị |
| C7 | Sensitivity Heatmap | Heatmap/table | Page 6 | Có |

### 9.1. Chart generation contract

```json
{
  "chart_id": "C2",
  "title": "Revenue & EBITDA Margin Trend",
  "ticker": "DHG",
  "periods": ["2021A", "2022A", "2023A", "2024A", "2025A"],
  "metrics": ["net_revenue", "ebitda_margin"],
  "unit": "ty_vnd_and_percent",
  "data_refs": ["FACT-...", "METRIC-..."],
  "source_refs": ["SRC-..."],
  "status": "valid"
}
```

### 9.2. Chart fallback

Nếu chart bắt buộc không đủ dữ liệu:

```yaml
chart_status: omitted_due_to_missing_data
required_action:
  - explain_missing_data
  - do_not_fabricate_chart
  - flag_in_eval_result
```

---

## 10. Financial metric checklist

### 10.1. Metrics bắt buộc

| Nhóm | Chỉ số |
|---|---|
| Growth | Revenue growth, net profit growth, revenue CAGR, net profit CAGR |
| Profitability | Gross margin, EBIT/EBITDA margin, net margin, ROE, ROA |
| Valuation | EPS, BVPS, P/E, P/B, EV/EBITDA, dividend yield nếu có |
| Balance sheet | Debt/equity, net debt/cash, current ratio nếu có |
| Working capital | Inventory days, receivable days, payable days, cash conversion cycle nếu đủ dữ liệu |
| Cash flow | CFO, CAPEX, FCFF, FCF conversion nếu đủ dữ liệu |

### 10.2. Formula registry requirement

Formula IDs trong code phải đồng bộ chính xác với `FORMULA_FINANCE.md` nếu file đó tồn tại trong repository. Mục tiêu là để agent/tool calling gọi đúng deterministic Python function, không tự tính bằng ngôn ngữ tự nhiên.

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

### 10.3. Unit rules

| Data type | Internal storage | PDF display |
|---|---|---|
| VND amount | raw VND or normalized numeric with unit metadata | tỷ VND |
| Per-share | VND/share | VND/cp |
| Percent | decimal internally | % in PDF |
| Multiple | numeric | x |
| Date | ISO date | dd/mm/yyyy hoặc yyyy |

Không được trộn `triệu VND`, `tỷ VND`, `nghìn VND` nếu không có unit conversion rõ.

---

## 11. Claim ledger contract

Mỗi claim trong report phải được ghi vào `claim_ledger.json`.

### 11.1. Minimal schema

```json
{
  "claim_id": "CLM-001",
  "run_id": "RUN-...",
  "section": "investment_thesis",
  "page": 1,
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

### 11.2. Claim types

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
  - disclaimer
```

### 11.3. Support status

```yaml
support_status:
  supported: "Có đủ nguồn hoặc artifact"
  partially_supported: "Có nguồn nhưng thiếu một phần logic"
  unsupported: "Không được phép xuất hiện trong final report"
  conflicting: "Nguồn mâu thuẫn, cần review"
```

### 11.4. Final report rule

```text
unsupported claims allowed in final report = 0
conflicting claims allowed in final report = 0 unless explicitly labeled as conflict and approved by reviewer
```

---

## 12. Source manifest contract

### 12.1. Minimal schema

```json
{
  "source_id": "SRC-001",
  "run_id": "RUN-...",
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

### 12.2. Reliability tiers

```yaml
reliability_tier:
  official: "Company filing, exchange disclosure, audited financial statement"
  regulated_public: "Government/regulatory/tender/BHYT source"
  reputable_media: "Recognized business/financial media"
  third_party_data: "Market data/data API/vendor"
  unknown: "Not allowed for final claims unless reviewer approves with note"
```

### 12.3. Source usage rule

| Source type | Allowed usage |
|---|---|
| Official filing | Financial facts, business overview, management discussion |
| Audited financial statement | Canonical financial facts |
| Exchange disclosure | Events, corporate actions, listing data |
| Regulatory/tender/BHYT | Catalysts and policy risk |
| Reputable media | Context, catalyst, market interpretation |
| Third-party API | Market data or provisional data; must be reconciled for critical financial facts |
| Unknown source | Not allowed in final report |

---

## 13. Valuation result contract

`valuation_result.json` là nguồn duy nhất cho target price, upside/downside, DCF output, multiples output, sensitivity và scenario.

### 13.1. Minimal schema

```json
{
  "run_id": "RUN-...",
  "ticker": "DHG",
  "valuation_date": "2026-05-31",
  "currency": "VND",
  "base_year": "2025A",
  "forecast_years": ["2026F", "2027F", "2028F", "2029F", "2030F"],
  "current_price": 0,
  "target_price": 0,
  "upside_downside": 0,
  "rating_model_output": "UNDER_REVIEW",
  "fcff_dcf": {
    "wacc": 0,
    "terminal_growth": 0,
    "pv_fcff": 0,
    "terminal_value": 0,
    "pv_terminal_value": 0,
    "enterprise_value": 0,
    "cash_and_equivalents": 0,
    "debt": 0,
    "minority_interest": 0,
    "equity_value": 0,
    "shares_outstanding": 0,
    "implied_price": 0
  },
  "multiples": {
    "pe": {"implied_price": 0, "weight": 0, "status": "valid"},
    "pb": {"implied_price": 0, "weight": 0, "status": "valid"},
    "ev_ebitda": {"implied_price": 0, "weight": 0, "status": "valid"}
  },
  "sensitivity": {},
  "scenarios": {},
  "assumptions": [],
  "reproducibility_hash": "sha256:..."
}
```

### 13.2. Valuation reproducibility

Report final phải có khả năng recompute target price từ `valuation_result.json`.

```text
recomputed_target_price == reported_target_price within configured tolerance
```

Nếu không pass, export phải bị block.

---

## 14. Evaluation gates

### 14.1. Gate thresholds

```yaml
evaluation_thresholds:
  quantitative_claim_citation_coverage: 1.00
  numeric_consistency_min: 0.99
  valuation_reproducibility: 1.00
  unsupported_claims_allowed: 0
  conflicting_claims_allowed_without_label: 0
  stale_financial_data_allowed: false
  fake_citation_allowed: false
  final_confidence_min: 0.70
```

### 14.2. Source gate

Pass khi:

- tất cả financial facts chính có source;
- source tồn tại trong source manifest;
- source không thuộc tier `unknown` cho claim quan trọng;
- financial facts chính ưu tiên official hoặc reconciled source;
- không có source conflict chưa xử lý.

### 14.3. Numeric consistency gate

Agent phải kiểm tra:

- số trong report khớp với `canonical facts` hoặc `valuation_result`;
- đơn vị không bị sai: VND, tỷ VND, triệu VND, %, x;
- năm/kỳ không bị nhầm;
- forecast và actual được ký hiệu đúng;
- tổng tài sản = tổng nguồn vốn nếu hiển thị bảng cân đối kế toán;
- FCFF có thể recompute từ các thành phần;
- target price có thể recompute từ equity value và shares outstanding;
- chart data khớp với data trong bảng.

### 14.4. Citation gate

Pass khi:

```text
100% quantitative claims have valid citation or artifact reference
0 fake citation
0 dangling citation
0 citation pointing to wrong ticker
0 citation pointing to wrong period
```

### 14.5. Valuation reproducibility gate

Pass khi:

```text
DCF output recompute được từ valuation_result
final target price recompute được từ weighted valuation summary
upside/downside recompute được từ target price và current price
sensitivity matrix recompute được từ assumptions
```

### 14.6. Risk language gate

Pass khi:

- không có “chắc chắn”, “đảm bảo”, “nên mua ngay”;
- rating được giải thích là model conclusion;
- risks gắn với financial driver;
- disclaimer đầy đủ;
- report không đưa lời khuyên cá nhân hóa.

### 14.7. Human review gate

Pass khi:

```json
{
  "human_assumption_approval": "pass",
  "human_final_review": "pass",
  "approved_by": "reviewer_id",
  "approved_at": "timestamp",
  "approved_artifact_hashes": ["sha256:..."]
}
```

---

## 15. Report quality rubric

| Dimension | Score 1 | Score 3 | Score 5 |
|---|---|---|---|
| Accuracy | Nhiều lỗi số/nguồn | Có lỗi nhỏ | Số và nguồn nhất quán |
| Logicality | Luận điểm rời rạc | Có logic nhưng thiếu driver | Driver -> forecast -> valuation -> risk rõ |
| Storytelling | Dài, khó đọc | Đọc được | Ngắn gọn, chuyên nghiệp, có insight |
| Grounding | Thiếu citation | Citation chưa đều | Claim quan trọng đều có source |
| Valuation transparency | Assumption mơ hồ | Có bảng assumption | Reproducible, có sensitivity |
| Risk balance | Thiên lệch | Có rủi ro nhưng chung | Rủi ro cụ thể, gắn financial driver |
| Visual design | Rối, khó đọc | Đạt mức cơ bản | PDF gọn, chuyên nghiệp, đúng page budget |

### 15.1. Minimum target

```yaml
quality_targets:
  accuracy: 5
  logicality: 4
  storytelling: 4
  grounding: 5
  valuation_transparency: 5
  risk_balance: 4
  visual_design: 4
```

---

## 16. Markdown skeleton cho report final

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
risk_level: "{RISK_LEVEL}"
data_confidence: "{DATA_CONFIDENCE}"
status: "{DRAFT|NEEDS_REVIEW|PENDING_APPROVAL|APPROVED|BLOCKED|FINAL_EXPORTABLE}"
---

# {TICKER} — {COMPANY_NAME}
## Equity Research Report | {REPORT_DATE}

### Investment Snapshot

| Rating | Current Price | Target Price | Upside/Downside | Horizon | Risk Level | Data Confidence |
|---|---:|---:|---:|---|---|---|
| {RATING} | {CURRENT_PRICE} | {TARGET_PRICE} | {UPSIDE_DOWNSIDE} | {HORIZON} | {RISK_LEVEL} | {DATA_CONFIDENCE} |

### Key Metrics Snapshot

{KEY_METRICS_TABLE}

### Investment Thesis

{INVESTMENT_THESIS}

![Stock vs VNINDEX](charts/{TICKER}_price_vs_vnindex.png)

\pagebreak

## Company Overview & Business Model

{COMPANY_OVERVIEW}

{BUSINESS_DRIVER_TABLE_OR_REVENUE_MIX_CHART}

\pagebreak

## Financial Performance

{FINANCIAL_PERFORMANCE_NARRATIVE}

{FINANCIAL_SUMMARY_TABLE}

![Revenue & EBITDA Trend](charts/{TICKER}_revenue_ebitda.png)

![EPS & P/E Trend](charts/{TICKER}_eps_pe.png)

![Margin & ROE Trend](charts/{TICKER}_margin_roe.png)

\pagebreak

## Forecast & Key Assumptions

{FORECAST_NARRATIVE}

{DRIVER_BASED_FORECAST_TABLE}

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

## Sensitivity, Scenario & Peer Check

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

## Conclusion, Quality Summary & Disclaimer

### Key Takeaways

{KEY_TAKEAWAYS}

### Final Valuation Conclusion

{FINAL_CONCLUSION}

### Quality Summary

{CLIENT_FACING_QUALITY_SUMMARY}

### Key Sources

{KEY_SOURCES_TABLE}

### Disclaimer

{DISCLAIMER}
```

---

## 17. Agent execution instruction

Khi được yêu cầu sinh báo cáo, agent phải tuân thủ thứ tự sau:

```text
1. Load run state and ticker metadata.
2. Validate source_manifest and data freshness.
3. Load canonical facts.
4. Run deterministic financial metric computation.
5. Run deterministic valuation engine.
6. Generate chart data from computed artifacts.
7. Build or verify driver-based forecast table.
8. Ask/verify human approval for assumptions if required.
9. Draft section-by-section report narrative.
10. Build claim_ledger.
11. Run citation audit.
12. Run numeric consistency audit.
13. Run valuation reproducibility audit.
14. Run risk language audit.
15. Run visual/page-budget check.
16. If all gates pass, export report.md/html/pdf.
17. If any gate fails, mark report as NEEDS_REVIEW/BLOCKED/PENDING_APPROVAL and explain failure.
```

### 17.1. Section writing constraints

| Section | Allowed source | Prohibited |
|---|---|---|
| Investment Thesis | facts + valuation_result + claim ledger | Unsupported growth story |
| Company Overview | official filings + company source + verified news | Generic company praise |
| Financial Performance | canonical facts + computed metrics | LLM-calculated ratios |
| Forecast | approved assumptions + valuation artifact + driver table | Invented assumptions |
| Valuation | valuation_result only | Manual target price in text |
| Sensitivity | valuation_result only | Manually invented matrix |
| Risks | evidence + domain risk taxonomy | Generic risk list |
| Conclusion | passed gates + valuation summary | Personalized investment advice |

### 17.2. LLM prompt boundary

LLM prompt phải nhận artifact đã chuẩn hóa, không nhận raw unverified data để tự suy đoán.

```text
LLM input allowed:
- cleaned evidence snippets
- source metadata
- canonical facts summary
- computed metrics table
- valuation_result summary
- approved assumptions
- gate status summary

LLM input not allowed:
- unverified raw financial data as source of truth
- ambiguous API output without unit metadata
- unsupported news snippets without source metadata
- user instruction to alter rating without valuation evidence
```

---

## 18. Failure handling

Nếu thiếu dữ liệu hoặc kiểm định không pass, báo cáo không được giả vờ hoàn chỉnh.

### 18.1. Failure messages

| Failure | Report Status | Required Message |
|---|---|---|
| Missing financial facts | `NEEDS_REVIEW` | Thiếu dữ liệu tài chính cho kỳ X; không thể hoàn tất valuation |
| Source conflict | `NEEDS_REVIEW` | Nguồn A và B mâu thuẫn tại chỉ tiêu X |
| Failed numeric audit | `BLOCKED` | Số trong report không khớp artifact |
| Failed citation audit | `BLOCKED` | Có claim quan trọng thiếu nguồn |
| Failed valuation reproducibility | `BLOCKED` | Target price không tái lập được từ valuation_result |
| Extreme sensitivity | `NEEDS_REVIEW` | Target price quá nhạy với WACC/growth |
| Missing human approval | `PENDING_APPROVAL` | Assumptions/final report chưa được duyệt |
| Missing chart data | `NEEDS_REVIEW` hoặc `DRAFT` | Chart X bị bỏ vì thiếu dữ liệu đã kiểm định |
| Layout overflow | `NEEDS_REVIEW` | Report vượt page budget; cần nén nội dung hoặc chuyển appendix |

### 18.2. Không được dùng các câu sau

- “Có thể công ty sẽ tăng trưởng mạnh” nếu không có driver và nguồn.
- “Cổ phiếu chắc chắn hấp dẫn”.
- “Nên mua ngay”.
- “Theo dữ liệu thị trường” nhưng không nêu nguồn cụ thể.
- “Target price được tính toán” nhưng không có valuation artifact.
- “Rủi ro thấp” nếu chưa có risk scoring.
- “Nguồn: database” mà không có source id/fact id.

---

## 19. Definition of Done

Một báo cáo được coi là đạt chuẩn nếu thỏa toàn bộ tiêu chí:

| Category | Requirement |
|---|---|
| Structure | Đủ 8 section chính, PDF khoảng 8 trang |
| Visual | Layout chuyên nghiệp, chart/table rõ, không tràn page budget |
| Data | Có source manifest và data cutoff |
| Financials | Có bảng financial summary và forecast summary |
| Forecast | Có driver-based forecast table |
| Valuation | Có FCFF DCF, assumptions, target price, sensitivity |
| Rating | BUY/HOLD/SELL/UNDER_REVIEW theo threshold, data confidence và review |
| Charts | Có tối thiểu 5 chart chính nếu dữ liệu đủ |
| Citation | 100% claim định lượng có citation hoặc artifact reference |
| Numeric | >=99% numeric consistency |
| Reproducibility | Target price recompute được từ valuation_result |
| Risk | Rủi ro cụ thể, gắn financial driver |
| Disclaimer | Có disclaimer chuẩn |
| Audit | Có eval_result, claim_ledger, source_manifest, run_log |
| Human Review | Có approval record trước final export |

---

## 20. Minimal viable report cho demo 6 tuần

Nếu không đủ thời gian làm bản full 8 trang, demo tối thiểu phải có:

1. Page 1: Investment snapshot + thesis + price chart.
2. Page 2: Company overview + business model.
3. Page 3: Financial performance + 2 charts.
4. Page 4: Driver-based forecast assumptions + forecast table.
5. Page 5: FCFF DCF + target price.
6. Page 6: Sensitivity + risks.
7. Appendix artifacts: `claim_ledger`, `source_manifest`, `valuation_result`, `eval_result`.

Không được cắt bỏ valuation audit, citation audit hoặc numeric audit, vì đây là lõi tin cậy của dự án.

### 20.1. MVP minimum gates

```yaml
mvp_minimum_gates:
  source_gate: required
  numeric_consistency_gate: required
  valuation_reproducibility_gate: required
  citation_gate: required
  risk_language_gate: required
  human_final_review: required
```

---

## 21. Implementation notes for Claude/code agent

### 21.1. Recommended module split

Dù tài liệu này là single-file spec, implementation nên tách code theo module:

```text
report_renderer/
  markdown_builder.py
  html_renderer.py
  pdf_renderer.py
  layout_rules.py

report_contracts/
  claim_ledger_schema.py
  source_manifest_schema.py
  valuation_result_schema.py
  eval_result_schema.py

report_gates/
  source_gate.py
  citation_gate.py
  numeric_consistency_gate.py
  valuation_reproducibility_gate.py
  risk_language_gate.py
  visual_budget_gate.py

report_sections/
  page_1_snapshot.py
  page_2_company.py
  page_3_financials.py
  page_4_forecast.py
  page_5_valuation.py
  page_6_sensitivity_peer.py
  page_7_catalyst_risk.py
  page_8_conclusion.py
```

### 21.2. Rendering strategy

Khuyến nghị pipeline:

```text
Markdown section builder
  -> HTML renderer with CSS layout
  -> PDF renderer
  -> visual/page-budget validation
  -> final export
```

Không nên render PDF trực tiếp từ raw LLM text nếu chưa qua structured section builder.

### 21.3. Test requirements

Cần có test cho:

- missing citation blocks export;
- fake citation blocks export;
- numeric mismatch blocks export;
- target price mismatch blocks export;
- unsupported claim removed from final;
- failed human approval prevents final_exportable;
- chart with missing data omitted safely;
- report exceeding page budget flagged;
- driver-based forecast table required for Page 4;
- rating downgraded to UNDER_REVIEW when gate fails.

---

## 22. Final instruction for report-generating agent

Sinh báo cáo như một analyst chuyên nghiệp, nhưng vận hành như một hệ thống kiểm định dữ liệu nghiêm ngặt.

Ưu tiên theo thứ tự:

```text
Correctness > Traceability > Valuation Reproducibility > Risk Balance > Readability > Visual Design
```

Không được đánh đổi độ đúng số liệu để lấy văn phong hay. Một báo cáo ngắn nhưng đúng nguồn, đúng số, đúng valuation tốt hơn một báo cáo dài, đẹp nhưng không thể kiểm chứng.

