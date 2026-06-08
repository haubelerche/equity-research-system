# Audit E: FCFF/FCFE Formula and Implementation Audit
**Date:** 2026-06-07
**Scope:** Formula correctness, sign conventions, discount rate sourcing, blocking gates

---

## E1. FCFF — Formula Verification

**File:** `backend/analytics/fcff.py`
**Spec:** CLAUDE.md §6

| Spec | Implementation | Line | Status |
|------|---------------|------|--------|
| FCFF = EBIT(1-T) + D&A - CAPEX - ΔNWC | `fcff = ebit_after_tax + dep - capex - delta_nwc` | 254 | ✓ EXACT |
| `ebit_after_tax = ebit * (1-tax_rate)` | `ebit_after_tax = ebit * (1 - tax_rate)` | 252 | ✓ EXACT |
| CAPEX as positive outflow | `capex = abs(fy.capex)` | 236 | ✓ POSITIVE (forced) |
| ΔNWC positive = WC increase | subtracted: `- delta_nwc` | 254 | ✓ CORRECT |
| WACC from balance sheet D/E | `d_weight = total_debt / total_capital` | 185-188 | ✓ DYNAMIC |
| Terminal value = Gordon Growth | `tv = terminal_fcff*(1+g)/(wacc-g)` | 281-282 | ✓ EXACT |
| EV − net_debt = equity value | `equity_val = ev - net_debt` | 289-290 | ✓ CORRECT |

---

## E2. FCFE — Formula Verification

**File:** `backend/analytics/fcfe.py`
**Spec:** CLAUDE.md §6

| Spec | Implementation | Line | Status |
|------|---------------|------|--------|
| FCFE = NI + D&A - CAPEX - ΔNWC + Net Borrowing | `fcfe = ni + dep - capex_pos - delta_nwc + net_borrowing` | 244 | ✓ EXACT |
| FCFE → Equity Value directly (no net_debt subtract) | `equity_val = sum_pv + pv_tv` (no net_debt) | 281 | ✓ CORRECT |
| Re ≠ WACC | Separate `CostOfEquityAssumptions` class | 32-55 | ✓ SEPARATE |
| Terminal value uses Re (not WACC) | `tv = terminal_fcfe / (re - terminal_growth)` | 272-273 | ✓ CORRECT |

---

## E3. WACC vs Cost of Equity

Both FCFF and FCFE use Extended CAPM but through separate classes:

| Parameter | FCFF (WACCAssumptions) | FCFE (CostOfEquityAssumptions) | Same? |
|-----------|----------------------|-------------------------------|-------|
| Risk-free rate | 4.0% | 4.0% | ✓ |
| Beta | 0.85 | 0.85 | ✓ |
| Equity Risk Premium | 8.0% | 8.0% | ✓ |
| Size Premium | 2.0% | 2.0% | ✓ |
| Specific Risk Premium | 1.0% | 1.0% | ✓ |
| Total (default Re) | ~15.7% | ~15.7% | ✓ same defaults |
| D/E weighting | Yes (balance sheet) | N/A — pure equity discount rate | — |

**Note:** Both produce the same default Re ≈ 15.7%. The FCFF WACC is lower because it mixes in
lower after-tax cost of debt, weighted by balance sheet D/(D+E) ratio.

---

## E4. Net Debt Bridge

**File:** `backend/analytics/net_debt_bridge.py:192`

```python
net_debt = (total_debt or 0.0) - (cash or 0.0) - (st_inv or 0.0)
```

| Component | Included | Source fact |
|-----------|---------|------------|
| Total interest-bearing debt | ✓ | `total_debt.ending` or `short_term_debt + long_term_debt` |
| Cash and equivalents | ✓ subtracted | `cash_and_equivalents.ending` |
| Short-term investments | ✓ subtracted | `short_term_investments.ending` |
| Minority interest | ✓ (in full bridge) | `minority_interest.ending` |
| Non-operating assets | ✓ added back | `non_operating_assets` |

**Sign convention:** Positive = net debt (owes more than cash); Negative = net cash position.

**DBD 2025FY example:**
- Total debt = 43.215 + 132.000 = 175.215 VND bn
- Cash = 202.784 VND bn
- STI = 409.201 VND bn
- Net debt = 175.215 − 202.784 − 409.201 = **−436.770 VND bn** (net cash position)

---

## E5. Net Borrowing Computation

**File:** `backend/analytics/debt_schedule.py:316-328`

| Priority | Method | Formula | Confidence | FCFE publishable? |
|----------|--------|---------|-----------|-----------------|
| 1 | Direct CFS | `new_borrow - abs(repayment)` | high | ✓ Yes |
| 2 | Balance sheet delta | `ending_debt - beginning_debt` | medium | ✗ No |
| 3 | Missing | 0.0 (stable leverage) | low | ✗ No |

**Forecast methods:**
| Method | Confidence | FCFE publishable? |
|--------|-----------|-----------------|
| `manual_override` (analyst-approved) | medium | ✓ if status='approved' |
| `zero_debt_policy` (historical debt < 1 VND bn) | high | ✓ Yes |
| `target_debt_ratio` (median historical debt) | low | ✗ No |
| `missing` | low | ✗ No |

---

## E6. FCFE Publishability Gate

**File:** `backend/analytics/debt_schedule.py:118-138`

```python
@property
def is_fcfe_publishable(self) -> bool:
    _PUBLISHABLE_METHODS = {"direct_cash_flow", "zero_debt_policy"}
    if self.forecast_method not in _PUBLISHABLE_METHODS:
        return False
    return all(row.confidence == "high" for row in self.forecast_rows)
```

**Consequence (fcfe.py:200-205):**
- If `is_fcfe_publishable = False` → FCFE target price blocked
- FCFE used as informational cross-check only (blend.py comment: "FCFE no longer a primary blend weight")

---

## E7. Blocking Gates Summary

| Condition | Where checked | Effect |
|-----------|--------------|--------|
| `total_debt` fact missing | net_debt_bridge.py:163-169 | `status="blocked"` → FCFF target_price = None |
| `shares_outstanding` missing | fcff.py:223-226 | FCFF target_price = None + warning |
| WACC ≤ terminal_growth | fcff.py:211-217 | FCFF `status="INVALID"`, target_price = None |
| Re ≤ terminal_growth | fcfe.py:168-174 | FCFE `status="INVALID"`, target_price = None |
| FCFE not publishable | fcfe.py:200-205 | FCFE target_price = None (informational warning) |
| ebit, dep, or capex is None | fcff.py:256-257 | FCFF = None + warning |
| ni, dep, or capex is None | fcfe.py:243-247 | FCFE = None + warning |

---

## E8. DHG Artifact Values (2026-06-05 run)

```json
{
  "fcff": {
    "wacc": 0.138,
    "terminal_growth": 0.03,
    "terminal_value_fcff": 50662.0,
    "pv_terminal_value_fcff": 30305.3,
    "enterprise_value_fcff": 34509.0,
    "net_debt": 129.9,
    "equity_value_fcff": 34381.0,
    "shares_mn": 130.75,
    "target_price_fcff_vnd": 92970.0
  },
  "blend_dcf": {
    "price_fcff_vnd": 92970.0,
    "price_pe_forward_vnd": 121427.0,
    "fcff_weight": 0.6,
    "pe_weight": 0.4,
    "target_price_dcf_vnd": 104353.0,
    "upside_pct": 0.1137,
    "tv_weight_fcff": 0.5244
  }
}
```

Blend verification: `0.60 × 92970 + 0.40 × 121427 = 55782 + 48570.8 = 104352.8 ≈ 104353` ✓
Terminal value weight: `30305.3 / 34509.0 = 52.4%` (below 70% warning threshold) ✓
