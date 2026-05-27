# Quy trình kiểm định số liệu cho AI Valuation Agent

> **Mục tiêu:** Tài liệu này mô tả quy trình kiểm định số liệu để AI agent không lặp lại lỗi dùng sai số liệu lịch sử khi tạo báo cáo định giá cổ phiếu. Quy trình được thiết kế cho các báo cáo equity research tự động, đặc biệt với doanh nghiệp niêm yết Việt Nam như DHG, nơi số liệu có thể đến từ nhiều nguồn như báo cáo tài chính kiểm toán, báo cáo thường niên, công bố thông tin, sàn giao dịch và API dữ liệu thị trường.

---

## 1. Vấn đề cần khắc phục

Trong báo cáo DHG trước đó, hệ thống trình bày số liệu lịch sử 2022FY–2025FY như dữ liệu “canonical đã kiểm toán”, nhưng nguồn dữ liệu lại được ghi là **vnstock API** và các chỉ tiêu được đưa thẳng vào mô hình định giá. Khi số liệu quá khứ sai hoặc chưa được đối chiếu với báo cáo tài chính gốc, toàn bộ phần phân tích tài chính, dự phóng, FCFF, FCFE, P/E, EV/EBITDA và khuyến nghị đều có thể sai theo.

Lỗi cốt lõi không chỉ là một con số sai. Lỗi nằm ở quy trình: agent đã xem dữ liệu từ một nguồn trung gian là “canonical” quá sớm, chưa yêu cầu đối chiếu với nguồn gốc, chưa kiểm tra chéo nhiều nguồn, chưa có ngưỡng dừng khi số liệu bất thường, và chưa tạo báo cáo kiểm định dữ liệu trước khi chạy định giá.

Từ nay agent phải tách rõ ba lớp dữ liệu:

| Lớp dữ liệu | Ý nghĩa | Có được dùng để định giá không? |
|---|---|---|
| `raw_data` | Dữ liệu lấy thô từ PDF, website, API, Excel hoặc nguồn crawl | Chưa |
| `normalized_data` | Dữ liệu đã chuẩn hóa đơn vị, kỳ, dấu âm/dương, tên khoản mục | Chưa đủ |
| `validated_canonical_facts` | Dữ liệu đã qua kiểm định nguồn, kiểm tra công thức, đối chiếu chéo và có confidence score | Có, nếu đạt chuẩn |

Agent chỉ được chạy mô hình định giá trên `validated_canonical_facts`, không được dùng trực tiếp `raw_data` hoặc dữ liệu API chưa kiểm định.

---

## 2. Nguyên tắc kiểm định bắt buộc

Nguyên tắc đầu tiên là **nguồn gốc quan trọng hơn định dạng**. Một bảng dữ liệu sạch từ API vẫn không thể thay thế báo cáo tài chính kiểm toán nếu chưa đối chiếu. Với doanh nghiệp niêm yết, nguồn ưu tiên cao nhất phải là báo cáo tài chính kiểm toán năm, báo cáo tài chính quý có soát xét, báo cáo thường niên, nghị quyết và công bố chính thức từ doanh nghiệp hoặc sàn giao dịch. API dữ liệu chỉ nên được xem là nguồn hỗ trợ để tăng tốc thu thập, không phải nguồn xác nhận cuối cùng.

Nguyên tắc thứ hai là **mỗi số liệu quan trọng phải có lineage**. Mỗi fact như doanh thu, lợi nhuận sau thuế, EPS, tổng tài sản, vốn chủ sở hữu, CFO, CAPEX, nợ vay, tiền mặt phải biết rõ lấy từ đâu, kỳ nào, trang nào, bảng nào, ngày cập nhật nào, đơn vị nào và đã qua bước kiểm tra nào.

Nguyên tắc thứ ba là **không có dữ liệu nào được tự động gắn nhãn “đã kiểm toán” chỉ vì nguồn nói như vậy**. Agent chỉ được gắn nhãn `audited` khi tài liệu gốc là báo cáo tài chính kiểm toán hoặc báo cáo thường niên có BCTC kiểm toán. Nếu dữ liệu lấy từ API nhưng API ghi “audited”, agent vẫn phải đối chiếu tối thiểu với một nguồn gốc.

Nguyên tắc thứ tư là **định giá phải bị chặn nếu dữ liệu lịch sử chưa pass kiểm định**. Nếu doanh thu, lợi nhuận, EPS, vốn chủ sở hữu, tổng tài sản, CFO hoặc CAPEX không đạt kiểm định, agent không được xuất target price, không được xuất BUY/HOLD/SELL, và chỉ được tạo báo cáo trạng thái `Data Validation Failed`.

---

## 3. Thứ bậc nguồn dữ liệu

Agent cần áp dụng thứ bậc nguồn như sau:

| Cấp nguồn | Nguồn | Vai trò | Độ tin cậy mặc định |
|---|---|---|---|
| Tier 1 | Báo cáo tài chính kiểm toán năm của doanh nghiệp | Nguồn chính cho số liệu lịch sử năm | Rất cao |
| Tier 1 | Báo cáo thường niên có BCTC kiểm toán | Nguồn chính cho số liệu năm, thuyết minh, chính sách kế toán | Rất cao |
| Tier 1 | Công bố thông tin chính thức trên HOSE/HNX/UPCoM/SSC | Đối chiếu báo cáo và sự kiện | Cao |
| Tier 2 | Báo cáo tài chính quý có soát xét | Nguồn chính cho dữ liệu quý/TTM | Cao |
| Tier 2 | Website quan hệ cổ đông của doanh nghiệp | Tải tài liệu gốc, công bố mới | Cao |
| Tier 3 | API tài chính như vnstock, FiinPro, Vietstock, CafeF, SSI iBoard, TCBS, v.v. | Nguồn hỗ trợ, không phải nguồn xác nhận cuối | Trung bình |
| Tier 4 | Tin tức, blog, diễn đàn, nguồn không chính thức | Chỉ dùng cho bối cảnh, không dùng làm fact tài chính | Thấp |

Quy tắc bắt buộc:

```text
Nếu số liệu lấy từ Tier 3, phải có ít nhất một nguồn Tier 1 hoặc Tier 2 xác nhận.
Nếu không có nguồn Tier 1/Tier 2, fact phải bị gắn nhãn "unverified".
Nếu fact trọng yếu bị unverified, valuation phải bị chặn.
```

---

## 4. Data contract cho một canonical fact

Mỗi số liệu sau khi được đưa vào kho canonical phải có cấu trúc tối thiểu như sau:

```yaml
fact_id: "DHG_2025FY_revenue_net"
ticker: "DHG"
company_name: "Công ty Cổ phần Dược Hậu Giang"
period: "2025FY"
fiscal_year: 2025
statement: "income_statement"
metric_key: "revenue.net"
reported_label_vi: "Doanh thu thuần"
value: 5267.0
unit: "VND_bn"
scale: 1000000000
sign_convention: "positive_for_income"
source_tier: 1
source_name: "Báo cáo tài chính kiểm toán năm 2025"
source_url_or_path: "..."
page: 12
table_name: "Báo cáo kết quả hoạt động kinh doanh"
extraction_method: "table_parser/manual_review"
extracted_at: "2026-05-26T12:44:00Z"
validated_at: "..."
validation_status: "pass"
confidence_score: 0.98
cross_check_sources:
  - source_name: "HOSE disclosure"
    value: 5267.0
    status: "matched"
warnings: []
```

Nếu fact thiếu `source_tier`, `source_name`, `period`, `metric_key`, `unit`, `validation_status` hoặc `confidence_score`, agent không được đưa fact đó vào mô hình định giá.

---

## 5. Quy trình kiểm định tổng thể

Luồng chuẩn của agent phải đi theo thứ tự sau:

```text
1. Source Discovery
2. Source Download & Versioning
3. Raw Extraction
4. Account Mapping
5. Unit & Sign Normalization
6. Cross-source Verification
7. Financial Statement Reconciliation
8. Time-series Sanity Check
9. Market Data Alignment
10. Canonical Fact Approval
11. Valuation Readiness Gate
12. Report Generation
13. Human-in-the-loop Review
```

Agent không được bỏ qua bước 6, 7, 8 và 11. Đây là các bước trực tiếp ngăn lỗi số liệu lịch sử sai.

---

## 6. Source Discovery

Agent phải tự động tìm và lưu danh sách nguồn cho từng kỳ tài chính. Với mỗi ticker, hệ thống cần tạo bảng `source_registry`.

| Ticker | Kỳ | Loại tài liệu | Nguồn | Trạng thái |
|---|---|---|---|---|
| DHG | 2025FY | BCTC kiểm toán | Công bố doanh nghiệp / HOSE | Required |
| DHG | 2025FY | Báo cáo thường niên | Công bố doanh nghiệp / HOSE | Required |
| DHG | 2025FY | API dữ liệu tài chính | vnstock / nguồn khác | Optional |
| DHG | 2024FY | BCTC kiểm toán | Công bố doanh nghiệp / HOSE | Required |

Quy tắc:

```text
Mỗi năm tài chính phải có ít nhất 1 nguồn Tier 1.
Nếu không có Tier 1, năm đó không được đánh dấu "audited".
Nếu thiếu 2 năm liên tiếp, agent không được chạy trend analysis.
```

---

## 7. Source Download & Versioning

Mọi tài liệu gốc phải được lưu lại với checksum để bảo đảm có thể tái lập.

```yaml
source_id: "src_DHG_2025_audited_fs"
ticker: "DHG"
period: "2025FY"
source_type: "audited_financial_statement"
source_tier: 1
file_name: "DHG_BCTC_KiemToan_2025.pdf"
downloaded_at: "2026-05-26T12:44:00Z"
checksum_sha256: "..."
url: "..."
status: "active"
```

Nếu cùng một kỳ có nhiều phiên bản báo cáo, agent phải ưu tiên phiên bản mới nhất và lưu phiên bản cũ với trạng thái `superseded`.

---

## 8. Raw Extraction

Agent có thể trích xuất dữ liệu bằng OCR, table parser, API hoặc nhập tay. Tuy nhiên, mọi dữ liệu trích xuất phải giữ lại bản gốc.

```yaml
raw_value: "-2,760.6"
raw_unit: "tỷ VND"
raw_label: "Giá vốn hàng bán"
raw_statement: "Báo cáo kết quả kinh doanh"
page: 18
row_index: 7
column_period: "2025"
extraction_confidence: 0.92
```

Nếu dữ liệu lấy từ API, agent vẫn phải lưu payload thô:

```yaml
api_provider: "vnstock"
endpoint: "finance/income_statement"
request_params:
  ticker: "DHG"
  period: "year"
raw_payload_hash: "..."
```

---

## 9. Account Mapping

Một lỗi phổ biến là nhầm tên khoản mục. Agent cần có dictionary ánh xạ tài khoản.

| Nhãn tiếng Việt | Metric chuẩn | Statement | Ghi chú |
|---|---|---|---|
| Doanh thu thuần | `revenue.net` | Income Statement | Số dương |
| Giá vốn hàng bán | `cogs.total` | Income Statement | Có thể lưu âm hoặc dương tùy quy ước |
| Lợi nhuận gộp | `gross_profit.total` | Income Statement | Phải khớp doanh thu + COGS nếu COGS âm |
| Lợi nhuận sau thuế của cổ đông công ty mẹ | `net_income.parent` | Income Statement | Dùng cho EPS |
| Dòng tiền từ hoạt động kinh doanh | `operating_cash_flow.total` | Cash Flow | CFO |
| Chi đầu tư TSCĐ | `capex.total` | Cash Flow | Thường là số âm trong CFS |
| Vay ngắn hạn | `short_term_debt.ending` | Balance Sheet | Nợ vay chịu lãi |
| Vốn chủ sở hữu của cổ đông công ty mẹ | `equity.parent` | Balance Sheet | Dùng cho ROE và BVPS |

Nếu một nhãn có nhiều khả năng ánh xạ, agent phải gắn trạng thái `mapping_ambiguous` và yêu cầu review.

---

## 10. Chuẩn hóa đơn vị

Agent phải chuẩn hóa đơn vị trước khi tính toán. Không được trộn VND, nghìn VND, triệu VND, tỷ VND và số cổ phiếu.

| Loại số liệu | Đơn vị canonical |
|---|---|
| Doanh thu, lợi nhuận, tài sản, nợ, dòng tiền | `VND_bn` |
| EPS, BVPS, DPS, giá cổ phiếu | `VND_per_share` |
| Số cổ phiếu | `million_shares` |
| Tỷ lệ | Decimal, ví dụ 15% = 0.15 |
| Multiple | x, ví dụ 15.0x |

Kiểm tra bắt buộc:

```text
shares_implied = net_income_parent_vnd / eps_vnd
Nếu shares_implied lệch > 2% so với shares_outstanding, flag HIGH.
```

Nếu lợi nhuận sau thuế là tỷ VND và EPS là VND/cổ phiếu, agent phải đổi lợi nhuận về VND trước khi suy ra số cổ phiếu. Đây là kiểm tra rất quan trọng để phát hiện sai đơn vị.

---

## 11. Chuẩn hóa dấu âm/dương

Agent phải có quy ước dấu thống nhất. Đây là bước bắt buộc trước khi tính margin, FCF, FCFF, FCFE và EV/EBITDA.

| Khoản mục | Dữ liệu gốc thường gặp | Quy ước trong mô hình |
|---|---|---|
| Doanh thu | Dương | Dương |
| COGS | Có thể âm hoặc dương | `cogs_expense_positive = ABS(COGS)` |
| SG&A | Có thể âm hoặc dương | `sga_expense_positive = ABS(SGA)` |
| Thuế | Có thể âm hoặc dương | `tax_expense_positive = ABS(tax_expense)` |
| Lãi vay | Có thể âm hoặc dương | `interest_expense_positive = ABS(interest_expense)` |
| CAPEX từ CFS | Thường âm | Lưu cả `capex_cfs_signed` và `capex_positive = ABS(capex_cfs_signed)` |
| CFO | Dương hoặc âm | Giữ đúng dấu dòng tiền |
| Net Borrowing | Dương nếu vay ròng, âm nếu trả nợ ròng | Giữ đúng dấu |

Quy tắc chống lỗi CAPEX:

```text
IF capex_cfs_signed < 0:
    capex_positive = ABS(capex_cfs_signed)
    fcf_from_cfo = CFO + capex_cfs_signed
    fcff_from_cfo = CFO + interest_expense_positive * (1 - tax_rate) + capex_cfs_signed
    fcfe_from_cfo = CFO + capex_cfs_signed + net_borrowing
ELSE:
    capex_positive = capex_cfs_signed
    fcf_from_cfo = CFO - capex_positive
    fcff_from_cfo = CFO + interest_expense_positive * (1 - tax_rate) - capex_positive
    fcfe_from_cfo = CFO - capex_positive + net_borrowing
```

Cảnh báo đỏ:

```text
Nếu CAPEX_CFS âm và công thức chứa "CFO - CAPEX_CFS", mô hình phải dừng.
```

---

## 12. Kiểm tra đối chiếu trong cùng báo cáo tài chính

Sau khi chuẩn hóa, agent phải kiểm tra các công thức kế toán cơ bản.

### 12.1. Income Statement checks

| Kiểm tra | Công thức | Ngưỡng |
|---|---|---|
| Lợi nhuận gộp | `revenue - cogs_expense_positive ≈ gross_profit` | Sai lệch < 1% doanh thu |
| EBIT | `gross_profit - sga_expense_positive + other_operating_items ≈ EBIT` | Nếu thiếu other items, cảnh báo |
| PBT | `EBIT - interest_expense + finance_income + other_income ≈ PBT` | Cần mapping đủ |
| Net income | `PBT - tax_expense_positive ≈ net_income` | Sai lệch < 1% PBT |
| EPS | `net_income_parent / weighted_avg_shares ≈ EPS` | Sai lệch < 2% |

### 12.2. Balance Sheet checks

| Kiểm tra | Công thức | Ngưỡng |
|---|---|---|
| Phương trình kế toán | `total_assets ≈ total_liabilities + total_equity` | Sai lệch < 0.5% tài sản |
| Vốn chủ sở hữu | `equity_parent + minority_interest ≈ total_equity` | Nếu có minority interest |
| Nợ vay | `short_term_debt + long_term_debt ≈ interest_bearing_debt` | Sai lệch < 1% |
| Net debt | `interest_bearing_debt - cash - short_term_investments` | Kiểm tra dấu |

### 12.3. Cash Flow checks

| Kiểm tra | Công thức | Ngưỡng |
|---|---|---|
| Thay đổi tiền | `CFO + CFI + CFF + FX_effect ≈ change_in_cash` | Sai lệch < 1% cash cuối kỳ |
| CAPEX | `cash_paid_for_ppe` phải âm nếu theo CFS | Nếu dương bất thường, kiểm tra mapping |
| CFO/NI | `CFO / net_income` | Cảnh báo nếu < 0.5x hoặc > 2.0x nhiều năm |
| FCF | `CFO + capex_cfs_signed` | Không dùng `CFO - capex_cfs_signed` nếu CAPEX âm |

---

## 13. Kiểm tra đối chiếu nhiều nguồn

Mỗi fact trọng yếu phải được đối chiếu với tối thiểu hai nguồn nếu có thể.

```yaml
metric: revenue.net
period: 2025FY
sources:
  - source_tier: 1
    source_name: "BCTC kiểm toán 2025"
    value: 5267.0
  - source_tier: 2
    source_name: "Báo cáo thường niên 2025"
    value: 5267.0
  - source_tier: 3
    source_name: "vnstock API"
    value: 5267.0
result: "matched"
```

Quy tắc sai lệch:

| Loại chỉ tiêu | Ngưỡng chấp nhận |
|---|---|
| Doanh thu, lợi nhuận, tài sản, vốn chủ | ±0.5% |
| EPS, BVPS | ±1.0% |
| CFO, CAPEX | ±1.0% |
| Market price | Theo timestamp; không so với dữ liệu quá khứ nếu là giá hiện tại |
| Số cổ phiếu | ±2.0% nếu có bình quân gia quyền |

Nếu Tier 3 khác Tier 1, agent phải ưu tiên Tier 1 và gắn cảnh báo cho Tier 3.

---

## 14. Kiểm tra chuỗi thời gian

Agent cần kiểm tra dữ liệu lịch sử theo chuỗi để phát hiện số liệu sai hoặc lệch kỳ.

| Kiểm tra | Điều kiện cảnh báo |
|---|---|
| Doanh thu YoY | Thay đổi > ±30% không có giải thích |
| Lợi nhuận sau thuế YoY | Thay đổi > ±40% không có giải thích |
| Biên lợi nhuận gộp | Thay đổi > ±5 điểm % |
| Biên lợi nhuận ròng | Thay đổi > ±5 điểm % |
| ROE | Thay đổi > ±10 điểm % |
| Tổng tài sản | Thay đổi > ±25% |
| Vốn chủ sở hữu | Thay đổi > ±25% |
| CFO/NI | < 0.5x hoặc > 2.0x |
| CAPEX/Revenue | Lớn hơn 2 lần trung vị 3 năm |
| EPS vs Net Income | EPS giảm nhưng net income tăng mạnh mà không có tăng shares tương ứng |

Cảnh báo chuỗi thời gian không có nghĩa số liệu chắc chắn sai, nhưng bắt buộc agent phải giải thích hoặc yêu cầu kiểm tra nguồn.

---

## 15. Kiểm tra dữ liệu thị trường

Báo cáo không được dùng giá hiện tại để tính sai dữ liệu lịch sử nếu không ghi nhãn rõ.

```text
Sai: dùng cùng một market cap hiện tại cho các năm 2022, 2023, 2024, 2025 rồi gọi là market cap lịch sử.
Đúng: nếu dùng giá hiện tại, phải ghi "Market cap at current price", không phải market cap lịch sử.
```

| Chỉ tiêu | Cách đúng |
|---|---|
| Current P/E | `current_price / latest_EPS_TTM_or_FY` |
| Historical P/E | `historical_year_end_price / EPS_that_year` |
| Current market cap | `current_price × current_shares` |
| Historical market cap | `historical_price_at_date × shares_at_date` |
| Forward P/E | `current_price / EPS_FY1` |

Nếu agent không có giá lịch sử, không được tạo bảng P/E lịch sử. Chỉ được tạo bảng “current price applied to historical EPS” và phải ghi rõ cách tính.

---

## 16. Valuation Readiness Gate

Trước khi chạy valuation, agent phải chạy `Valuation Readiness Gate`.

### 16.1. Các chỉ tiêu bắt buộc phải PASS

| Nhóm | Chỉ tiêu bắt buộc |
|---|---|
| Income Statement | Revenue, Gross Profit, PBT, Net Income Parent, EPS |
| Balance Sheet | Total Assets, Total Liabilities, Equity Parent, Cash, Debt |
| Cash Flow | CFO, CAPEX, Depreciation |
| Market Data | Current Price, Shares Outstanding |
| Mapping | Account mapping không ambiguous |
| Unit | Đơn vị đã chuẩn hóa |
| Sign | Dấu CAPEX, COGS, SGA, tax, interest đã chuẩn hóa |
| Source | Có ít nhất 1 nguồn Tier 1 cho mỗi năm lịch sử trọng yếu |

Nếu bất kỳ chỉ tiêu trọng yếu nào fail, output phải là:

```text
Status: DATA_VALIDATION_FAILED
Action: Do not run valuation
Reason: [list of failed checks]
```

---

## 17. Hệ thống confidence score

Mỗi fact cần có điểm tin cậy từ 0 đến 1.

```text
confidence_score =
    0.35 * source_quality_score
  + 0.25 * cross_source_match_score
  + 0.20 * accounting_reconciliation_score
  + 0.10 * extraction_confidence
  + 0.10 * time_series_sanity_score
```

| Score | Trạng thái | Hành động |
|---|---|---|
| ≥ 0.95 | High confidence | Có thể dùng |
| 0.85–0.95 | Acceptable | Có thể dùng nhưng lưu warning nhẹ |
| 0.70–0.85 | Needs review | Không dùng cho valuation nếu là fact trọng yếu |
| < 0.70 | Reject | Loại khỏi canonical facts |

Nguồn Tier 3 không thể tự đạt trên 0.85 nếu không có đối chiếu Tier 1/Tier 2.

---

## 18. Quy tắc cảnh báo và dừng mô hình

| Mức độ | Ví dụ | Hành động |
|---|---|---|
| CRITICAL | Tổng tài sản không bằng nợ + vốn chủ; CAPEX sai dấu; revenue khác nguồn chính > 1%; thiếu BCTC gốc | Dừng valuation |
| HIGH | EPS không khớp lợi nhuận và shares; CFO/NI bất thường; market cap lịch sử dùng giá hiện tại không ghi nhãn | Dừng hoặc yêu cầu analyst review |
| MEDIUM | Biên lợi nhuận biến động lớn; OCF bất thường; peer data thiếu một vài công ty | Cho chạy draft, nhưng phải cảnh báo |
| LOW | Thiếu một footnote không trọng yếu; chênh lệch làm tròn nhỏ | Cho chạy |

Không được để `warnings: []` nếu có bất kỳ giả định mặc định, nguồn API chưa đối chiếu, hoặc số liệu chưa pass fully validated.

---

## 19. Data Validation Report bắt buộc

Trước khi tạo báo cáo phân tích, agent phải tạo một file riêng:

```text
DATA_VALIDATION_REPORT_{ticker}_{snapshot}.md
```

Nội dung tối thiểu:

```markdown
# Data Validation Report — DHG

## 1. Data Snapshot
- Ticker:
- Snapshot ID:
- Created At:
- Historical Periods:
- Number of Facts:
- Number of Sources:

## 2. Source Coverage
| Period | Tier 1 Source | Tier 2 Source | API Source | Status |
|---|---|---|---|---|

## 3. Critical Fact Validation
| Metric | Period | Value | Primary Source | Cross-check | Status | Confidence |
|---|---:|---:|---|---|---|---:|

## 4. Accounting Reconciliation
| Check | Period | Expected | Actual | Difference | Status |
|---|---:|---:|---:|---:|---|

## 5. Time-series Warnings
| Metric | From → To | Change | Threshold | Status | Explanation |
|---|---|---:|---:|---|---|

## 6. Valuation Readiness Gate
- Status:
- Failed Checks:
- Allowed Output:
- Analyst Review Required:
```

Nếu `Valuation Readiness Gate = FAIL`, agent không được tạo target price.

---

## 20. Quy trình HITL — Human-in-the-loop

Con người phải duyệt ở ba điểm:

| Điểm duyệt | Người duyệt cần kiểm tra |
|---|---|
| Data approval | Nguồn gốc số liệu, fact trọng yếu, sai lệch giữa API và BCTC |
| Model approval | Công thức FCFF/FCFE, CAPEX, NWC, WACC/Re, terminal growth |
| Report approval | Kết luận, rating, target price, disclaimer, warning |

Trạng thái tài liệu:

| Trạng thái | Ý nghĩa |
|---|---|
| `Draft - Data Not Validated` | Chỉ mới có dữ liệu thô |
| `Draft - Data Validated` | Số liệu pass nhưng giả định mô hình chưa duyệt |
| `Draft - Model Validated` | Mô hình pass nhưng báo cáo chưa duyệt |
| `Final - Analyst Approved` | Có thể phát hành nội bộ hoặc publish theo chính sách |

---

## 21. Pseudocode cho agent

```python
def run_equity_report_pipeline(ticker, periods):
    sources = discover_sources(ticker, periods)
    source_registry = download_and_version_sources(sources)

    raw_facts = extract_raw_facts(source_registry)
    mapped_facts = map_accounts(raw_facts)
    normalized_facts = normalize_units_and_signs(mapped_facts)

    source_check = validate_source_coverage(normalized_facts)
    cross_check = cross_verify_facts(normalized_facts)
    accounting_check = reconcile_financial_statements(normalized_facts)
    time_series_check = run_time_series_sanity_checks(normalized_facts)
    market_check = validate_market_data_alignment(normalized_facts)

    validation_report = build_validation_report(
        source_check,
        cross_check,
        accounting_check,
        time_series_check,
        market_check,
    )

    if validation_report.has_critical_failures():
        return {
            "status": "DATA_VALIDATION_FAILED",
            "allowed_output": "validation_report_only",
            "valuation_allowed": False,
            "report": validation_report,
        }

    canonical_facts = approve_canonical_facts(normalized_facts, validation_report)

    readiness = valuation_readiness_gate(canonical_facts)
    if not readiness.pass_:
        return {
            "status": "VALUATION_READINESS_FAILED",
            "allowed_output": "draft_without_target_price",
            "valuation_allowed": False,
            "report": readiness,
        }

    valuation = run_valuation_models(canonical_facts)
    model_audit = audit_valuation_model(valuation)

    if model_audit.has_critical_failures():
        return {
            "status": "MODEL_AUDIT_FAILED",
            "allowed_output": "draft_without_rating",
            "valuation_allowed": False,
            "audit": model_audit,
        }

    return generate_draft_report(canonical_facts, valuation, model_audit)
```

---

## 22. Unit tests bắt buộc cho pipeline

### Test CAPEX sign

```python
def test_capex_sign():
    cfo = 1000
    capex_cfs = -200
    assert fcf_from_cfo(cfo, capex_cfs) == 800
```

### Test không dùng giá hiện tại cho P/E lịch sử

```python
def test_historical_pe_requires_historical_price():
    result = create_historical_pe(current_price=94400, eps_by_year={"2022FY": 7318})
    assert result.label != "Historical P/E"
```

### Test EPS và số cổ phiếu

```python
def test_eps_share_reconciliation():
    net_income_vnd = 852_400_000_000
    eps = 6308
    implied_shares = net_income_vnd / eps
    reported_shares = 135_100_000
    assert abs(implied_shares / reported_shares - 1) < 0.02
```

### Test nguồn Tier 3 không được tự canonical

```python
def test_api_source_not_canonical_without_primary_source():
    fact = Fact(source_tier=3, cross_checked=False)
    assert fact.validation_status != "pass"
```

---

## 23. Checklist triển khai nhanh

| Câu hỏi | Pass/Fail |
|---|---|
| Mỗi năm lịch sử có báo cáo tài chính gốc Tier 1 chưa? | |
| Dữ liệu API đã đối chiếu với BCTC gốc chưa? | |
| Mỗi fact trọng yếu có source_id, page/table, unit và confidence score chưa? | |
| Doanh thu, lợi nhuận, EPS có khớp giữa các nguồn không? | |
| Tổng tài sản có bằng nợ phải trả + vốn chủ sở hữu không? | |
| EPS có khớp lợi nhuận sau thuế và số cổ phiếu không? | |
| CAPEX âm trong CFS có được xử lý đúng dấu không? | |
| COGS, SGA, tax, interest đã chuẩn hóa dấu chưa? | |
| Có dùng giá hiện tại để tính historical market cap/P/E không? Nếu có, đã ghi nhãn chưa? | |
| Có cảnh báo khi số liệu biến động bất thường không? | |
| `warnings` có rỗng dù còn giả định default hoặc data chưa đối chiếu không? | |
| Valuation Readiness Gate đã PASS chưa? | |
| Nếu fail, agent có chặn target price và rating không? | |

---

## 24. Kết luận thực hành

Để AI valuation agent không mắc lỗi sai số liệu lịch sử, vấn đề quan trọng nhất là không cho phép dữ liệu từ API hoặc dữ liệu chưa đối chiếu đi thẳng vào mô hình. Agent phải có một lớp kiểm định độc lập trước valuation, bao gồm kiểm tra nguồn, kiểm tra đơn vị, kiểm tra dấu, kiểm tra công thức kế toán, kiểm tra chuỗi thời gian, kiểm tra dữ liệu thị trường và kiểm tra độ sẵn sàng định giá.

Quy tắc cuối cùng:

```text
Không có validated canonical facts thì không có valuation.
Không có reconciliation thì không có target price.
Không có human approval thì không có final rating.
```

Nếu số liệu lịch sử sai, mô hình định giá đúng công thức vẫn cho ra kết quả sai. Vì vậy, kiểm định dữ liệu phải là cổng bắt buộc đầu tiên của mọi AI agent tài chính.
