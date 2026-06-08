# Audit H: Red Flag Summary
**Date:** 2026-06-07
**Scope:** All inconsistencies, gaps, and risks found during the read-only audit

---

## RED FLAGS OVERVIEW

| # | Severity | Category | Title |
|---|----------|----------|-------|
| RF-01 | CRITICAL | Formula Inconsistency | sensitivity.py blend uses old FCFE formula, not P/E Forward |
| RF-02 | HIGH | Valuation | target_pe = 15.0 is hardcoded — no peer median computation |
| RF-03 | HIGH | Forecast | No convergence loop (debt-interest-NI feedback) |
| RF-04 | MEDIUM | Report | Recommendation shows "ĐANG HOÀN THIỆN" in analyst_draft mode |
| RF-05 | MEDIUM | Valuation | `implied_price_pe` always null when peer_data_source=None |
| RF-06 | LOW | Data | WACC defaults never verified against market conditions |
| RF-07 | LOW | Forecast | Revenue CAGR capped at ±25% — cap value undocumented in specs |

---

## RF-01: sensitivity.py blend formula inconsistent with blend.py

**Severity: CRITICAL**
**Files:** `backend/analytics/sensitivity.py:284` vs `backend/analytics/blend.py:77`

**blend.py (live formula — correct):**
```python
target_price = 0.60 × Price_FCFF + 0.40 × Price_PE_Forward
```

**sensitivity.py blend_sensitivity (WRONG — uses old formula):**
```python
blend = 0.60 × Price_FCFF + 0.40 × Price_FCFE   # sensitivity.py:284
```

**Impact:** The sensitivity matrix labeled `blend_sensitivity` in the valuation artifact produces
numbers based on the **old FCFE-blended formula**, not the current P/E Forward blend. Any analyst
or client reviewing the sensitivity table is seeing a different formula result than the headline
target price. This is a silent inconsistency that could mislead valuation analysis.

**Root cause:** `sensitivity.py` was not updated when the blend formula changed from
60% FCFF + 40% FCFE → 60% FCFF + 40% P/E Forward.

**Required fix:** Update `sensitivity.py` `build_blend_sensitivity_table()` to use
`0.60 × Price_FCFF + 0.40 × (eps × pe)` instead of FCFE.

---

## RF-02: target_pe = 15.0 hardcoded, no peer median computation

**Severity: HIGH**
**File:** `scripts/run_valuation.py:461`

```python
_DEFAULT_PE = 15.0
```

**Impact:** The 40% weight of the blend formula relies on `Price_PE_Forward = EPS × target_pe`.
The `target_pe` defaults to 15.0x for all tickers — this value is not computed from a peer group.

The system emits a warning:
> "target_pe=15.0x is model default — validate with peer-median P/E before publishing"

But currently `peer_median_pe` is never computed. `multiples.py` sets `implied_price_pe = null`
whenever `peer_data_source = None` (the current default), so the multiples section correctly
blocks relative valuation. However, `run_valuation.py` still uses the 15.0 default in the blend.

**Required fix:**
- Either implement peer median P/E computation from the universe registry, OR
- Block the blend's P/E Forward component until `target_pe` is explicitly approved by the analyst
- CLAUDE.md §6 requires `peer_multiples_approved` in the assumption gate — this flag must block
  `price_pe_forward` if not set

---

## RF-03: No convergence loop in forecast engine

**Severity: HIGH**
**File:** `backend/analytics/forecasting.py`

**Missing feedback:** The forecast does not model:
```
higher debt → higher interest expense → lower pre-tax income
→ lower retained earnings → different equity → different D/E ratio
→ different WACC → different terminal value
```

Each year is computed sequentially but the debt balance used to compute interest does not
feed back into the same year's net income computation. The P&L and balance sheet are
**not jointly balanced** in the model.

**Impact:** For companies with significant or changing debt (e.g. DBD with 175 VND bn debt,
or companies doing expansionary capex financed by debt), this can lead to:
- Overestimated net income (interest understated in high-debt years)
- Incorrect equity roll-forward
- WACC computed from wrong D/E weights for later forecast years

**Status:** Documented as TODO in codebase. Not a new discovery but a documented gap.

**Required fix:** Implement 3–5 iteration convergence loop in `forecasting.py`.

---

## RF-04: Recommendation shows "ĐANG HOÀN THIỆN" in analyst_draft mode

**Severity: MEDIUM**
**File:** `backend/reporting/client_report_view_model.py:730-737`

When `approved_for_display = False` (which is the default in `analyst_draft` mode), the
recommendation is hardcoded to display "ĐANG HOÀN THIỆN" regardless of the computed upside.

This is **by design** (HITL requirement). However:
- The analyst_draft report does show the computed target price and upside percentage
- But the recommendation card shows "ĐANG HOÀN THIỆN" with CSS class `recommendation-review`
- This inconsistency (price/upside visible but rating hidden) may confuse analysts reviewing drafts

**Impact:** Low risk of incorrect reporting (the gate works as designed), but creates UX
friction for the analyst reviewing the draft. The computed rating is available in the
view model but not surfaced in the draft HTML.

**Suggestion:** Add a draft-mode annotation: "Draft: computed rating = MUA (pending approval)"
to help analysts review without publishing the unapproved rating.

---

## RF-05: `implied_price_pe` always null without peer_data_source

**Severity: MEDIUM**
**File:** `backend/analytics/multiples.py:103-106`

```python
# Peer guard rule:
# If peer_data_source is None, implied prices from target multiples are set to None.
```

**Impact:** The multiples section in every valuation artifact currently shows:
```json
"implied_price_pe": null,
"implied_price_pb": null,
"implied_price_ev_ebitda": null,
"relative_valuation_status": "pending_peer_dataset"
```

This means the P/E relative valuation cross-check is **always pending** — it never validates
the 15.0x P/E assumption. An analyst approving the blend is approving a 40% weight that relies
on a hardcoded multiple that has never been cross-validated against peers.

**Required fix:** Implement peer median P/E derivation from the universe CSV, or require
explicit analyst input of `target_pe` and `peer_data_source` before the blend can be
marked non-draft.

---

## RF-06: WACC defaults never market-validated

**Severity: LOW**
**Files:** `backend/analytics/fcff.py:39-42`, `backend/analytics/fcfe.py:47-55`

Default WACC assumptions:
- Rf = 4.0% (Vietnam 10-year bond? Not dynamically sourced)
- Beta = 0.85 (same for all tickers regardless of sector/leverage)
- ERP = 8.0% (Vietnam equity risk premium — static, not updated)
- Size Premium = 2.0%, Specific Risk = 1.0% (fixed)

These defaults produce Re ≈ 15.7% and WACC ≈ 13.8% (for DHG).

**Impact:** Reasonable defaults, but applying the same WACC defaults to all 53 tickers
without calibration is a systematic risk. Beta = 0.85 may be too low for small-cap
distributors or too high for cash-rich pharma companies like DBD.

**Required fix:** Add beta lookup from market data per ticker, or require analyst to
explicitly set assumptions before approving the valuation.

---

## RF-07: Revenue CAGR cap at ±25% undocumented in specs

**Severity: LOW**
**File:** `backend/analytics/forecasting.py`

The ±25% revenue growth cap is hardcoded in the forecast engine. The value is not in
any spec document and is not exposed as a configurable parameter in the assumptions table.

**Impact:** Low risk — it's a sensible guardrail. But it should be documented in
`CLAUDE.md §6` or the assumptions table so analysts know it exists and can override it
for high-growth companies.

---

## Summary: Priority Order for Fixes

| Priority | Red Flag | Effort | Impact |
|----------|----------|--------|--------|
| P0 (fix now) | RF-01: sensitivity.py blend formula | Small (~10 lines) | Silent inconsistency in sensitivity output |
| P1 (this sprint) | RF-02: target_pe hardcoded | Medium (peer lookup or gate enforcement) | 40% of blend weight unvalidated |
| P1 (this sprint) | RF-05: implied_price_pe always null | Medium (peer data input mechanism) | Relative valuation cross-check missing |
| P2 (next sprint) | RF-03: no convergence loop | Large (3-5 iteration loop in forecasting.py) | Balance sheet accuracy for debt-heavy companies |
| P3 (backlog) | RF-04: draft recommendation UX | Small (add draft annotation) | Analyst UX improvement |
| P3 (backlog) | RF-06: WACC defaults | Medium (beta lookup per ticker) | Accuracy for diverse ticker universe |
| P3 (backlog) | RF-07: CAGR cap undocumented | Tiny (add to spec) | Documentation |
