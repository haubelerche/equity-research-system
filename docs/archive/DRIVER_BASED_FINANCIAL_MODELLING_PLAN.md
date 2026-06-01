# Kế hoạch xây dựng Driver-Based Financial Modelling

**Dự án:** Vietnam Pharma Equity Research Agent  
**Phiên bản:** 1.0  
**Ngày:** 2026-06-01  
**Mục tiêu:** Chuẩn hóa cách xây dựng mô hình dự phóng tài chính dựa trên các động lực kinh doanh cốt lõi, phục vụ báo cáo equity research ngành dược/y tế Việt Nam.

---

## Mục lục

1. [Tóm tắt điều hành](#1-tóm-tắt-điều-hành)
2. [Định nghĩa driver-based financial modelling](#2-định-nghĩa-driver-based-financial-modelling)
3. [Vì sao cần driver-based modelling trong equity research](#3-vì-sao-cần-driver-based-modelling-trong-equity-research)
4. [Bản chất tư duy của driver modelling](#4-bản-chất-tư-duy-của-driver-modelling)
5. [Cấu trúc tổng thể của mô hình](#5-cấu-trúc-tổng-thể-của-mô-hình)
6. [Phân loại driver cần xây dựng](#6-phân-loại-driver-cần-xây-dựng)
7. [Tiêu chí lựa chọn driver](#7-tiêu-chí-lựa-chọn-driver)
8. [Phương pháp xây dựng mô hình](#8-phương-pháp-xây-dựng-mô-hình)
9. [Thiết kế dữ liệu và schema đề xuất](#9-thiết-kế-dữ-liệu-và-schema-đề-xuất)
10. [Thiết kế công thức và engine tính toán](#10-thiết-kế-công-thức-và-engine-tính-toán)
11. [Kịch bản, sensitivity và stress test](#11-kịch-bản-sensitivity-và-stress-test)
12. [Driver modelling cho ngành dược Việt Nam](#12-driver-modelling-cho-ngành-dược-việt-nam)
13. [Evaluation và quality gates](#13-evaluation-và-quality-gates)
14. [Lộ trình triển khai theo phase](#14-lộ-trình-triển-khai-theo-phase)
15. [Deliverables cần tạo](#15-deliverables-cần-tạo)
16. [Acceptance criteria](#16-acceptance-criteria)
17. [Checklist triển khai](#17-checklist-triển-khai)
18. [Kết luận](#18-kết-luận)

---

## 1. Tóm tắt điều hành

Driver-based financial modelling là phương pháp dự phóng tài chính dựa trên các biến vận hành có quan hệ nhân quả với kết quả tài chính.

Thay vì dự báo đơn giản:

```text
Doanh thu năm sau = Doanh thu năm trước × 1.10
```

mô hình driver-based sẽ dự báo:

```text
Doanh thu = Sản lượng bán × Giá bán trung bình
```

hoặc chi tiết hơn:

```text
Doanh thu = Số khách hàng × Số đơn hàng/khách × Giá trị trung bình/đơn hàng
```

Trong dự án equity research ngành dược Việt Nam, driver-based modelling cần được thiết kế như một lớp trung gian giữa:

```text
Canonical Financial Facts
        ↓
Business Drivers & Assumptions
        ↓
Forecasted Financial Statements
        ↓
Valuation
        ↓
Grounded Narrative Report
```

Mục tiêu chính không phải chỉ là tạo bảng dự phóng đẹp, mà là giúp hệ thống trả lời được:

- Con số dự phóng đến từ driver nào?
- Driver đó có nguồn hoặc luận cứ không?
- Driver đó tác động đến doanh thu, biên lợi nhuận, dòng tiền và định giá như thế nào?
- Nếu driver thay đổi, valuation thay đổi bao nhiêu?
- Assumption nào cần con người duyệt trước khi xuất báo cáo?

---

## 2. Định nghĩa driver-based financial modelling

### 2.1 Định nghĩa ngắn gọn

**Driver-based financial modelling** là phương pháp xây dựng mô hình tài chính trong đó các chỉ tiêu như doanh thu, lợi nhuận, dòng tiền và định giá được tính ra từ các driver vận hành hoặc kinh tế cốt lõi, thay vì chỉ ngoại suy từ tỷ lệ tăng trưởng lịch sử.

### 2.2 Định nghĩa theo hệ thống

Trong hệ thống equity research, driver-based modelling là một module có nhiệm vụ:

1. Nhận dữ liệu lịch sử đã được chuẩn hóa.
2. Xác định các driver kinh doanh chính của doanh nghiệp.
3. Tạo assumptions cho từng driver.
4. Tính forecast bằng code theo công thức cố định.
5. Sinh financial statements dự phóng.
6. Đưa output sang valuation engine.
7. Ghi lại lineage giữa driver, assumption, source, formula và output.

### 2.3 Driver là gì?

**Driver** là biến đầu vào có tác động trực tiếp hoặc gián tiếp đến kết quả tài chính.

Ví dụ:

| Loại driver | Ví dụ | Output bị ảnh hưởng |
|---|---|---|
| Volume driver | Sản lượng bán, số đơn hàng, số khách hàng | Doanh thu |
| Price driver | Giá bán trung bình, mức tăng giá | Doanh thu, gross margin |
| Mix driver | Tỷ trọng ETC/OTC, branded generic, generic | Revenue mix, gross margin |
| Cost driver | Giá nguyên liệu API, tỷ giá, chi phí sản xuất | COGS, gross profit |
| Efficiency driver | Utilization nhà máy, productivity, automation | Margin, capex efficiency |
| Working capital driver | DSO, DIO, DPO | Operating cash flow, FCFF |
| Capex driver | Mở rộng nhà máy, nâng chuẩn GMP | FCFF, depreciation |
| Financial driver | Lãi suất vay, nợ vay, thuế suất | Net income, FCFE |
| Catalyst driver | Đấu thầu thuốc, BHYT, regulatory change | Revenue, margin, risk premium |

### 2.4 Điểm khác biệt với mô hình tăng trưởng cơ học

| Tiêu chí | Growth-based model | Driver-based model |
|---|---|---|
| Cách dự báo | Dùng % tăng trưởng tổng | Dùng biến nguyên nhân |
| Logic kinh doanh | Yếu | Mạnh |
| Dễ giải thích | Thấp | Cao |
| Dễ kiểm chứng | Khó | Dễ hơn |
| Sensitivity analysis | Nông | Sâu |
| Phù hợp equity research | Chỉ phù hợp giai đoạn sơ bộ | Phù hợp hơn cho báo cáo nghiêm túc |
| Rủi ro hallucination | Cao nếu LLM tự viết narrative | Giảm nếu driver có source và code tính toán |

---

## 3. Vì sao cần driver-based modelling trong equity research

### 3.1 Vấn đề của dự báo chỉ dựa vào tỷ lệ lịch sử

Một forecast kiểu “doanh thu tăng 8% mỗi năm” có thể nhanh, nhưng thiếu ba yếu tố quan trọng:

1. **Không giải thích nguyên nhân:** Không biết tăng do giá, sản lượng, thị phần hay mix sản phẩm.
2. **Không kiểm định được assumption:** Không rõ 8% đến từ nguồn nào.
3. **Không kể được câu chuyện tài chính:** Báo cáo chỉ có bảng số, không có thesis.

### 3.2 Lợi ích đối với báo cáo equity research

Driver-based modelling giúp báo cáo có:

- Cấu trúc phân tích rõ ràng hơn.
- Valuation assumptions minh bạch hơn.
- Sensitivity analysis có ý nghĩa hơn.
- Narrative gắn trực tiếp với số liệu.
- Dễ audit hơn vì mỗi output có thể truy về driver và formula.

### 3.3 Lợi ích đối với hệ multi-agent

Đối với hệ thống AI equity research, driver-based modelling giúp tách rõ:

```text
Facts ≠ Assumptions ≠ Calculations ≠ Narrative
```

Trong đó:

- **Facts**: số liệu lịch sử đã xác thực.
- **Assumptions**: giả định về driver tương lai.
- **Calculations**: công thức chạy bằng code.
- **Narrative**: phần diễn giải do LLM tạo dựa trên artifact đã khóa.

Nguyên tắc quan trọng: LLM không được tự tạo số liệu forecast nếu không đi qua driver assumption và calculation engine.

---

## 4. Bản chất tư duy của driver modelling

### 4.1 Tư duy nhân quả

Driver modelling bắt đầu từ câu hỏi:

```text
Điều gì thực sự làm chỉ tiêu tài chính này thay đổi?
```

Ví dụ:

```text
Doanh thu tăng vì:
- Bán được nhiều sản phẩm hơn?
- Giá bán tăng?
- Mở rộng kênh phân phối?
- Tăng thị phần?
- Có sản phẩm mới?
- Trúng thầu bệnh viện?
```

### 4.2 Tư duy phân rã

Một chỉ tiêu tài chính lớn cần được phân rã thành các thành phần nhỏ hơn.

Ví dụ:

```text
Revenue
= OTC Revenue + ETC Revenue + Export Revenue

OTC Revenue
= OTC Volume × OTC Average Selling Price

ETC Revenue
= Tender Volume × Tender Price × Fulfillment Rate
```

### 4.3 Tư duy materiality

Không phải mọi biến đều nên trở thành driver. Chỉ chọn driver nếu nó có tác động đủ lớn đến kết quả tài chính hoặc luận điểm đầu tư.

Ví dụ: Với một công ty dược, giá nguyên liệu API, tỷ trọng ETC/OTC, số đăng ký thuốc, và tỷ lệ trúng thầu thường quan trọng hơn chi tiết rất nhỏ như chi phí văn phòng.

### 4.4 Tư duy kiểm chứng

Mỗi driver tốt cần trả lời được:

- Có dữ liệu lịch sử không?
- Có nguồn để giải thích assumption không?
- Có thể đo được không?
- Có thể kiểm tra lại khi có actual không?
- Có tác động rõ đến financial statement không?

---

## 5. Cấu trúc tổng thể của mô hình

### 5.1 Kiến trúc logic

```text
1. Historical Facts Layer
   - Revenue
   - COGS
   - Gross profit
   - SG&A
   - EBIT
   - Net income
   - Cash flow
   - Balance sheet items

2. Driver Layer
   - Volume
   - Price
   - Mix
   - Cost
   - Working capital
   - Capex
   - Financial assumptions
   - Catalyst impact

3. Forecast Layer
   - Income statement forecast
   - Balance sheet forecast
   - Cash flow forecast

4. Valuation Layer
   - FCFF
   - FCFE
   - DCF
   - P/E
   - EV/EBITDA
   - Sensitivity table

5. Narrative Layer
   - Growth explanation
   - Margin story
   - Cash flow story
   - Risk and catalyst interpretation
```

### 5.2 Luồng dữ liệu tiêu chuẩn

```text
Raw Sources
  ↓
Ingestion + Validation
  ↓
Canonical Facts
  ↓
Driver Definition
  ↓
Driver Historical Calibration
  ↓
Driver Assumption Draft
  ↓
Human Review Gate
  ↓
Forecast Engine
  ↓
Valuation Engine
  ↓
Sensitivity + Scenario Analysis
  ↓
Grounded Report Narrative
```

### 5.3 Nguyên tắc phân tách trách nhiệm

| Thành phần | Nhiệm vụ | Không được làm |
|---|---|---|
| Data ingestion | Lấy và chuẩn hóa dữ liệu | Không tự suy diễn forecast |
| Driver module | Định nghĩa driver và assumption | Không viết narrative dài |
| Forecast engine | Tính financial statements | Không dùng LLM để tính toán chính |
| Valuation engine | Tính valuation range | Không tự sửa facts |
| LLM report writer | Diễn giải artifact | Không tạo số mới ngoài artifact |
| Auditor/eval gate | Kiểm tra source, logic, số liệu | Không tự approve báo cáo |

---

## 6. Phân loại driver cần xây dựng

### 6.1 Revenue drivers

| Driver | Ý nghĩa | Công thức gợi ý |
|---|---|---|
| Volume | Sản lượng bán | Revenue = Volume × ASP |
| ASP | Giá bán trung bình | ASP = Revenue / Volume |
| Channel mix | Tỷ trọng doanh thu OTC/ETC/export | Revenue = Σ Revenue by channel |
| Product mix | Tỷ trọng generic, branded generic, supplement | Revenue = Σ Revenue by product group |
| Market share | Thị phần theo phân khúc | Company revenue = Market size × Market share |
| New product launch | Đóng góp từ sản phẩm mới | New product revenue = units × ASP |
| Tender win rate | Tỷ lệ trúng thầu | ETC revenue = tender value × win rate × fulfillment |
| Pharmacy coverage | Độ phủ kênh OTC | OTC sales = points of sale × sales/store |

### 6.2 Gross margin drivers

| Driver | Ý nghĩa | Output |
|---|---|---|
| API/raw material cost | Giá nguyên liệu dược | COGS, gross margin |
| FX rate | Tỷ giá nhập nguyên liệu | COGS |
| Product mix | Tỷ trọng sản phẩm biên cao/thấp | Gross margin |
| Factory utilization | Mức sử dụng công suất | Unit cost, margin |
| Outsourcing ratio | Tỷ trọng thuê ngoài sản xuất | COGS |
| GMP/EU-GMP status | Năng lực sản xuất chuẩn cao | Pricing power, margin |

### 6.3 Operating expense drivers

| Driver | Ý nghĩa | Output |
|---|---|---|
| Salesforce headcount | Số trình dược viên/nhân viên bán hàng | Selling expense |
| Marketing intensity | Chi phí marketing/doanh thu | SG&A |
| Admin headcount | Nhân sự quản trị | G&A |
| R&D intensity | R&D/revenue | Operating expense |
| Distribution cost | Chi phí logistics và phân phối | Selling expense |

### 6.4 Working capital drivers

| Driver | Ý nghĩa | Output |
|---|---|---|
| DSO | Số ngày phải thu | Accounts receivable, CFO |
| DIO | Số ngày tồn kho | Inventory, CFO |
| DPO | Số ngày phải trả | Accounts payable, CFO |
| Inventory buffer | Dự trữ nguyên liệu/thành phẩm | Inventory |
| Receivable quality | Khả năng thu tiền | Bad debt, working capital |

### 6.5 Capex and depreciation drivers

| Driver | Ý nghĩa | Output |
|---|---|---|
| Maintenance capex | Capex duy trì | FCFF |
| Expansion capex | Capex mở rộng nhà máy | FCFF, future capacity |
| GMP upgrade capex | Nâng chuẩn nhà máy | Capex, margin potential |
| Depreciation rate | Khấu hao/tài sản cố định | EBIT, tax shield |

### 6.6 Financial drivers

| Driver | Ý nghĩa | Output |
|---|---|---|
| Debt balance | Nợ vay | Interest expense, FCFE |
| Interest rate | Chi phí vay | Net income |
| Tax rate | Thuế suất hiệu dụng | Net income |
| Shares outstanding | Số cổ phiếu lưu hành | EPS, target price |
| Dividend payout | Tỷ lệ cổ tức | FCFE, equity value bridge |

### 6.7 Catalyst drivers

| Catalyst | Driver tác động | Output có thể bị ảnh hưởng |
|---|---|---|
| Trúng thầu thuốc | Tender win rate, ETC volume | Revenue |
| Thay đổi BHYT | Reimbursement, demand | Revenue, margin |
| Gia hạn số đăng ký thuốc | Product availability | Revenue |
| Thu hồi thuốc | Volume, reputation risk | Revenue, risk premium |
| GMP/EU-GMP approval | Capacity, pricing, export potential | Revenue, margin |
| Biến động API | Raw material cost | Gross margin |
| Chính sách kiểm soát giá | ASP | Revenue, margin |

---

## 7. Tiêu chí lựa chọn driver

Một driver nên được đưa vào mô hình nếu đạt phần lớn các tiêu chí sau.

### 7.1 Materiality

Driver phải có tác động đáng kể đến doanh thu, lợi nhuận, dòng tiền hoặc valuation.

Câu hỏi kiểm tra:

```text
Nếu driver này thay đổi 5-10%, valuation có thay đổi đáng kể không?
```

Nếu không, không nên đưa vào mô hình chính.

### 7.2 Causality

Driver phải có quan hệ nhân quả hợp lý với output.

Ví dụ tốt:

```text
API cost tăng → COGS tăng → gross margin giảm
```

Ví dụ yếu:

```text
Tin tức nhiều hơn → giá trị doanh nghiệp tăng
```

Trường hợp yếu có thể đưa vào catalyst narrative, nhưng không nên đưa trực tiếp vào valuation nếu không có cơ chế định lượng.

### 7.3 Measurability

Driver phải đo được bằng dữ liệu lịch sử, báo cáo doanh nghiệp, nguồn ngành, hoặc proxy hợp lý.

Ví dụ:

| Driver | Dữ liệu trực tiếp | Proxy nếu thiếu |
|---|---|---|
| Volume bán thuốc | Báo cáo nội bộ hoặc thuyết minh | Revenue / ASP ước tính |
| ASP | Revenue / volume | Chỉ số giá thuốc hoặc pricing disclosure |
| API cost | Giá nguyên liệu | Gross margin trend, import price index |
| Tender exposure | Kết quả đấu thầu | Tỷ trọng ETC hoặc hospital channel |

### 7.4 Data availability

Driver cần có nguồn dữ liệu đủ ổn định để cập nhật định kỳ.

Đánh giá:

| Mức | Ý nghĩa |
|---|---|
| A | Có dữ liệu trực tiếp, nguồn chính thức |
| B | Có dữ liệu gián tiếp, nguồn đáng tin |
| C | Có proxy yếu, cần human review |
| D | Không có dữ liệu, chỉ dùng narrative |

### 7.5 Forecastability

Driver phải có khả năng dự báo hợp lý.

Một số driver dễ dự báo:

- Tax rate.
- Depreciation rate.
- SG&A/revenue nếu ổn định.
- DSO/DIO/DPO nếu có lịch sử tốt.

Một số driver khó dự báo:

- Tender win rate.
- Regulatory approval timing.
- Sudden recall.
- FX shock.

Driver khó dự báo vẫn có thể dùng, nhưng nên nằm trong scenario hoặc stress test thay vì base case cứng.

### 7.6 Auditability

Mỗi driver assumption cần truy được về:

```text
driver_id
source_id
evidence_id
assumption_version
approved_by
approved_at
```

Nếu không audit được, driver không nên đi vào bản báo cáo final.

### 7.7 Interpretability

Driver phải dễ giải thích cho analyst/reviewer.

Nếu mô hình quá phức tạp đến mức người duyệt không hiểu driver tác động thế nào đến forecast, mô hình đó không phù hợp với equity research production.

### 7.8 Stability

Driver không nên quá nhiễu nếu không có giá trị giải thích rõ.

Ví dụ: daily market noise không nên dùng làm driver cho forecast doanh thu năm của công ty dược.

### 7.9 Actionability

Driver nên giúp người đọc hiểu điều gì cần theo dõi tiếp.

Ví dụ:

- Nếu DIO tăng mạnh, cần theo dõi tồn kho và cash conversion cycle.
- Nếu ETC mix tăng, cần theo dõi kết quả đấu thầu và biên lợi nhuận.
- Nếu API cost tăng, cần theo dõi gross margin và pricing power.

---

## 8. Phương pháp xây dựng mô hình

### Phase 1 — Xác định output cần dự phóng

Trước khi chọn driver, cần xác định mô hình phải dự phóng những output nào.

Output tối thiểu:

| Nhóm | Output |
|---|---|
| Income statement | Revenue, COGS, gross profit, SG&A, EBIT, tax, net income, EPS |
| Balance sheet | Cash, receivables, inventory, payables, debt, equity |
| Cash flow | CFO, capex, FCFF, FCFE |
| Valuation | Enterprise value, equity value, target price |
| Report | Growth story, margin story, risk/catalyst story |

### Phase 2 — Mapping output sang driver

Ví dụ mapping cơ bản:

| Output | Driver chính |
|---|---|
| Revenue | Volume, ASP, channel mix, product mix |
| Gross margin | API cost, FX, product mix, factory utilization |
| SG&A | Salesforce, marketing ratio, admin cost |
| EBIT | Gross profit, SG&A, depreciation |
| Net income | EBIT, interest, tax |
| Working capital | DSO, DIO, DPO |
| FCFF | EBIT, tax, depreciation, capex, NWC |
| FCFE | FCFF, debt repayment/issuance, interest |
| Target price | FCFF/FCFE, WACC, terminal growth, shares |

### Phase 3 — Calibrate driver lịch sử

Từ dữ liệu historical facts, tính lại driver lịch sử.

Ví dụ:

```text
Gross margin = Gross profit / Revenue
SG&A ratio = SG&A / Revenue
DSO = Average accounts receivable / Revenue × 365
DIO = Average inventory / COGS × 365
DPO = Average accounts payable / COGS × 365
```

Mục tiêu của bước này:

- Hiểu baseline quá khứ.
- Phát hiện bất thường.
- Xác định range hợp lý cho forecast.
- Không nhập assumption tương lai một cách tùy tiện.

### Phase 4 — Draft assumptions

Assumption phải có cấu trúc rõ:

```yaml
driver_id: revenue_growth_by_volume
ticker: DHG
period: 2026F
scenario: base
value: 0.05
unit: percentage
rationale: "Sản lượng tăng nhờ kênh OTC ổn định và ETC phục hồi nhẹ."
source_refs:
  - source_id: annual_report_2025
  - source_id: tender_result_2026
confidence: medium
created_by: analyst_or_agent
requires_human_approval: true
```

### Phase 5 — Human review gate cho assumptions

Trước khi forecast, reviewer cần duyệt:

- Driver nào được dùng.
- Assumption nào là base case.
- Assumption nào là bull/bear case.
- Assumption nào thiếu nguồn và cần flag.
- Assumption nào không được phép đi vào valuation.

### Phase 6 — Tính forecast bằng code

Forecast phải chạy bằng công thức deterministic.

Ví dụ:

```text
Revenue_FY2026 = Volume_FY2026 × ASP_FY2026
COGS_FY2026 = Revenue_FY2026 × COGS_ratio_FY2026
Gross_profit_FY2026 = Revenue_FY2026 - COGS_FY2026
EBIT_FY2026 = Gross_profit_FY2026 - SG&A_FY2026 - D&A_FY2026
```

Không cho LLM tự tính số chính trong text.

### Phase 7 — Reconcile financial statements

Sau khi forecast, cần kiểm tra:

- Balance sheet cân bằng.
- Cash flow khớp với thay đổi balance sheet.
- Working capital không âm bất thường.
- Debt schedule khớp interest expense.
- EPS khớp net income và shares outstanding.

### Phase 8 — Chạy valuation

Valuation có thể gồm:

```text
DCF based on FCFF
DCF based on FCFE
P/E multiple
EV/EBITDA multiple
Sensitivity analysis
```

Mọi valuation output phải lưu thành artifact riêng.

### Phase 9 — Sinh narrative từ artifact đã khóa

LLM chỉ được viết narrative dựa trên:

- Historical facts.
- Driver assumptions đã duyệt.
- Forecast outputs.
- Valuation outputs.
- Sensitivity results.
- Evidence/citation map.

Narrative không được thêm số mới ngoài artifact.

---

## 9. Thiết kế dữ liệu và schema đề xuất

### 9.1 Bảng `driver_definitions`

Mục đích: lưu danh mục driver chuẩn.

```sql
CREATE TABLE driver_definitions (
    driver_id TEXT PRIMARY KEY,
    driver_name TEXT NOT NULL,
    driver_category TEXT NOT NULL,
    description TEXT,
    unit TEXT NOT NULL,
    financial_statement_link TEXT,
    default_formula_id TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

Ví dụ:

```text
driver_id: revenue_volume_growth
driver_name: Revenue Volume Growth
driver_category: revenue
unit: percentage
financial_statement_link: income_statement.revenue
default_formula_id: revenue_from_volume_asp
```

### 9.2 Bảng `driver_historical_values`

Mục đích: lưu driver tính từ dữ liệu lịch sử.

```sql
CREATE TABLE driver_historical_values (
    id UUID PRIMARY KEY,
    ticker TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    driver_id TEXT NOT NULL REFERENCES driver_definitions(driver_id),
    value NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    calculation_method TEXT,
    source_fact_ids JSONB,
    confidence NUMERIC,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ticker, fiscal_year, driver_id)
);
```

### 9.3 Bảng `driver_assumptions`

Mục đích: lưu giả định forecast theo scenario.

```sql
CREATE TABLE driver_assumptions (
    assumption_id UUID PRIMARY KEY,
    ticker TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    scenario TEXT NOT NULL,
    driver_id TEXT NOT NULL REFERENCES driver_definitions(driver_id),
    value NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    rationale TEXT,
    evidence_refs JSONB,
    confidence TEXT CHECK (confidence IN ('low', 'medium', 'high')),
    status TEXT CHECK (status IN ('draft', 'approved', 'rejected', 'needs_review')),
    approved_by TEXT,
    approved_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ticker, fiscal_year, scenario, driver_id)
);
```

### 9.4 Bảng `forecast_outputs`

Mục đích: lưu output dự phóng.

```sql
CREATE TABLE forecast_outputs (
    forecast_id UUID PRIMARY KEY,
    ticker TEXT NOT NULL,
    fiscal_year INTEGER NOT NULL,
    scenario TEXT NOT NULL,
    metric_id TEXT NOT NULL,
    value NUMERIC NOT NULL,
    unit TEXT NOT NULL,
    formula_id TEXT NOT NULL,
    input_driver_ids JSONB,
    input_assumption_ids JSONB,
    calculation_trace JSONB,
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(ticker, fiscal_year, scenario, metric_id)
);
```

### 9.5 Bảng `sensitivity_results`

Mục đích: lưu sensitivity table.

```sql
CREATE TABLE sensitivity_results (
    sensitivity_id UUID PRIMARY KEY,
    ticker TEXT NOT NULL,
    valuation_method TEXT NOT NULL,
    base_scenario TEXT NOT NULL,
    variable_1 TEXT NOT NULL,
    variable_2 TEXT,
    result_matrix JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 9.6 Bảng `driver_evidence_map`

Mục đích: nối driver assumption với citation/source.

```sql
CREATE TABLE driver_evidence_map (
    id UUID PRIMARY KEY,
    assumption_id UUID NOT NULL REFERENCES driver_assumptions(assumption_id),
    source_id TEXT NOT NULL,
    evidence_type TEXT,
    evidence_text TEXT,
    source_date DATE,
    source_reliability TEXT,
    created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 10. Thiết kế công thức và engine tính toán

### 10.1 Nguyên tắc công thức

Công thức phải:

1. Có `formula_id` ổn định.
2. Có input schema rõ.
3. Có output schema rõ.
4. Có unit validation.
5. Có calculation trace.
6. Có test case.
7. Không phụ thuộc vào text generation của LLM.

### 10.2 Công thức revenue cơ bản

```text
revenue = volume × asp
```

Nếu không có volume/ASP trực tiếp:

```text
revenue_forecast = revenue_previous_year × (1 + revenue_growth_assumption)
```

Tuy nhiên, growth assumption vẫn phải được giải thích bằng sub-driver:

```text
revenue_growth = volume_growth + price_growth + mix_effect
```

### 10.3 Công thức margin

```text
gross_profit = revenue × gross_margin
cogs = revenue - gross_profit
```

Hoặc:

```text
cogs = volume × unit_cost
gross_profit = revenue - cogs
```

### 10.4 Công thức operating expenses

```text
selling_expense = revenue × selling_expense_ratio
admin_expense = revenue × admin_expense_ratio
r_and_d_expense = revenue × r_and_d_ratio
```

### 10.5 Công thức working capital

```text
accounts_receivable = revenue × DSO / 365
inventory = COGS × DIO / 365
accounts_payable = COGS × DPO / 365
net_working_capital = accounts_receivable + inventory - accounts_payable
change_in_nwc = nwc_current_year - nwc_previous_year
```

### 10.6 Công thức FCFF

```text
FCFF = EBIT × (1 - tax_rate) + depreciation - capex - change_in_nwc
```

### 10.7 Công thức FCFE

```text
FCFE = FCFF - interest_expense × (1 - tax_rate) + net_borrowing
```

### 10.8 Công thức DCF

```text
enterprise_value = Σ FCFF_t / (1 + WACC)^t + terminal_value / (1 + WACC)^n

terminal_value = FCFF_n × (1 + terminal_growth) / (WACC - terminal_growth)
```

### 10.9 Rule kiểm tra công thức

| Rule | Ý nghĩa |
|---|---|
| Unit consistency | Không cộng VND với % |
| Period consistency | Không trộn FY2024 actual với FY2026 assumption nếu không có mapping |
| Ticker consistency | Không dùng driver của ticker khác |
| Scenario consistency | Base, bull, bear không được trộn lẫn |
| Formula reproducibility | Chạy lại cùng input phải ra cùng output |
| Numerical tolerance | Sai lệch do rounding phải nằm trong ngưỡng định nghĩa |

---

## 11. Kịch bản, sensitivity và stress test

### 11.1 Scenario design

Tối thiểu cần ba scenario:

| Scenario | Ý nghĩa |
|---|---|
| Base case | Trường hợp hợp lý nhất dựa trên dữ liệu hiện tại |
| Bull case | Trường hợp tích cực nhưng vẫn có luận cứ |
| Bear case | Trường hợp tiêu cực hoặc conservative |

### 11.2 Driver theo scenario

Ví dụ:

| Driver | Bear | Base | Bull |
|---|---:|---:|---:|
| Revenue growth | 3% | 7% | 11% |
| Gross margin | 42% | 44% | 46% |
| SG&A/revenue | 25% | 24% | 23% |
| DSO | 95 ngày | 85 ngày | 75 ngày |
| Terminal growth | 1.5% | 2.0% | 2.5% |

### 11.3 Sensitivity analysis

Sensitivity nên tập trung vào các driver có ảnh hưởng lớn đến valuation:

| Nhóm | Biến sensitivity |
|---|---|
| DCF | WACC, terminal growth |
| Growth | Revenue growth, volume growth, ASP growth |
| Margin | Gross margin, EBIT margin |
| Working capital | DSO, DIO, DPO |
| Capex | Capex/revenue |
| Multiple valuation | Target P/E, target EV/EBITDA |

### 11.4 Stress test

Stress test nên dùng cho các biến rủi ro cao:

- API cost tăng mạnh.
- Không trúng thầu ETC.
- Gross margin giảm 300-500 bps.
- DSO tăng mạnh do kênh bệnh viện thanh toán chậm.
- Capex tăng vượt kế hoạch.
- WACC tăng do thị trường rủi ro hơn.
- Regulatory delay khiến sản phẩm mới không đóng góp doanh thu.

---

## 12. Driver modelling cho ngành dược Việt Nam

### 12.1 Revenue model đề xuất

Tùy mức dữ liệu, có ba cấp độ.

#### Level 1 — Top-down tối giản

```text
Revenue_t = Revenue_t-1 × (1 + revenue_growth)
```

Chỉ dùng khi thiếu dữ liệu chi tiết. Growth assumption phải được giải thích bằng narrative và citation.

#### Level 2 — Channel-based

```text
Revenue = OTC revenue + ETC revenue + Export revenue
```

Trong đó:

```text
OTC revenue = OTC revenue_t-1 × (1 + OTC growth)
ETC revenue = ETC revenue_t-1 × (1 + ETC growth)
Export revenue = Export revenue_t-1 × (1 + export growth)
```

#### Level 3 — Driver-based chi tiết

```text
OTC revenue = pharmacies_covered × sales_per_pharmacy
ETC revenue = tender_value × win_rate × fulfillment_rate
Export revenue = export_volume × export_ASP
```

MVP nên bắt đầu ở Level 1 hoặc Level 2, sau đó nâng lên Level 3 khi có dữ liệu tốt hơn.

### 12.2 Margin model đề xuất

```text
Gross margin = base_margin + product_mix_effect + API_cost_effect + FX_effect + utilization_effect
```

Trong MVP có thể đơn giản hóa:

```text
Gross margin forecast = historical average adjusted by known catalysts
```

Nhưng mọi adjustment cần có rationale.

### 12.3 SG&A model đề xuất

```text
SG&A = Revenue × SG&A_ratio
```

Nếu có dữ liệu chi tiết hơn:

```text
Selling expense = salesforce_headcount × average_cost_per_salesperson + marketing_budget
Admin expense = revenue × admin_ratio
```

### 12.4 Working capital model đề xuất

```text
Receivables = Revenue × DSO / 365
Inventory = COGS × DIO / 365
Payables = COGS × DPO / 365
```

Đây là phần rất quan trọng vì công ty có thể có lợi nhuận kế toán tốt nhưng dòng tiền xấu nếu phải thu/tồn kho tăng mạnh.

### 12.5 Capex model đề xuất

```text
Capex = maintenance_capex + expansion_capex
```

Nếu thiếu dữ liệu:

```text
Maintenance capex = depreciation × maintenance_ratio
Expansion capex = known_project_capex hoặc capex/revenue assumption
```

### 12.6 Valuation link

Driver không dừng ở forecast. Nó phải nối đến valuation.

Ví dụ:

```text
Tender win rate ↑
→ ETC revenue ↑
→ Total revenue ↑
→ EBIT ↑
→ FCFF ↑
→ DCF value ↑
```

Hoặc:

```text
API cost ↑
→ COGS ↑
→ Gross margin ↓
→ EBIT ↓
→ FCFF ↓
→ Target price ↓
```

---

## 13. Evaluation và quality gates

### 13.1 Data quality gate

Trước khi dùng dữ liệu lịch sử để calibrate driver:

- Phải có nguồn.
- Phải đúng ticker.
- Phải đúng năm tài chính.
- Phải đúng đơn vị.
- Phải qua missing-field check.
- Phải qua reconciliation subtotal/total nếu có.
- Phải có confidence score.

### 13.2 Driver quality gate

Một driver chỉ được dùng trong forecast nếu:

| Tiêu chí | Pass condition |
|---|---|
| Definition | Có driver_id và mô tả rõ |
| Formula link | Có công thức hoặc mapping đến output |
| Historical baseline | Có dữ liệu lịch sử hoặc proxy |
| Assumption | Có giá trị forecast rõ |
| Rationale | Có giải thích |
| Evidence | Có source hoặc được flag thiếu nguồn |
| Approval | Được reviewer duyệt nếu ảnh hưởng valuation lớn |

### 13.3 Forecast quality gate

Forecast pass nếu:

- Không có output âm bất thường nếu không có rationale.
- Revenue, margin, working capital nằm trong range hợp lý.
- Balance sheet cân bằng.
- Cash flow khớp với working capital và capex.
- EPS khớp net income/shares.
- Các năm forecast liên tục, không thiếu kỳ.
- Scenario không bị trộn assumptions.

### 13.4 Valuation quality gate

Valuation pass nếu:

- FCFF/FCFE tính lại được từ forecast.
- WACC và terminal growth có assumption rõ.
- Terminal growth < WACC.
- Sensitivity table đã sinh.
- Target price trace được về valuation artifact.
- Không có investment conclusion tuyệt đối nếu chưa qua final review.

### 13.5 Narrative quality gate

Narrative pass nếu:

- Không có số ngoài artifact.
- Mỗi claim định lượng có citation hoặc fact record.
- Phần “storytelling” giải thích được driver chính.
- Có nêu uncertainty nếu driver thiếu dữ liệu.
- Có risk/catalyst phù hợp với mô hình.

---

## 14. Lộ trình triển khai theo phase

### Phase 0 — Chốt phạm vi MVP

**Mục tiêu:** Không xây quá rộng.

Deliverables:

- Danh sách ticker MVP: DHG, IMP, DMC, TRA, DBD.
- Chọn forecast horizon: 3-5 năm.
- Chọn model level: top-down, channel-based hoặc chi tiết.
- Chọn valuation methods: DCF, P/E, EV/EBITDA.
- Chọn output report template.

Exit criteria:

- Có tài liệu scope.
- Có danh sách output bắt buộc.
- Có non-goals rõ ràng.

---

### Phase 1 — Xây driver taxonomy

**Mục tiêu:** Chuẩn hóa danh mục driver.

Deliverables:

- `driver_definitions.yaml`
- Mapping driver → financial statement output.
- Mapping driver → formula_id.
- Driver category: revenue, margin, opex, working capital, capex, financial, catalyst.

Exit criteria:

- Mỗi driver có ID ổn định.
- Không trùng nghĩa.
- Có unit.
- Có mô tả.
- Có output link.

---

### Phase 2 — Xây historical driver calibration

**Mục tiêu:** Tính lại driver lịch sử từ canonical facts.

Deliverables:

- Function tính gross margin, SG&A ratio, DSO, DIO, DPO, capex/revenue.
- Historical driver table cho từng ticker.
- Data quality warnings.

Exit criteria:

- Chạy được cho ít nhất 1 ticker.
- Output trace được về source facts.
- Có test case cho từng formula.

---

### Phase 3 — Xây assumption layer

**Mục tiêu:** Tách assumptions khỏi facts.

Deliverables:

- `driver_assumptions` schema.
- YAML/JSON input format cho base/bull/bear.
- Human approval status.
- Evidence mapping cho assumption.

Exit criteria:

- Assumption không ghi đè facts.
- Mỗi assumption có scenario.
- Assumption ảnh hưởng lớn phải cần approval.

---

### Phase 4 — Xây forecast engine

**Mục tiêu:** Tạo financial statements dự phóng bằng code.

Deliverables:

- Income statement forecast.
- Working capital forecast.
- Capex and depreciation forecast.
- Debt and interest forecast.
- FCFF/FCFE forecast.

Exit criteria:

- Không dùng LLM để tính số chính.
- Có calculation trace.
- Có unit checks.
- Có forecast output artifact.

---

### Phase 5 — Xây valuation integration

**Mục tiêu:** Nối forecast vào DCF/multiples.

Deliverables:

- DCF FCFF.
- DCF FCFE nếu đủ dữ liệu.
- P/E valuation.
- EV/EBITDA valuation.
- Sensitivity matrix.

Exit criteria:

- Valuation output reproducible.
- Target price trace được về assumptions.
- Sensitivity có ít nhất WACC × terminal growth.

---

### Phase 6 — Xây narrative integration

**Mục tiêu:** Biến driver output thành câu chuyện tài chính.

Deliverables:

- Template narrative cho revenue growth.
- Template narrative cho margin.
- Template narrative cho working capital/cash flow.
- Template narrative cho valuation.
- Citation map.

Exit criteria:

- Narrative không thêm số ngoài artifact.
- Mỗi claim định lượng có citation.
- Có phần “key drivers behind forecast”.

---

### Phase 7 — Xây evaluation harness

**Mục tiêu:** Kiểm định driver modelling trước khi dùng trong report final.

Deliverables:

- Driver quality tests.
- Forecast consistency tests.
- Valuation reproducibility tests.
- Narrative grounding tests.
- Reviewer correction tracking.

Exit criteria:

- Có pass/fail gate.
- Có regression baseline.
- Có report lỗi rõ ràng.

---

## 15. Deliverables cần tạo

### 15.1 Tài liệu

| File | Mục đích |
|---|---|
| `DRIVER_MODELING_PLAN.md` | Kế hoạch tổng thể |
| `DRIVER_TAXONOMY.md` | Danh mục driver |
| `DRIVER_ASSUMPTION_GUIDE.md` | Hướng dẫn tạo assumption |
| `FORECAST_FORMULA_SPEC.md` | Đặc tả công thức forecast |
| `DRIVER_EVALUATION_RUBRIC.md` | Rubric kiểm định driver |

### 15.2 Config

| File | Mục đích |
|---|---|
| `config/driver_definitions.yaml` | Định nghĩa driver |
| `config/driver_formula_mapping.yaml` | Mapping driver → formula |
| `config/driver_thresholds.yaml` | Ngưỡng cảnh báo |
| `config/scenario_templates.yaml` | Base/bull/bear templates |

### 15.3 Code modules

| Module | Nhiệm vụ |
|---|---|
| `backend/drivers/taxonomy.py` | Load và validate driver definitions |
| `backend/drivers/calibration.py` | Tính driver lịch sử |
| `backend/drivers/assumptions.py` | Quản lý assumptions |
| `backend/forecasting/driver_forecast.py` | Forecast bằng driver |
| `backend/valuation/driver_integrated_dcf.py` | Nối driver forecast vào valuation |
| `backend/evaluation/driver_quality_gate.py` | Kiểm định driver/forecast |

### 15.4 Tests

| Test | Mục tiêu |
|---|---|
| Unit tests cho formula | Đảm bảo công thức đúng |
| Unit tests cho unit conversion | Không sai đơn vị |
| Reconciliation tests | Statement cân bằng |
| Scenario isolation tests | Không trộn scenario |
| Golden tests | So với dữ liệu đã kiểm định |
| Regression tests | Không làm hỏng output cũ |

---

## 16. Acceptance criteria

Driver-based modelling được coi là đạt MVP nếu thỏa các điều kiện sau.

### 16.1 Data acceptance

- Có ít nhất 3-5 năm facts lịch sử cho mỗi ticker MVP.
- Mỗi fact chính có source metadata.
- Driver lịch sử tính được từ canonical facts.
- Có cảnh báo khi thiếu dữ liệu.

### 16.2 Driver acceptance

- Mỗi driver có `driver_id`, category, unit, description.
- Mỗi driver có output financial statement liên quan.
- Driver quan trọng có rationale và evidence.
- Assumption có scenario và approval status.

### 16.3 Forecast acceptance

- Forecast chạy bằng code.
- Không có LLM-generated numeric facts.
- Income statement, balance sheet, cash flow có reconciliation.
- FCFF/FCFE tính lại được.
- Có trace từ output về driver assumption.

### 16.4 Valuation acceptance

- DCF dùng forecast output đã khóa.
- Multiples dùng metric đã chuẩn hóa.
- Sensitivity table có ít nhất 2 biến trọng yếu.
- Target price trace được về assumptions và formula.

### 16.5 Report acceptance

- Report có phần “Key Forecast Drivers”.
- Mỗi claim định lượng có citation hoặc fact record.
- Narrative giải thích được vì sao revenue/margin/cash flow thay đổi.
- Report bị block nếu driver assumption quan trọng chưa được duyệt.

---

## 17. Checklist triển khai

### 17.1 Checklist thiết kế driver

- [ ] Driver có tên rõ ràng.
- [ ] Driver có ID ổn định.
- [ ] Driver thuộc category cụ thể.
- [ ] Driver có unit.
- [ ] Driver có financial output liên quan.
- [ ] Driver có công thức hoặc mapping.
- [ ] Driver có dữ liệu lịch sử hoặc proxy.
- [ ] Driver có source/evidence nếu dùng forecast.
- [ ] Driver có ngưỡng cảnh báo.
- [ ] Driver có test case.

### 17.2 Checklist assumption

- [ ] Assumption phân biệt rõ actual vs forecast.
- [ ] Assumption có scenario.
- [ ] Assumption có kỳ dự báo.
- [ ] Assumption có rationale.
- [ ] Assumption có confidence.
- [ ] Assumption có evidence hoặc flag thiếu evidence.
- [ ] Assumption có reviewer approval nếu material.
- [ ] Assumption có version.

### 17.3 Checklist forecast

- [ ] Forecast không dùng LLM để tính số.
- [ ] Có unit validation.
- [ ] Có period validation.
- [ ] Có ticker validation.
- [ ] Có scenario validation.
- [ ] Có reconciliation.
- [ ] Có calculation trace.
- [ ] Có regression test.

### 17.4 Checklist report

- [ ] Có phần key drivers.
- [ ] Có valuation assumptions table.
- [ ] Có sensitivity table.
- [ ] Có risk/catalyst mapping.
- [ ] Có citation cho số liệu.
- [ ] Không có claim vượt quá evidence.
- [ ] Có trạng thái human review.

---

## 18. Kết luận

Driver-based financial modelling là nền tảng để biến hệ thống equity research từ một công cụ “viết báo cáo có bảng số” thành một hệ thống phân tích có logic nhân quả.

Trong dự án Vietnam Pharma Equity Research Agent, driver modelling cần được xây theo hướng:

```text
Facts trước
Assumptions sau
Code tính toán
LLM chỉ diễn giải
Human duyệt driver quan trọng
Report xuất bản kèm citation và audit trail
```

Nguyên tắc triển khai quan trọng nhất:

> Không dự phóng bằng cảm tính. Không để LLM tự tạo số. Không đưa driver vào valuation nếu không có định nghĩa, công thức, source hoặc approval rõ ràng.

Nếu xây đúng, mô hình sẽ giúp báo cáo không chỉ nói “doanh thu tăng 8%”, mà giải thích được:

```text
Doanh thu tăng do driver nào?
Biên lợi nhuận thay đổi vì sao?
Dòng tiền tốt/xấu do working capital hay capex?
Valuation nhạy nhất với assumption nào?
Catalyst nào cần theo dõi để cập nhật thesis?
```

Đây là lớp bắt buộc để dự án đạt chuẩn `code-first valuation`, `citation-first reporting`, `data quality gates`, và `human-in-the-loop approval`.
