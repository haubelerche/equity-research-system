# Evaluation Gate Audit — Phase 0

**Date:** 2026-05-30  
**Scope:** Audit all 9 gates in `scripts/evaluate_report.py`. For each gate: what does it actually check, when does it pass silently (false positive), and what is the severity of the gap.

---

## Summary

| Gate | Name | True deterministic? | Silent pass condition | Severity |
|---|---|---|---|---|
| G1 | numeric_consistency | ⚠️ Partial | Empty citation_map → 0 facts checked → pass | HIGH |
| G2 | citation_coverage | ❌ Hollow | `claims` list always empty → never produces critical_fail, just WARN | CRITICAL |
| G3 | valuation_reproducibility | ⚠️ Partial | Empty val_artifact → passes silently | HIGH |
| G4 | stale_data | ✅ Real | Fails if snapshot_as_of missing or >30 days | LOW — but threshold is wrong (30 days instead of 18 months) |
| G5 | unsupported_claims | ✅ Real | Only passes if no forbidden phrases found | OK |
| G6 | user_facing_citation_quality | ❌ Hollow | Empty citation_map → pass; "vnstock API" label NOT in _GENERIC_LABELS | CRITICAL |
| G7 | balance_sheet_identity_check | ⚠️ Partial | No forecast artifact → pass=False but critical_fail=False | MEDIUM |
| G8 | valuation_sanity | ⚠️ Partial | Empty val_artifact → passes silently | HIGH |
| G9 | approval_gate_check | ⚠️ Partial | Empty val_artifact → "No approval_gate" added to issues but pass=True | HIGH |

---

## Gate 1: Numeric Consistency

**Location:** `evaluate_report.py:123–170`

**What it does:** Iterates over `citation_map` keys; for each fact value, searches `report_text` for any number within 5% tolerance via regex.

**Silent pass condition:**
```python
# If citation_map is {} (empty), the for-loop body never executes.
# checked = 0, issues = [], critical = False (0 > 0*0.5 = 0 → False)
# pass = True
```
An empty citation_map — which happens when generate_report fails to load facts from DB — silently passes this gate.

**Additional weakness:** The regex `r"[\d]{1,3}(?:[,.][\d]{3})*(?:[.,][\d]+)?"` matches years (2023, 2024), table row numbers, percentages, and page numbers. A number like "5.2" in "revenue grew 5.2%" will be extracted and potentially matched against a completely unrelated fact value.

**Required fix (per plan):** Gate 4 (renamed in new 6-gate design) must read from `report_claims` table (structured objects), not from regex over rendered Markdown. Regex check is secondary guardrail only.

---

## Gate 2: Citation Coverage

**Location:** `evaluate_report.py:173–210`

**What it does:** Checks `citation_data.get("claims", [])` — a list of extracted quantitative claim objects — against the citation map.

**Critical finding: `claims` is ALWAYS EMPTY.**

In `scripts/generate_report.py`, `_build_citation_map()` returns a `dict` keyed by `{ticker}/{year}FY/{metric}`. The citation JSON artifact is saved as:
```python
citation_artifact = {
    "citation_map": cmap,
    # "claims" key is NEVER added
}
```

When `citation_data.get("claims", [])` returns `[]`, the gate branch at line 178 fires:
```python
if not claims:
    return {
        "pass": False,
        "critical_fail": False,   # ← not critical_fail!
        "issues": ["No quantitative claims extracted — citation coverage cannot be verified (WARN)"],
    }
```

**This gate NEVER produces `critical_fail=True`.** It always returns a soft warning. The overall `any_critical` check therefore never flags citation coverage as blocking. This means a report with zero citations can pass the evaluator's `CRITICAL_FAIL` threshold.

**Required fix (per plan):** Generate `report_claims` as structured objects during report generation. Populate `claims` in the citation artifact. Gate must FAIL (not warn) if `claims` is empty in a report that has quantitative sections.

---

## Gate 3: Valuation Reproducibility

**Location:** `evaluate_report.py:213–250`

**What it does:** Checks snapshot_id consistency between citation map and valuation artifact; checks that DCF intrinsic value exists.

**Silent pass condition:** If `val_artifact = {}` (file not found, loaded as empty dict at line 578):
- `intrinsic = None` → enters the fallback branch
- `blend_target = None` → `blend_target is not None` is False  
- `intentionally_blocked = False` (dcf_warnings is `[]`)
- The `else` branch adds `"DCF intrinsic value missing"` BUT this is only reached if `blend_target is None` AND NOT `intentionally_blocked`:

Actually re-reading the logic at lines 229–240:
```python
if intrinsic is None:
    intentionally_blocked = any("blocked" in w or "INVALID" in w for w in dcf_warnings)
    if blend_target is not None and intentionally_blocked:
        pass  # OK
    elif blend_target is not None:
        pass  # OK — blend is primary
    else:
        issues.append("DCF intrinsic value missing from valuation artifact")
```

If `val_artifact = {}`, then `blend_target = None` and the final `else` fires → `issues = ["DCF intrinsic value missing"]`.

BUT: `critical_fail = any("mismatch" in i for i in issues)` → "mismatch" not in "DCF intrinsic value missing" → `critical_fail = False` → `pass = True` because `pass = len(issues) == 0` is False but `critical_fail = False`.

Wait — `pass = len(issues) == 0` means if issues is non-empty then `pass=False`. Let me re-read:

```python
return {
    "pass": len(issues) == 0,
    "critical_fail": any("mismatch" in i for i in issues),
}
```

So `pass=False` when val_artifact is empty (because "DCF intrinsic value missing" is added). This gate does NOT silently pass on empty val_artifact — it returns `pass=False, critical_fail=False` (WARN level). This is actually acceptable behavior, but the WARN does not block export.

**Real weakness:** The gate does not check `formula_version`, `input_fact_ids`, or `canonical_version` — it cannot verify reproducibility, only that a value exists.

---

## Gate 4: Stale Data Detection

**Location:** `evaluate_report.py:253–309`

**What it does:** Checks `val_artifact.get("snapshot_as_of", "")` against a 30-day threshold; also checks max fiscal year lag.

**Assessment:** This is one of the more honest gates. It fails (`pass=False`) when:
- `snapshot_as_of` is missing
- Snapshot is older than 30 days
- Max fiscal year is 2+ years behind current year

**Threshold issue:** `_STALE_THRESHOLD_DAYS = 30` (line 49). The plan requires 18 months for current/latest period claims, not 30 days. A 30-day threshold means the evaluation fails immediately after any run more than a month old, even for a valid historical research report. This threshold is too aggressive for report snapshots.

The fiscal year lag check is correct: `lag > 2` years → issue. But it warns rather than fails for `lag == 2`.

**Required fix (per plan):** Distinguish freshness by claim type: current period claims → 18 months; historical FY facts → not stale if tied to final filing; market price → 5 business days.

---

## Gate 5: Unsupported Claims (Forbidden Phrases)

**Location:** `evaluate_report.py:403–418`

**Assessment:** This gate is purely deterministic and correctly implemented. It scans report Markdown for 8 forbidden regex patterns. `critical_fail=True` if any match.

**Minor gaps:**
- The phrase list does not include English variants like "guaranteed profit", "sure thing", "100% upside"
- Does not check for causal language tied to `contextual_event` catalyst (required by new Gate 6)

**Required fix (per plan):** Add causal language detection (`"do", "khiến", "vì", "bởi vì", "dẫn đến"`) linked to events that have `causality_level=contextual_event`.

---

## Gate 6: User-Facing Citation Quality

**Location:** `evaluate_report.py:312–341`

**What it does:** Checks if `source_title` is in a hardcoded set of generic labels; checks if `source_uri` is empty.

**Critical finding: "Báo cáo tài chính (vnstock API)" is NOT in `_GENERIC_LABELS`.**

```python
_GENERIC_LABELS = {
    "dữ liệu tài chính canonical",
    "canonical financial facts",
    "nguồn không xác định",
}
```

The most common citation label in every DHG report — `"Báo cáo tài chính (vnstock API)"` (set at `generate_report.py:81`) — is **not in this set**. Therefore every citation with this label passes Gate 6 as if it were a real named source document.

**Silent pass condition:** If citation_map is empty (`{}`):
- `checked = 0`, `issues = []`
- `pass = True`, `critical_fail = False` (0 > 0*0.5 = 0 → False)

This gate always passes on empty citation maps AND on the most common citation label used in production reports.

**Required fix (per plan):** 
1. Add `"Báo cáo tài chính (vnstock API)"` and all entries from `_SOURCE_TYPE_LABEL` to the blocked labels list.
2. Gate must fail if `source_tier` is missing or `source_tier >= 3` for material metrics.
3. Gate must verify `source_title` references a real document name (not a provider label).

---

## Gate 7: Balance Sheet Identity Check

**Location:** `evaluate_report.py:351–400`

**What it does:** Loads `artifacts/forecast/` and checks `total_assets == equity + debt + other_liabilities` per forecast year.

**Assessment:** Functionally correct for what it does. Returns `pass=False, critical_fail=True` if identity is violated. However:
- Returns `pass=False, critical_fail=False` if no forecast artifact — this is a soft failure, not a blocker
- This gate only checks the forecasted balance sheet, not the historical one

---

## Gate 8: Valuation Sanity

**Location:** `evaluate_report.py:421–478`

**What it does:** Compares simplified DCF vs FCFF/FCFE blend price; flags >50% divergence as critical.

**Silent pass condition:** If `val_artifact = {}`:
```python
dcf_base_price = None
blend_price = None
# No issues added (both conditions require non-None prices)
# pass = True (no critical issues)
```

Also: if only simplified DCF exists and blend is absent (which is a valid state for early-stage reports), the gate only adds an issue if DCF > 2x current price. If current_price is also None, no issues are added.

**Required fix:** Gate must explicitly check for missing artifact rather than silently passing.

---

## Gate 9: Approval Gate Status

**Location:** `evaluate_report.py:481–541`

**What it does:** Checks ticker consistency, blend draft flag, and approval gate status from valuation artifact.

**Silent pass condition:** If `val_artifact = {}`:
```python
artifact_ticker = ""    # → no mismatch check fires (empty string skip)
blend_block = {}        # → is_draft_only = False → no issue
gate_status = ""        # → fires "No approval_gate found" issue

# pass = len([i for i in issues if "mismatch" in i or "BLOCKED" in i]) == 0
# "No approval_gate found" does not contain "mismatch" or "BLOCKED"
# → pass = True
```

A report evaluated against an empty/missing valuation artifact passes Gate 9. This means the approval gate check passes even when there is no approval record at all.

**Required fix (per plan):** `pass` should be `False` if `gate_status` is missing or empty. "No approval_gate found" is a blocking condition, not a warning.

---

## Summary: Gates That Cannot Block Export Even When They Should

| Gate | Condition | Current behavior | Required behavior |
|---|---|---|---|
| G1 | No facts in citation_map | `pass=True` | `pass=False` (no facts to verify = cannot confirm correctness) |
| G2 | No `claims` in citation artifact | `pass=False, critical_fail=False` (WARN only) | `pass=False, critical_fail=True` for report with quantitative sections |
| G6 | "vnstock API" citation label | `pass=True` (label not in blocked set) | `pass=False` (Tier 3 label without document name) |
| G6 | Empty citation_map | `pass=True` | `pass=False` |
| G8 | Empty val_artifact | `pass=True` | `pass=False, critical_fail=False` at minimum |
| G9 | Empty val_artifact | `pass=True` | `pass=False` ("no approval_gate" is blocking, not a warning) |

---

## Quantified Gate Status (worst case: DHG report with no DB connection)

| Gate | Would block export? | Actual behavior without DB |
|---|---|---|
| G1 | No | Passes (empty citation map) |
| G2 | No | Warns only (never critical_fail) |
| G3 | No | Warns (pass=False but not critical) |
| G4 | No | Warns (snapshot_as_of missing = pass=False but not critical) |
| G5 | No | Passes (no forbidden phrases in empty report) |
| G6 | No | Passes (empty citation map) |
| G7 | No | Warns (no forecast artifact = pass=False but not critical) |
| G8 | No | Passes (empty val_artifact) |
| G9 | No | Passes (empty val_artifact, "no approval_gate" not blocking) |

**Conclusion:** In the worst case (missing DB connection, empty artifacts), zero of the 9 gates would block export. The system would print `OVERALL: WARN` and the report would be publishable. This confirms the evaluation layer is evaluating structure, not truth.
