T# DBD Report Rendering Regression Fix

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restore the full professional report that worked on 2026-06-03 — the current build shows "CẦN CHUYÊN VIÊN RÀ SOÁT" instead of the full SELL report with target price, narrative, and financial tables.

**Architecture:** Two nested regressions. Primary: `_report_display_governance()` in `client_report_view_model.py` enforces `is_publishable=True` for *both* `analyst_draft` and `client_final` modes. Since `valuation_result.json` always has `is_publishable=False` (because `blend.is_draft_only=True`), this causes `vm.target_price=None` → `_is_publishable(vm)=False` → `_review_dashboard_pages()` called → "CẦN CHUYÊN VIÊN RÀ SOÁT" template. Fix: analyst_draft bypasses the gate, client_final keeps it strict. Secondary: valuation numbers shifted (FCFF/FCFE gap now 45%) — diagnosed in Task 5, not yet fixed.

**Tech Stack:** Python, `backend/reporting/client_report_view_model.py`, `client_section_builder.py`, `render_report.py`, pytest.

---

## Root Cause Trace (verified)

```
render_report.py --ticker DBD --allow-latest-artifacts
  → build_client_report_view_model(ticker, "analyst_draft", ...)
    → _report_display_governance("analyst_draft", val_result, blend)
      val_result["is_publishable"] = False              ← always False
      blend["is_draft_only"]       = True               ← always True
      blend["valuation_gap_pct"]   = 0.453 > 0.25      ← gap check fires
      → approved_for_display = False                    ← BUG: analyst_draft treated same as client_final
      → target_price = None, upside = None
    → vm.target_price = None
    → vm.display_blocking_reasons = ["blend_is_draft_only", "valuation_gap_gt_25pct", ...]
  → build_client_report_sections(vm)
    → _is_publishable(vm) = False  (vm.target_price is None)
    → _review_dashboard_pages(vm)  ← renders "CẦN CHUYÊN VIÊN RÀ SOÁT"
```

**Correct behavior for analyst_draft:** always show computed numbers with draft caveats.  
**Correct behavior for client_final:** block until `is_publishable=True`.

---

## File Map

| File | Action | What changes |
|------|--------|--------------|
| `backend/reporting/client_report_view_model.py:651-685` | Modify | `_report_display_governance()` — analyst_draft bypasses gate |
| `tests/unit/test_client_report_view_model.py` | Modify | add two regression tests (analyst_draft shows target; client_final still blocks) |

---

## Task 1: Write failing regression test

**Files:**
- Modify: `tests/unit/test_client_report_view_model.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/unit/test_client_report_view_model.py`:

```python
class TestReportDisplayGovernance:
    """Regression guard: analyst_draft must not blank target_price when is_publishable=False."""

    _val_result_blocked = {"is_publishable": False, "current_price": 50200, "target_price": 27444}
    _blend_draft = {
        "is_draft_only": True,
        "current_price_vnd": 50200.0,
        "target_price_dcf_vnd": 27444.0,
        "upside_pct": -0.453,
        "valuation_gap_pct": 0.45,
    }

    def test_analyst_draft_shows_target_price_when_not_publishable(self):
        from backend.reporting.client_report_view_model import _report_display_governance
        result = _report_display_governance("analyst_draft", self._val_result_blocked, self._blend_draft)
        assert result["target_price"] == 27444.0, (
            "analyst_draft must show computed target price even when is_publishable=False"
        )
        assert result["approved_for_display"] is True
        assert result["recommendation"] == "BÁN"
        assert result["blocking_reasons"] == []

    def test_client_final_blocks_target_price_when_not_publishable(self):
        from backend.reporting.client_report_view_model import _report_display_governance
        result = _report_display_governance("client_final", self._val_result_blocked, self._blend_draft)
        assert result["target_price"] is None, (
            "client_final must block target_price when is_publishable=False"
        )
        assert result["approved_for_display"] is False
        assert "valuation_result_not_publishable" in result["blocking_reasons"]
```

- [ ] **Step 2: Run to confirm it fails**

Run: `python -m pytest tests/unit/test_client_report_view_model.py::TestReportDisplayGovernance -v`
Expected output:
```
FAILED tests/unit/test_client_report_view_model.py::TestReportDisplayGovernance::test_analyst_draft_shows_target_price_when_not_publishable
```

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/unit/test_client_report_view_model.py
git commit -m "test(report): add failing regression test — analyst_draft must show target price"
```

---

## Task 2: Fix `_report_display_governance()` in client_report_view_model.py

**Files:**
- Modify: `backend/reporting/client_report_view_model.py:651-685`

- [ ] **Step 1: Apply the fix**

Replace the function body of `_report_display_governance()` (lines 651-685).  
**Old code** (the broken part — the last 6 lines before the return):
```python
    approved_for_display = is_publishable and not reasons
    current, target, upside = _market_price_inputs(mode, val_result, blend)
    if not approved_for_display:
        target = None
        upside = None

    return {
        "approved_for_display": approved_for_display,
        "current_price": current,
        "target_price": target,
        "upside": upside,
        "recommendation": _recommendation(upside, mode, approved_for_display),
        "blocking_reasons": sorted(set(reasons)),
    }
```

**New code:**
```python
    # analyst_draft: show computed numbers always; blocking reasons are informational
    #   warnings for the analyst, not gates. client_final enforces all gates.
    if mode == "analyst_draft":
        approved_for_display = True
        blocking_reasons: list[str] = []
    else:
        approved_for_display = is_publishable and not reasons
        blocking_reasons = sorted(set(reasons))

    current, target, upside = _market_price_inputs(mode, val_result, blend)
    if not approved_for_display:
        target = None
        upside = None

    return {
        "approved_for_display": approved_for_display,
        "current_price": current,
        "target_price": target,
        "upside": upside,
        "recommendation": _recommendation(upside, mode, approved_for_display),
        "blocking_reasons": blocking_reasons,
    }
```

- [ ] **Step 2: Run the regression test suite**

Run: `python -m pytest tests/unit/test_client_report_view_model.py -v`
Expected: ALL PASS including both new tests

- [ ] **Step 3: Run broader unit tests**

Run: `python -m pytest tests/unit/ -v --tb=short 2>&1 | tail -30`
Expected: no new failures

- [ ] **Step 4: Commit**

```bash
git add backend/reporting/client_report_view_model.py
git commit -m "fix(report): analyst_draft always shows computed target price; client_final enforces is_publishable gate"
```

---

## Task 3: End-to-end render verification

**Files:**
- Run: `scripts/render_report.py`
- Read: `artifacts/reports_html/DBD_report.html` (output)

- [ ] **Step 1: Render the report**

Run:
```bash
python scripts/render_report.py --ticker DBD --allow-latest-artifacts
```

Expected console output:
```
[ctx] DBD: mode=analyst_draft current=50,200 target=27,444 upside=-45.3% recommendation=BÁN
[html] saved: artifacts/reports_html/DBD_report.html
```
(Target price will be 27,444 — different from the 2026-06-03 report's 30,409. This is a secondary issue addressed in Task 5.)

- [ ] **Step 2: Verify HTML content**

Run:
```python
html = open("artifacts/reports_html/DBD_report.html", encoding="utf-8").read()
assert "CẦN CHUYÊN VIÊN RÀ SOÁT" not in html, "Review template must not appear"
assert "BÁN" in html, "SELL rating must appear"
assert "Doanh thu thuần" in html, "Financial table must appear"
assert "Tăng trưởng doanh thu" in html, "Forecast table must appear"
assert "27,444" in html or "27.444" in html, "Target price must appear"
print("PASS: full report rendered correctly")
```

Run: `python -c "<above script>"`
Expected: `PASS: full report rendered correctly`

- [ ] **Step 3: Verify client_final still blocks**

Run:
```bash
python scripts/render_report.py --ticker DBD --allow-latest-artifacts --mode client_final 2>&1 | head -5
```
Expected: either exits with error or shows `target=—` (blocked), confirming the gate still enforces for client_final.

---

## Task 4: Regression guard — confirm all tickers still render

**Files:**
- Run: `scripts/render_report.py` for other tickers

- [ ] **Step 1: Spot-check DHG**

Run:
```bash
python scripts/render_report.py --ticker DHG --allow-latest-artifacts 2>&1 | grep "\[ctx\]"
```
Expected: shows a target price (not `target=—`), confirming DHG also benefits from the fix

- [ ] **Step 2: Commit if all clear**

No code change. If a ticker shows unexpected output, investigate before committing.

---

## Task 5: Diagnose secondary regression — valuation gap 45% (target: 27,444 vs ref: 30,409)

> This task is **diagnostic only** — no code changes. Findings will determine if a follow-up plan is needed.

**Files:**
- Read: `artifacts/forecast/DBD_*_fcff.json` (latest)
- Read: `artifacts/forecast/DBD_*_fcfe.json` (latest)
- Read: `artifacts/valuation_results/20260603T052954_DBD_valuation_result.json` (reference)

- [ ] **Step 1: Compare current vs reference valuation numbers**

Run:
```python
import json, pathlib

old = json.loads(pathlib.Path("artifacts/valuation_results/20260603T052954_DBD_valuation_result.json").read_text())
new_files = sorted(pathlib.Path("artifacts/forecast").glob("DBD_*_fcff.json"))
new_fcff = json.loads(new_files[-1].read_text()) if new_files else {}
new_files_e = sorted(pathlib.Path("artifacts/forecast").glob("DBD_*_fcfe.json"))
new_fcfe = json.loads(new_files_e[-1].read_text()) if new_files_e else {}

print("=== Reference (2026-06-03) ===")
print("target_price:", old.get("target_price"))
print("blend:", old.get("blend", {}).get("target_price"))

print("=== Current ===")
print("FCFF target:", new_fcff.get("target_price_vnd"))
print("FCFE target:", new_fcfe.get("target_price_vnd"))
print("FCFF net_debt:", new_fcff.get("net_debt"))
print("FCFF shares_mn:", new_fcff.get("shares_mn"))
print("FCFF wacc:", new_fcff.get("wacc"))
```

- [ ] **Step 2: Identify the top driver of the gap**

Run:
```bash
git log --oneline -- backend/analytics/fcff.py backend/analytics/fcfe.py backend/analytics/forecasting.py backend/analytics/shares.py backend/analytics/debt_schedule.py | head -10
```
Expected: shows which commits touched the valuation engines since 2026-06-03

- [ ] **Step 3: Document findings in a follow-up note**

Write a brief comment in memory or note what changed. Decide if a follow-up plan is needed to reconcile the valuation numbers with the 2026-06-03 reference.

---

## Self-Review

**Spec coverage:**
- ✅ Primary regression (review template): Tasks 1-3
- ✅ Client-final gate preserved: Task 2 test + Task 3 Step 3
- ✅ Multi-ticker regression check: Task 4
- ✅ Secondary valuation gap: Task 5 (diagnostic)

**No placeholders:** all code is complete.

**Type consistency:** `_report_display_governance()` return type unchanged (`dict[str, Any]`). `blocking_reasons` field always `list[str]`.
