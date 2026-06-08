# Audit D: Forecast Method Audit
**Date:** 2026-06-07
**Scope:** How each P&L and balance sheet line item is projected in the forecast engine

---

## D1. Forecast Engine Overview

**File:** `backend/analytics/forecasting.py`

The forecast engine uses a **two-pass** approach:
- **Pass 1:** Income statement (revenue → EBIT → tax → net income → EPS)
- **Pass 2:** Equity roll-forward (after building debt/NWC/shares sub-schedules)

Forecast horizon: **5 years forward** (default)
Output: `ForecastArtifact` with per-year rows + `eps_fy1_vnd` for P/E Forward computation

---

## D2. Line-by-Line Forecast Methods

### Revenue
- **Method:** Historical CAGR over available FY periods
- **Cap:** ±25% (prevents runaway projections from short history)
- **Source fact:** `fact_table["revenue.net"]`

### Gross Profit / COGS
- **Method:** Historical **median** gross margin ratio × projected revenue
- `gross_profit = revenue × median_gross_margin`
- `cogs = revenue - gross_profit`
- **Source fact:** `fact_table["gross_profit.total"]`

### SG&A (Selling + Admin Expenses)
- **Method:** Historical **median** SG&A as % of revenue
- `sga = revenue × median_sga_pct`
- **Source facts:** `fact_table["selling_expense.total"]` + `fact_table["admin_expense.total"]`

### EBIT
- `ebit = gross_profit - sga` (derived, not directly forecast)

### Depreciation & Amortization
- **Method:** Historical **median** D&A as % of revenue
- **Source fact:** `fact_table["depreciation.total"]`

### CAPEX
- **Method:** Historical **median** CAPEX as % of revenue
- **Source fact:** `fact_table["capex.total"]`
- Stored as **positive outflow** (`abs()` applied in fcff.py:236)

### Interest Expense
- **Method:** `avg_debt × cost_of_debt` — **NOT a % of revenue**
- Uses forecast debt balance (from debt_schedule) × assumed interest rate
- **Source:** `debt_schedule.py` interest computation

### Delta NWC (Change in Working Capital)
- **Method:** DSO/DIO/DPO days model via `backend/analytics/working_capital_schedule.py`
- Historical median days → projected ending NWC balance → delta vs prior year
- Positive delta_NWC = working capital increased = cash absorbed (reduces FCFF/FCFE)

### Net Borrowing
- **Source:** `debt_schedule.net_borrowing_schedule()`
- Uses whichever method `debt_schedule.py` selects (direct CFS if available, else balance sheet delta)

### Tax Rate
- Historical effective tax rate (net_income / profit_before_tax median)
- Falls back to statutory rate (20% for Vietnamese pharma) if insufficient history

### EPS Forward
- `EPS = net_income_parent / weighted_avg_diluted_shares`
- Uses `shares_outstanding.ending` fact (not inferred from market cap)
- `eps_fy1_vnd` = year 1 EPS used in P/E Forward computation

### Dividend per Share
- **Method:** Historical **median** payout ratio × projected EPS

---

## D3. Sub-Schedule Dependencies

```
forecasting.py (Pass 1: income statement)
    → working_capital_schedule.py   (DSO/DIO/DPO → delta_NWC)
    → debt_schedule.py              (interest expense + net_borrowing)
    → share_rollforward.py          (shares outstanding evolution)
    → forecasting.py (Pass 2: equity roll-forward)
```

---

## D4. Missing Data Fallbacks

| Line Item | Missing Behavior |
|-----------|----------------|
| Revenue history < 2 years | Use single-year value, no CAGR |
| Gross margin history missing | Use 0% or emit None + warning |
| D&A / CAPEX missing | Use 0.0 + warning (conservative, underestimates FCFF) |
| delta_NWC not computable | Use 2% of revenue change (hardcoded fallback in fcff.py:243,248) |
| Shares missing | `target_price = None`, warning issued (fcff.py:223-226) |
| Debt schedule unavailable | Assume stable leverage: `net_borrowing = 0.0` (fcfe.py:206-210) |

---

## D5. Known Gaps and Limitations

### D5.1 No Convergence Loop
**Status: NOT IMPLEMENTED (documented as TODO)**

The forecast engine does NOT model the circular dependency:
```
higher debt → higher interest → lower NI → lower retained earnings
→ lower equity → different D/E ratio → different WACC → different valuation
```

Each forecast year is computed in sequence but the debt-interest-NI feedback loop is open.
This means:
- Interest expense is computed from forecast debt, but the forecast debt itself uses a simple schedule
- Changes in NI do not feed back to revise the debt assumption in the same period
- Impact: modest overstatement or understatement of FCFF for debt-heavy or rapidly deleveraging firms

### D5.2 Historical Period Sensitivity
CAGR is sensitive to the choice of base year. A single abnormal year (e.g., COVID dip) will distort the CAGR used for all 5 projection years. There is no normalization of outlier historical periods.

### D5.3 Median Ratio Stability Assumption
All ratios (gross margin, SG&A%, D&A%, CAPEX%) use historical **median** as the forward projection. This assumes structural stability — mean-reversion to median — which may not hold for companies undergoing expansion CAPEX cycles or margin pressure.

### D5.4 No Scenario Branching in Forecast
The forecast engine produces a single base-case path. Bull/bear scenarios are handled by re-running sensitivity with different WACC/g parameters, not by running distinct revenue/margin scenario paths through the forecast engine.

---

## D6. Forecast Artifact Output Fields

```python
ForecastArtifact:
    rows: list[ForecastRow]           # per-year: revenue, EBIT, NI, EPS, FCFF, FCFE
    eps_fy1_vnd: float | None         # EPS year 1 (used in P/E Forward blend)
    wacc: float                       # used in FCFF discounting
    terminal_growth: float            # used in terminal value
    assumption_status: str            # "default_unapproved" | "approved"
    warnings: list[str]               # data quality issues, missing inputs
```
