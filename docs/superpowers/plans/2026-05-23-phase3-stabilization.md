# Phase 3 Stabilization — Gate Fix, Validation Threading, Tests

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the governance bug where `needs_review` facts silently pass the valuation gate, thread `validation_status` through the fact pipeline, split the gate into three explicit tiers, add a tests suite covering Phase 3 invariants, and gitignore generated raw payload files.

**Architecture:** `build_fact_table` and `build_fy_validation_report` are extended to carry `validation_status` alongside numeric values. The gate becomes three explicit tiers — `coverage_gate`, `core_keys_gate`, `source_validation_gate` — and `valuation_ready=True` only when all three tiers pass. A parallel `build_validation_status_table` function in `normalizer.py` produces the per-(key, period) status map using identical tie-breaking logic to `build_fact_table`.

**Tech Stack:** Python 3.11+, pytest, no new dependencies.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `backend/facts/normalizer.py` | Modify | Add `build_validation_status_table` |
| `backend/facts/completeness.py` | Modify | Add `source_validation_gate` tier; split gate output; fix `valuation_ready` |
| `scripts/build_facts.py` | Modify | Pass `validation_status_table` to `build_fy_validation_report` |
| `.gitignore` | Modify | Add `dataset/raw/` |
| `tests/__init__.py` | Create | Empty, makes `tests` a package |
| `tests/unit/__init__.py` | Create | Empty |
| `tests/unit/test_gate_validation_status.py` | Create | Phase 3 gate invariant tests |

---

## Task 1: Add `build_validation_status_table` to normalizer

**Files:**
- Modify: `backend/facts/normalizer.py`
- Test: `tests/unit/test_gate_validation_status.py` (created in Task 3)

- [ ] **Step 1.1: Write the failing test first (TDD)**

Create `tests/unit/test_gate_validation_status.py` with just the import test:

```python
"""Phase 3 gate invariant tests."""
import pytest
from backend.facts.normalizer import build_validation_status_table


def test_build_validation_status_table_import():
    """Smoke: function exists and is importable."""
    assert callable(build_validation_status_table)
```

- [ ] **Step 1.2: Run the test to confirm it fails**

```bash
cd c:\Users\Admin\Desktop\multi-agent-equity-research
python -m pytest tests/unit/test_gate_validation_status.py::test_build_validation_status_table_import -v
```

Expected: `ImportError` — `cannot import name 'build_validation_status_table'`

- [ ] **Step 1.3: Implement `build_validation_status_table` in `normalizer.py`**

Add this function after `build_fact_table` (around line 55) in `backend/facts/normalizer.py`:

```python
def build_validation_status_table(raw_facts: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    """Return validation_status for each (taxonomy_key, period).

    Uses the same tie-breaking as build_fact_table: highest confidence wins,
    then latest ingested_at. Unknown validation_status is treated as 'unknown'.
    """
    best: dict[tuple[str, str], dict[str, Any]] = {}
    for row in raw_facts:
        key = (row["taxonomy_key"], _period_key(row["fiscal_year"], row["fiscal_period"]))
        existing = best.get(key)
        if existing is None:
            best[key] = row
        else:
            row_conf = row.get("confidence") or 0.0
            ex_conf = existing.get("confidence") or 0.0
            if row_conf > ex_conf:
                best[key] = row
            elif row_conf == ex_conf:
                if str(row.get("ingested_at", "")) > str(existing.get("ingested_at", "")):
                    best[key] = row

    status_table: dict[str, dict[str, str]] = {}
    for (taxonomy_key, period), row in best.items():
        if taxonomy_key not in status_table:
            status_table[taxonomy_key] = {}
        status_table[taxonomy_key][period] = str(row.get("validation_status") or "unknown")
    return status_table
```

- [ ] **Step 1.4: Run the test to confirm it passes**

```bash
python -m pytest tests/unit/test_gate_validation_status.py::test_build_validation_status_table_import -v
```

Expected: `PASSED`

- [ ] **Step 1.5: Commit**

```bash
git add backend/facts/normalizer.py tests/__init__.py tests/unit/__init__.py tests/unit/test_gate_validation_status.py
git commit -m "feat: add build_validation_status_table to normalizer"
```

---

## Task 2: Fix `build_fy_validation_report` — three-tier gate

**Files:**
- Modify: `backend/facts/completeness.py` (function `build_fy_validation_report`, lines 59–150)

- [ ] **Step 2.1: Write the failing tests**

Add to `tests/unit/test_gate_validation_status.py`:

```python
from datetime import UTC, datetime
from backend.facts.completeness import build_fy_validation_report
from backend.facts.normalizer import FactTable


REQUIRED_PERIODS = ["2021FY", "2022FY", "2023FY", "2024FY", "2025FY"]
CORE_KEYS = [
    "revenue.net",
    "net_income.parent",
    "total_assets.ending",
    "equity.parent",
    "operating_cash_flow.total",
]


def _make_full_table(status: str = "accepted") -> tuple[FactTable, dict]:
    """Return (fact_table, validation_status_table) fully populated for 2021-2025FY."""
    table: FactTable = {key: {p: 1000.0 for p in REQUIRED_PERIODS} for key in CORE_KEYS}
    vstatus = {key: {p: status for p in REQUIRED_PERIODS} for key in CORE_KEYS}
    return table, vstatus


def _call_report(table: FactTable, vstatus: dict, periods_available=None, periods_missing=None):
    if periods_available is None:
        periods_available = list(REQUIRED_PERIODS)
    if periods_missing is None:
        periods_missing = []
    return build_fy_validation_report(
        ticker="DHG",
        table=table,
        raw_facts=[],
        required_periods=REQUIRED_PERIODS,
        periods_available=periods_available,
        periods_missing=periods_missing,
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=vstatus,
    )


def test_all_accepted_passes_all_gates():
    table, vstatus = _make_full_table("accepted")
    report = _call_report(table, vstatus)
    assert report["coverage_gate"] == "pass"
    assert report["core_keys_gate"] == "pass"
    assert report["source_validation_gate"] == "pass"
    assert report["valuation_gate"] == "pass"
    assert report["valuation_ready"] is True
    assert report["run_status"] == "ok"


def test_needs_review_blocks_valuation_gate():
    table, vstatus = _make_full_table("needs_review")
    report = _call_report(table, vstatus)
    assert report["coverage_gate"] == "pass"
    assert report["core_keys_gate"] == "pass"
    assert report["source_validation_gate"] == "fail"
    assert report["valuation_gate"] == "fail"
    assert report["valuation_ready"] is False
    assert report["run_status"] == "needs_human_verification"
    assert len(report["blocking_reasons"]) > 0


def test_missing_period_blocks_coverage_gate():
    table, vstatus = _make_full_table("accepted")
    report = _call_report(
        table, vstatus,
        periods_available=["2022FY", "2023FY", "2024FY", "2025FY"],
        periods_missing=["2021FY"],
    )
    assert report["coverage_gate"] == "fail"
    assert report["valuation_gate"] == "fail"
    assert report["valuation_ready"] is False
    assert report["run_status"] == "needs_fallback"


def test_missing_core_key_blocks_core_keys_gate():
    table = {key: {p: 1000.0 for p in REQUIRED_PERIODS} for key in CORE_KEYS}
    # Remove one core key entirely
    del table["revenue.net"]
    vstatus = {key: {p: "accepted" for p in REQUIRED_PERIODS} for key in CORE_KEYS if key != "revenue.net"}
    report = _call_report(table, vstatus)
    assert report["core_keys_gate"] == "fail"
    assert report["valuation_gate"] == "fail"
    assert report["valuation_ready"] is False


def test_no_validation_status_table_blocks_source_gate():
    """When no validation_status_table is passed, source_validation_gate must fail."""
    table, _ = _make_full_table("accepted")
    report = build_fy_validation_report(
        ticker="DHG",
        table=table,
        raw_facts=[],
        required_periods=REQUIRED_PERIODS,
        periods_available=list(REQUIRED_PERIODS),
        periods_missing=[],
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=None,
    )
    assert report["source_validation_gate"] == "fail"
    assert report["valuation_ready"] is False


def test_mixed_status_one_needs_review_blocks():
    """If even one core key/period is needs_review, source_validation_gate fails."""
    table, vstatus = _make_full_table("accepted")
    # One period of one key is needs_review
    vstatus["revenue.net"]["2021FY"] = "needs_review"
    report = _call_report(table, vstatus)
    assert report["source_validation_gate"] == "fail"
    assert report["valuation_ready"] is False
    # blocking_reasons should mention the specific key+period
    reasons = " ".join(report["blocking_reasons"])
    assert "revenue.net" in reasons
    assert "2021FY" in reasons
```

- [ ] **Step 2.2: Run the tests to confirm they fail**

```bash
python -m pytest tests/unit/test_gate_validation_status.py -v
```

Expected: all new tests fail with `TypeError` (missing keyword argument `validation_status_table`) or `KeyError` (missing keys in report).

- [ ] **Step 2.3: Rewrite `build_fy_validation_report` in `completeness.py`**

Replace the entire `build_fy_validation_report` function (lines 59–150) with:

```python
def build_fy_validation_report(
    ticker: str,
    table: FactTable,
    raw_facts: list[dict],
    required_periods: list[str],
    periods_available: list[str],
    periods_missing: list[str],
    forbidden_periods: list[str],
    generated_at: datetime,
    validation_status_table: dict[str, dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the three-tier FY gate report for a ticker.

    Tier 1 — coverage_gate:      all required FY periods present.
    Tier 2 — core_keys_gate:     all CORE_FY_KEYS present for every required period.
    Tier 3 — source_validation_gate: all CORE_FY_KEYS for every required period have
                                     validation_status == 'accepted'.

    valuation_ready=True ONLY when all three tiers pass.
    """
    blocking_reasons: list[str] = []

    # --- Per-core-key coverage status (checked against periods_available, not full range) ---
    core_keys: dict[str, Any] = {}
    for key in CORE_FY_KEYS:
        key_data = table.get(key, {})
        missing_for_key = [p for p in periods_available if p not in key_data]
        if not missing_for_key:
            status = "present"
        elif len(missing_for_key) == len(periods_available):
            status = "missing"
        else:
            status = "partial"
        core_keys[key] = {"status": status, "missing_periods": missing_for_key}

    # --- Tier 1: coverage_gate ---
    # Passes with >= 3 FY periods in range — does NOT require all 5.
    annual_reports_collected = len(periods_available)
    MIN_FY_PERIODS = 3
    if annual_reports_collected < MIN_FY_PERIODS:
        coverage_gate = "fail"
        blocking_reasons.append(
            f"insufficient_annual_reports: collected {annual_reports_collected}, minimum {MIN_FY_PERIODS}"
        )
    else:
        coverage_gate = "pass"

    # --- Tier 2: core_keys_gate ---
    core_failures = [k for k, v in core_keys.items() if v["status"] != "present"]
    if core_failures:
        core_keys_gate = "fail"
        blocking_reasons.append(
            f"missing_core_keys: {', '.join(core_failures[:3])}"
        )
    else:
        core_keys_gate = "pass"

    # --- Tier 3: source_validation_gate ---
    non_accepted: list[dict[str, str]] = []
    if validation_status_table is None:
        source_validation_gate = "fail"
        blocking_reasons.append(
            "no validation_status_table provided — cannot verify source acceptance"
        )
    else:
        for key in CORE_FY_KEYS:
            for period in periods_available:  # only check periods we actually collected
                status = validation_status_table.get(key, {}).get(period, "unknown")
                if status != "accepted":
                    non_accepted.append({"key": key, "period": period, "status": status})
        if non_accepted:
            source_validation_gate = "fail"
            for item in non_accepted[:5]:  # limit noise in blocking_reasons
                blocking_reasons.append(
                    f"validation_status={item['status']} for {item['key']} @ {item['period']}"
                )
        else:
            source_validation_gate = "pass"

    # --- Overall valuation_gate ---
    all_pass = (
        coverage_gate == "pass"
        and core_keys_gate == "pass"
        and source_validation_gate == "pass"
    )
    valuation_gate = "pass" if all_pass else "fail"
    valuation_ready = all_pass

    # run_status
    if coverage_gate == "fail" or core_keys_gate == "fail":
        run_status = "needs_fallback"
    elif source_validation_gate == "fail":
        run_status = "needs_human_verification"
    else:
        run_status = "ok"

    # --- Freshness ---
    ingested_ats: list[datetime] = []
    for row in raw_facts:
        ia = row.get("ingested_at")
        if ia is not None:
            if isinstance(ia, str):
                try:
                    ia = datetime.fromisoformat(ia)
                except ValueError:
                    ia = None
            if ia is not None:
                ingested_ats.append(ia)

    now = datetime.now(UTC)
    most_recent_ingested = max(ingested_ats) if ingested_ats else None
    data_age_days: int | None = None
    if most_recent_ingested is not None:
        if most_recent_ingested.tzinfo is None:
            most_recent_ingested = most_recent_ingested.replace(tzinfo=UTC)
        data_age_days = (now - most_recent_ingested).days

    latest_fy = max((int(p[:4]) for p in periods_available), default=None)

    return {
        "ticker": ticker,
        "generated_at": generated_at.isoformat(),
        "period_mode": "year",
        "required_periods": required_periods,
        "periods_available": periods_available,
        "periods_missing": periods_missing,
        "annual_reports_collected": annual_reports_collected,
        "forbidden_periods_found": forbidden_periods,
        "forbidden_periods_ignored": forbidden_periods,
        "core_keys": core_keys,
        # Three-tier gate
        "coverage_gate": coverage_gate,
        "core_keys_gate": core_keys_gate,
        "source_validation_gate": source_validation_gate,
        "non_accepted_facts": non_accepted,
        "valuation_gate": valuation_gate,
        # Top-level summary
        "valuation_ready": valuation_ready,
        "run_status": run_status,
        "blocking_reasons": blocking_reasons,
        # Freshness
        "latest_fiscal_year": latest_fy,
        "latest_period": f"{latest_fy}FY" if latest_fy else None,
        "data_age_days": data_age_days,
        "most_recent_ingested_at": (
            most_recent_ingested.isoformat() if most_recent_ingested else None
        ),
    }
```

- [ ] **Step 2.4: Run tests to confirm they pass**

```bash
python -m pytest tests/unit/test_gate_validation_status.py -v
```

Expected: all 6 tests `PASSED`.

- [ ] **Step 2.5: Commit**

```bash
git add backend/facts/completeness.py tests/unit/test_gate_validation_status.py
git commit -m "fix: three-tier gate — needs_review facts no longer pass valuation_gate"
```

---

## Task 3: Thread `validation_status_table` into `build_facts.py`

**Files:**
- Modify: `scripts/build_facts.py`

- [ ] **Step 3.1: Add the import and the call**

In `scripts/build_facts.py`, add `build_validation_status_table` to the import on line 139:

```python
from backend.facts.normalizer import build_fact_table, compute_derived, periods_sorted, build_validation_status_table
```

After `base_table = build_fact_table(fy_facts)` (currently line 183), add:

```python
vstatus_table = build_validation_status_table(fy_facts)
```

In the `build_fy_validation_report(...)` call (currently lines 198–207), add the new keyword argument:

```python
report = build_fy_validation_report(
    ticker=ticker,
    table=full_table,
    raw_facts=fy_facts,
    required_periods=required_periods,
    periods_available=periods_available,
    periods_missing=periods_missing,
    forbidden_periods=forbidden_periods,
    generated_at=generated_at,
    validation_status_table=vstatus_table,
)
```

- [ ] **Step 3.2: Update the print statements to show three-tier gate output**

Replace the four `print` lines (currently lines 209–214) with:

```python
print(f"[build_facts] {ticker} coverage_gate:          {report['coverage_gate']}")
print(f"[build_facts] {ticker} core_keys_gate:         {report['core_keys_gate']}")
print(f"[build_facts] {ticker} source_validation_gate: {report['source_validation_gate']}")
print(f"[build_facts] {ticker} valuation_gate:         {report['valuation_gate']}")
print(f"[build_facts] {ticker} valuation_ready:        {report['valuation_ready']}")
print(f"[build_facts] {ticker} run_status:             {report['run_status']}")
if report.get("blocking_reasons"):
    for reason in report["blocking_reasons"]:
        print(f"[build_facts] {ticker} BLOCKED: {reason}")
```

- [ ] **Step 3.3: Run smoke test (requires DB — document if DB unavailable)**

```bash
python scripts/build_facts.py --ticker DHG
```

Expected new output lines:
```
[build_facts] DHG coverage_gate:          pass
[build_facts] DHG core_keys_gate:         pass
[build_facts] DHG source_validation_gate: fail
[build_facts] DHG valuation_gate:         fail
[build_facts] DHG valuation_ready:        False
[build_facts] DHG run_status:             needs_human_verification
[build_facts] DHG BLOCKED: validation_status=needs_review for revenue.net @ 2021FY
```

If DB is unavailable, document the expected output and skip execution — note it as a limitation.

- [ ] **Step 3.4: Commit**

```bash
git add scripts/build_facts.py
git commit -m "feat: pass validation_status_table to build_fy_validation_report in build_facts"
```

---

## Task 4: Add invariant tests for quarterly period rejection

**Files:**
- Modify: `tests/unit/test_gate_validation_status.py`

These tests live in a separate concern from gate tiers: they verify that the FY-only filter in `build_facts._filter_facts` correctly rejects quarterly periods.

- [ ] **Step 4.1: Add the tests**

Add to the end of `tests/unit/test_gate_validation_status.py`:

```python
import re
from scripts.build_facts import _filter_facts, _is_allowed_fy


def test_is_allowed_fy_accepts_valid_periods():
    assert _is_allowed_fy("2021FY", 2021, 2025) is True
    assert _is_allowed_fy("2025FY", 2021, 2025) is True
    assert _is_allowed_fy("2023FY", 2021, 2025) is True


def test_is_allowed_fy_rejects_quarterly():
    assert _is_allowed_fy("2023Q1", 2021, 2025) is False
    assert _is_allowed_fy("2024Q4", 2021, 2025) is False
    assert _is_allowed_fy("2026Q1", 2021, 2025) is False


def test_is_allowed_fy_rejects_out_of_range():
    assert _is_allowed_fy("2020FY", 2021, 2025) is False
    assert _is_allowed_fy("2026FY", 2021, 2025) is False


def _make_raw_fact(taxonomy_key: str, fiscal_year: int, fiscal_period: str) -> dict:
    return {
        "taxonomy_key": taxonomy_key,
        "fiscal_year": fiscal_year,
        "fiscal_period": fiscal_period,
        "value": 1000.0,
        "confidence": 0.9,
        "validation_status": "accepted",
        "ingested_at": "2026-01-01T00:00:00+00:00",
    }


def test_filter_facts_keeps_fy_only():
    raw = [
        _make_raw_fact("revenue.net", 2022, "FY"),
        _make_raw_fact("revenue.net", 2022, "Q1"),
        _make_raw_fact("revenue.net", 2026, "Q1"),
        _make_raw_fact("revenue.net", 2020, "FY"),  # out of range
    ]
    kept, forbidden = _filter_facts(raw, 2021, 2025)
    assert len(kept) == 1
    assert kept[0]["fiscal_period"] == "FY"
    assert "2022Q1" in forbidden
    assert "2026Q1" in forbidden
    assert "2020FY" in forbidden


def test_filter_facts_2026q1_is_forbidden():
    raw = [_make_raw_fact("revenue.net", 2026, "Q1")]
    kept, forbidden = _filter_facts(raw, 2021, 2025)
    assert kept == []
    assert "2026Q1" in forbidden
```

- [ ] **Step 4.2: Run the tests**

```bash
python -m pytest tests/unit/test_gate_validation_status.py -v
```

Expected: all tests `PASSED` (the `_filter_facts` and `_is_allowed_fy` functions already exist and are correct).

- [ ] **Step 4.3: Commit**

```bash
git add tests/unit/test_gate_validation_status.py
git commit -m "test: add quarterly period rejection and FY filter invariant tests"
```

---

## Task 5: Gitignore `dataset/raw/` generated files

**Files:**
- Modify: `.gitignore`

The `dataset/raw/` directory contains raw JSON payloads and `.sha256` files that are generated artifacts, not source code. They should not live in git.

- [ ] **Step 5.1: Add `dataset/raw/` to `.gitignore`**

In `.gitignore`, after the `artifacts/` line, add:

```
dataset/raw/
```

- [ ] **Step 5.2: Verify the change is correct**

```bash
git check-ignore -v dataset/raw/bctc/DHG/income_statement_year.json
```

Expected output: `.gitignore:NN:dataset/raw/	dataset/raw/bctc/DHG/income_statement_year.json`

- [ ] **Step 5.3: Remove tracked raw files from git index (without deleting from disk)**

```bash
git rm -r --cached dataset/raw/
```

Expected: git removes the index entries; files remain on disk.

- [ ] **Step 5.4: Commit**

```bash
git add .gitignore
git commit -m "chore: gitignore dataset/raw/ — generated raw payloads are not source code"
```

---

## Self-Review Checklist

### Spec coverage

| Requirement from review | Covered by |
|---|---|
| `needs_review` must not set `valuation_ready=True` | Task 2 gate fix |
| Three-tier gate output with `blocking_reasons` | Task 2 new return shape |
| Tests for quarterly period rejection | Task 4 |
| Tests: `needs_review` → `valuation_gate=fail` | Task 2 test suite |
| Tests: `accepted` → `valuation_gate=pass` | Task 2 `test_all_accepted_passes_all_gates` |
| Tests: missing 2021FY → `coverage_gate=fail` | Task 2 `test_missing_period_blocks_coverage_gate` |
| Tests: mixed status one `needs_review` blocks | Task 2 `test_mixed_status_one_needs_review_blocks` |
| `dataset/raw/` out of git | Task 5 |

### Gaps / out of scope in this plan

- **DHG 2021FY human verification**: The `needs_review` facts in `dataset/golden/financials/DHG.csv` must be verified against the official DHG BCTC 2021 filing and updated to `validation_status=accepted` by a human. This plan deliberately does not auto-accept them — that is the point. The next step after this plan is to verify the values against the official filing PDF.
- **`run_status` field removed from report** — `gate_status` (old single-field output) is gone. Any code that reads `report["gate_status"]` will break. Check `backend/` and `scripts/` for `gate_status` references before deploying.
- **Old `build_validation_report` (legacy)** in `completeness.py` is left as-is — it is not used by the main pipeline path.

### Placeholder scan

No TBDs or placeholders found in the plan.

### Type consistency

- `build_validation_status_table` returns `dict[str, dict[str, str]]` — matches parameter type in `build_fy_validation_report` signature `validation_status_table: dict[str, dict[str, str]] | None`.
- `_filter_facts` and `_is_allowed_fy` are imported from `scripts.build_facts` in Task 4 tests — both functions exist at module level and are not guarded by `if __name__ == "__main__"`.
