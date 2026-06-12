# Valuation Calculation Audit Checklist

## Objective

Audit the current valuation and financial calculation system to finalize **one single official calculation methodology** for all Vietnam pharma equity research reports.

The system must stop using multiple hidden or conflicting methods for target price, financial ratios, debt, EPS, P/E, FCFF, FCFE, dividend yield, and recommendation.

Final production target price must use only:

```text
Target Price = 0.60 × Price_FCFF + 0.40 × Price_FCFE
```

All other methods such as Core P/E + Net Cash, Forward P/E, P/B, and EV/EBITDA are allowed only as **supplementary cross-checks**. They must never override the official target price.

---

## 1. Key Audit Questions

### 1.1 Target Price Source

Check every place where `target_price`, `fair_value`, `blended_target`, or `recommendation_price` is calculated or overwritten.

Confirm:

- The report cover page target price comes only from `0.60 × FCFF + 0.40 × FCFE`.
- No module silently replaces the blended target price.
- Core P/E + Net Cash does not override target price.
- Forward P/E does not enter the blend.
- Sensitivity table base case reconciles with the same valuation artifact.

### 1.2 DBD Case Verification

For DBD, explicitly decompose the previous 63,560 VND/share result.

Check whether it came from:

```text
Core EPS × Target P/E + Net Cash Per Share
```

If yes, classify it as **supplementary valuation only**, not the official target price.

Then rerun DBD using only:

```text
0.60 × Price_FCFF + 0.40 × Price_FCFE
```

If the result differs from 63,560 VND/share, explain the difference through:

- revenue forecast
- margin forecast
- WACC
- cost of equity
- terminal growth
- CAPEX
- change in working capital
- net borrowing
- net debt adjustment
- shares outstanding
- unit conversion

Do not force the model to reproduce 63,560 unless the FCFF/FCFE bridge supports it.

---

## 2. Official Calculation Methodology

### 2.1 FCFF

```text
FCFF = EBIT × (1 - Tax Rate) + D&A - CAPEX - ΔNWC
```

```text
Enterprise Value = PV(Explicit FCFF) + PV(Terminal Value)
Equity Value = Enterprise Value - Net Debt - Minority Interest + Non-operating Assets
Price_FCFF = Equity Value / Shares Outstanding
```

Required bridge fields:

- EBIT
- tax rate
- NOPAT
- D&A
- CAPEX
- ΔNWC
- FCFF by year
- discount factor
- PV of FCFF
- terminal value
- PV of terminal value
- enterprise value
- cash and short-term investments
- total interest-bearing debt
- net debt
- minority interest
- non-operating assets
- equity value
- shares outstanding
- price_fcff

### 2.2 FCFE

```text
FCFE = Net Income + D&A - CAPEX - ΔNWC + Net Borrowing
```

```text
Equity Value = PV(Explicit FCFE) + PV(Terminal Value)
Price_FCFE = Equity Value / Shares Outstanding
```

Required bridge fields:

- net income
- D&A
- CAPEX
- ΔNWC
- net borrowing
- FCFE by year
- cost of equity
- terminal growth
- PV of FCFE
- PV of terminal value
- equity value
- shares outstanding
- price_fcfe

### 2.3 Net Borrowing and Debt Schedule

Net borrowing must not be guessed.

Use this priority order:

```text
1. Direct cash flow statement:
   Net Borrowing = Proceeds from Borrowings - Repayment of Borrowings

2. Balance sheet delta:
   Net Borrowing = Ending Interest-Bearing Debt - Beginning Interest-Bearing Debt

3. Stable leverage fallback:
   Net Borrowing = 0 or target debt ratio method, with low-confidence warning
```

Debt schedule must include:

- opening short-term debt
- opening long-term debt
- new borrowing
- repayment
- closing short-term debt
- closing long-term debt
- total debt
- net borrowing
- interest expense
- average debt
- cost of debt
- debt-to-equity
- debt-to-assets
- confidence level
- method used

### 2.4 Blended Target Price

Official formula:

```text
Target Price = 0.60 × Price_FCFF + 0.40 × Price_FCFE
```

Allowed fallback only for draft mode:

```text
If FCFE is missing: use 100% FCFF, mark as draft_only, require analyst approval.
If FCFF is missing: use 100% FCFE, mark as draft_only, require analyst approval.
If both are missing: no target price.
```

No final report can be exported if FCFF or FCFE bridge is missing unless analyst approval explicitly accepts draft-only valuation.

---

## 3. Mandatory Financial Metrics

For every ticker and forecast year, the system must calculate and expose:

- revenue
- gross profit
- EBIT
- EBITDA
- net income
- EPS
- DPS
- book value per share
- operating cash flow
- CAPEX
- free cash flow
- short-term debt
- long-term debt
- total debt
- net debt
- net borrowing
- shares outstanding
- gross margin
- EBIT margin
- EBITDA margin
- net margin
- ROE
- ROA
- ROIC
- P/E
- P/B
- EV/EBITDA
- dividend yield

If a metric cannot be calculated, output:

```json
{
  "value": null,
  "missing_reason": "source data unavailable / formula input missing / data quality failed"
}
```

Never output `0` when the real issue is missing data.

---

## 4. Reconciliation Rules

The following formulas must pass before export:

```text
EPS = Net Income / Shares Outstanding
P/E = Current Price / EPS
Dividend Yield = DPS / Current Price
Total Debt = Short-Term Debt + Long-Term Debt
Net Debt = Total Debt - Cash - Short-Term Investments
EV = Market Cap + Net Debt + Minority Interest - Non-operating Assets
EV/EBITDA = EV / EBITDA
ROE = Net Income / Average Equity
ROA = Net Income / Average Assets
ROIC = NOPAT / Invested Capital
Target Price = 0.60 × Price_FCFF + 0.40 × Price_FCFE
Upside = Target Price / Current Price - 1
Total Expected Return = Upside + Dividend Yield
```

Recommendation rule:

```text
BUY  if Total Expected Return > 20%
SELL if Total Expected Return < -10%
HOLD otherwise
```

---

## 5. Hard Export Gates

Block report export if any gate fails:

1. Target price does not equal `0.60 × FCFF + 0.40 × FCFE`.
2. Cover page target price differs from valuation artifact target price.
3. Core P/E + Net Cash overrides the official target price.
4. Forward P/E enters the official blend.
5. FCFF bridge is missing or empty.
6. FCFE bridge is missing or empty.
7. Sensitivity base case does not reconcile with FCFF/FCFE/blend base case.
8. EPS does not reconcile with net income and shares outstanding.
9. P/E does not reconcile with price and EPS.
10. Dividend yield does not reconcile with DPS and current price.
11. Net borrowing does not reconcile with the debt schedule.
12. Net debt does not reconcile with debt, cash, and short-term investments.
13. Recommendation does not reconcile with total expected return.
14. Any required metric is zero because of missing data.
15. Any LLM-generated number bypasses the code-first calculation engine.

---

## 6. Files / Modules to Inspect

Inspect and report all files involved in:

- valuation blend
- FCFF calculation
- FCFE calculation
- debt schedule
- net borrowing
- EPS and share count
- dividend yield
- multiples
- sensitivity analysis
- report view model
- report section builder
- export gate
- valuation artifact writer

For each module, answer:

```text
1. What does it calculate?
2. What formula does it use?
3. What input data does it depend on?
4. Does it write or overwrite target price?
5. Does it duplicate another calculation?
6. Is it production, fallback, legacy, or display-only?
7. Should it be kept, rewritten, demoted, or deleted?
```

---

## 7. Expected Audit Output

Create one Markdown report with:

1. Current calculation map
2. All conflicting formulas found
3. The exact source of DBD 63,560 VND/share
4. Whether DBD 63,560 is FCFF/FCFE-supported or only P/E-supported
5. Final official formula map
6. Modules to delete, demote, or rewrite
7. Required valuation artifact schema
8. Required export gates
9. Test plan
10. Implementation checklist

---

## 8. Final Decision Rule

The system must not be optimized to reproduce a desired target price manually.

The system must be optimized so that every output number is:

```text
source-backed → code-calculated → reconciled → traceable → export-gated
```

The final official valuation method is:

```text
Target Price = 0.60 × Price_FCFF + 0.40 × Price_FCFE
```

All P/E-based methods are supplementary cross-checks only.
