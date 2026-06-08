# Audit B: Formula Inventory
**Date:** 2026-06-07
**Scope:** Every formula in the analytics layer — exact implementation, file, line

---

## B1. FCFF (Free Cash Flow to Firm)

**File:** `backend/analytics/fcff.py:254`

```python
fcff = ebit_after_tax + dep - capex - delta_nwc
# where:
ebit_after_tax = ebit * (1 - tax_rate)        # fcff.py:252
capex = abs(fy.capex)                          # fcff.py:236  — forced positive
delta_nwc  # positive = WC increase (cash absorbed, reduces FCFF)
```

**WACC (Extended CAPM + balance sheet weights):**
```python
# fcff.py:185-188
d_weight = wacc_assumptions.debt_weight or (total_debt / total_capital if total_capital > 0 else 0.3)
e_weight = wacc_assumptions.equity_weight or (1.0 - d_weight)

# fcff.py:39-42
Re = Rf + Beta × ERP + Size_Premium + Specific_Risk_Premium
# defaults: Rf=4%, Beta=0.85, ERP=8%, Size=2%, Risk=1%  → Re ≈ 15.7%

kd_after_tax = cost_of_debt * (1 - tax_rate)
wacc = e_weight * Re + d_weight * kd_after_tax   # fcff.py:48-49
```

**Terminal Value (Gordon Growth):**
```python
# fcff.py:281-282
terminal_fcff = last_fcff * (1 + terminal_growth)
tv = terminal_fcff / (wacc - terminal_growth)
pv_tv = tv / (1 + wacc) ** n
```

**EV → Equity Bridge:**
```python
# fcff.py:289-290
ev = sum_pv + pv_tv
equity_val = ev - net_debt           # net_debt from net_debt_bridge.py
target_price_fcff = (equity_val / shares_mn) * 1_000   # bn → VND/share
```

---

## B2. FCFE (Free Cash Flow to Equity)

**File:** `backend/analytics/fcfe.py:244`

```python
fcfe = ni + dep - capex_pos - delta_nwc + net_borrowing
```

**Equity Value (direct — no net_debt subtraction):**
```python
# fcfe.py:281
equity_val = sum_pv + pv_tv    # NO net_debt subtraction — FCFE gives equity value directly
```

**Cost of Equity (separate from WACC):**
```python
# fcfe.py:47-55
cost_of_equity = risk_free_rate + beta * equity_risk_premium + size_premium + specific_risk_premium
# defaults: Rf=4%, Beta=0.85, ERP=8%, Size=2%, Risk=1%  → Re ≈ 15.7%
```

**Terminal Value:**
```python
# fcfe.py:272-273
terminal_fcfe = last_fcfe * (1 + terminal_growth)
tv = terminal_fcfe / (re - terminal_growth)
pv_tv = tv / (1 + re) ** n
```

---

## B3. Blend (Primary Target Price)

**File:** `backend/analytics/blend.py:77`

```
Target Price = 0.60 × Price_FCFF + 0.40 × Price_PE_Forward
```

```python
# blend.py:23-24
FCFF_WEIGHT: float = 0.60
PE_WEIGHT: float = 0.40
```

FCFE is supplementary cross-check only — not a primary blend weight.

---

## B4. P/E Forward Price

**File:** `scripts/run_valuation.py:458-459`

```python
price_pe_forward = EPS_FY1 × target_pe
# where EPS_FY1 = forecast.eps_fy1_vnd (from forecasting.py)
# target_pe default = 15.0  (hardcoded — see red flags)
```

---

## B5. Core P/E + Net Cash (supplementary, cash-rich companies)

**File:** `backend/analytics/core_pe_net_cash.py:207-233`

```python
# Net cash (per share)
net_cash_bn = (cash or 0.0) + (sti or 0.0) - total_debt
net_cash_per_share = net_cash_bn * 1_000.0 / shares_mn    # bn → VND/share

# Core EPS (strips out after-tax financial income)
net_fi = vas_ebit - pure_ebit    # financial income = total EBIT - operating EBIT
ati_per_share = net_fi * (1.0 - eff_tax) * 1_000.0 / shares_mn
core_eps = eps_forward - (ati_per_share or 0.0)   # unless flag says already excluded

# Target price
target_price = core_eps * target_core_pe + net_cash_per_share
# default target_core_pe = 19.0x
```

---

## B6. Net Debt Bridge

**File:** `backend/analytics/net_debt_bridge.py:192`

```python
net_debt = (total_debt or 0.0) - (cash or 0.0) - (st_inv or 0.0)
# positive = net debt; negative = net cash

# Full EV → Equity bridge (net_debt_bridge.py:199-204):
equity_value_from_ev = enterprise_value - net_debt - minority_interest + non_operating_assets
```

---

## B7. Net Borrowing

**File:** `backend/analytics/debt_schedule.py:316-328`

Priority 1 — Direct CFS (confidence: high):
```python
net_borrow = new_borrow - abs(repayment)
# new_borrow = proceeds_from_borrowings.total
# repayment = repayment_of_borrowings.total
```

Priority 2 — Balance sheet delta (confidence: medium):
```python
net_borrow = ending_debt - beginning_debt
```

Priority 3 — Missing (confidence: low): `net_borrow = 0`

---

## B8. Ratios

**File:** `backend/analytics/ratios.py:70-136`

```python
gross_margin   = gross_profit / revenue.net
ebitda_margin  = ebitda / revenue.net
ebit_margin    = ebit / revenue.net
net_margin     = net_income.parent / revenue.net
roe            = net_income.parent / equity.parent
roa            = net_income.parent / total_assets
```

All prefer pre-computed fact_table values over inline recomputation.

---

## B9. Sensitivity Matrices

**File:** `backend/analytics/sensitivity.py`

| Table | Axes | Key format | Range |
|-------|------|-----------|-------|
| `fcff_wacc_g` | WACC × terminal_growth | `{wacc:.3f}` × `{g:.4f}` | WACC [0.08–0.12], g [0.02–0.04] |
| `fcfe_re_g` | Re × terminal_growth | `{re:.3f}` × `{g:.4f}` | Re [0.09–0.13], g [0.02–0.04] |
| `blend_sensitivity` | Price_FCFF × Price_FCFE | `{price_fcff}` × `{price_fcfe}` | **USES OLD 60% FCFF + 40% FCFE formula** ⚠️ |
| `pe_sensitivity` | EPS × Target P/E | `{eps}` × `{pe}` | — |
| `ev_ebitda_sensitivity` | EBITDA × Multiple | `{ebitda}` × `{multiple}` | — |
| `operating_sensitivity` | Revenue growth × Gross margin | `{rev_growth:.4f}` × `{gm:.4f}` | — |

**⚠️ CRITICAL:** `blend_sensitivity` (sensitivity.py:284) uses `0.60 × Price_FCFF + 0.40 × Price_FCFE`
but the live blend formula (blend.py:77) uses `0.60 × Price_FCFF + 0.40 × Price_PE_Forward`.
These are **inconsistent**.

---

## B10. Forecast Engine

**File:** `backend/analytics/forecasting.py`

| Line item | Method | Source |
|-----------|--------|--------|
| Revenue | Historical CAGR, capped ±25% | fact_table["revenue.net"] |
| Gross margin | Median historical ratio-to-revenue | fact_table["gross_profit.total"] |
| SG&A | % of revenue (historical median) | fact_table["selling_expense.total"] + ["admin_expense.total"] |
| D&A | % of revenue (historical median) | fact_table["depreciation.total"] |
| CAPEX | % of revenue (historical median) | fact_table["capex.total"] |
| Interest expense | avg_debt × cost_of_debt | NOT % of revenue |
| delta_NWC | DSO/DIO/DPO days model | `working_capital_schedule.py` |
| Dividend | Historical median payout ratio | fact_table["dividends_per_share.cash"] |
| Net borrowing | From `debt_schedule.net_borrowing_schedule()` | `debt_schedule.py` |
| EPS FY1 | net_income_parent / weighted_avg_shares | forecasting.py (two-pass) |

**Two-pass structure:**
- Pass 1: Income statement (revenue → EBIT → tax → net income → EPS)
- Pass 2: Equity roll-forward after building debt/NWC sub-schedules

**No convergence loop:** debt→interest→NI→cash→debt feedback is NOT implemented (documented as TODO).
