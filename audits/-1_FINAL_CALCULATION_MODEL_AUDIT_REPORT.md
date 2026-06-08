# FINAL CALCULATION MODEL AUDIT REPORT
**Project:** Multi-Agent Vietnamese Pharma Equity Research Pipeline
**Audit Date:** 2026-06-07
**Audit Type:** Read-only — no code changes made
**Auditor:** Claude (automated read-only audit)
**Scope:** All 8 audit phases (A–H): pipeline lineage, source-metric, formula inventory,
forecast method, FCFF/FCFE correctness, valuation bridge, report number trace, red flags

---

## EXECUTIVE SUMMARY

The calculation model is **structurally sound** with correct FCFF/FCFE formulas, proper
sign conventions, clean data lineage, and a strong no-LLM-in-analytics enforcement.

**4 actionable issues** were found, ranked by severity:

| # | Severity | Issue | Fix effort |
|---|----------|-------|-----------|
| RF-01 | CRITICAL | `sensitivity.py` blend uses old FCFE formula (not P/E Forward) — silent inconsistency | ~10 lines |
| RF-02 | HIGH | `target_pe = 15.0` hardcoded, no peer median computation; 40% blend weight unvalidated | Medium |
| RF-03 | HIGH | No convergence loop in forecast (debt→interest→NI feedback absent) | Large |
| RF-05 | MEDIUM | `implied_price_pe` always null — relative valuation cross-check never runs | Medium |

The remaining 3 flags (RF-04, RF-06, RF-07) are minor UX/documentation issues.

---

## PART 1: WHAT IS CORRECT ✓

### Formulas — All Exact

| Formula | Spec | Implementation | File:Line | Status |
|---------|------|---------------|----------|--------|
| FCFF = EBIT(1−T) + D&A − CAPEX − ΔNWC | CLAUDE.md §6 | `fcff = ebit_after_tax + dep - capex - delta_nwc` | fcff.py:254 | ✓ EXACT |
| WACC from balance sheet D/E | CLAUDE.md §6 | `d_weight = total_debt / total_capital` | fcff.py:185 | ✓ DYNAMIC |
| CAPEX as positive outflow | CLAUDE.md §6 | `capex = abs(fy.capex)` | fcff.py:236 | ✓ FORCED |
| Terminal value = Gordon Growth | CLAUDE.md §6 | `tv = fcff*(1+g)/(wacc-g)` | fcff.py:281 | ✓ EXACT |
| FCFE = NI + D&A − CAPEX − ΔNWC + NetBorrow | CLAUDE.md §6 | `fcfe = ni + dep - capex_pos - delta_nwc + net_borrowing` | fcfe.py:244 | ✓ EXACT |
| FCFE → equity value directly | CLAUDE.md §6 | `equity_val = sum_pv + pv_tv` (no net_debt) | fcfe.py:281 | ✓ NO DOUBLE-SUBTRACT |
| Net debt includes STI | CLAUDE.md §6 | `net_debt = total_debt - cash - st_inv` | net_debt_bridge.py:192 | ✓ STI INCLUDED |
| Net borrowing = new_debt − repayment | CLAUDE.md §6 | `net_borrow = new_borrow - abs(repayment)` | debt_schedule.py:316 | ✓ DIRECT CFS |
| Blend = 60% FCFF + 40% P/E Forward | CLAUDE.md §6 | `FCFF_WEIGHT=0.60, PE_WEIGHT=0.40` | blend.py:23-24 | ✓ EXACT |
| Core EPS + Net Cash variant | CLAUDE.md §6 | `core_eps * target_core_pe + net_cash_per_share` | core_pe_net_cash.py:233 | ✓ EXACT |
| Rating: BUY >20%, SELL <-20%, HOLD else | CLAUDE.md §8 | `if upside > 0.20: MUA` | client_report_view_model.py:733 | ✓ EXACT |

### Data Lineage — Clean

- `FactEntry` has full provenance: 10 fields including `source_tier`, `confidence`, `source_uri`, `ingested_at`
- `FactTable = dict[str, dict[str, FactEntry]]` — no bare floats anywhere in analytics
- Source tier hierarchy enforced: Tier 0 (audited) overrides Tier 3 (API)
- Golden CSV rejection at confidence < 0.80
- DBD 2025FY: 15 metrics, all Tier 0, confidence 0.85–0.95

### LLM Barrier — Absolute

All 19 `backend/analytics/` modules explicitly state: *"All arithmetic is deterministic Python — no LLM involvement."*
LLM output is only used for draft narrative sections. Numbers in the report come
exclusively from locked valuation artifacts produced by Python.

### Blocking Gates — Correctly Implemented

- Missing `total_debt` → FCFF target price blocked (`net_debt_bridge.status = "blocked"`)
- Missing `shares_outstanding` → all per-share prices blocked
- WACC ≤ terminal_growth → FCFF blocked with `INVALID` status
- Re ≤ terminal_growth → FCFE blocked with `INVALID` status
- `is_fcfe_publishable = False` → FCFE target price blocked (informational warning)
- `final_recommendation_approved = False` → rating hidden ("ĐANG HOÀN THIỆN")

---

## PART 2: CRITICAL ISSUES ✗

### RF-01: sensitivity.py blend formula is wrong (CRITICAL)

**Where:** `backend/analytics/sensitivity.py:284`
**Impact:** Silent — analysts reviewing sensitivity tables see different formula than headline price

```python
# sensitivity.py:284 — WRONG (old formula)
blend = 0.60 × Price_FCFF + 0.40 × Price_FCFE

# blend.py:77 — CORRECT (live formula)
Target Price = 0.60 × Price_FCFF + 0.40 × Price_PE_Forward
```

The `blend_sensitivity` matrix in the valuation artifact uses the old 60%/40% FCFE split.
This produces **different numbers** than the headline target price which uses P/E Forward.
An analyst reading: "sensitivity target = X" is reading a number computed from a formula
that is no longer the primary valuation method.

**Fix required:**
```python
# sensitivity.py — change build_blend_sensitivity_table() to:
blend = 0.60 × price_fcff + 0.40 × (eps_fy1 × target_pe)
```

---

### RF-02: target_pe = 15.0 hardcoded, peer median never computed (HIGH)

**Where:** `scripts/run_valuation.py:461`
**Impact:** 40% of the blend (Price_PE_Forward = EPS × target_pe) uses an unvalidated multiple

The system emits a warning but still proceeds:
> "target_pe=15.0x is model default — validate with peer-median P/E before publishing"

CLAUDE.md §6 requires:
- peer_median_pe computed from peer group
- Target P/E = peer median × (1 ± premium/discount) with written rationale
- `peer_multiples_approved` gate must be set

Currently:
- `peer_median_pe` is **never computed** by the system
- `peer_data_source = None` → `implied_price_pe = null` in multiples section
- But `run_valuation.py` still applies 15.0x in the blend regardless

**Fix required:**
Either implement peer median lookup from `pharma_vn_universe.csv`, OR
block `price_pe_forward` in the blend until `peer_multiples_approved = True` in the
assumption gate.

---

### RF-03: No convergence loop in forecast engine (HIGH)

**Where:** `backend/analytics/forecasting.py`
**Impact:** Balance sheet inaccuracy for debt-heavy or rapidly-changing-leverage companies

The circular dependency is not modeled:
```
debt balance → interest expense → net income → retained earnings
→ equity → D/E ratio → WACC → terminal value
```

Each year uses the previous year's debt balance to compute interest, but the resulting
NI and equity do not feed back to revise WACC or the debt schedule within the same
forecast iteration.

**For DBD specifically:** With 175 VND bn debt (modest, net cash company), this gap
is low-impact. For a debt-heavy company, this could materially distort the FCFF.

**Fix required:** 3–5 iteration convergence loop in `forecasting.py`. Documented as TODO.

---

## PART 3: MEDIUM ISSUES

### RF-05: Relative valuation cross-check never runs (MEDIUM)

**Where:** `backend/analytics/multiples.py:103-106`

Every valuation artifact produced to date has:
```json
"implied_price_pe": null,
"relative_valuation_status": "pending_peer_dataset"
```

The `target_pe = 15.0` stored in the artifact is not cross-checked against peers.
The P/E Forward price in the blend is computed from this unvalidated multiple.

**Fix required:** Implement peer data input mechanism, or require analyst to explicitly
provide `target_pe` with rationale before the blend is marked non-draft.

---

## PART 4: PIPELINE ARCHITECTURE SUMMARY

```
CLI Entry         → scripts/run_valuation.py
                    scripts/auto_ingest_official_documents.py
                    scripts/render_report.py

Facts             → FactEntry (10 fields, fully traced)
                    FactTable dict[str, dict[str, FactEntry]]
                    Source tier: 0=audited, 1=verified, 2=semi-official, 3=API

Analytics         → fcff.py, fcfe.py, blend.py, forecasting.py
                    sensitivity.py, ratios.py, net_debt_bridge.py
                    debt_schedule.py, core_pe_net_cash.py
                    ALL: deterministic Python, zero LLM

HITL Gates        → approval_gate.py: 10 flags, 2 mandatory blockers
                    data_quality_passed + final_recommendation_approved

Artifacts         → artifacts/valuation/{ticker}_{ts}_valuation.json

Report            → report_data_loader.py (extracts from artifact only)
                    client_report_view_model.py (typed view model)
                    section_builder.py (8 sections)
                    html_renderer.py → pdf_renderer.py

Export Gate       → export_gate.py (citation coverage, numeric consistency)
```

---

## PART 5: RECOMMENDED FIX ORDER

### P0 — Fix immediately (before next report run)

**RF-01:** Update `sensitivity.py build_blend_sensitivity_table()` to use P/E Forward blend.
- File: `backend/analytics/sensitivity.py:284`
- Change: `blend = 0.60 * price_fcff + 0.40 * price_fcfe` → `0.60 * price_fcff + 0.40 * (eps * pe)`
- Test: `tests/unit/test_sensitivity.py` — verify blend matrix values match `blend.py` output

### P1 — Fix this sprint

**RF-02:** Gate `price_pe_forward` on `peer_multiples_approved`. Add `target_pe` to the
assumption table as a required field (not a default). Block blend if not set by analyst.
- Files: `scripts/run_valuation.py`, `backend/analytics/approval_gate.py`, `backend/analytics/blend.py`

**RF-05:** Implement peer data input. Minimum viable: analyst can provide a JSON file with
`{ticker: {peer_median_pe: X, source: "..."}}`; this unlocks `implied_price_pe` and
`peer_multiples_approved`.

### P2 — Next sprint

**RF-03:** Implement 3-iteration convergence loop in `forecasting.py`. Verify with a
high-leverage test case where the difference is material.

### P3 — Backlog

- RF-04: Add draft annotation showing computed (unapproved) rating to improve analyst UX
- RF-06: Add per-ticker beta lookup from market data
- RF-07: Document ±25% CAGR cap in CLAUDE.md §6 and add to assumptions table

---

## PART 6: FILES AUDITED

| File | Lines | Audit Phase |
|------|-------|------------|
| `backend/analytics/fcff.py` | ~330 | E, F |
| `backend/analytics/fcfe.py` | ~290 | E |
| `backend/analytics/blend.py` | ~150 | F |
| `backend/analytics/sensitivity.py` | ~610 | B, RF-01 |
| `backend/analytics/forecasting.py` | — | D |
| `backend/analytics/debt_schedule.py` | ~501 | E |
| `backend/analytics/net_debt_bridge.py` | ~210 | E |
| `backend/analytics/core_pe_net_cash.py` | ~257 | F |
| `backend/analytics/ratios.py` | ~136 | B |
| `backend/analytics/approval_gate.py` | ~40 | F |
| `backend/analytics/multiples.py` | ~120 | RF-05 |
| `backend/facts/normalizer.py` | ~472 | C |
| `backend/facts/metric_metadata.py` | ~250 | C |
| `backend/reporting/report_data_loader.py` | 1304 | G |
| `backend/reporting/client_report_view_model.py` | ~740+ | F, G |
| `backend/reporting/section_builder.py` | — | G |
| `scripts/run_valuation.py` | ~870 | F, RF-02 |
| `config/dataset/golden/financials/DBD.csv` | — | C |
| `config/dataset/golden/financials/DBD_golden_provenance.json` | — | C |

---

## PART 7: AUDIT FILES PRODUCED

| File | Content |
|------|---------|
| `audits/-1_calculation_lineage_map.md` | End-to-end pipeline map, data flow, HITL points |
| `audits/-1_formula_inventory.md` | Every formula with file:line citations |
| `audits/-1_source_to_metric_audit.md` | FactEntry, source tiers, normalization, DBD data |
| `audits/-1_forecast_method_audit.md` | Per-line-item forecast methods, gaps |
| `audits/-1_fcff_fcfe_audit.md` | FCFF/FCFE verification, net debt, gates |
| `audits/-1_valuation_bridge_audit.md` | Blend, target price, approval, multiples |
| `audits/-1_report_number_trace_audit.md` | Report data loading, number extraction path |
| `audits/-1_red_flag_summary.md` | All 7 red flags with priority ranking |
| `audits/-1_FINAL_CALCULATION_MODEL_AUDIT_REPORT.md` | This document |

---

*Audit completed 2026-06-07. All findings are from read-only inspection of production code.
No code was modified during this audit. Recommended fixes are listed in Part 5.*
