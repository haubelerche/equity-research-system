# Audit F: Valuation Bridge Audit
**Date:** 2026-06-07
**Scope:** Full path from FCFF equity value → blend target price → recommendation

---

## F1. Primary Valuation Method: FCFF + P/E Forward Blend

**File:** `backend/analytics/blend.py`

```
Target Price = 0.60 × Price_FCFF + 0.40 × Price_PE_Forward
```

**Constants (blend.py:23-24):**
```python
FCFF_WEIGHT: float = 0.60
PE_WEIGHT: float = 0.40
```

---

## F2. Price_FCFF Bridge

```
FCFF (per year) → discounted at WACC → sum of PV_FCFF
→ + PV of terminal value (Gordon Growth)
= Enterprise Value (FCFF)
→ - Net Debt (via net_debt_bridge.py)
→ - Minority Interest (if present)
→ + Non-Operating Assets (if present)
= Equity Value
→ / shares_mn (in millions)
× 1_000 (bn → VND per share)
= Price_FCFF
```

**Files:** `fcff.py:289-290`, `net_debt_bridge.py:199-204`

---

## F3. Price_PE_Forward Bridge

```
Forecast net_income_parent (FY1)
→ / weighted_avg_diluted_shares
= EPS_FY1 (VND per share)
→ × target_pe
= Price_PE_Forward
```

**File:** `scripts/run_valuation.py:458-459`

```python
price_pe_forward = forecast.eps_fy1_vnd * target_pe
```

**Default target_pe = 15.0** (hardcoded — no peer dataset computation in current implementation)

---

## F4. Blend Quality Gates

**File:** `backend/analytics/blend.py:103-147`

| Gate | Threshold | Trigger | Effect |
|------|-----------|---------|--------|
| Gate 1: FCFF/FCFE gap | > 25% | `abs(price_fcff - price_fcfe) / max(...)` | `is_draft_only = True` (blocks blend) |
| Gate 2: FCFE publishability | not publishable | `is_fcfe_publishable = False` | Informational warning only (does NOT block) |
| Gate 3: FCFF vs P/E gap | > 40% | `abs(price_fcff - price_pe_forward) / max(...)` | `is_draft_only = True` (sets draft-only flag) |
| Gate 4: Terminal value weight | > 70% | `pv_tv / ev` | Warning only |

**Important:** Gate 2 is informational — missing/unpublishable FCFE does NOT block the blend.
FCFE is now a supplementary cross-check only.

---

## F5. Recommendation Logic

**File:** `backend/reporting/client_report_view_model.py:730-737`

```python
def _recommendation(upside: float | None, mode: RenderMode, approved_for_display: bool = False):
    if not approved_for_display or upside is None:
        return "ĐANG HOÀN THIỆN"  # "Under Review"
    if upside > 0.20:
        return "MUA"   # BUY
    if upside < -0.20:
        return "BÁN"   # SELL
    return "GIỮ"        # HOLD
```

| Rating | Vietnamese | Threshold |
|--------|-----------|----------|
| BUY | MUA | upside > 20% |
| HOLD | GIỮ | -20% ≤ upside ≤ 20% |
| SELL | BÁN | upside < -20% |
| Pending | ĐANG HOÀN THIỆN | `approved_for_display = False` |

**Upside:** stored as decimal (0.20 = 20%).
`upside = (target_price - current_price) / current_price`

---

## F6. Approval Gate Fields

**File:** `backend/analytics/approval_gate.py:25-40`

```python
@dataclass
class AssumptionGate:
    data_quality_passed: bool = False
    tax_policy_approved: bool = False
    wacc_approved: bool = False
    cost_of_equity_approved: bool = False
    terminal_growth_approved: bool = False
    forecast_assumptions_approved: bool = False
    debt_schedule_approved: bool = False
    dividend_assumptions_approved: bool = False
    peer_multiples_approved: bool = False
    final_recommendation_approved: bool = False
    status: GateStatus = "draft_needs_analyst_review"
    blocking_reasons: list[str] = field(default_factory=list)
```

**Blocking rules:**
- `data_quality_passed = False` → CRITICAL BLOCK (valuation cannot proceed)
- `final_recommendation_approved = False` → recommendation shows "ĐANG HOÀN THIỆN"

All other flags are warnings — they do not block the blend computation but prevent analyst sign-off.

---

## F7. Multiples (Relative Valuation)

**File:** `backend/analytics/multiples.py`

```python
compute_multiples(
    ticker, fact_table,
    current_price_vnd=None,
    target_pe=None,
    peer_data_source=None   # if None → implied prices blocked
)
```

| peer_data_source | implied_price_pe | status |
|----------------|-----------------|--------|
| None (current default) | null | `pending_peer_dataset` |
| Provided | computed from target_pe | `ok` |

**The `peer_median_pe` field is never computed by the system** — it must be provided externally.
Without it, `target_pe = 15.0` is stored in the artifact but not used to compute implied_price_pe.

---

## F8. Core P/E + Net Cash (Supplementary)

**File:** `backend/analytics/core_pe_net_cash.py`

```
Value per share = core_eps × target_core_pe + net_cash_per_share
where:
  core_eps = eps_forward - after_tax_financial_income_per_share
  net_cash_per_share = (cash + STI - total_debt) × 1_000 / shares_mn
  default target_core_pe = 19.0x
```

This is supplementary — computed alongside main blend, not a primary weight.
The `financial_income_already_excluded` flag prevents double-counting.

---

## F9. Valuation Artifact Top-Level Structure

**File:** `scripts/run_valuation.py:824-867`
**Path:** `artifacts/valuation/{ticker}_{timestamp}_valuation.json`

```json
{
  "ticker": "DHG",
  "formula_version": "valuation_v1_code_first_fcff_fcfe_blend",
  "valuation_methods": ["fcff", "blend_dcf_fcff_pe", "multiples", "sensitivity", "fcfe_informational"],
  "assumptions": { ... },
  "ratios": { ... },
  "fcff": { ... },
  "fcfe": { ... },
  "blend_dcf": { ... },
  "multiples": { ... },
  "core_pe_net_cash": { ... },
  "sensitivity": { ... },
  "formula_traces": [ ... ]
}
```
