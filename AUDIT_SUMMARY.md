# AUDIT SUMMARY — DHG Report Quality Gate Review

**Date:** 2026-05-26  
**Report audited:** `reports/DHG_20260526T073554_full_report.md`  
**Evaluation artifact:** `artifacts/evaluation/DHG_20260526T073736_evaluation.json`  
**Auditor:** Internal automated review

---

## Pass/Fail Table

| # | Finding | Priority | Verdict | File:Line |
|---|---------|----------|---------|-----------|
| 1 | Citation footnotes: always "Dữ liệu tài chính canonical" — source_title/URI/table/excerpt missing | **P0** | **FAIL** | `generate_report.py:141`, `snapshot.py:151-167` |
| 2 | `_source_title()` can never match prefix patterns (source_id is SHA-256 hash, not a name string) | **P0** | **FAIL** | `generate_report.py:134-141` |
| 3 | Balance sheet forecast identity: `total_assets = current_equity + current_debt` ignores non-debt liabilities | **P0** | **FAIL** | `forecasting.py:314` |
| 4 | Gate 2 (citation_coverage) false-pass: returns 100% if `claims=[]` | **P1** | **FALSE-PASS** | `evaluate_report.py:174-180` |
| 5 | Gate 4 (stale_data) false-pass: checks snapshot run date, not financial data vintage | **P1** | **FALSE-PASS** | `evaluate_report.py:244-250` |
| 6 | FCFF sign convention | **P1** | **PASS** (correct) | `fcff.py:181-195` |
| 7 | Peer multiples are hardcoded defaults (15x PE, 10x EV/EBITDA) — no real peer data | **P1** | **WARN** | `run_valuation.py`, `multiples.py` |
| 8 | Six evaluation gates missing | **P1** | **FAIL** | `evaluate_report.py` |
| 9 | Forecast assumptions not exported as standalone artifact | **P2** | **WARN** | `generate_report.py` |
| 10 | `generate_report.py` is ~900 lines — monolithic | **P2** | **WARN** | `generate_report.py` |

---

## P0 — Critical Failures

### P0-1 & P0-2: Citation Quality — All Footnotes Are Database-Only

**What the report shows:**
```
[^revenue_net_2022]: **Doanh thu thuần** — 4,676.0 tỷ VND, kỳ 2022FY.
Nguồn: _Dữ liệu tài chính canonical_. (Internal: fact_id=4)
```

**What is required (user standard):**
- `source_title` — e.g., "Báo cáo tài chính Q4/2022 DHG"
- `publisher / source_type` — e.g., "vnstock API / HNX filing"
- `period` — 2022FY ✓ (present)
- `table / section` — e.g., "Kết quả kinh doanh / Doanh thu"
- `original line item label` — e.g., "3. Doanh thu bán hàng và cung cấp dịch vụ"
- `excerpt / value_original` — the raw value as it appears in the source
- `source_url / file_path` — e.g., `data/raw/DHG_...json`
- `internal lineage` — fact_id ✓ (present), but **source_version_id missing**

**Root cause (two bugs in chain):**

**Bug A — `_source_title()` always returns fallback** (`generate_report.py:134-141`):
```python
def _source_title(source_id: str) -> str:
    for prefix, label in _SOURCE_TITLE_MAP.items():
        if prefix in source_id.lower():   # source_id is a SHA-256 hex string
            return label                   # "vnstock_finance" is NEVER in a SHA-256 hash
    return "Dữ liệu tài chính canonical"  # always reached
```
The prefix patterns (`"vnstock_finance"`, `"golden_csv"`, `"syn_facts"`) are designed to match a descriptive source name, but `source_id` is a SHA-256 hash — so the fallback is always returned.

**Bug B — `load_snapshot_facts()` does not JOIN `ingest.sources`** (`snapshot.py:151-167`):
```sql
SELECT ff.id, ff.ticker, ff.fiscal_year, ff.line_item_code, ff.value, ff.unit,
       ff.source_id, ...     -- only the hash; no JOIN to ingest.sources
FROM research.snapshot_items si
JOIN fact.financial_facts ff ON ff.id = si.item_id::BIGINT
WHERE si.snapshot_id = %s
```
Fields available in `ingest.sources` but not fetched: `source_title`, `source_uri`, `source_type`, `published_at`, `fiscal_year`, `reliability_tier`.

**Gate impact:** `citation_coverage` gate PASSes because it only checks `key in cmap` (fact_id presence), not whether the displayed citation is user-readable. This is a false-pass — the evaluation artifact shows `"pass": true` but the citations fail user-facing quality.

**Required fix:**
1. Add JOIN to `ingest.sources` in `load_snapshot_facts()` SQL query
2. Replace SHA-256 prefix matching in `_source_title()` with actual `source_type` field from DB
3. Add `source_uri`, `published_at`, `table_section`, `original_label` to citation footnote format
4. Add new gate `user_facing_citation_quality` that validates these fields are non-null and non-generic

---

### P0-3: Balance Sheet Forecast Violates Accounting Identity

**Location:** `forecasting.py:313-314`

```python
# Simple balance sheet: equity grows by net income (no dividends in MVP)
current_equity = current_equity + net_income
total_assets = current_equity + current_debt  # simplified
```

**The accounting identity:** `total_assets = total_liabilities + total_equity`

**The bug:** The code equates `total_liabilities ≡ total_debt`, ignoring all other liabilities (trade payables, accrued expenses, deferred revenues, taxes payable, etc.).

**Magnitude of error for DHG (approximate):**
- Historical 2025FY: total_assets ≈ 5,700 tỷ, equity ≈ 3,000 tỷ, total_debt ≈ 500 tỷ
- Code computes: `total_assets = 3,000 + 500 = 3,500 tỷ` (understated by ~2,200 tỷ = 39%)
- A reader comparing the forecast balance sheet to historical would see a discontinuity of 39%

**Why it still runs without error:** Python does not enforce the accounting identity. The model simply produces wrong numbers silently.

**Required fix (two options):**
- **Option A (minimal):** Add `other_liabilities` as constant from latest historical balance sheet (`total_assets - equity - total_debt`), carry it forward. `total_assets = current_equity + current_debt + other_liabilities`.
- **Option B (correct):** Add a `balance_sheet_identity_check` gate in `evaluate_report.py` that verifies `|total_assets - (total_liabilities + total_equity)| < 1 tỷ` for every forecast year, and fail if violated.

---

## P1 — High Priority

### P1-1: Gate 2 (citation_coverage) False-Pass on Empty Claims

**Location:** `evaluate_report.py:174-180`

```python
def _check_citation_coverage(citation_data: dict) -> dict:
    claims = citation_data.get("claims", [])
    if not claims:
        return {
            "coverage_ratio": 1.0,
            "pass": True,     # ← ALWAYS PASSES if no claims extracted
            ...
        }
```

If the citation artifact has no `"claims"` list (or an empty one), the gate returns 100% coverage as PASS. Since the citation_data is generated by `_build_citation_map()` which does not extract sentence-level quantitative claims (it builds a lookup dict, not a claim list), the `"claims"` key in the saved JSON may be missing entirely.

**Required fix:** If `claims` is empty, return WARN (not PASS) and note "No claims extracted — cannot verify coverage."

---

### P1-2: Gate 4 (stale_data) Checks Run Date, Not Data Vintage

**Location:** `evaluate_report.py:239-260`

```python
snap_as_of = val_artifact.get("snapshot_as_of", "")
...
snap_date = date.fromisoformat(snap_as_of)
age_days = (today - snap_date).days
if age_days > 30:
    issues.append(...)
```

`snapshot_as_of` is the date the pipeline was run (today = 2026-05-26). It is always fresh. But the **underlying financial data** covers FY2021–FY2025. If the most recent audited period is 2025FY and it was filed 6 months ago, the user deserves to see: "Latest financial period: 2025FY (filed ~Nov 2025)."

**Required fix:** Add check on the latest `fiscal_year` in the fact snapshot vs. the current year. Flag if `current_year - max_fiscal_year > 1`.

---

### P1-3: FCFF Sign Convention — PASS (No Bug)

**Verified:** `fcff.py:181-195`
```python
capex = abs(fy.capex) if fy.capex is not None else None  # positive magnitude
fcff = ebit_after_tax + dep - capex - delta_nwc           # subtracts correctly
```
`ForecastYear.capex` is stored as negative (convention `capex = -revenue * capex_to_rev`). `abs()` extracts the positive magnitude. Then FCFF subtracts it. **Formula is correct: FCFF = EBIT(1-T) + D&A − CAPEX − ΔNWC.**

The FCFFYear object stores `capex=(-capex)` (i.e., negative) for display in the table, which is fine as a sign convention for the output table.

---

### P1-4: Peer Multiples Are Hardcoded Defaults

Both `target_pe = 15x` and `target_ev_ebitda = 10x` used in `multiples.py` are analyst-sector defaults, not derived from a real peer dataset (IMP, DMC, TRA, DBD actual trailing multiples). The report presents these as "Valuation multiples" without disclosing that they are assumed, not computed from peers.

**Required fix:** Either (a) compute median trailing PE/EV-EBITDA from fact-table data for the 5-ticker peer group, or (b) clearly label in the report: "Assumed sector multiple — not derived from peer data."

---

### P1-5: Six Missing Evaluation Gates

None of the following gates exist in `evaluate_report.py`:

| Gate | What it checks |
|------|---------------|
| `user_facing_citation_quality` | Every footnote has non-null source_title, source_uri ≠ SHA hash, non-generic label |
| `qualitative_evidence_grounding` | Evidence section quotes come from real chunks in DB, not hallucinated |
| `forecast_assumption_completeness` | All 7 drivers (revenue_growth, gross_margin, sga_to_rev, dep_to_rev, capex_to_rev, tax_rate, interest_to_rev) are logged with method + source_periods |
| `peer_dataset_validation` | Peer multiples are labelled as assumed/default if not computed from real data |
| `balance_sheet_identity_check` | `|total_assets - (total_liabilities + total_equity)| < 1 tỷ` for all forecast years |
| `approval_status_consistency` | Report approval_status matches latest `research.run_approvals` record |

---

## P2 — Low Priority

### P2-1: Forecast Assumptions Not Saved as Standalone Artifact

`ForecastArtifact.drivers` is embedded inside the valuation JSON, not saved separately. The user requested a standalone `artifacts/forecast/DHG_..._forecast_assumptions.json` with:
```json
{
  "ticker": "DHG",
  "generated_at": "...",
  "historical_periods_used": ["2021FY", "2022FY", ...],
  "drivers": {
    "revenue_growth": {"method": "historical_cagr", "value": 0.08, "source_periods": [...], "capped": true},
    "gross_margin": {"method": "historical_median", "value": 0.46, "source_periods": [...]},
    ...
  }
}
```

### P2-2: generate_report.py Too Large (~900 Lines)

The file combines: data loading, citation building, ratio table formatting, forecast table rendering, FCFF section, risk table, appendix generation, evaluation summary table. Should be split into `backend/reporting/` modules as per CLAUDE.md Section 6.

---

## Required Code Changes (Prioritized)

### P0 Fixes

**Fix 1 — Citation SQL JOIN** (`backend/dataops/snapshot.py:151-167`)  
Add JOIN to `ingest.sources` to fetch `source_title`, `source_uri`, `source_type`, `published_at`:
```sql
SELECT ff.id, ff.ticker, ff.fiscal_year, ff.line_item_code, ff.value, ff.unit,
       ff.source_id, ff.connector_version, ff.validation_status, ff.confidence, ff.ingested_at,
       s.source_title, s.source_uri, s.source_type, s.published_at, s.reliability_tier
FROM research.snapshot_items si
JOIN fact.financial_facts ff ON ff.id = si.item_id::BIGINT
LEFT JOIN ingest.sources s ON s.source_id = ff.source_id
WHERE si.snapshot_id = %s AND si.item_type = 'financial_fact'
ORDER BY ff.fiscal_year, ff.line_item_code
```

**Fix 2 — Footnote format** (`generate_report.py:200-203`)  
Use the actual `source_title`, `source_uri`, `source_type` fields from the fact dict (after Fix 1):
```
[^metric_2022]: **Doanh thu thuần** — 4,676.0 tỷ VND, kỳ 2022FY.
Nguồn: _Báo cáo tài chính (vnstock API)_ | Loại: income_statement | Năm: 2022
Chi tiết: source_uri=vnstock://DHG/income/2022 | Độ tin cậy: tier 1
(Internal: fact_id=4 | source_id=abc123...)
```

**Fix 3 — Balance sheet identity** (`forecasting.py:313-314`)  
Carry forward residual non-debt liabilities:
```python
# Compute once from latest historical
other_liabilities = start_assets - start_equity - start_debt  # constant carry-forward
...
# Inside the year loop:
current_equity = current_equity + net_income
total_liabilities = current_debt + other_liabilities
total_assets = current_equity + total_liabilities
```

### P1 Fixes

**Fix 4 — Gate 2 no-claims guard** (`evaluate_report.py:174-180`)  
Return WARN instead of PASS when claims list is empty.

**Fix 5 — Gate 4 data vintage check** (`evaluate_report.py:236-261`)  
Add fiscal year vintage check: warn if `current_year - max_fiscal_year > 1`.

**Fix 6 — Add 6 missing gates** (`evaluate_report.py`)  
Add `balance_sheet_identity_check` and `user_facing_citation_quality` at minimum.

**Fix 7 — Label peer multiples** (`generate_report.py` multiples section)  
Add footnote: "PE múltiplo giả định 15x — chưa tính từ dữ liệu peer thực tế."

---

## Gate Verdict Summary

| Gate | Stated Result | True Result | Reason |
|------|--------------|-------------|--------|
| numeric_consistency | PASS | WARN | Regex number matching is loose; checks structured state, not report prose correctness |
| citation_coverage | PASS | **FALSE-PASS** | Claims list is empty → always 100%; source display is DB-only |
| valuation_reproducibility | PASS | PASS | Snapshot ID cross-check works correctly |
| stale_data | PASS | **FALSE-PASS** | Checks run date (today), not financial data vintage |
| unsupported_claims | PASS | PASS | Forbidden phrase scan is correct |
| user_facing_citation_quality | (missing) | **FAIL** | Would fail: all citations are SHA hash + "canonical" label |
| balance_sheet_identity_check | (missing) | **FAIL** | Would fail: total_assets understated ~39% vs accounting identity |

**True overall status: FAIL** (2 existing false-pass gates + 2 new gates would fail hard)
