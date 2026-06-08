# Core Plan — Fix Debt Schedule / Net Borrowing / FCFE Gate

## 0. Mục tiêu sửa lỗi

Sửa lỗi valuation engine đang tính sai `Net Borrowing` trong FCFE bằng cách ép nợ vay về `historical_median_debt`. Từ nay `Net Borrowing` chỉ được sinh từ debt schedule hoặc cash sweep có kiểm định.

Invariant bắt buộc:

```text
Không có DebtScheduleArtifact approved
→ không có Net Borrowing publishable
→ không có FCFE publishable
→ không có Blend DCF publishable
→ không có recommendation client-facing.
```

---

## 1. Xóa logic sai khỏi valuation path

Tìm và loại bỏ hoàn toàn logic dạng:

```text
target_debt = historical_median_debt
ending_debt = target_debt
net_borrowing = ending_debt - beginning_debt
```

Quy định mới:

- `historical_median_debt` chỉ được dùng làm diagnostic/reference.
- Không được dùng nó để tạo `ending_debt`, `debt_borrowing`, `net_borrowing`, hoặc FCFE publishable.
- Nếu code vẫn dùng median debt trong publishable path thì phải raise blocking error.

---

## 2. Chuẩn hóa khái niệm Interest-bearing Debt

Không dùng tổng nợ phải trả để tính debt schedule.

```text
Interest-bearing Debt =
Short-term Borrowings
+ Current Portion of Long-term Debt
+ Long-term Borrowings
+ Finance Lease Liabilities
```

Không bao gồm phải trả người bán, thuế phải nộp, chi phí phải trả, người mua trả trước, doanh thu chưa thực hiện, và các khoản nợ vận hành khác.

---

## 3. Implement DebtScheduleArtifact

Tạo artifact riêng cho debt schedule, tối thiểu có các field theo từng năm:

```text
Beginning Debt
New Borrowing
Mandatory Debt Repayment
Optional Debt Repayment
Debt Repayment
Ending Debt
Net Borrowing
Average Debt
Cost of Debt
Interest Expense
Confidence
Status
```

Công thức bắt buộc:

```text
Beginning Debt_t = Ending Debt_t-1
Ending Debt_t = Beginning Debt_t + New Borrowing_t - Debt Repayment_t
Net Borrowing_t = New Borrowing_t - Debt Repayment_t
Average Debt_t = (Beginning Debt_t + Ending Debt_t) / 2
Interest Expense_t = Average Debt_t × Cost of Debt_t
```

Status rule:

```text
approved: có source/analyst approval đầy đủ
high: có CFS hoặc maturity schedule rõ
medium: model bằng cash sweep nhưng chưa approved
low: thiếu dữ liệu quan trọng
blocked: không đủ dữ liệu để tính FCFE
```

---

## 4. Implement CashSweepArtifact

`Net Borrowing` không forecast trực tiếp. Nó phải là kết quả của cash sweep.

Cash sweep tối thiểu cần:

```text
Beginning Cash
CFO
CAPEX_positive
Dividends Paid
Equity Issuance
Share Buyback
Asset Disposal Proceeds
Acquisitions
Other Non-debt Cash Flows
Pre-financing Cash
Minimum Cash
Target Cash
New Borrowing
Debt Repayment
Ending Cash
```

Cash identity bắt buộc:

```text
Ending Cash =
Beginning Cash
+ CFO
- CAPEX_positive
- Dividends Paid
+ Equity Issuance
- Share Buyback
+ New Borrowing
- Debt Repayment
+/- Other Non-debt Cash Flows
```

Nếu identity không khớp:

```text
CashSweepArtifact.status = failed
DebtScheduleArtifact.status = blocked
FCFE.status = blocked
BlendDCF.status = blocked
```

Minimum cash policy bắt buộc. Nếu chưa có policy thì block FCFE.

Gợi ý default cho doanh nghiệp dược nếu chưa có analyst input:

```text
Minimum Cash = MAX(50 tỷ VND, 5% doanh thu, 45 ngày cash operating expenses)
```

Default này chỉ được dùng nếu được ghi rõ là model assumption và cần approval.

---

## 5. Pipeline order bắt buộc

Sửa pipeline valuation theo thứ tự:

```text
1. Forecast Revenue / Gross Profit / SG&A / EBITDA
2. Forecast D&A / EBIT / Tax assumptions
3. Forecast CAPEX_positive
4. Forecast NWC and CFO
5. Forecast Dividend Schedule
6. Build CashSweepArtifact
7. Build DebtScheduleArtifact
8. Calculate Net Borrowing
9. Calculate Average Debt
10. Calculate Interest Expense
11. Recalculate PBT / Tax / Net Income
12. Re-run CFO if needed
13. Iterate Debt-Cash-Interest until convergence
14. Calculate FCFE
15. Run FCFF/FCFE reconciliation
16. Run valuation gates
17. Decide publishable status
```

Vì có vòng lặp:

```text
Debt → Interest Expense → PBT → Tax → Net Income → CFO → Cash Sweep → Debt
```

Dừng khi:

```text
abs(Ending Debt_new - Ending Debt_old) < 0.1 tỷ VND
abs(Interest Expense_new - Interest Expense_old) < 0.1 tỷ VND
max_iterations = 10
```

---

## 6. FCFE formula mới

FCFE chỉ được tính sau khi có `Net Borrowing` từ `DebtScheduleArtifact`.

Công thức được phép:

```text
FCFE = CFO - CAPEX_positive + Net Borrowing
```

hoặc:

```text
FCFE = Net Income + D&A - CAPEX_positive - ΔNWC + Net Borrowing
```

Cấm:

```text
FCFE = CFO - CAPEX_positive + historical_median_debt_adjustment
FCFE = CFO - CAPEX_positive + target_debt_delta
```

---

## 7. Valuation gates bắt buộc

Implement hard gates:

```python
if debt_schedule.status != "approved":
    fcfe.publishable = False
    blend_dcf.publishable = False
```

```python
if net_borrowing.confidence not in ["high", "approved"]:
    fcfe.publishable = False
    blend_dcf.publishable = False
```

```python
if fcfe.publishable is False:
    blend_dcf.publishable = False
    recommendation_allowed = False
```

```python
valuation_gap = abs(price_fcff / price_fcfe - 1)
if valuation_gap > 0.25:
    blend_dcf.publishable = False
    recommendation_allowed = False
    require("FCFF_FCFE_Reconciliation")
```

```python
if valuation_allowed is False or recommendation_allowed is False:
    render_mode = "audit_only"
```

Không được render target price/recommendation client-facing nếu gate fail.

---

## 8. FCFF/FCFE reconciliation bắt buộc

Nếu FCFF và FCFE lệch giá trị > 25%, phải sinh reconciliation table giải thích tối thiểu:

```text
NOPAT / Net Income
D&A
CAPEX
ΔNWC
Interest after tax
Net Borrowing
Net Debt bridge
Terminal assumptions
Discount rate difference: WACC vs Cost of Equity
```

Nếu không sinh được reconciliation thì block blend DCF và recommendation.

---

## 9. Output audit artifact bắt buộc

Valuation run phải xuất audit table:

```text
Year
Beginning Debt
New Borrowing
Debt Repayment
Ending Debt
Net Borrowing
Beginning Cash
Ending Cash
Average Debt
Interest Expense
Confidence
Status
```

Nếu bảng này không tồn tại:

```text
FCFE.status = blocked
BlendDCF.status = blocked
```

---

## 10. Test bắt buộc

Thêm regression tests:

```python
assert ending_debt == beginning_debt + new_borrowing - debt_repayment
assert net_borrowing == new_borrowing - debt_repayment
assert interest_expense == average_debt * cost_of_debt
assert fcfe == cfo - capex_positive + net_borrowing
```

Cash sweep identity:

```python
assert ending_cash == (
    beginning_cash
    + cfo
    - capex_positive
    - dividends_paid
    + equity_issuance
    - share_buyback
    + new_borrowing
    - debt_repayment
    + other_non_debt_cash_flows
)
```

Median debt blocking test:

```python
if ending_debt == historical_median_debt and not analyst_approved_debt_policy:
    raise BlockingError("Forced median debt is not allowed")
```

Publish gate tests:

```python
if debt_schedule.status != "approved":
    assert fcfe.publishable is False
    assert blend_dcf.publishable is False

if abs(price_fcff / price_fcfe - 1) > 0.25:
    assert blend_dcf.publishable is False
    assert recommendation_allowed is False
```

---

## 11. Priority triển khai

### P0 — Must fix now

1. Remove `historical_median_debt` from FCFE publishable path.
2. Add `CashSweepArtifact`.
3. Add `DebtScheduleArtifact`.
4. Make `Net Borrowing = New Borrowing - Debt Repayment` only.
5. Block FCFE if debt schedule is not approved.
6. Block Blend DCF if FCFE is blocked.
7. Block recommendation if valuation gates fail.
8. Add FCFF/FCFE gap gate at 25%.

### P1 — Next

1. Link interest expense to average debt.
2. Link dividend schedule into cash sweep.
3. Link net debt bridge to ending debt from DebtScheduleArtifact.
4. Add equity issuance/share dilution handling.
5. Add audit table to valuation JSON/report artifact.

### P2 — Later hardening

1. Parse maturity schedule from financial statement notes.
2. Add scenarios: stable debt, deleveraging, project financing.
3. Add sensitivity on net borrowing and cost of debt.
4. Add analyst approval object for debt/minimum cash policy.
5. Add claim-level citation for debt assumptions.

---

## 12. Final acceptance rule

Publish FCFE/Blend DCF only if all conditions pass:

```text
DebtScheduleArtifact.status = approved
CashSweepArtifact.status = approved
NetBorrowing.confidence in [high, approved]
DividendSchedule.status = approved
CAPEXSchedule.status = approved
InterestExpense.reconciled = true
FCFF_FCFE_Gap <= 25%
valuation_allowed = true
recommendation_allowed = true
```

Nếu không pass:

```text
Only audit artifact.
No client-facing target price.
No recommendation.
No FCFF/FCFE blend.
No silent fallback.
```
