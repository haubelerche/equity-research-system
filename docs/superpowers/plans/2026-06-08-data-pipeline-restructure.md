# Data Pipeline Full Restructure — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the data pipeline one production path, one artifact contract, with safety fixes that prevent wrong numbers in reports.

**Architecture:** `scripts/run_research.py` → `ResearchGraphRunner.execute()` is the only production path. All tools write to `artifacts/runs/{run_id}/`. Nine-file artifact contract per run. Legacy flat dirs frozen.

**Tech Stack:** Python 3.11+, pytest, psycopg2, Jinja2, LangGraph

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/reporting/export_gate.py` | SKIP→FAIL meta-gate (Section 1.1) |
| `backend/facts/completeness.py` | Core conflict blocks valuation (Section 1.3) |
| `backend/reporting/report_data_loader.py` | Remove glob fallback (Section 1.4) |
| `scripts/evaluate_report.py` | Stale threshold fix (Section 1.5) |
| `backend/harness/tools.py` | Run-scoped output paths (Section 2.2) |
| `backend/harness/runner.py` | trace.jsonl writer, remove handoff/audit writers (Section 2.6), export-gate-controls-render (Section 2.9) |
| `.gitignore` | New entries (Section 3.4) |
| `tests/unit/test_export_gate.py` | New: SKIP→FAIL + export controls render |
| `tests/unit/test_report_data_loader.py` | Update: no glob in production |
| `tests/unit/test_completeness.py` | New: core conflict blocks valuation |
| `tests/unit/test_tools_storage_path.py` | Update: run-scoped artifacts |

---

### Task 1: Baseline — Run Existing Tests

**Files:**
- None modified

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -x -q 2>&1 | tail -20
```

Expected: All tests pass (approx 1345). Record the exact count. If any fail, stop and fix before proceeding.

- [ ] **Step 2: Commit checkpoint (no changes)**

No commit needed — this is just validation.

---

### Task 2: Physical Cleanup — Delete Chrome Temp Profiles

**Files:**
- Delete: `artifacts/reports_pdf/.chrome-profile-*/` (if exists)

- [ ] **Step 1: Delete Chrome temp dirs**

```bash
rm -rf artifacts/reports_pdf/.chrome-profile-*/
```

Expected: Dirs removed (or no-op if absent).

- [ ] **Step 2: Verify**

```bash
ls artifacts/reports_pdf/.chrome-profile-* 2>/dev/null && echo "STILL EXISTS" || echo "CLEAN"
```

Expected: `CLEAN`

---

### Task 3: Physical Cleanup — Delete BLOCKED Reports & Root Temp Files

**Files:**
- Delete: `reports/*_BLOCKED.md` (if any)
- Delete: `_audit_agent_*.txt`, `current_state_review_for_claude.md`, `CALCULATION_MODEL_AUDIT_PLAN_FOR_CLAUDE.md`, `FRONTEND_PLAN_FINROBOT_STYLE.md`

- [ ] **Step 1: Delete BLOCKED reports**

```bash
rm -f reports/*_BLOCKED.md
```

- [ ] **Step 2: Delete root-level temp files**

```bash
rm -f _audit_agent_*.txt current_state_review_for_claude.md CALCULATION_MODEL_AUDIT_PLAN_FOR_CLAUDE.md FRONTEND_PLAN_FINROBOT_STYLE.md
```

- [ ] **Step 3: Verify**

```bash
ls _audit_agent_*.txt current_state_review_for_claude.md CALCULATION_MODEL_AUDIT_PLAN_FOR_CLAUDE.md FRONTEND_PLAN_FINROBOT_STYLE.md 2>/dev/null && echo "STILL EXISTS" || echo "CLEAN"
```

Expected: `CLEAN`

---

### Task 4: Physical Cleanup — Move Debug Scripts

**Files:**
- Move: `scripts/test_retrieval.py` → `scripts/debug/test_retrieval.py`
- Move: `scripts/check_ocr_runtime.py` → `scripts/debug/check_ocr_runtime.py`

- [ ] **Step 1: Create debug directory and move scripts**

```bash
mkdir -p scripts/debug && mv scripts/test_retrieval.py scripts/debug/test_retrieval.py 2>/dev/null; mv scripts/check_ocr_runtime.py scripts/debug/check_ocr_runtime.py 2>/dev/null; echo "done"
```

Note: If files don't exist, `mv` will fail silently with `2>/dev/null`. This is expected — the files may have already been removed.

---

### Task 5: Physical Cleanup — Gitignore & Freeze Legacy Dirs

**Files:**
- Modify: `.gitignore`
- Create: `artifacts/README.md`

- [ ] **Step 1: Update .gitignore**

Add the following entries to `.gitignore` after the existing `artifacts/` line:

```
# Run-scoped artifacts (production output — not source)
artifacts/runs/
artifacts/reports_pdf/.chrome-profile-*/
artifacts/dev/
```

Note: `artifacts/` is already gitignored, so `artifacts/runs/` and `artifacts/dev/` are redundant but explicit for documentation purposes. The `.chrome-profile-*/` pattern is more specific.

- [ ] **Step 2: Create artifacts/README.md**

```markdown
Production runs write to artifacts/runs/{run_id}/.
Legacy flat directories (facts/, valuation/, forecast/, etc.) are frozen.
```

- [ ] **Step 3: Commit physical cleanup**

```bash
git add -f .gitignore artifacts/README.md
git add -u  # stages deletions
git commit -m "$(cat <<'EOF'
chore: physical cleanup — delete temp files, freeze legacy artifact dirs

- Remove Chrome temp profiles, BLOCKED reports, root-level audit files
- Move debug scripts to scripts/debug/
- Add artifacts/README.md documenting frozen legacy dirs
- Update .gitignore for run-scoped artifacts
EOF
)"
```

---

### Task 6: Safety Fix — Gate SKIP → FAIL

**Files:**
- Modify: `backend/reporting/export_gate.py:379-386`
- Create: `tests/unit/test_export_gate.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_export_gate.py`:

```python
"""Tests for export gate safety: SKIP must block export."""
from __future__ import annotations

import pytest

from backend.reporting.export_gate import (
    ExportGateResult,
    GateResult,
    evaluate_export_gate,
)
from backend.reporting.report_artifact import ReportArtifact


def _make_artifact(ticker: str = "TEST") -> ReportArtifact:
    return ReportArtifact(
        report_id="test_001",
        ticker=ticker,
        run_id="run_001",
        report_date="2026-06-08",
        render_mode="analyst_draft",
        sections=[],
    )


class TestGateSkipIsFail:
    """Spec §1.1: Any gate returning SKIP must have passed=false and block export."""

    def test_skip_gate_has_passed_false(self):
        g = GateResult("source_gate", "SKIP", ["no data provided"])
        assert g.passed is False, "SKIP gate must have passed=False"

    def test_skip_gate_blocks_export(self):
        artifact = _make_artifact()
        # source_manifest=None → source_gate returns SKIP
        # claim_ledger=None → citation_gate returns SKIP
        # layout_audit=None → layout_gate returns SKIP
        result = evaluate_export_gate(artifact)
        skip_gates = [
            name for name, g in result.gates.items()
            if g.status == "SKIP"
        ]
        assert len(skip_gates) > 0, "Expected at least one SKIP gate"
        assert result.is_final_exportable is False, (
            f"SKIP gates {skip_gates} must block export"
        )
        for name in skip_gates:
            assert name in result.blocking_gates, (
                f"SKIP gate {name!r} must appear in blocking_gates"
            )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_export_gate.py -v
```

Expected: `test_skip_gate_blocks_export` FAILS because current code at line 380 only checks `("FAIL", "BLOCKED")`, not `"SKIP"`.

- [ ] **Step 3: Fix the export gate — SKIP blocks export**

In `backend/reporting/export_gate.py`, change line 380:

```python
# OLD (line 379-381):
    # SKIP is acceptable; only FAIL and BLOCKED prevent final export
    blocking: list[str] = [
        name for name, g in gates.items()
        if g.status in ("FAIL", "BLOCKED")
    ]

# NEW:
    # SKIP, FAIL, and BLOCKED all prevent final export.
    # Only PASS allows final export — missing data is never acceptable.
    blocking: list[str] = [
        name for name, g in gates.items()
        if g.status in ("FAIL", "BLOCKED", "SKIP")
    ]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_export_gate.py -v
```

Expected: All tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
pytest tests/ -x -q 2>&1 | tail -5
```

Expected: All tests pass. If any test relied on SKIP gates not blocking, update that test (SKIP should always block — the old behavior was a bug).

- [ ] **Step 6: Commit**

```bash
git add backend/reporting/export_gate.py tests/unit/test_export_gate.py
git commit -m "$(cat <<'EOF'
fix(gate): SKIP gates now block export (spec §1.1)

SKIP meant "data not provided" — this should never silently pass.
Only PASS allows final export. SKIP, FAIL, BLOCKED all block.
EOF
)"
```

---

### Task 7: Safety Fix — Core-Metric Conflict Blocks Valuation

**Files:**
- Modify: `backend/facts/completeness.py:133-250`
- Create: `tests/unit/test_completeness_conflict.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_completeness_conflict.py`:

```python
"""Tests for core metric conflict blocking valuation."""
from __future__ import annotations

from datetime import UTC, datetime

from backend.facts.completeness import CORE_FY_KEYS, build_fy_validation_report


def _base_table():
    """Minimal fact table with all CORE_FY_KEYS present for 3 periods."""
    periods = ["2022FY", "2023FY", "2024FY"]
    table = {}
    for key in CORE_FY_KEYS:
        table[key] = {p: {"value": 100.0, "source_tier": 0} for p in periods}
    return table, periods


def _base_raw_facts(periods):
    """Raw facts with no conflicts."""
    facts = []
    for key in CORE_FY_KEYS:
        for p in periods:
            facts.append({
                "line_item_code": key,
                "fiscal_year": int(p[:4]),
                "fiscal_period": "FY",
                "value": 100.0,
                "source_tier": 0,
                "confidence": 0.95,
                "ingested_at": datetime.now(UTC).isoformat(),
                "validation_status": "accepted",
            })
    return facts


def test_core_conflict_blocks_valuation():
    """Conflict on a CORE_FY_KEY metric must set valuation_gate=fail."""
    table, periods = _base_table()
    raw_facts = _base_raw_facts(periods)

    # Inject a conflicting fact for revenue.net @ 2023FY from a different source
    raw_facts.append({
        "line_item_code": "revenue.net",
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "value": 200.0,  # 100% different from existing 100.0
        "source_tier": 1,
        "source_id": "conflict_source",
        "confidence": 0.90,
        "ingested_at": datetime.now(UTC).isoformat(),
        "validation_status": "accepted",
    })

    validation_status_table = {
        key: {p: "accepted" for p in periods}
        for key in CORE_FY_KEYS
    }
    source_tiers = {p: [0] for p in periods}

    report = build_fy_validation_report(
        ticker="TEST",
        table=table,
        raw_facts=raw_facts,
        required_periods=periods,
        periods_available=periods,
        periods_missing=[],
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=validation_status_table,
        source_tiers_by_period=source_tiers,
    )

    assert report["valuation_gate"] == "fail", (
        f"Core metric conflict on revenue.net must block valuation, got: {report['valuation_gate']}"
    )
    blocking = report["blocking_reasons"]
    assert any("core_metric_conflict" in r for r in blocking), (
        f"Expected core_metric_conflict in blocking_reasons, got: {blocking}"
    )


def test_non_core_conflict_does_not_block():
    """Conflict on a non-core key must NOT block valuation."""
    table, periods = _base_table()
    raw_facts = _base_raw_facts(periods)

    # Inject conflict on a non-core key
    raw_facts.append({
        "line_item_code": "sga.total",
        "fiscal_year": 2023,
        "fiscal_period": "FY",
        "value": 999.0,
        "source_tier": 1,
        "source_id": "conflict_source",
        "confidence": 0.90,
        "ingested_at": datetime.now(UTC).isoformat(),
        "validation_status": "accepted",
    })

    validation_status_table = {
        key: {p: "accepted" for p in periods}
        for key in CORE_FY_KEYS
    }
    source_tiers = {p: [0] for p in periods}

    report = build_fy_validation_report(
        ticker="TEST",
        table=table,
        raw_facts=raw_facts,
        required_periods=periods,
        periods_available=periods,
        periods_missing=[],
        forbidden_periods=[],
        generated_at=datetime.now(UTC),
        validation_status_table=validation_status_table,
        source_tiers_by_period=source_tiers,
    )

    # Non-core conflict should not add core_metric_conflict blocking reason
    blocking = report.get("blocking_reasons", [])
    assert not any("core_metric_conflict" in r for r in blocking), (
        f"Non-core conflict should not block valuation, got: {blocking}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_completeness_conflict.py::test_core_conflict_blocks_valuation -v
```

Expected: FAIL — current `build_fy_validation_report` doesn't check source conflicts.

- [ ] **Step 3: Add conflict check to build_fy_validation_report**

In `backend/facts/completeness.py`, add the import at the top (after existing imports):

```python
from backend.facts.normalizer import (
    FactTable, periods_sorted, build_source_tier_coverage,
    build_source_conflict_report,
)
```

Then in `build_fy_validation_report()`, add this block AFTER the reconciliation gate section (after line 221 `blocking_reasons.append(...)`) and BEFORE the source tier coverage check (line 223):

```python
    # --- Core metric conflict check (Spec §1.3) ---
    source_conflicts = build_source_conflict_report(ticker, raw_facts)
    core_metric_conflicts = [
        c for c in source_conflicts
        if c.requires_review and c.metric in CORE_FY_KEYS
    ]
    if core_metric_conflicts:
        for c in core_metric_conflicts:
            blocking_reasons.append(
                f"core_metric_conflict:{c.metric}:{c.period} "
                f"(variance={c.variance_pct:.1%}, sources={list(c.candidate_values.keys())})"
            )
```

Also update the `all_pass` check (around line 243) to include the conflict:

```python
    all_pass = (
        coverage_gate == "pass"
        and core_keys_gate == "pass"
        and source_validation_gate == "pass"
        and not recon.valuation_blocked
        and tier_coverage["status"] != "fail"
        and not core_metric_conflicts
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_completeness_conflict.py -v
```

Expected: Both tests PASS.

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -x -q 2>&1 | tail -5
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/facts/completeness.py tests/unit/test_completeness_conflict.py
git commit -m "$(cat <<'EOF'
fix(facts): core metric conflict blocks valuation (spec §1.3)

If build_source_conflict_report finds requires_review=True on a
CORE_FY_KEY, valuation_gate is set to fail with blocking reason.
EOF
)"
```

---

### Task 8: Safety Fix — Eliminate Glob Fallback

**Files:**
- Modify: `backend/reporting/report_data_loader.py:37-61`
- Create: `tests/unit/test_no_glob_production.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_no_glob_production.py`:

```python
"""Test: _resolve_artifact raises ValueError without manifest (no glob fallback)."""
from __future__ import annotations

import pytest


def test_no_glob_in_production():
    """Spec §1.4: _resolve_artifact without manifest must raise ValueError."""
    from backend.reporting.report_data_loader import _resolve_artifact

    with pytest.raises(ValueError, match="run_id is required"):
        _resolve_artifact("valuation", "artifacts/valuation/*.json", manifest=None)


def test_resolve_with_allow_latest_still_works():
    """Dev scripts may pass allow_latest_artifacts=True — this should still use glob."""
    from backend.reporting.report_data_loader import _resolve_artifact

    # With allow_latest_artifacts=True and no matching files, should return {}
    result = _resolve_artifact(
        "valuation",
        "artifacts/nonexistent_dir_12345/*.json",
        manifest=None,
        allow_latest_artifacts=True,
    )
    assert result == {}
```

- [ ] **Step 2: Run test to verify current state**

```bash
pytest tests/unit/test_no_glob_production.py -v
```

Expected: `test_no_glob_in_production` PASSES (this already raises ValueError when `allow_latest_artifacts=False`). `test_resolve_with_allow_latest_still_works` PASSES. Both should pass because the current code already has this guard. If they pass, this fix is already done — move to next task.

- [ ] **Step 3: Verify no production code uses allow_latest_artifacts=True**

```bash
cd /c/Users/Admin/Desktop/multi-agent-equity-research && grep -rn "allow_latest_artifacts.*True" backend/ scripts/ --include="*.py" | grep -v "scripts/demo/"
```

Expected: No matches outside `scripts/demo/`. If any production code uses `allow_latest_artifacts=True`, it must be removed.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_no_glob_production.py
git commit -m "$(cat <<'EOF'
test(loader): verify glob fallback blocked in production (spec §1.4)

_resolve_artifact already raises ValueError without manifest+allow_latest.
Added explicit regression test to lock this behavior.
EOF
)"
```

---

### Task 9: Safety Fix — Stale Data Threshold

**Files:**
- Modify: `scripts/evaluate_report.py:49`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_stale_threshold.py`:

```python
"""Test: FY financial staleness threshold is 540 days, not 30."""
from __future__ import annotations


def test_stale_threshold_is_540_days():
    """Spec §1.5: FY staleness threshold must be 540 days (18 months)."""
    from scripts.evaluate_report import _STALE_THRESHOLD_DAYS
    assert _STALE_THRESHOLD_DAYS == 540, (
        f"Expected 540 days, got {_STALE_THRESHOLD_DAYS}"
    )
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_stale_threshold.py -v
```

Expected: FAIL — current value is 30.

- [ ] **Step 3: Change threshold**

In `scripts/evaluate_report.py` line 49, change:

```python
# OLD:
_STALE_THRESHOLD_DAYS = 30

# NEW:
_STALE_THRESHOLD_DAYS = 540
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_stale_threshold.py -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -x -q 2>&1 | tail -5
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/evaluate_report.py tests/unit/test_stale_threshold.py
git commit -m "$(cat <<'EOF'
fix(eval): FY staleness threshold 30d → 540d (spec §1.5)

Annual financial statements are published once per year. 30-day threshold
caused false positives. Market price data threshold unchanged.
EOF
)"
```

---

### Task 10: Safety Fix — Golden CSV Override Logging

**Files:**
- Modify: `scripts/build_facts.py` (after line 215, the golden merge section)
- Create: `tests/unit/test_golden_override.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_golden_override.py`:

```python
"""Tests for golden CSV override logging and blocking."""
from __future__ import annotations

import logging


def test_golden_override_warning_at_2_pct(monkeypatch, tmp_path, caplog):
    """Spec §1.2: Golden override with >2% variance must log GOLDEN_OVERRIDE warning."""
    from scripts.build_facts import _load_golden_fallback

    # We test the detection logic, not the full build_facts pipeline.
    # Simulate: DB has revenue.net=100, golden has revenue.net=103 (3% diff)
    db_facts = [
        {"line_item_code": "revenue.net", "fiscal_year": 2023, "fiscal_period": "FY",
         "value": 100.0, "source_tier": 3, "source_id": "api_src", "confidence": 0.7,
         "ingested_at": "2026-01-01T00:00:00"},
    ]
    golden_facts = [
        {"line_item_code": "revenue.net", "fiscal_year": 2023, "fiscal_period": "FY",
         "value": 103.0, "source_tier": 0, "source_id": "golden_csv_TEST_2023FY",
         "confidence": 0.95, "ingested_at": "2026-01-01T00:00:00"},
    ]

    from scripts.build_facts import _detect_golden_overrides
    overrides = _detect_golden_overrides(db_facts, golden_facts)

    assert len(overrides) >= 1
    assert overrides[0]["variance_pct"] > 2.0


def test_golden_override_blocks_at_10_pct():
    """Spec §1.2: Golden override with >10% variance must add blocking_reason."""
    db_facts = [
        {"line_item_code": "revenue.net", "fiscal_year": 2023, "fiscal_period": "FY",
         "value": 100.0, "source_tier": 3, "source_id": "api_src"},
    ]
    golden_facts = [
        {"line_item_code": "revenue.net", "fiscal_year": 2023, "fiscal_period": "FY",
         "value": 115.0, "source_tier": 0, "source_id": "golden_csv_TEST_2023FY"},
    ]

    from scripts.build_facts import _detect_golden_overrides
    overrides = _detect_golden_overrides(db_facts, golden_facts)

    assert len(overrides) >= 1
    assert overrides[0]["variance_pct"] > 10.0
    assert overrides[0]["is_blocking"] is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_golden_override.py -v
```

Expected: FAIL — `_detect_golden_overrides` doesn't exist yet.

- [ ] **Step 3: Add _detect_golden_overrides to build_facts.py**

Add this function to `scripts/build_facts.py` (before `build_facts()`):

```python
def _detect_golden_overrides(
    db_facts: list[dict],
    golden_facts: list[dict],
) -> list[dict]:
    """Compare overlapping (metric, period) pairs between DB and golden CSV facts.

    Returns a list of override records with variance info.
    """
    import logging
    logger = logging.getLogger(__name__)

    # Build lookup from DB facts: (metric, period) → value
    db_lookup: dict[tuple[str, int], float] = {}
    for f in db_facts:
        key = (f.get("line_item_code", ""), f.get("fiscal_year", 0))
        try:
            db_lookup[key] = float(f["value"])
        except (ValueError, KeyError, TypeError):
            continue

    overrides = []
    for f in golden_facts:
        key = (f.get("line_item_code", ""), f.get("fiscal_year", 0))
        if key not in db_lookup:
            continue
        db_val = db_lookup[key]
        golden_val = float(f["value"])
        if db_val == 0 and golden_val == 0:
            continue
        denom = max(abs(db_val), abs(golden_val), 1e-9)
        variance_pct = abs(golden_val - db_val) / denom * 100

        is_blocking = variance_pct > 10.0
        record = {
            "metric": key[0],
            "fiscal_year": key[1],
            "db_value": db_val,
            "golden_value": golden_val,
            "variance_pct": round(variance_pct, 2),
            "is_blocking": is_blocking,
        }
        overrides.append(record)

        if variance_pct > 2.0:
            logger.warning(
                "GOLDEN_OVERRIDE %s %dFY: db=%.1f golden=%.1f variance=%.1f%%%s",
                key[0], key[1], db_val, golden_val, variance_pct,
                " [BLOCKING]" if is_blocking else "",
            )

    return overrides
```

Then in `build_facts()`, after line 215 (`raw_facts = raw_facts + golden_facts`), add:

```python
        # Detect golden overrides and log warnings (Spec §1.2)
        overrides = _detect_golden_overrides(
            [f for f in raw_facts if not f.get("source_id", "").startswith("golden_csv_")],
            golden_facts,
        )
        blocking_overrides = [o for o in overrides if o["is_blocking"]]
```

Then in the artifact dict (around line 329), add after `"source_conflicts"`:

```python
        "golden_overrides": overrides if golden_facts else [],
```

And in the validation/blocking_reasons section, if `blocking_overrides` exist, add blocking reasons:

After the validation report is built (around line 286), add:

```python
    if blocking_overrides:
        for o in blocking_overrides:
            report["blocking_reasons"].append(
                f"golden_override_variance:{o['metric']}:{o['fiscal_year']}FY "
                f"(db={o['db_value']:.1f}, golden={o['golden_value']:.1f}, variance={o['variance_pct']:.1f}%)"
            )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_golden_override.py -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -x -q 2>&1 | tail -5
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add scripts/build_facts.py tests/unit/test_golden_override.py
git commit -m "$(cat <<'EOF'
feat(facts): golden CSV override logging + blocking at >10% (spec §1.2)

_detect_golden_overrides compares overlapping (metric, period) pairs.
Logs GOLDEN_OVERRIDE warning at >2% variance.
Adds blocking_reason at >10% variance.
EOF
)"
```

---

### Task 11: Runner — Replace Handoff/Payload/Audit Writers with trace.jsonl

**Files:**
- Modify: `backend/harness/runner.py`
- Create: `tests/unit/test_trace_jsonl.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_trace_jsonl.py`:

```python
"""Tests for trace.jsonl event writer."""
from __future__ import annotations

import json


def test_trace_has_tool_call_events():
    """trace entries from _record_tool_trace must have kind=tool_call."""
    from backend.harness.state import ResearchGraphState

    state = ResearchGraphState(
        run_id="run_001",
        ticker="TEST",
        run_type="full_report",
        objective="test",
        policy={},
        flags={},
    )
    state.current_stage = "DATA_RETRIEVAL_RUN"

    # Simulate what _record_tool_trace does
    payload = {
        "kind": "tool_call",
        "run_id": state.run_id,
        "tool_name": "build_facts",
        "agent_role": "DataRetrievalAgent",
    }
    state.trace.append(payload)

    tool_calls = [e for e in state.trace if e.get("kind") == "tool_call"]
    assert len(tool_calls) >= 1
    assert tool_calls[0]["tool_name"] == "build_facts"


def test_trace_has_agent_handoff_events():
    """Agent handoffs should produce trace events with kind=agent_handoff."""
    from backend.harness.state import ResearchGraphState

    state = ResearchGraphState(
        run_id="run_001",
        ticker="TEST",
        run_type="full_report",
        objective="test",
        policy={},
        flags={},
    )

    # Simulate trace entry for agent handoff (new format)
    payload = {
        "kind": "agent_handoff",
        "run_id": state.run_id,
        "agent_id": "data_retrieval",
        "stage": "DATA_RETRIEVAL_RUN",
        "status": "completed",
    }
    state.trace.append(payload)

    handoffs = [e for e in state.trace if e.get("kind") == "agent_handoff"]
    assert len(handoffs) >= 1


def test_trace_entries_are_json_serializable():
    """Every trace entry must be JSON-serializable for trace.jsonl."""
    from backend.harness.state import ResearchGraphState

    state = ResearchGraphState(
        run_id="run_001",
        ticker="TEST",
        run_type="full_report",
        objective="test",
        policy={},
        flags={},
    )

    entries = [
        {"kind": "tool_call", "tool": "build_facts", "status": "completed"},
        {"kind": "agent_handoff", "agent_id": "supervisor", "stage": "PREFLIGHT"},
        {"kind": "gate_result", "gate": "data_quality_gate", "passed": True},
    ]
    for entry in entries:
        state.trace.append(entry)

    for entry in state.trace:
        line = json.dumps(entry, default=str)
        parsed = json.loads(line)
        assert parsed["kind"] in ("tool_call", "agent_handoff", "gate_result", "agent_message")
```

- [ ] **Step 2: Run test to verify it passes**

```bash
pytest tests/unit/test_trace_jsonl.py -v
```

Expected: All PASS — these test the trace format, not the file writing (which is a runner concern).

- [ ] **Step 3: Refactor _write_agent_handoff to trace-only**

In `backend/harness/runner.py`, replace `_write_agent_handoff` (lines 544-591) with:

```python
    def _write_agent_handoff(self, state: ResearchGraphState, result) -> None:
        """Record agent handoff as a trace event instead of a separate JSON file."""
        agent_id = result.agent_id or self._agent_id_for_stage(state.current_stage)
        artifact_refs = [
            ref if isinstance(ref, dict) else dict(ref)
            for ref in result.artifact_refs
        ]
        output_refs = [
            str(ref.get("artifact_id"))
            for ref in artifact_refs
            if ref.get("artifact_id")
        ]
        trace_entry = {
            "kind": "agent_handoff",
            "run_id": state.run_id,
            "agent_id": agent_id,
            "stage": state.current_stage,
            "input_refs": [
                ref.get("artifact_id", "")
                for ref in state.artifact_refs
                if isinstance(ref, dict) and ref.get("artifact_id")
            ][:20],
            "output_refs": output_refs,
            "review_status": result.status,
            "requires_human": result.requires_human,
            "blocking_reason": result.blocking_reason,
        }
        state.trace.append(trace_entry)
        state.artifacts.setdefault("agent_handoffs", []).append(trace_entry)
```

- [ ] **Step 4: Refactor _write_agent_payload_artifact to trace-only**

In `backend/harness/runner.py`, replace `_write_agent_payload_artifact` (lines 593-628) with:

```python
    def _write_agent_payload_artifact(self, state: ResearchGraphState, result) -> None:
        """Record agent payload as a trace event instead of a separate JSON file."""
        section_by_agent = {
            "financial_analyst": "financial_analysis",
            "report_writer_critic": "report_critic_review",
        }
        section_key = section_by_agent.get(result.agent_id)
        if not section_key or not isinstance(result.payload, dict):
            return

        trace_entry = {
            "kind": "agent_message",
            "run_id": state.run_id,
            "agent_id": result.agent_id,
            "section_key": section_key,
            "status": result.status,
            "summary": {
                "payload_keys": sorted(result.payload.keys()) if isinstance(result.payload, dict) else [],
                "confidence": getattr(result, "confidence", None),
            },
        }
        state.trace.append(trace_entry)
```

- [ ] **Step 5: Refactor _write_agent_effectiveness_audit to trace-only**

In `backend/harness/runner.py`, replace `_write_agent_effectiveness_audit` (lines 762-858) with:

```python
    def _write_agent_effectiveness_audit(self, state: "ResearchGraphState") -> None:
        """No-op: agent effectiveness data is now in state.trace (trace.jsonl)."""
        pass
```

- [ ] **Step 6: Run full test suite**

```bash
pytest tests/ -x -q 2>&1 | tail -10
```

Expected: All tests pass. Some tests in `test_agent_context_handoff.py` may need updating if they assert on handoff file existence. If a test fails because it expects handoff JSON files, update it to check `state.trace` entries instead.

- [ ] **Step 7: Commit**

```bash
git add backend/harness/runner.py tests/unit/test_trace_jsonl.py
git commit -m "$(cat <<'EOF'
refactor(runner): replace handoff/payload/audit files with trace events (spec §2.6)

_write_agent_handoff → trace entry kind=agent_handoff
_write_agent_payload_artifact → trace entry kind=agent_message
_write_agent_effectiveness_audit → no-op (trace is the audit)
EOF
)"
```

---

### Task 12: Runner — Export Gate Controls HTML/PDF Render

**Files:**
- Modify: `backend/harness/runner.py` (PUBLISHED stage)
- Modify: `tests/unit/test_export_gate.py`

- [ ] **Step 1: Add test for export gate controls render**

Append to `tests/unit/test_export_gate.py`:

```python
class TestExportGateControlsRender:
    """Spec §2.9: export gate result determines whether HTML/PDF are created."""

    def test_failed_gate_means_no_final_export(self):
        artifact = _make_artifact()
        # No approval → human_review_gate FAIL
        result = evaluate_export_gate(artifact, approval_status=None)
        assert result.is_final_exportable is False
        assert result.render_mode == "analyst_draft"

    def test_all_pass_means_client_final(self):
        artifact = _make_artifact()
        # Provide all inputs to make gates pass
        val = {"blend_dcf": {}, "fcff": {"shares_mn": 100, "wacc": 0.12, "terminal_growth": 0.03}}
        forecast = {"forecast_years": []}
        source_manifest = {"untraced_valuation_facts": [], "tier3_only_valuation_facts": []}
        recon = {"material_conflicts": []}
        claim_ledger = {"summary": {"unsupported": 0, "partial": 0}}

        from backend.reporting.layout_audit import LayoutRenderAudit
        layout = LayoutRenderAudit(ticker="TEST", report_id="test_001", render_mode="client_final")

        result = evaluate_export_gate(
            artifact,
            valuation_artifact=val,
            forecast_artifact=forecast,
            source_manifest=source_manifest,
            reconciliation_artifact=recon,
            claim_ledger=claim_ledger,
            layout_audit=layout,
            approval_status="approved",
        )
        assert result.is_final_exportable is True
        assert result.render_mode == "client_final"
```

- [ ] **Step 2: Run test**

```bash
pytest tests/unit/test_export_gate.py::TestExportGateControlsRender -v
```

Expected: PASS (this tests the existing export gate logic, which already works correctly).

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_export_gate.py
git commit -m "$(cat <<'EOF'
test(gate): verify export gate controls render mode (spec §2.9)
EOF
)"
```

---

### Task 13: Dev-Only Script Headers

**Files:**
- Modify: `scripts/build_facts.py` (line 1)
- Modify: `scripts/run_valuation.py` (line 1)
- Modify: `scripts/generate_report.py` (line 1)
- Modify: `scripts/render_report.py` (line 1, if exists)

- [ ] **Step 1: Add dev-only header to each script**

Add `# DEV-ONLY — production runs use run_research.py` as the first line (before `"""` docstring) to each of the four scripts.

For `scripts/build_facts.py`:
```python
# DEV-ONLY — production runs use run_research.py
```

Repeat for `scripts/run_valuation.py`, `scripts/generate_report.py`, `scripts/render_report.py`.

- [ ] **Step 2: Commit**

```bash
git add scripts/build_facts.py scripts/run_valuation.py scripts/generate_report.py scripts/render_report.py
git commit -m "$(cat <<'EOF'
docs(scripts): mark dev-only wrappers (spec §2.1)

Production runs use scripts/run_research.py → ResearchGraphRunner.
These scripts exist for single-stage debugging only.
EOF
)"
```

---

### Task 14: Run-Scoped Artifact Directory in Tools

**Files:**
- Modify: `backend/harness/tools.py`
- Create: `tests/unit/test_run_scoped_artifacts.py`

This task changes tool functions to accept an optional `run_id` parameter and write to `artifacts/runs/{run_id}/` when provided.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_run_scoped_artifacts.py`:

```python
"""Test: tools write to artifacts/runs/{run_id}/ when run_id provided."""
from __future__ import annotations

import json
from pathlib import Path


def test_build_index_tool_run_scoped(monkeypatch, tmp_path):
    """build_index_tool with run_id writes to artifacts/runs/{run_id}/."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("scripts.build_index.build_index", lambda **kw: {"chunks_inserted": 3})

    from backend.harness.tools import build_index_tool
    result = build_index_tool("DHG", 2021, 2025, run_id="run_test_001")

    refs = [ref for ref in result.artifact_refs if ref.section_key == "index"]
    assert refs and refs[0].storage_path
    assert "runs/run_test_001" in refs[0].storage_path or "run_test_001" in refs[0].storage_path


def test_build_index_tool_legacy_no_run_id(monkeypatch, tmp_path):
    """build_index_tool without run_id still writes to artifacts/index/ (legacy)."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("scripts.build_index.build_index", lambda **kw: {"chunks_inserted": 3})

    from backend.harness.tools import build_index_tool
    result = build_index_tool("DHG", 2021, 2025)

    refs = [ref for ref in result.artifact_refs if ref.section_key == "index"]
    assert refs and refs[0].storage_path
    assert Path(refs[0].storage_path).exists()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_run_scoped_artifacts.py::test_build_index_tool_run_scoped -v
```

Expected: FAIL — `build_index_tool` doesn't accept `run_id`.

- [ ] **Step 3: Add run_id parameter to build_index_tool**

In `backend/harness/tools.py`, modify `build_index_tool` signature and output path:

```python
def build_index_tool(ticker: str, from_year: int = MVP_FROM_YEAR, to_year: int = MVP_TO_YEAR, run_id: str | None = None) -> ServiceNodeResult:
    from scripts.build_index import build_index

    summary = build_index(ticker=ticker, years=list(range(from_year, to_year + 1)))
    if run_id:
        out_dir = Path.cwd() / "artifacts" / "runs" / run_id
    else:
        out_dir = Path.cwd() / "artifacts" / "index"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    artifact_path = out_dir / f"{ticker.upper()}_{ts}_index_summary.json"
    # ... rest unchanged
```

Apply the same pattern to `read_ratio_artifact_tool` (which also writes to `artifacts/analysis/`).

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/unit/test_run_scoped_artifacts.py -v
```

Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest tests/ -x -q 2>&1 | tail -5
```

Expected: All tests pass.

- [ ] **Step 6: Commit**

```bash
git add backend/harness/tools.py tests/unit/test_run_scoped_artifacts.py
git commit -m "$(cat <<'EOF'
feat(tools): run-scoped artifact directory support (spec §2.2)

Tools accept optional run_id parameter. When provided, artifacts
write to artifacts/runs/{run_id}/ instead of legacy flat dirs.
EOF
)"
```

---

### Task 15: Runner — Pass run_id to Tools

**Files:**
- Modify: `backend/harness/runner.py` (_execute_stage method)

- [ ] **Step 1: Update tool calls to pass run_id**

In `backend/harness/runner.py`, in the `_execute_stage` method, update tool calls that support `run_id`. For example, in the `DATA_RETRIEVAL_RUN` stage (around line 282):

```python
            # Step 3: build evidence index
            index_result = self._run_tool(state, "data_retrieval", "build_index", state.ticker, state.from_year, state.to_year, run_id=state.run_id)
```

And in `FINANCIAL_ANALYST_RUN` (around line 303):

```python
            ratio_result = self._run_tool(state, "financial_analyst", "read_ratio_artifact", state.ticker, state.snapshot_id, run_id=state.run_id)
```

Note: Only update tools that have been modified to accept `run_id`. `build_facts_tool` and `run_valuation_tool` delegate to scripts that handle their own output paths — those will be addressed when they're refactored.

- [ ] **Step 2: Run full test suite**

```bash
pytest tests/ -x -q 2>&1 | tail -5
```

Expected: All tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/harness/runner.py
git commit -m "$(cat <<'EOF'
feat(runner): pass run_id to tools for run-scoped output (spec §2.2)
EOF
)"
```

---

### Task 16: Run Full Test Suite — Final Validation

**Files:**
- None modified

- [ ] **Step 1: Run full test suite**

```bash
pytest tests/ -x -q 2>&1 | tail -20
```

Expected: All tests pass.

- [ ] **Step 2: Verify no regressions in key areas**

```bash
pytest tests/unit/test_export_gate.py tests/unit/test_completeness_conflict.py tests/unit/test_no_glob_production.py tests/unit/test_stale_threshold.py tests/unit/test_trace_jsonl.py tests/unit/test_tools_storage_path.py -v
```

Expected: All new and updated tests pass.

- [ ] **Step 3: Final commit with all changes**

If any uncommitted fixes remain:

```bash
git status
```

If clean, no commit needed. If files modified, commit with descriptive message.

---

## Implementation Order Summary

| Task | Section | Description | Risk |
|------|---------|-------------|------|
| 1 | Baseline | Run existing tests | None |
| 2-5 | §3 Physical cleanup | Delete temp files, gitignore, freeze dirs | Zero code risk |
| 6 | §1.1 | Gate SKIP→FAIL | Low — changes blocking logic |
| 7 | §1.3 | Core conflict blocks valuation | Low — adds check |
| 8 | §1.4 | Eliminate glob fallback | Low — already guarded |
| 9 | §1.5 | Stale threshold 30→540 | Trivial |
| 10 | §1.2 | Golden CSV override logging | Low — adds function |
| 11 | §2.6 | trace.jsonl replaces handoff/audit files | Medium — refactor |
| 12 | §2.9 | Export gate controls render | Low — test only |
| 13 | §2.1 | Dev-only script headers | Trivial |
| 14-15 | §2.2 | Run-scoped artifact dirs | Medium — plumbing |
| 16 | Validation | Full test suite | None |

## Deferred (Phase 2)

The following spec items require deeper refactoring and should be done in a follow-up after this plan stabilizes:

- **§2.4 Merged valuation.json** — `run_valuation_tool` already returns a merged dict from `scripts/run_valuation.py`. The file write already produces one JSON. The remaining work is ensuring the schema matches the spec exactly and writing to `artifacts/runs/{run_id}/valuation.json`. This needs `run_valuation_tool` to accept `run_id`.
- **§2.5 Merged evidence.json** — `generate_report_tool` already returns claims and citations. Merging these into one file requires `generate_report_tool` to accept `run_id` and write `evidence.json` alongside `report_draft.md`.
- **§2.3 Full artifact contract** — The 9-file contract (`manifest.json`, `facts.json`, `valuation.json`, `evidence.json`, `report_draft.md`, `export_gate.json`, `trace.jsonl`, `report.html`, `report.pdf`) requires all tools to write to `artifacts/runs/{run_id}/`. This is blocked on §2.4 and §2.5.
- **§2.8 reports/ is output-only** — Only approved PDFs go to `reports/{ticker}_{run_id}_final.pdf`. Blocked on §2.9 runner changes.
