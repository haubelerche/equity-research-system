# Gợi ý sửa `forecasting.py`: Driver-Based Forecasting cho nợ vay, cổ tức và kịch bản

## 1. Mục tiêu sửa đổi

`forecasting.py` hiện mới dừng ở mức dự phóng đơn giản: doanh thu tăng theo CAGR, các dòng chi phí đi theo tỷ lệ doanh thu, sau đó bảng cân đối được tạo bằng equity waterfall. Cách này có thể dùng cho bản nháp, nhưng chưa đủ chắc để làm valuation chính thức vì nợ vay, cổ tức, vốn lưu động và chi phí lãi vay chưa được dự phóng bằng driver riêng.

Mục tiêu sửa đổi là biến `debt_schedule.py` và `dividend_schedule.py` thành các driver chính thức của forecast, thay vì chỉ là bảng phụ trình bày. Agent không được tự đoán nợ vay hoặc cổ tức bằng LLM, mà phải sử dụng dữ liệu lịch sử, công thức deterministic và assumption được khai báo rõ ràng.

Luồng forecast nên chuyển từ:

```text
Revenue forecast
→ Margin forecast
→ Equity waterfall đơn giản
```

sang:

```text
Operating forecast
→ Debt schedule
→ Interest expense
→ Net income
→ Dividend schedule
→ Retained earnings
→ Equity
→ FCFF / FCFE
→ Blend valuation
→ Approval gate
```

---

## 2. Nguyên tắc chung cho Agent

Agent phải tuân thủ các nguyên tắc sau:

1. Không được giữ nợ vay cố định mặc định trong toàn bộ kỳ forecast nếu chưa có lý do.
2. Không được tính lãi vay theo tỷ lệ doanh thu.
3. Không được tự tính retained earnings riêng nếu đã có `dividend_schedule.py`.
4. Không được mặc định cổ tức bằng 0 khi thiếu dữ liệu mà không cảnh báo.
5. Không được xuất BUY/HOLD/SELL nếu debt schedule hoặc dividend schedule chưa được approve.
6. Mọi giả định về nợ vay, lãi suất, payout ratio và kịch bản phải có method, confidence và warning nếu dùng fallback.

---

## 3. Dự phóng nợ vay theo driver-based forecasting

### 3.1. Công thức roll-forward nợ vay

Agent nên dự phóng nợ vay bằng debt roll-forward:

```text
Beginning Debt
+ New Borrowing
- Debt Repayment
= Ending Debt
```

Hoặc dạng rút gọn:

```text
Ending Debt = Beginning Debt + Net Borrowing
```

Trong đó:

```text
Net Borrowing = New Borrowing - Debt Repayment
```

Kết quả `net_borrowing` phải được xuất ra để `fcfe.py` dùng trực tiếp trong công thức:

```text
FCFE = Net Income + D&A - CAPEX - ΔNWC + Net Borrowing
```

---

### 3.2. Thứ tự ưu tiên chọn phương pháp dự phóng nợ vay

Agent nên chọn phương pháp dự phóng nợ vay theo thứ tự ưu tiên sau:

```text
1. manual_override
2. direct_cash_flow
3. target_debt_ratio
4. balance_sheet_delta
5. zero_debt_policy
6. missing
```

Nếu analyst nhập kế hoạch vay hoặc trả nợ cụ thể, Agent dùng `manual_override`. Đây là nguồn ưu tiên cao nhất.

Nếu có dữ liệu từ báo cáo lưu chuyển tiền tệ, Agent dùng:

```text
Net Borrowing = Proceeds from Borrowings - Repayment of Borrowings
```

Nếu không có dữ liệu vay/trả nợ trực tiếp, Agent có thể dùng thay đổi dư nợ trên bảng cân đối:

```text
Net Borrowing ≈ Ending Debt_t - Ending Debt_t-1
```

Tuy nhiên, phương pháp này phải có confidence thấp hơn vì thay đổi nợ trên bảng cân đối có thể bao gồm tái phân loại, điều chỉnh tỷ giá hoặc sai lệch kế toán.

---

### 3.3. Driver nên thêm vào `ForecastAssumptions`

Nên bổ sung các trường sau vào `ForecastAssumptions`:

```python
target_debt_to_assets: float | None = None
target_debt_to_equity: float | None = None
target_debt_to_ebitda: float | None = None
min_cash_balance: float | None = None
cost_of_debt_override: float | None = None
net_borrowing_schedule_override: dict[str, float] | None = None
debt_policy: str = "stable_leverage"
```

Các trường này giúp Agent chọn chính sách nợ vay theo từng doanh nghiệp thay vì giữ nợ cố định.

---

### 3.4. Các chính sách nợ vay nên hỗ trợ

#### Chính sách 1: `zero_debt_policy`

Dùng cho doanh nghiệp gần như không vay nợ hoặc có định hướng trả hết nợ.

```text
Ending Debt = 0
Net Borrowing = -Beginning Debt nếu còn nợ
Interest Expense = 0 sau khi hết nợ
```

#### Chính sách 2: `stable_debt`

Dùng khi doanh nghiệp duy trì dư nợ ổn định.

```text
Ending Debt = Beginning Debt
Net Borrowing = 0
Interest Expense = -Average Debt × Cost of Debt
```

Chính sách này có thể dùng cho base case nếu lịch sử nợ vay ổn định, nhưng phải ghi rõ là giả định ổn định, không phải kết luận chắc chắn.

#### Chính sách 3: `target_debt_ratio`

Dùng khi nợ vay đi theo quy mô doanh nghiệp.

Ví dụ theo EBITDA:

```text
Target Debt = Target Debt / EBITDA × EBITDA
Net Borrowing = Target Debt - Beginning Debt
```

Hoặc theo tài sản:

```text
Target Debt = Target Debt / Assets × Total Assets
Net Borrowing = Target Debt - Beginning Debt
```

#### Chính sách 4: `funding_gap`

Dùng khi doanh nghiệp vay để tài trợ CAPEX, vốn lưu động hoặc thiếu hụt tiền mặt.

```text
Pre-financing Cash Flow = CFO - CAPEX - Dividends
Funding Gap = Minimum Cash Balance - Ending Cash Before Financing
Net Borrowing = max(0, Funding Gap)
```

Nếu có tiền dư:

```text
Debt Repayment = min(Excess Cash, Beginning Debt)
```

Đây là logic tốt nhất nếu sau này hệ thống phát triển thành full 3-statement model.

---

## 4. Dự phóng lãi vay

Lãi vay không nên forecast theo doanh thu. Logic hiện tại kiểu:

```text
Interest Expense = -Revenue × Interest / Revenue
```

là chưa đúng bản chất tài chính. Lãi vay phải phụ thuộc vào dư nợ và chi phí nợ vay.

Công thức nên sửa thành:

```text
Average Debt = (Beginning Debt + Ending Debt) / 2
Interest Expense = -Average Debt × Cost of Debt
```

`Cost of Debt` nên được lấy theo thứ tự:

```text
1. analyst override
2. historical median implied cost of debt
3. sector/default cost of debt
```

Nếu dùng default, Agent phải warning và hạ confidence.

---

## 5. Dự phóng cổ tức theo driver-based forecasting

### 5.1. Nguyên tắc

Cổ tức nên được forecast bằng payout policy. `forecasting.py` không nên tự tính retained earnings riêng trong vòng lặp nếu sau đó lại gọi `build_dividend_schedule()`.

Quy trình đúng nên là:

```text
Forecast Net Income
→ Build Dividend Schedule
→ Cash Dividend
→ Retained Earnings Addition
→ Update Equity
```

`dividend_schedule.py` đã có sẵn logic:

```text
Payout Ratio = |Dividends Paid| / Net Income
Cash Dividend = Net Income × Payout Ratio
Retained Earnings Addition = Net Income - Cash Dividend
```

Do đó, `forecasting.py` nên dùng `dividend_schedule.retained_earnings_schedule()` để cập nhật equity.

---

### 5.2. Thứ tự ưu tiên chọn chính sách cổ tức

Agent nên chọn dividend policy theo thứ tự sau:

```text
1. manual_payout_ratio
2. historical_median_payout
3. stable_DPS
4. residual_dividend
5. no_dividend_due_to_missing_data
```

#### Chính sách 1: `manual_payout_ratio`

Dùng khi analyst nhập tỷ lệ chi trả cổ tức.

```text
Dividend = Net Income × Manual Payout Ratio
```

#### Chính sách 2: `historical_median_payout`

Dùng khi có dữ liệu cổ tức lịch sử.

```text
Historical Payout = median(|Dividends Paid| / Net Income)
Forecast Dividend = Forecast Net Income × Historical Payout
```

#### Chính sách 3: `stable_DPS`

Dùng với công ty có lịch sử trả cổ tức tiền mặt đều.

```text
Dividend per Share_t = Dividend per Share_t-1 × (1 + DPS Growth)
Cash Dividend = DPS × Shares Outstanding
```

#### Chính sách 4: `residual_dividend`

Dùng khi công ty ưu tiên giữ lại vốn để tái đầu tư trước, sau đó mới chia cổ tức.

```text
Residual Cash = Net Income - Required Retained Earnings
Dividend = max(0, Residual Cash)
```

Hoặc dựa trên cash flow:

```text
Dividend = max(0, CFO - CAPEX - Required Debt Repayment - Minimum Cash Buffer)
```

---

### 5.3. Ràng buộc an toàn cho cổ tức

Agent phải áp dụng các rule kiểm soát sau:

```text
Nếu Net Income <= 0 → Dividend = 0 hoặc cần analyst override.
Nếu Payout Ratio > 100% → cap ở 100% và warning.
Nếu FCFE trước cổ tức âm → không tăng cổ tức.
Nếu Debt/Equity vượt ngưỡng → giảm payout trong bear case.
Nếu thiếu dữ liệu dividends_paid.total → không âm thầm giả định zero dividend.
```

Nếu thiếu dữ liệu cổ tức, Agent nên tạo warning:

```text
Dividend schedule missing — all earnings treated as retained; equity may be overstated.
```

và hạ confidence của forecast.

---

## 6. Mở rộng `ForecastYear`

Để truy vết được nợ vay và cổ tức, nên mở rộng `ForecastYear` với các trường sau:

```python
beginning_debt: float | None
new_borrowing: float | None
debt_repayment: float | None
net_borrowing: float | None
ending_debt: float | None
average_debt: float | None
cost_of_debt: float | None

payout_ratio: float | None
cash_dividend: float | None
retained_earnings_addition: float | None
dividend_policy: str | None
debt_policy: str | None
```

Các trường này giúp báo cáo giải thích rõ: nợ thay đổi ra sao, lãi vay được tính từ đâu, cổ tức bao nhiêu, lợi nhuận giữ lại bao nhiêu và equity tăng vì lý do gì.

---

## 7. Flow chạy forecast nên dùng 2-pass hoặc 3-pass

Vì nợ vay, lãi vay, thuế, net income, cổ tức và equity liên kết với nhau, không nên forecast tất cả trong một pass quá đơn giản.

### Pass 1: Operating forecast

Agent dự phóng:

```text
Revenue
COGS
Gross Profit
SG&A
EBIT
Depreciation
CAPEX
Working Capital
```

### Pass 2: Debt + Interest

Agent dự phóng:

```text
Beginning Debt
Net Borrowing
Ending Debt
Average Debt
Interest Expense
```

### Pass 3: Net Income + Dividend + Equity

Agent tính:

```text
PBT = EBIT + Interest Expense
Tax = PBT × Tax Rate
Net Income = PBT - Tax
Dividend = Net Income × Payout Ratio
Retained Earnings = Net Income - Dividend
Equity_t = Equity_t-1 + Retained Earnings
```

Nếu debt policy phụ thuộc vào equity hoặc cash flow, Agent có thể lặp lại 2–3 vòng để cân bằng.

---

## 8. Thiết kế kịch bản Bear / Base / Bull

Agent không nên chỉ thay đổi WACC và terminal growth. Kịch bản phải thay đổi cả operating drivers, financing policy và dividend policy.

### 8.1. Base case

Base case đại diện cho kịch bản hợp lý nhất.

```text
Revenue growth = historical CAGR đã cap hoặc analyst-approved
Gross margin = historical median
CAPEX / Revenue = historical median
Working capital days = historical median
Debt policy = stable leverage hoặc target debt ratio
Cost of debt = historical implied cost of debt
Dividend payout = historical median payout
```

### 8.2. Bear case

Bear case phản ánh môi trường xấu hơn.

```text
Revenue growth giảm 2–5 điểm %
Gross margin giảm
SG&A / Revenue tăng
CAPEX / Revenue không giảm quá mạnh nếu công ty vẫn phải đầu tư
Working capital xấu đi: DSO tăng, inventory days tăng
Cost of debt tăng 1–2 điểm %
Debt repayment giảm hoặc net borrowing tăng do thiếu cash
Dividend payout giảm hoặc bị cắt nếu FCFE âm
```

Trong bear case, Agent không được tự động tăng cổ tức theo payout lịch sử nếu lợi nhuận hoặc FCFE suy giảm mạnh.

### 8.3. Bull case

Bull case phản ánh vận hành tốt hơn nhưng không nên quá lạc quan.

```text
Revenue growth tăng 2–5 điểm %
Gross margin cải thiện
SG&A / Revenue giảm nhẹ
Working capital cải thiện
Cost of debt giảm nhẹ hoặc giữ nguyên
Net borrowing giảm do cash flow tốt hơn
Debt repayment tăng nếu có excess cash
Dividend payout giữ nguyên hoặc tăng nhẹ, nhưng không vượt cap
```

---

## 9. Scenario riêng cho nợ vay và cổ tức

Ngoài bear/base/bull tổng hợp, Agent nên có scenario phụ cho financing và dividend.

### 9.1. Debt scenarios

```text
Conservative debt:
- Repay debt with excess cash
- No new borrowing unless funding gap exists
- Cost of debt higher

Base debt:
- Maintain target Debt/EBITDA or Debt/Assets
- Net borrowing follows funding gap

Expansion debt:
- Borrow to fund CAPEX/growth
- Higher debt balance
- Higher interest expense
```

### 9.2. Dividend scenarios

```text
Conservative dividend:
- Payout ratio lower than historical
- Cut dividend if FCFE negative

Base dividend:
- Historical median payout

Shareholder-friendly dividend:
- Higher payout or stable DPS
- Only allowed if leverage and cash buffer remain safe
```

### 9.3. Integrated scenarios

```text
Bear = Conservative operating + higher debt cost + conservative dividend
Base = Base operating + stable debt + historical payout
Bull = Strong operating + deleveraging/excess cash + stable or slightly higher payout
```

---

## 10. Approval Gate và Confidence

Agent phải truyền trạng thái nợ vay và cổ tức vào artifact hoặc warnings. Nếu nợ vay chỉ là giả định giữ nguyên, hoặc cổ tức bị giả định bằng 0 do thiếu dữ liệu, valuation chỉ nên được xem là:

```text
Draft / Needs Analyst Review
```

Không nên cho phép xuất:

```text
BUY / HOLD / SELL
```

Các điều kiện chặn nên bao gồm:

```text
Data quality chưa pass
Debt schedule chưa approved
Dividend schedule chưa approved
Tax policy chưa approved
Forecast assumptions chưa approved
Terminal growth chưa approved
Final recommendation chưa approved
```

---

## 11. Prompt mẫu cho Agent/Codex

```text
Hãy sửa forecasting.py để nợ vay và cổ tức được dự phóng theo driver-based forecasting, không giữ nợ cố định và không tự tính retained earnings tách rời dividend_schedule.

Yêu cầu:
1. Tích hợp debt_schedule.py vào run_forecast().
2. Thêm debt_policy, target_debt_to_assets, target_debt_to_ebitda, cost_of_debt_override, net_borrowing_schedule_override vào ForecastAssumptions.
3. Mỗi năm forecast phải có beginning_debt, new_borrowing, debt_repayment, net_borrowing, ending_debt, average_debt, cost_of_debt và interest_expense.
4. Interest expense phải tính bằng -average_debt × cost_of_debt, không được tính theo revenue.
5. Net borrowing forecast phải được xuất ra để fcfe.py dùng trực tiếp.
6. Tích hợp dividend_schedule.py vào forecast flow. Không tự tính retained earnings riêng nếu dividend_schedule đã có retained_earnings_schedule().
7. Thêm dividend_policy, payout_ratio_override, stable_dps_growth, minimum_cash_buffer.
8. Mỗi năm forecast phải có payout_ratio, cash_dividend, retained_earnings_addition.
9. Nếu thiếu dữ liệu nợ vay hoặc cổ tức, phải tạo warning và hạ confidence; không được im lặng giả định là 0.
10. Xây dựng scenario bear/base/bull cho revenue growth, margin, CAPEX/revenue, working capital, cost_of_debt, net_borrowing và payout ratio.
11. Không cho phép BUY/HOLD/SELL nếu debt_schedule_approved hoặc dividend_schedule_approved chưa đạt approval gate.
12. Tất cả công thức phải deterministic Python, không dùng LLM để bịa assumption.
```

---

## 12. Kết luận

Phần forecast nên được sửa theo nguyên tắc:

```text
Nợ vay là driver của interest expense và FCFE.
Cổ tức là driver của retained earnings, equity, BVPS và cash.
```

Không nên để `forecasting.py` giữ nợ cố định hoặc tự tính retained earnings riêng. Debt schedule và dividend schedule phải trở thành input chính thức của forecast và FCFE, đồng thời được đưa vào approval gate trước khi Agent được phép đưa ra khuyến nghị đầu tư.
