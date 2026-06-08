# Gợi ý luồng Agent dự phóng từ đầu đến cuối trước khi đưa vào định giá

## 1. Mục tiêu thiết kế

Agent không nên dự phóng bằng cách “đoán” trực tiếp từ LLM. Toàn bộ forecast phải đi theo một pipeline tài chính có kiểm soát, dựa trên dữ liệu lịch sử, driver-based assumptions, scenario assumptions và các bước sanity check trước khi đưa vào định giá.

Mục tiêu của luồng này là đảm bảo rằng các phần quan trọng như doanh thu, biên lợi nhuận, vốn lưu động, CAPEX, nợ vay, lãi vay, thuế, cổ tức, vốn chủ sở hữu và dòng tiền đều được liên kết với nhau trước khi chạy FCFF, FCFE và blend valuation.

---

## 2. Luồng tổng thể khuyến nghị

```text
1. Chuẩn hóa dữ liệu lịch sử
2. Kiểm định dữ liệu đầu vào
3. Tính driver lịch sử
4. Xây dựng assumption cho từng kịch bản
5. Dự phóng operating forecast
6. Dự phóng working capital
7. Dự phóng CAPEX và depreciation
8. Dự phóng nợ vay
9. Dự phóng lãi vay
10. Tính PBT, thuế, net income
11. Dự phóng cổ tức
12. Cập nhật equity, debt, cash, balance sheet
13. Tạo ForecastArtifact hoàn chỉnh
14. Chạy sanity check
15. Đưa vào FCFF, FCFE, blend valuation
16. Chạy sensitivity, approval gate và valuation confidence
```

---

## 3. Bước 1 — Chuẩn hóa dữ liệu lịch sử

Agent phải bắt đầu từ `fact_table` đã chuẩn hóa. Không được lấy dữ liệu thô chưa kiểm định để đưa thẳng vào forecast.

Các dữ liệu tối thiểu cần có:

```text
Revenue
COGS
Gross Profit
SG&A
EBIT
Depreciation
CAPEX
Current assets
Current liabilities
Cash
Short-term investments
Total debt
Equity
Interest expense
Profit before tax
Net income
EPS
Dividends paid
Proceeds from borrowings
Repayment of borrowings
```

Nếu thiếu dữ liệu trọng yếu, Agent không được âm thầm thay bằng `0`. Agent phải ghi rõ:

```text
missing_source_data
required_for_publish = True / False
confidence = high / medium / low
warning = mô tả dữ liệu bị thiếu
```

---

## 4. Bước 2 — Kiểm định dữ liệu trước forecast

Trước khi forecast, Agent cần kiểm tra các điều kiện tối thiểu:

```text
Revenue > 0
Gross margin hợp lý
SG&A / Revenue không âm bất thường
CAPEX sign đúng
Total debt không thiếu
Cash không thiếu
PBT và Net Income dùng được để tính tax
Dividends paid có hay không
Borrowing / repayment có hay không
EPS có khớp với Net Income / Shares không
```

Nếu data quality chưa đạt, Agent vẫn có thể tạo bản nháp nhưng không được xuất khuyến nghị chính thức như BUY/HOLD/SELL. Kết quả chỉ nên được gắn nhãn:

```text
Draft / Needs Analyst Review
```

---

## 5. Bước 3 — Tính driver lịch sử

Agent nên tính driver lịch sử theo từng nhóm.

### 5.1. Operating drivers

```text
Revenue CAGR
Gross margin
SG&A / Revenue
EBIT margin
Depreciation / Revenue
CAPEX / Revenue
Tax rate
```

Các driver này dùng để tạo operating forecast.

### 5.2. Working capital drivers

Nên bổ sung vào `forecasting.py`:

```text
DSO = Accounts Receivable / Revenue × 365
DIO = Inventory / COGS × 365
DPO = Accounts Payable / COGS × 365
NWC = Receivables + Inventory - Payables
ΔNWC = NWC_t - NWC_t-1
```

Việc forecast working capital trong `forecasting.py` sẽ tốt hơn việc để `fcff.py` hoặc `fcfe.py` tự dùng proxy như `2% × change in revenue`.

### 5.3. Debt drivers

```text
Debt / EBITDA
Debt / Assets
Debt / Equity
Net Borrowing lịch sử
Implied Cost of Debt = Interest Expense / Average Debt
```

Agent nên ưu tiên dữ liệu vay/trả nợ từ cash flow statement. Nếu không có, có thể dùng thay đổi nợ trên bảng cân đối nhưng phải hạ confidence.

### 5.4. Dividend drivers

```text
Payout Ratio = |Dividends Paid| / Net Income
DPS nếu có shares
Historical median payout
Dividend stability
```

Nếu thiếu dữ liệu cổ tức, Agent không được tự kết luận rằng doanh nghiệp không trả cổ tức. Cần warning và yêu cầu analyst review.

---

## 6. Bước 4 — Xây dựng assumption theo kịch bản

Agent không nên chỉ có một bộ forecast base case. Tối thiểu cần có:

```text
Bear
Base
Bull
```

Mỗi kịch bản phải thay đổi đủ các nhóm driver:

```text
Operating drivers
Working capital drivers
CAPEX drivers
Debt policy
Cost of debt
Dividend policy
Tax policy nếu cần
```

### Gợi ý scenario matrix

| Driver | Bear | Base | Bull |
|---|---:|---:|---:|
| Revenue growth | CAGR - 2 đến 5 điểm % | CAGR lịch sử / analyst approved | CAGR + 2 đến 5 điểm % |
| Gross margin | Giảm | Median lịch sử | Tăng nhẹ |
| SG&A / Revenue | Tăng | Median lịch sử | Giảm nhẹ |
| CAPEX / Revenue | Giữ hoặc tăng nếu cần đầu tư | Median lịch sử | Tối ưu hơn |
| DSO / DIO | Tăng | Median lịch sử | Giảm |
| DPO | Giảm hoặc giữ | Median lịch sử | Tăng nhẹ |
| Cost of debt | Tăng 1–2 điểm % | Median lịch sử | Giữ hoặc giảm nhẹ |
| Net borrowing | Tăng nếu thiếu cash | Stable leverage | Giảm hoặc trả nợ |
| Payout ratio | Giảm/cắt nếu FCFE yếu | Median lịch sử | Giữ hoặc tăng nhẹ |

---

## 7. Bước 5 — Dự phóng operating forecast

Agent nên forecast theo thứ tự:

```text
Revenue
COGS
Gross Profit
SG&A
EBIT
Depreciation
EBITDA
CAPEX
```

Công thức gợi ý:

```text
Revenue_t = Revenue_t-1 × (1 + Revenue Growth)

COGS_t = -Revenue_t × (1 - Gross Margin)

Gross Profit_t = Revenue_t + COGS_t

SG&A_t = -Revenue_t × SG&A / Revenue

EBIT_t = Gross Profit_t + SG&A_t

Depreciation_t = Revenue_t × Depreciation / Revenue

EBITDA_t = EBIT_t + Depreciation_t

CAPEX_t = Revenue_t × CAPEX / Revenue
```

Lưu ý: nếu depreciation đã nằm trong COGS hoặc SG&A lịch sử, Agent không nên trừ depreciation thêm một lần khỏi EBIT, tránh double-count.

---

## 8. Bước 6 — Dự phóng working capital

Thay vì dùng proxy đơn giản, Agent nên forecast working capital bằng DSO, DIO, DPO.

Công thức:

```text
Accounts Receivable_t = Revenue_t × DSO / 365

Inventory_t = COGS_abs_t × DIO / 365

Accounts Payable_t = COGS_abs_t × DPO / 365

NWC_t = Accounts Receivable_t + Inventory_t - Accounts Payable_t

ΔNWC_t = NWC_t - NWC_t-1
```

Sau đó, `ForecastYear` nên có thêm các trường:

```python
accounts_receivable: float | None
inventory: float | None
accounts_payable: float | None
net_working_capital: float | None
delta_nwc: float | None
```

`fcff.py` và `fcfe.py` nên dùng trực tiếp `fy.delta_nwc`, không tự ước lượng lại.

---

## 9. Bước 7 — Dự phóng nợ vay

Agent nên dự phóng nợ vay bằng debt roll-forward.

Công thức:

```text
Beginning Debt_t = Ending Debt_t-1

Net Borrowing_t = New Borrowing_t - Debt Repayment_t

Ending Debt_t = Beginning Debt_t + Net Borrowing_t
```

Agent nên chọn debt policy theo thứ tự ưu tiên:

```text
1. Manual debt path nếu analyst nhập
2. Direct cash flow nếu có borrowing / repayment lịch sử
3. Target Debt / EBITDA
4. Target Debt / Assets
5. Stable debt
6. Zero debt policy
7. Missing → chặn publish
```

### 9.1. Stable debt policy

Dùng khi doanh nghiệp duy trì dư nợ ổn định.

```text
Ending Debt_t = Beginning Debt_t
Net Borrowing_t = 0
```

### 9.2. Target Debt / EBITDA policy

Dùng khi doanh nghiệp duy trì leverage theo EBITDA.

```text
Target Debt_t = Target Debt / EBITDA × EBITDA_t
Net Borrowing_t = Target Debt_t - Beginning Debt_t
Ending Debt_t = Target Debt_t
```

### 9.3. Target Debt / Assets policy

Dùng khi nợ đi theo quy mô tài sản.

```text
Target Debt_t = Target Debt / Assets × Total Assets_t
Net Borrowing_t = Target Debt_t - Beginning Debt_t
Ending Debt_t = Target Debt_t
```

### 9.4. Funding gap policy

Dùng khi doanh nghiệp vay để tài trợ CAPEX, working capital hoặc thiếu hụt cash.

```text
Pre-financing Cash Flow = CFO - CAPEX - Dividends

Funding Gap = Minimum Cash Balance - Ending Cash Before Financing

Net Borrowing = max(0, Funding Gap)
```

Nếu có tiền dư:

```text
Debt Repayment = min(Excess Cash, Beginning Debt)
```

Đây là policy tốt nhất nếu sau này xây full 3-statement model.

---

## 10. Bước 8 — Dự phóng lãi vay

Không nên tính:

```text
Interest Expense = Revenue × Interest / Revenue
```

vì lãi vay phụ thuộc vào nợ vay, không phụ thuộc trực tiếp vào doanh thu.

Công thức nên dùng:

```text
Average Debt_t = (Beginning Debt_t + Ending Debt_t) / 2

Interest Expense_t = -Average Debt_t × Cost of Debt_t
```

Cost of debt lấy theo thứ tự:

```text
1. Analyst override
2. Historical implied cost of debt median
3. Default sector cost of debt
```

Nếu dùng default, Agent phải hạ confidence và thêm warning.

---

## 11. Bước 9 — Tính PBT, thuế và net income

Sau khi có EBIT và interest expense:

```text
PBT_t = EBIT_t + Interest Expense_t

Tax Expense_t = -max(0, PBT_t × Tax Rate)

Net Income_t = PBT_t + Tax Expense_t
```

Tax rate nên lấy từ `tax_policy.py`. Nếu phải dùng statutory default vì thiếu dữ liệu, forecast phải được đánh dấu là cần analyst review.

---

## 12. Bước 10 — Dự phóng cổ tức

Sau khi có net income forecast, Agent mới được forecast cổ tức.

Công thức:

```text
Cash Dividend_t = Net Income_t × Payout Ratio_t

Retained Earnings Addition_t = Net Income_t - Cash Dividend_t
```

Không nên để `forecasting.py` tự tính retained earnings riêng rồi sau đó lại tạo dividend schedule. Nên để dividend schedule là nguồn duy nhất cho:

```text
payout_ratio
cash_dividend
retained_earnings_addition
```

Policy cổ tức nên chọn theo thứ tự:

```text
1. Manual payout ratio
2. Historical median payout
3. Stable DPS
4. Residual dividend
5. Missing → warning + analyst review
```

### 12.1. Manual payout ratio

```text
Dividend_t = Net Income_t × Manual Payout Ratio
```

### 12.2. Historical median payout

```text
Historical Payout = median(|Dividends Paid| / Net Income)

Dividend_t = Net Income_t × Historical Payout
```

### 12.3. Stable DPS

```text
Dividend per Share_t = Dividend per Share_t-1 × (1 + DPS Growth)

Cash Dividend_t = Dividend per Share_t × Shares Outstanding
```

### 12.4. Residual dividend

```text
Residual Cash = CFO - CAPEX - Required Debt Repayment - Minimum Cash Buffer

Dividend_t = max(0, Residual Cash)
```

---

## 13. Bước 11 — Cập nhật equity và balance sheet

Công thức tối thiểu:

```text
Equity_t = Equity_t-1 + Retained Earnings Addition_t
```

Nếu có phát hành cổ phiếu hoặc mua cổ phiếu quỹ:

```text
Equity_t = Equity_t-1
         + Retained Earnings Addition_t
         + Equity Issuance_t
         - Share Buyback_t
```

Balance sheet tối thiểu nên là:

```text
Total Assets_t = Cash_t + Receivables_t + Inventory_t + Net PPE_t + Other Assets_t

Total Liabilities_t = Debt_t + Payables_t + Other Liabilities_t

Equity_t = Total Assets_t - Total Liabilities_t
```

Nếu chưa xây full balance sheet, Agent vẫn có thể dùng simplified balance sheet, nhưng phải ghi rõ:

```text
Balance sheet is simplified; cash, working capital and PPE are not fully linked.
```

---

## 14. Bước 12 — Tạo ForecastArtifact hoàn chỉnh

`ForecastArtifact` nên chứa đầy đủ:

```text
Forecast P&L
Working capital schedule
CAPEX / depreciation schedule
Debt schedule
Interest schedule
Tax policy
Dividend schedule
Equity schedule
Warnings
Driver methods
Assumption status
Scenario name
Confidence
```

`ForecastYear` nên được mở rộng thêm:

```python
beginning_debt: float | None
ending_debt: float | None
new_borrowing: float | None
debt_repayment: float | None
net_borrowing: float | None
average_debt: float | None
cost_of_debt: float | None

accounts_receivable: float | None
inventory: float | None
accounts_payable: float | None
net_working_capital: float | None
delta_nwc: float | None

payout_ratio: float | None
cash_dividend: float | None
retained_earnings_addition: float | None
```

---

## 15. Bước 13 — Sanity check trước valuation

Trước khi đưa vào FCFF/FCFE, Agent phải kiểm tra:

```text
Revenue growth có vượt cap không?
Gross margin có bất thường không?
EBIT margin có hợp lý không?
CAPEX / Revenue có quá thấp hoặc quá cao không?
ΔNWC có bất thường không?
Debt / EBITDA có vượt ngưỡng không?
Interest coverage có yếu không?
Payout ratio có vượt 100% không?
Dividend có lớn hơn FCFE không?
Equity có âm không?
Shares có thiếu không?
Tax rate có bị default không?
Debt schedule có approved không?
Dividend schedule có approved không?
```

Nếu fail nghiêm trọng, valuation chỉ được là draft.

---

## 16. Bước 14 — Chuyển sang valuation

Sau khi forecast artifact pass sanity check, Agent mới đưa vào:

```text
FCFF valuation
FCFE valuation
Blend valuation
Sensitivity analysis
Approval gate
Confidence score
```

### 16.1. FCFF cần input

```text
EBIT
Tax rate
Depreciation
CAPEX
ΔNWC
WACC
Net debt
Shares
```

Công thức:

```text
FCFF = EBIT(1 - Tax Rate) + Depreciation - CAPEX - ΔNWC
```

### 16.2. FCFE cần input

```text
Net Income
Depreciation
CAPEX
ΔNWC
Net Borrowing
Cost of Equity
Shares
```

Công thức:

```text
FCFE = Net Income + Depreciation - CAPEX - ΔNWC + Net Borrowing
```

FCFE cần `net_borrowing_schedule` từ debt forecast. Nếu không có, không nên mặc định net borrowing bằng 0 mà không warning.

---

## 17. Luồng hoàn chỉnh khuyến nghị

```text
INPUT
↓
Historical fact_table
↓
Data quality validation
↓
Historical driver calculation
↓
Scenario assumption builder
↓
Operating forecast
↓
Working capital forecast
↓
CAPEX & depreciation forecast
↓
Debt schedule forecast
↓
Interest expense forecast
↓
Tax policy
↓
Net income forecast
↓
Dividend schedule forecast
↓
Equity & balance sheet update
↓
ForecastArtifact
↓
Sanity checks
↓
Approval gate: forecast / debt / dividend / tax assumptions
↓
FCFF valuation
↓
FCFE valuation
↓
60/40 DCF blend
↓
Sensitivity analysis
↓
Valuation confidence
↓
Draft / Approved recommendation
```

---

## 18. Rule ngắn gọn để đưa vào Agent

```text
Agent phải dự phóng theo thứ tự:
operating forecast → working capital → CAPEX/depreciation → debt schedule → interest expense → tax → net income → dividend schedule → equity/balance sheet.

Không được tính interest expense theo revenue. Interest expense phải dựa trên average debt × cost of debt.

Không được tự giữ total debt cố định nếu có thể xây debt schedule. Net borrowing forecast phải được xuất ra để dùng trong FCFE.

Không được tự tính retained earnings tách rời dividend_schedule. Cổ tức phải được tính bằng payout policy, sau đó retained earnings từ dividend_schedule phải được dùng để cập nhật equity.

Nếu thiếu dữ liệu nợ vay hoặc cổ tức, Agent phải tạo warning, hạ confidence và chặn khuyến nghị chính thức cho đến khi analyst approve.

Chỉ sau khi ForecastArtifact, DebtSchedule, DividendSchedule và TaxPolicy được tạo và kiểm tra xong, Agent mới được đưa forecast vào FCFF/FCFE/blend valuation.
```

---

## 19. Kết luận

Agent nên xem forecast là một pipeline tài chính có kiểm soát, không phải chỉ là kéo doanh thu theo CAGR. Phần quan trọng nhất trước valuation là làm cho các mắt xích sau liên kết với nhau:

```text
Nợ vay → Lãi vay → PBT → Thuế → Net Income → Cổ tức → Retained Earnings → Equity → FCFE
```

và:

```text
Revenue → Working Capital → CAPEX → FCFF / FCFE
```

Nếu hai chuỗi này chưa được forecast nhất quán, kết quả FCFF, FCFE và target price phía sau có thể bị lệch đáng kể.
