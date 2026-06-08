# Quy trình dự phóng cổ tức và nợ vay cho AI Valuation Agent — Mẫu áp dụng DP3

> **Mục tiêu:** Tài liệu này mô tả cách sửa luồng dự phóng cổ tức và nợ vay để AI agent không còn mặc định “không có cổ tức” hoặc “vay ròng = 0” một cách máy móc. Quy trình được thiết kế cho mô hình định giá cổ phiếu DP3 theo hướng **60% FCFF + 40% FCFE**, đồng thời có thể tái sử dụng cho cổ phiếu dược Việt Nam khác như DHG, TRA, IMP, DBD.

> **Nguồn mẫu sử dụng:** `BCTC DP3.xlsx`, các báo cáo agent trước đó về DHG/TRA, cẩm nang định giá 60% FCFF / 40% FCFE và hướng dẫn sensitivity analysis.

---

## 1. Vấn đề cần giải quyết

Trong các báo cáo định giá trước đó, agent đã cải thiện đáng kể phần CAPEX và sign convention, nhưng vẫn còn vấn đề lớn ở **dự phóng cổ tức** và **nợ vay**. Hai biến này đặc biệt quan trọng với FCFE vì:

```text
FCFE = Net Income + D&A - CAPEX - ΔNWC + Net Borrowing
```

Trong đó:

- **Net Borrowing** ảnh hưởng trực tiếp đến FCFE.
- **Cổ tức không nằm trong công thức FCFE**, nhưng lại ảnh hưởng đến cash balance, retained earnings, equity roll-forward và khả năng duy trì chính sách phân phối lợi nhuận.
- Nếu agent không mô hình hóa cổ tức, vốn chủ sở hữu có thể bị phóng đại vì lợi nhuận giữ lại tăng toàn bộ theo Net Income.
- Nếu agent đặt Net Borrowing = 0 mà không kiểm tra lịch vay/trả nợ, FCFE có thể bị sai đáng kể.

Trong báo cáo TRA, agent đã cảnh báo rằng không có dữ liệu cổ tức nên mô hình giả định zero dividend payout, dẫn đến vốn chủ sở hữu có thể bị overstated. Đây là cảnh báo đúng, nhưng chưa đủ. Agent không nên dừng ở cảnh báo; nó cần một quy trình xử lý thay thế có kiểm soát.

---

## 2. Nguyên tắc định giá liên quan đến cổ tức và nợ vay

### 2.1. FCFF không dùng cổ tức và net borrowing

FCFF là dòng tiền cho toàn bộ doanh nghiệp, thuộc về cả chủ nợ và cổ đông. Công thức chuẩn:

```text
FCFF = EBIT × (1 - Tax Rate) + D&A - CAPEX_positive - ΔNWC
```

Nếu CAPEX lấy từ lưu chuyển tiền tệ và đang là số âm:

```text
FCFF = EBIT × (1 - Tax Rate) + D&A + CAPEX_CFS_signed - ΔNWC
```

FCFF không cộng Net Borrowing và không trừ cổ tức. Sau khi chiết khấu FCFF bằng WACC, mô hình đi từ EV về Equity Value:

```text
Equity Value_FCFF = EV - Net Debt - Minority Interest + Non-operating Assets
```

### 2.2. FCFE cần Net Borrowing nhưng không trừ cổ tức

FCFE là dòng tiền còn lại cho cổ đông sau khi doanh nghiệp đã đầu tư CAPEX, tài trợ vốn lưu động và xử lý vay/trả nợ. Công thức chuẩn:

```text
FCFE = Net Income + D&A - CAPEX_positive - ΔNWC + Net Borrowing
```

Hoặc nếu đi từ CFO:

```text
FCFE = CFO - CAPEX_positive + Net Borrowing
```

Nếu CAPEX trong cash flow là số âm:

```text
FCFE = CFO + CAPEX_CFS_signed + Net Borrowing
```

Cổ tức là **cách sử dụng FCFE**, không phải là thành phần phải trừ thêm trong công thức FCFE. Tuy nhiên, cổ tức phải được đưa vào cash sweep và equity roll-forward:

```text
Cash_end = Cash_begin + CFO + CFI + Net Borrowing - Dividends Paid + Other Financing Flows
```

```text
Equity_end = Equity_begin + Net Income - Dividends Paid + Share Issuance - Share Buyback + OCI/Other Equity Changes
```

---

## 3. Dữ liệu DP3 cần lấy trước khi dự phóng

Agent phải tạo một bảng `Dividend_Debt_Input_Check` trước khi chạy forecast. Với DP3, các dòng cần lấy từ `BCTC DP3.xlsx` gồm:

### 3.1. Dòng tiền cổ tức

Từ báo cáo lưu chuyển tiền tệ, dòng cần lấy là:

```text
Cổ tức, lợi nhuận đã trả cho chủ sở hữu
```

Dữ liệu lịch sử DP3:

| Năm | LNST cổ đông mẹ (tỷ VND) | Cổ tức đã trả (tỷ VND) | Payout ratio |
|---:|---:|---:|---:|
| 2021 | 92.9 | 68.7 | 74.0% |
| 2022 | 108.8 | 51.6 | 47.4% |
| 2023 | 125.3 | 66.3 | 52.9% |
| 2024 | 121.2 | 65.4 | 54.0% |
| 2025 | 156.1 | 62.2 | 39.9% |

Nhận xét:

- DP3 có lịch sử trả cổ tức tiền mặt đều.
- Không được giả định payout = 0 nếu thiếu dòng cổ tức trong một nguồn dữ liệu.
- Payout trung vị 2021–2025 khoảng **52.9%**.
- Payout bình quân theo tổng cổ tức / tổng lợi nhuận khoảng **52.0%**.
- Năm 2021 có payout cao hơn bình thường; năm 2025 thấp hơn do lợi nhuận tăng nhưng cổ tức trả chưa tăng tương ứng.

Vì vậy, nếu không có kế hoạch cổ tức cụ thể, base case hợp lý hơn là payout khoảng **50%–55% LNST**, không phải 0%.

### 3.2. Dữ liệu vay và trả nợ

Từ báo cáo lưu chuyển tiền tệ:

```text
Tiền vay ngắn hạn, dài hạn nhận được
Tiền chi trả nợ gốc vay
```

Từ bảng cân đối kế toán:

```text
Vay và nợ thuê tài chính ngắn hạn
Vay và nợ dài hạn đến hạn phải trả
Vay và nợ thuê tài chính dài hạn
```

Dữ liệu DP3:

| Năm | Debt cuối kỳ (tỷ VND) | Vay mới CFS (tỷ VND) | Trả nợ CFS (tỷ VND) | Net Borrowing CFS (tỷ VND) | ΔDebt BS (tỷ VND) | Chênh lệch cần kiểm tra |
|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 3.5 | 10.2 | 12.1 | -1.9 | — | — |
| 2022 | 5.2 | 16.1 | 14.4 | 1.7 | 1.7 | 0.0 |
| 2023 | 7.8 | 15.1 | 12.6 | 2.5 | 2.5 | 0.0 |
| 2024 | 0.0 | 10.7 | 18.5 | -7.8 | -7.8 | 0.0 |
| 2025 | 34.3 | 0.0 | 56.9 | -56.9 | 34.3 | 91.2 |

Nhận xét quan trọng:

- Giai đoạn 2022–2024, ΔDebt trên bảng cân đối khớp khá tốt với Net Borrowing từ lưu chuyển tiền tệ.
- Năm 2025 có dấu hiệu **DebtFlowMismatch**: Debt cuối kỳ tăng lên 34.3 tỷ VND, trong khi cash flow ghi trả nợ 56.9 tỷ VND và không ghi vay mới. Chênh lệch cần kiểm tra khoảng 91.2 tỷ VND.
- Agent không được tự động coi Net Borrowing 2025 là số đúng tuyệt đối nếu reconciliation fail.
- Nếu không giải thích được chênh lệch, FCFE dựa trên Net Borrowing phải bị hạ confidence.

### 3.3. Tiền và đầu tư tài chính ngắn hạn

DP3 có lượng tiền và đầu tư tài chính ngắn hạn lớn:

| Năm | Cash + Đầu tư ngắn hạn (tỷ VND) | Tỷ lệ trên doanh thu thuần |
|---:|---:|---:|
| 2021 | 161.7 | 42.4% |
| 2022 | 206.5 | 42.6% |
| 2023 | 306.4 | 74.8% |
| 2024 | 341.7 | 81.8% |
| 2025 | 475.5 | 108.6% |

Nhận xét:

- DP3 là doanh nghiệp có vị thế **net cash / treasury assets rất mạnh**.
- Khi dự phóng cổ tức, không chỉ nhìn CFO hoặc FCFE từng năm, mà còn phải kiểm tra lượng cash + short-term investments có thể hỗ trợ cổ tức.
- Khi dự phóng nợ vay, không nên tự động vay thêm nếu doanh nghiệp còn lượng đầu tư ngắn hạn rất lớn, trừ khi đó là tiền gửi bị ràng buộc hoặc có chính sách tài chính riêng.

---

## 4. Quy trình dự phóng cổ tức cho DP3

### 4.1. Không được giả định cổ tức bằng 0 khi thiếu dữ liệu

Nếu dòng `dividends_paid.total` bị thiếu, agent phải làm theo thứ tự:

```text
Bước 1: Tìm trong cash flow statement dòng "Cổ tức, lợi nhuận đã trả cho chủ sở hữu".
Bước 2: Nếu chưa có, tìm trong thuyết minh BCTC hoặc báo cáo thường niên.
Bước 3: Nếu vẫn chưa có, tìm nghị quyết ĐHĐCĐ / HĐQT về phân phối lợi nhuận.
Bước 4: Nếu vẫn thiếu, dùng payout ratio lịch sử hoặc payout peer group, nhưng phải gắn cảnh báo.
Bước 5: Tuyệt đối không mặc định payout = 0 nếu doanh nghiệp có lịch sử trả cổ tức đều.
```

### 4.2. Công thức payout lịch sử

```text
Dividend_Payout_Ratio_t = ABS(Dividends_Paid_t) / Net_Income_Parent_t
```

```text
DPS_t = ABS(Dividends_Paid_t) / Weighted_Average_Shares_t
```

```text
Dividend_Yield_t = DPS_t / Market_Price_t
```

Đối với DP3, base case có thể lấy:

```text
Normalized Payout Ratio = Median(Payout Ratio 2021–2025)
```

Hoặc thận trọng hơn:

```text
Normalized Payout Ratio = Median(Payout Ratio 2022–2025)
```

Với DP3, khoảng hợp lý nên kiểm tra:

| Kịch bản | Payout ratio gợi ý | Khi nào dùng |
|---|---:|---|
| Bear / Expansion CAPEX | 35%–40% | Khi CAPEX tăng, dòng tiền yếu hoặc công ty giữ tiền cho dự án. |
| Base | 50%–55% | Khi công ty duy trì chính sách cổ tức tiền mặt đều. |
| Bull / Cash-rich | 60%–65% | Khi công ty dư tiền, net cash cao, không có dự án CAPEX lớn. |
| Special dividend | >65% | Chỉ dùng nếu có nghị quyết hoặc tiền mặt dư thừa rõ ràng. |

### 4.3. Công thức cổ tức dự phóng

Base case:

```text
Dividends_Paid_t = Net_Income_Parent_t × Target_Payout_Ratio_t
```

Có giới hạn an toàn:

```text
Dividends_Paid_t = MIN(
    Net_Income_Parent_t × Target_Payout_Ratio_t,
    Dividend_Capacity_t
)
```

Trong đó:

```text
Dividend_Capacity_t = MAX(0, Liquidity_Before_Dividend_t - Minimum_Liquidity_t - Required_Debt_Repayment_t)
```

Với doanh nghiệp có nhiều đầu tư ngắn hạn như DP3:

```text
Liquidity_Before_Dividend_t = Cash_begin_t + Short_Term_Investments_begin_t + CFO_t + Interest_Income_After_Tax_t - CAPEX_positive_t
```

Minimum liquidity có thể lấy theo một trong ba cách:

```text
Minimum_Cash_t = MAX(
    2% × Revenue_t,
    1 tháng Cash Operating Expense_t,
    Historical Minimum Cash / Revenue × Revenue_t
)
```

Nếu mô hình tách tiền mặt và đầu tư ngắn hạn:

```text
Minimum_Liquidity_t = Minimum_Cash_t + Required_Strategic_STI_t
```

### 4.4. Cổ tức và retained earnings

Cổ tức phải được trừ khỏi lợi nhuận giữ lại:

```text
Retained_Earnings_end_t = Retained_Earnings_begin_t + Net_Income_t - Dividends_Paid_t - Reserve_Appropriation_t + Other_Adjustments_t
```

Với doanh nghiệp Việt Nam, cần chú ý các khoản phân phối lợi nhuận vào quỹ:

```text
Quỹ đầu tư phát triển
Quỹ khen thưởng phúc lợi
Các quỹ khác thuộc vốn chủ sở hữu
```

Reserve transfer có thể không làm thay đổi tổng vốn chủ nếu chỉ chuyển giữa các cấu phần vốn chủ. Tuy nhiên, nếu chuyển sang quỹ khen thưởng phúc lợi nằm ở nợ phải trả, nó có thể làm giảm vốn chủ và tạo nghĩa vụ chi tiền sau này.

Agent phải có bảng kiểm tra:

```text
Opening Retained Earnings
+ Net Income
- Dividends Paid
- Appropriation to Funds
+/- Other Adjustments
= Ending Retained Earnings
```

Nếu không khớp, sinh cảnh báo:

```text
RetainedEarningsRollforwardMismatch
```

---

## 5. Quy trình dự phóng nợ vay cho DP3

### 5.1. Phân biệt nợ vay chịu lãi và nợ phải trả

Không dùng tổng nợ phải trả để tính debt schedule. Chỉ dùng nợ vay chịu lãi:

```text
Interest_Bearing_Debt = Short_Term_Debt + Current_Portion_of_Long_Term_Debt + Long_Term_Debt + Lease_Liabilities
```

Không đưa các khoản sau vào nợ vay chịu lãi:

```text
Phải trả người bán
Người mua trả tiền trước
Thuế phải nộp
Lương phải trả
Chi phí phải trả
Quỹ khen thưởng phúc lợi
```

### 5.2. Debt roll-forward lịch sử

Agent phải kiểm tra debt reconciliation trước khi dự phóng:

```text
Debt_BS_Change_t = Ending_Interest_Bearing_Debt_t - Beginning_Interest_Bearing_Debt_t
```

```text
Net_Borrowing_CFS_t = Debt_Proceeds_t - Debt_Repayment_t
```

```text
Debt_Reconciliation_Difference_t = Debt_BS_Change_t - Net_Borrowing_CFS_t
```

Điều kiện pass:

```text
ABS(Debt_Reconciliation_Difference_t) <= Tolerance
```

Tolerance gợi ý:

```text
Tolerance = MAX(1 tỷ VND, 2% × Ending Debt_t)
```

Nếu không pass:

```text
Warning = DebtFlowMismatch
FCFE confidence = Low / Needs Analyst Review
Không dùng Net Borrowing lịch sử để train forecast nếu chưa xử lý mismatch.
```

Với DP3, năm 2025 có mismatch lớn nên cần kiểm tra lại dữ liệu vay mới, dòng trả nợ, tái phân loại nợ hoặc mapping dòng tiền.

### 5.3. Dự phóng nợ vay theo cash sweep

Với DP3, do cash + short-term investments rất lớn, debt forecast không nên chỉ đặt bằng 0 hoặc lấy tỷ lệ cứng trên doanh thu. Cần dùng cash sweep:

```text
Liquidity_begin_t = Cash_begin_t + Short_Term_Investments_begin_t
```

```text
Cash_Flow_After_Operations_t = CFO_t - CAPEX_positive_t - Dividends_Paid_t
```

```text
Liquidity_Before_Financing_t = Liquidity_begin_t + Cash_Flow_After_Operations_t
```

```text
Debt_Repayment_Capacity_t = MAX(0, Liquidity_Before_Financing_t - Minimum_Liquidity_t)
```

Nếu doanh nghiệp có nợ đầu kỳ:

```text
Debt_Repayment_t = MIN(Beginning_Debt_t, Debt_Repayment_Capacity_t)
```

Nếu sau khi trả nợ, thanh khoản thấp hơn mức tối thiểu:

```text
New_Borrowing_t = MAX(0, Minimum_Liquidity_t - Liquidity_After_Repayment_t)
```

Nợ cuối kỳ:

```text
Ending_Debt_t = Beginning_Debt_t + New_Borrowing_t - Debt_Repayment_t
```

Vay ròng đưa vào FCFE:

```text
Net_Borrowing_t = New_Borrowing_t - Debt_Repayment_t
```

### 5.4. Dự phóng nợ vay theo target leverage

Nếu analyst muốn dùng target capital structure:

```text
Target_Debt_t = EBITDA_t × Target_Debt_to_EBITDA
```

hoặc:

```text
Target_Debt_t = Revenue_t × Target_Debt_to_Revenue
```

hoặc:

```text
Target_Net_Debt_t = EBITDA_t × Target_Net_Debt_to_EBITDA
```

Với DP3, do doanh nghiệp có net cash lớn, base case nên ưu tiên:

```text
Target_Net_Debt <= 0
```

Tức là công ty không cần vay ròng dài hạn để tài trợ hoạt động bình thường. Nợ ngắn hạn nếu có nên được xem là working-capital revolver hoặc khoản vay mùa vụ, không nên tự động phóng đại thành debt-driven FCFE.

### 5.5. Các kịch bản nợ vay cho DP3

| Kịch bản | Chính sách nợ vay | Cách mô hình hóa |
|---|---|---|
| Base | Net cash, không cần vay ròng dài hạn | Dùng cash/STI để trả nợ hiện hữu; Ending Debt về mức thấp hoặc 0 nếu không có bằng chứng vay mới. |
| Working capital revolver | Duy trì vay ngắn hạn nhỏ | Ending Debt = 1%–2% doanh thu hoặc theo median Debt/Revenue bình thường. |
| Expansion CAPEX | Có dự án đầu tư lớn | Cho phép vay mới nếu CAPEX vượt CFO + thanh khoản dư thừa. |
| Stress | Biên lợi nhuận giảm, NWC tăng | Tăng vay ngắn hạn nếu cash/STI không đủ duy trì minimum liquidity. |

---

## 6. Cách tích hợp cổ tức và nợ vay vào mô hình DP3

### 6.1. Thứ tự forecast nên dùng

Agent nên chạy theo thứ tự sau:

```text
1. Forecast Income Statement
2. Forecast Working Capital
3. Forecast CAPEX and D&A
4. Forecast CFO / operating cash flow
5. Forecast dividend policy
6. Forecast debt schedule
7. Run cash sweep and short-term investment schedule
8. Build FCFF
9. Build FCFE
10. Run valuation 60% FCFF + 40% FCFE
11. Run sensitivity and QA gates
```

Không nên tính FCFE trước khi có debt schedule. Không nên forecast equity trước khi có dividend schedule.

### 6.2. Cash sweep đầy đủ

Một cash sweep tối thiểu nên có các dòng:

```text
Beginning Cash
+ CFO
- CAPEX_positive
- Dividends Paid
+ New Borrowing
- Debt Repayment
+/- Net Short-term Investment Withdrawal / Purchase
= Ending Cash
```

Vì DP3 có đầu tư tài chính ngắn hạn rất lớn, nên short-term investments không nên để trôi tự do hoặc bị nhầm với CAPEX. Nên tách riêng:

```text
Operating Cash = cash cần cho vận hành
Treasury Cash / Short-term Investments = tiền nhàn rỗi hoặc tiền gửi kỳ hạn
```

Công thức phân bổ:

```text
If Liquidity_surplus > 0:
    Repay debt first if debt cost > after-tax treasury yield
    Then allocate surplus to short-term investments
```

```text
If Liquidity_deficit > 0:
    Withdraw short-term investments first
    Then draw debt if still below minimum cash
```

### 6.3. FCFE valuation không được double count cổ tức

Trong valuation:

```text
Price_FCFE = PV(FCFE forecast + Terminal Value) / Shares
```

Không dùng:

```text
FCFE_after_dividend = FCFE - Dividends
```

vì điều này sẽ biến FCFE thành dòng tiền còn lại sau khi đã trả cho cổ đông, làm sai ý nghĩa định giá. Cổ tức chỉ dùng để:

- kiểm tra khả năng phân phối lợi nhuận;
- roll-forward cash và equity;
- xây DDM nếu dùng thêm phương pháp dividend discount;
- kiểm tra dividend yield và investor return.

---

## 7. Mẫu bảng forecast cần thêm vào Excel / AI agent

### 7.1. Sheet `Dividend_Schedule`

| Dòng | Công thức |
|---|---|
| Net Income | Link từ Forecast_IS |
| Historical payout | ABS(Dividends Paid) / Net Income |
| Target payout | Assumption theo scenario |
| Regular dividends | Net Income × Target payout |
| Dividend capacity | MAX(0, Liquidity Before Dividend - Minimum Liquidity - Required Debt Repayment) |
| Dividends paid | MIN(Regular dividends, Dividend capacity) |
| DPS | Dividends paid / Shares |
| Dividend yield | DPS / Current price |
| Retention ratio | 1 - Dividends paid / Net Income |

### 7.2. Sheet `Debt_Schedule`

| Dòng | Công thức |
|---|---|
| Beginning debt | Prior year ending debt |
| Scheduled repayment | Theo maturity hoặc assumption |
| Cash available for repayment | MAX(0, Liquidity Before Financing - Minimum Liquidity) |
| Debt repayment | MIN(Beginning debt, Scheduled repayment + Cash available for repayment) |
| New borrowing | MAX(0, Minimum Liquidity - Liquidity After Repayment) |
| Ending debt | Beginning debt + New borrowing - Debt repayment |
| Net borrowing | New borrowing - Debt repayment |
| Average debt | (Beginning debt + Ending debt) / 2 |
| Interest expense | Average debt × Cost of debt |
| Debt/EBITDA | Ending debt / EBITDA |
| Net debt/EBITDA | (Ending debt - Cash - STI) / EBITDA |

### 7.3. Sheet `Cash_Sweep`

| Dòng | Công thức |
|---|---|
| Beginning cash | Prior year ending cash |
| Beginning short-term investments | Prior year STI |
| CFO | Link từ cash flow forecast |
| CAPEX | Link từ capex forecast |
| Dividends paid | Link từ Dividend_Schedule |
| Net borrowing | Link từ Debt_Schedule |
| Minimum cash | MAX(2% Revenue, 1 month cash opex) |
| Ending cash before STI | Beginning cash + CFO - CAPEX - Dividends + Net borrowing |
| Excess cash | MAX(0, Ending cash before STI - Minimum cash) |
| STI purchase / withdrawal | Balancing item |
| Ending cash | Minimum cash hoặc actual policy cash |
| Ending liquidity | Ending cash + Ending STI |

### 7.4. Sheet `FCFE_Check`

| Dòng | Công thức |
|---|---|
| FCFE from NI | NI + D&A - CAPEX - ΔNWC + Net Borrowing |
| FCFE from CFO | CFO - CAPEX + Net Borrowing |
| Difference | FCFE from NI - FCFE from CFO |
| Dividend coverage | FCFE before dividends / Dividends paid |
| Warning | Nếu coverage < 1 hoặc difference lớn |

---

## 8. QA gates bắt buộc cho AI agent

### 8.1. Gate cổ tức

| Check | Điều kiện fail | Hành động |
|---|---|---|
| Missing dividends | Không tìm thấy dòng cổ tức nhưng doanh nghiệp có lịch sử payout | Không mặc định 0; dùng proxy payout và gắn warning. |
| Payout outlier | Payout > 100% hoặc < 10% bất thường | Cần giải thích hoặc normalize. |
| Dividend unfunded | Dividends > dividend capacity | Giảm payout hoặc yêu cầu analyst approval. |
| Equity overstated | Equity tăng bằng toàn bộ NI dù có cổ tức | Fail balance sheet forecast. |
| Retained earnings mismatch | RE roll-forward không khớp | Tạo warning và không publish valuation final. |

### 8.2. Gate nợ vay

| Check | Điều kiện fail | Hành động |
|---|---|---|
| Debt flow mismatch | ΔDebt BS không khớp Net Borrowing CFS | Không dùng Net Borrowing cho FCFE nếu chưa giải thích. |
| Debt assumed zero | Agent đặt debt = 0 dù lịch sử có nợ | Cần policy giải thích. |
| New borrowing unsupported | Vay mới xuất hiện nhưng không có financing need | Gắn warning. |
| Interest mismatch | Interest expense không khớp average debt × cost of debt | Cần sửa cost of debt hoặc debt schedule. |
| Net debt wrong | Không trừ cash/STI khi tính net debt | Fail valuation bridge. |

### 8.3. Gate FCFE

| Check | Điều kiện fail | Hành động |
|---|---|---|
| Net borrowing missing | FCFE dùng Net Borrowing = 0 mà không có giải thích | Hạ confidence FCFE. |
| FCFE volatility | FCFE đổi dấu do vay/trả nợ bất thường | Dùng normalized FCFE terminal year. |
| FCFF/FCFE gap | Chênh lệch Price_FCFF và Price_FCFE > 25% | Audit CAPEX, NWC, Net Borrowing. |
| Dividend coverage < 1 | Cổ tức vượt FCFE nhiều năm | Kiểm tra nguồn tiền từ STI hoặc giảm payout. |
| Terminal FCFE distorted | Năm cuối có vay/trả nợ bất thường | Normalize Net Borrowing về target leverage. |

---

## 9. Sensitivity cần thêm cho cổ tức và nợ vay

Agent không nên chỉ chạy sensitivity WACC/g hoặc Price_FCFF × Price_FCFE. Với cổ tức và nợ vay, cần thêm:

### 9.1. Payout ratio sensitivity

| Payout ratio | Ý nghĩa |
|---:|---|
| 35% | Công ty giữ tiền cho CAPEX hoặc chu kỳ khó khăn. |
| 45% | Thận trọng nhưng vẫn có cổ tức. |
| 55% | Base case cho DP3 nếu duy trì lịch sử. |
| 65% | Cash-rich case. |

Đầu ra cần kiểm tra:

```text
Ending cash
Ending short-term investments
Dividend coverage
Equity value per share
Dividend yield
```

### 9.2. Debt policy sensitivity

| Chính sách debt | Ý nghĩa |
|---|---|
| Debt = 0 | Công ty dùng tiền và STI để trả hết nợ. |
| Debt/Revenue = 1% | Working capital revolver nhỏ. |
| Debt/Revenue = 3% | Duy trì vay ngắn hạn mùa vụ. |
| Debt/EBITDA = 0.5x | Expansion/stress case. |

Đầu ra cần kiểm tra:

```text
Net Borrowing
FCFE
Interest expense
Net debt/EBITDA
FCFF/FCFE gap
```

### 9.3. Combined payout × debt sensitivity

Bảng nên có dạng:

```text
Rows: payout ratio 35% / 45% / 55% / 65%
Columns: debt policy Debt=0 / Debt=1% revenue / Debt=3% revenue / Debt=0.5x EBITDA
Output: Price_FCFE hoặc Target Price_DCF
```

Nếu target price thay đổi mạnh chỉ vì debt policy, agent phải kết luận:

```text
FCFE valuation is financing-policy sensitive; FCFF should receive higher confidence until debt schedule is validated.
```

---

## 10. Pseudocode cho AI agent

```python
for year in forecast_years:
    revenue = forecast_revenue(year)
    ebit = forecast_ebit(year)
    tax_rate = forecast_tax_rate(year)
    ni = forecast_net_income(year)
    da = forecast_depreciation(year)
    capex = forecast_capex_positive(year)
    nwc = forecast_operating_nwc(year)
    delta_nwc = nwc - prior_nwc

    # 1. Dividend policy
    target_payout = scenario_payout_ratio(year)
    regular_dividend = ni * target_payout

    liquidity_before_dividend = cash_begin + short_term_investments_begin + cfo - capex
    minimum_liquidity = max(0.02 * revenue, one_month_cash_opex)
    required_debt_repayment = scheduled_debt_repayment(year)
    dividend_capacity = max(0, liquidity_before_dividend - minimum_liquidity - required_debt_repayment)
    dividends_paid = min(regular_dividend, dividend_capacity)

    # 2. Debt schedule and cash sweep
    liquidity_before_financing = liquidity_before_dividend - dividends_paid
    cash_available_for_repayment = max(0, liquidity_before_financing - minimum_liquidity)
    debt_repayment = min(beginning_debt, required_debt_repayment + cash_available_for_repayment)
    liquidity_after_repayment = liquidity_before_financing - debt_repayment
    new_borrowing = max(0, minimum_liquidity - liquidity_after_repayment)
    ending_debt = beginning_debt + new_borrowing - debt_repayment
    net_borrowing = new_borrowing - debt_repayment

    # 3. FCFF and FCFE
    fcff = ebit * (1 - tax_rate) + da - capex - delta_nwc
    fcfe = ni + da - capex - delta_nwc + net_borrowing

    # 4. Roll-forward statements
    retained_earnings_end = retained_earnings_begin + ni - dividends_paid - reserve_appropriation
    equity_end = equity_begin + ni - dividends_paid + share_issuance - share_buybacks + other_equity_changes
    cash_end, short_term_investments_end = allocate_liquidity(liquidity_after_repayment + new_borrowing, minimum_liquidity)

    # 5. QA checks
    assert capex >= 0
    create_warning_if(dividends_paid > dividend_capacity, "DividendUnfunded")
    create_warning_if(abs((ending_debt - beginning_debt) - net_borrowing) > tolerance, "DebtRollforwardMismatch")
    create_warning_if(fcfe_terminal_year_distorted, "TerminalFCFENotNormalized")
```

---

## 11. Cách áp dụng vào mô hình định giá DP3 60% FCFF / 40% FCFE

### 11.1. FCFF DCF

FCFF vẫn là phần chính, trọng số 60%:

```text
Price_FCFF = Equity Value_FCFF / Diluted Shares
```

```text
Equity Value_FCFF = EV_FCFF - Net Debt + Non-operating Assets - Minority Interest
```

Với DP3, cần chú ý Net Debt phải tính sau khi trừ:

```text
Cash + Short-term Investments
```

Vì DP3 có đầu tư ngắn hạn rất lớn, nếu chỉ trừ cash mà bỏ qua STI thì equity value theo FCFF sẽ bị thấp hơn thực tế.

### 11.2. FCFE DCF

FCFE trọng số 40%:

```text
Price_FCFE = Equity Value_FCFE / Diluted Shares
```

```text
Equity Value_FCFE = PV(FCFE forecast) + PV(Terminal Value FCFE)
```

Điểm cần sửa so với mô hình hiện tại:

- Không dùng Net Borrowing tùy ý hoặc hardcoded.
- Không đặt Net Borrowing = 0 nếu không có debt schedule.
- Không để năm terminal có vay/trả nợ bất thường.
- Nếu debt reconciliation fail, vẫn có thể trình bày FCFE nhưng phải giảm confidence.

### 11.3. Blend valuation

```text
Target Price_DCF = 0.60 × Price_FCFF + 0.40 × Price_FCFE
```

Nếu FCFE confidence bị hạ vì nợ vay chưa kiểm định, agent có hai lựa chọn:

```text
Cách 1: Giữ 60/40 nhưng gắn warning "FCFE requires debt schedule validation".
Cách 2: Tạm thời dùng 70/30 hoặc 80/20 trong bản draft, nhưng chỉ khi analyst phê duyệt thay đổi trọng số.
```

Vì user đã chọn chuẩn 60/40, khuyến nghị là **giữ 60/40 trong báo cáo**, nhưng thêm confidence score cho từng thành phần.

---

## 12. Mẫu warning messages cho agent

```text
DividendDataMissing:
Không tìm thấy dòng cổ tức đã trả. Không được giả định payout = 0 nếu doanh nghiệp có lịch sử trả cổ tức. Hãy dùng payout lịch sử hoặc yêu cầu dữ liệu bổ sung.
```

```text
DividendPayoutNormalized:
Payout lịch sử biến động mạnh. Mô hình dùng normalized payout thay vì năm gần nhất.
```

```text
DebtFlowMismatch:
Thay đổi nợ vay trên bảng cân đối không khớp vay ròng trên lưu chuyển tiền tệ. Net Borrowing cần kiểm tra thủ công trước khi dùng trong FCFE.
```

```text
NetBorrowingApproximated:
Không có dữ liệu vay mới/trả gốc chi tiết. Net Borrowing được xấp xỉ bằng thay đổi nợ vay chịu lãi.
```

```text
EquityMayBeOverstated:
Mô hình chưa trừ cổ tức khỏi vốn chủ sở hữu. Vốn chủ dự phóng có thể bị phóng đại.
```

```text
TerminalFCFENotNormalized:
FCFE năm cuối bị ảnh hưởng bởi vay/trả nợ bất thường. Cần normalize Net Borrowing trong terminal year.
```

---

## 13. Checklist triển khai cho Agent

Trước khi xuất báo cáo DP3, agent phải trả lời được các câu hỏi sau:

| Nhóm | Câu hỏi | Pass khi nào? |
|---|---|---|
| Cổ tức | Có dòng cổ tức đã trả không? | Có dữ liệu CFS hoặc proxy payout hợp lý. |
| Cổ tức | Payout forecast có dựa trên lịch sử/nghị quyết không? | Có target payout theo scenario. |
| Cổ tức | Cổ tức có trừ khỏi retained earnings không? | RE roll-forward khớp. |
| Cổ tức | Cổ tức có làm cash âm không? | Cash/STI sau cổ tức vẫn trên minimum liquidity. |
| Nợ vay | Debt BS có khớp CFS vay/trả nợ không? | Sai lệch dưới tolerance. |
| Nợ vay | Net Borrowing có nguồn không? | Lấy từ CFS hoặc debt schedule. |
| Nợ vay | Interest expense có khớp average debt × Rd không? | Sai lệch giải thích được. |
| FCFE | FCFE có cộng Net Borrowing đúng chưa? | Có debt schedule. |
| FCFE | Terminal FCFE có normalized không? | Không có vay/trả nợ bất thường. |
| Valuation | FCFF/FCFE gap có vượt 25% không? | Nếu vượt, không publish final. |

---

## 14. Kết luận áp dụng cho DP3

Với DP3, vấn đề lớn không phải là thiếu dữ liệu cổ tức. Trái lại, DP3 có lịch sử trả cổ tức tiền mặt khá rõ ràng trong cash flow statement. Vì vậy, nếu agent không tìm thấy `dividends_paid.total`, nó phải xem đó là lỗi mapping taxonomy, không phải bằng chứng rằng doanh nghiệp không trả cổ tức.

Đối với cổ tức, base case nên dùng payout chuẩn hóa khoảng **50%–55% LNST**, sau đó kiểm tra bằng dividend capacity dựa trên cash + short-term investments. Với lượng đầu tư tài chính ngắn hạn rất lớn, DP3 có khả năng duy trì cổ tức ngay cả khi CAPEX hoặc working capital biến động, nhưng vẫn phải giữ minimum liquidity và không làm méo cash forecast.

Đối với nợ vay, DP3 nhìn chung có đòn bẩy thấp và vị thế net cash. Tuy nhiên, năm 2025 có dấu hiệu không khớp giữa thay đổi debt trên bảng cân đối và vay/trả nợ trên lưu chuyển tiền tệ. Agent phải tạo cảnh báo `DebtFlowMismatch` và không nên dùng Net Borrowing 2025 để train forecast nếu chưa kiểm tra lại nguồn. Base case nên dùng cash sweep: dùng tiền và đầu tư ngắn hạn để trả nợ hiện hữu nếu không có nhu cầu vay vốn lưu động hoặc CAPEX mở rộng.

Trong định giá, FCFF vẫn nên là phương pháp chính 60%, FCFE giữ vai trò 40% nhưng phải đi kèm debt schedule và dividend schedule. Nếu debt schedule chưa qua kiểm định, FCFE vẫn có thể trình bày nhưng phải hạ confidence và không được để FCFE làm phóng đại target price.

Nguyên tắc cuối cùng cho agent:

```text
Không có dữ liệu cổ tức ≠ không trả cổ tức.
Không có dữ liệu vay mới ≠ Net Borrowing = 0.
FCFE không đáng tin nếu chưa có debt schedule.
Vốn chủ dự phóng không đáng tin nếu chưa trừ cổ tức.
```
