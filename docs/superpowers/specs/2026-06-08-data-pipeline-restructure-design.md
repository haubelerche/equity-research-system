# Data Pipeline Full Restructure — Design Spec

**Date:** 2026-06-08
**Status:** Approved
**Scope:** Safety fixes, single production path, artifact cleanup, test validation.
**Constraint:** DB always available (C1). No offline fallback. No overengineering.

---

## Goal

Make the data pipeline easy to understand, easy to describe, and easy to validate. One production workflow (`full_report`), one orchestrator (`ResearchGraphRunner`), one artifact contract per run.

## Non-Goals

- Multiple run types (flash_memo, catalyst_refresh) — disabled for now
- Offline rendering without DB
- Migration of legacy artifacts to new structure
- Script directory reorganization beyond moving 2 debug scripts

---

## Section 1: Safety Fixes

Five targeted code changes that prevent wrong numbers in reports.

### 1.1 Gate SKIP → FAIL

**File:** `backend/reporting/export_gate.py`

Any gate returning `status: SKIP` must have `passed: false`. Add meta-check at end of `run_export_gate()`: if any gate status is SKIP, set `is_final_exportable = false` with blocking reason `"gate_skipped:{gate_name}"`.

**Test:** `test_gate_skip_is_fail` — assert SKIP gates block export.

### 1.2 Golden CSV Override Logging

**File:** `scripts/build_facts.py` (and the internal `build_facts()` function)

After merging golden CSV facts with DB facts, compare overlapping `(metric, period)` pairs. Log `GOLDEN_OVERRIDE` warning with both values, sources, and variance %. If variance > 10% on any metric, add to `blocking_reasons`.

**Test:** `test_golden_override_warning` — assert warning at >2%, blocking at >10%.

### 1.3 Core-Metric Conflict Blocks Valuation

**File:** `backend/facts/completeness.py`

When building the validation report, check `source_conflicts` from `build_source_conflict_report()`. If any `ConflictRecord` has `requires_review=True` AND the metric is in `CORE_FY_KEYS`, set `valuation_gate = "fail"` with blocking reason `"core_metric_conflict:{metric}:{period}"`.

**Test:** `test_core_conflict_blocks_valuation` — assert conflict on revenue.net blocks valuation.

### 1.4 Eliminate Glob Fallback

**File:** `backend/reporting/report_data_loader.py`

Remove `allow_latest_artifacts` parameter from `_resolve_artifact()`. Remove the glob fallback branch. Always require a manifest (which requires `run_id`). `_resolve_artifact()` without manifest raises `ValueError`.

Exception: `scripts/demo/` scripts may load artifacts however they want — they are not production code.

**Test:** `test_no_glob_in_production` — assert ValueError when no manifest provided.

### 1.5 Stale Data Threshold Fix

**File:** `scripts/evaluate_report.py`

Change FY financial statement staleness threshold from 30 days to 540 days (18 months). Market price data stays at 5 business days.

**Test:** Update existing staleness test to reflect new threshold.

---

## Section 2: Single Production Path

### 2.1 One Orchestrator

`scripts/run_research.py` → `ResearchGraphRunner.execute()` is the only production path.

Scripts that become dev-only wrappers (header: `# DEV-ONLY — production runs use run_research.py`):
- `scripts/build_facts.py` — prints to stdout, writes to `artifacts/dev/`
- `scripts/run_valuation.py` — same
- `scripts/generate_report.py` — same
- `scripts/render_report.py` — same

Dev wrappers never write to `artifacts/runs/`. They exist for single-stage debugging only.

### 2.2 Run-Scoped Artifact Directory

Every production tool writes to `artifacts/runs/{run_id}/` instead of flat timestamp-named files in `artifacts/facts/`, `artifacts/valuation/`, etc.

The `run_id` is already available in `ResearchGraphState` and passed to all tools. Each tool function in `backend/harness/tools.py` changes its output path.

Legacy flat directories are frozen — no new files written, no deletion.

### 2.3 Artifact Contract

One production run produces exactly these files:

```
artifacts/runs/{run_id}/
  manifest.json       — run metadata + file inventory
  facts.json          — FactTable + validation + conflicts + tier coverage
  valuation.json      — forecast + fcff + fcfe + blend + sensitivity + assumptions + formula_traces
  evidence.json       — claims + citations + source_manifest
  report_draft.md     — Vietnamese narrative (always written)
  export_gate.json    — 9-gate results + render_mode decision
  trace.jsonl         — append-only: tool calls, agent messages, gate results, approvals
  report.html         — ONLY if export_gate passes
  report.pdf          — ONLY if export_gate passes
```

### 2.4 Merged valuation.json

`run_valuation()` returns one dict. The harness tool writes one file:

```json
{
  "ticker": "DHG",
  "snapshot_id": "snap_...",
  "forecast": { "..." },
  "fcff": { "base": {}, "bull": {}, "bear": {} },
  "fcfe": { "..." },
  "blend": { "target_price_vnd": 0, "weights": {} },
  "sensitivity": { "wacc_g_matrix": [], "eps_pe_matrix": [] },
  "assumptions": { "..." },
  "formula_traces": [],
  "valuation_methods": ["FCFF", "PE_Forward"],
  "currency": "VND",
  "unit_policy": "vnd_absolute"
}
```

Individual sub-module functions (`fcff.py`, `blend.py`, etc.) still return their own dicts. The merge happens in `run_valuation_tool()` which assembles them into one payload before writing.

### 2.5 Merged evidence.json

Citation map, evidence packet, and source manifest merge into one file:

```json
{
  "claims": [{"claim_id": "...", "text": "...", "type": "financial_fact", "status": "supported"}],
  "citations": {"claim_id": {"fact_id": "...", "source_uri": "...", "source_tier": 0}},
  "source_manifest": [{"source_id": "...", "source_uri": "...", "tier": 0, "title": "..."}]
}
```

Written by `generate_report_tool()` which already produces claims and citations.

### 2.6 trace.jsonl

Replaces: agent handoffs, agent effectiveness audit, agent payload artifacts.

Each line is one JSON object:

```jsonl
{"ts":"...","kind":"tool_call","tool":"build_facts","agent":"data_retrieval","status":"completed","summary":{}}
{"ts":"...","kind":"agent_message","agent":"data_retrieval","action":"review","confidence":0.85}
{"ts":"...","kind":"gate_result","gate":"data_quality_gate","passed":true,"issues":[]}
{"ts":"...","kind":"approval","stage":"valuation_assumptions","decision":"approved","reviewer":"analyst"}
```

The runner appends to this file throughout execution. Methods removed from `ResearchGraphRunner`:
- `_write_agent_handoff()` → trace.jsonl line with `kind: "agent_handoff"`
- `_write_agent_payload_artifact()` → trace.jsonl line with `kind: "agent_message"` (payload in summary)
- `_write_agent_effectiveness_audit()` → removed entirely (trace.jsonl is the audit)

### 2.7 Disabled Outputs

Removed from production path:
- Layout audit as separate JSON → folded into `export_gate.json` as `layout_check` key
- Agent handoff JSON files → replaced by trace.jsonl
- Agent effectiveness audit JSON → replaced by trace.jsonl
- Agent payload artifact JSON → replaced by trace.jsonl
- `flash_memo` run type → rejected at preflight (already the case)
- `catalyst_refresh` run type → rejected at preflight (already the case)

### 2.8 reports/ Is Output-Only

- Only approved final PDFs: `reports/{ticker}_{run_id}_final.pdf`
- Draft markdown → `artifacts/runs/{run_id}/report_draft.md`
- No BLOCKED .md files in `reports/`
- `reports/eval/` stays

### 2.9 Export Gate Controls Final Output

In `ResearchGraphRunner._execute_stage()` for the render/export stages:

```python
if export_gate_passed:
    render_html(run_dir / "report.html")
    render_pdf(run_dir / "report.pdf")
else:
    # report.html and report.pdf are NOT created
    # run status = BLOCKED

# Later, after HITL final approval in PUBLISHED stage:
if final_approval == "approved" and export_gate_passed:
    copy(run_dir / "report.pdf", reports_dir / f"{ticker}_{run_id}_final.pdf")
```

---

## Section 3: Physical Cleanup

### 3.1 Delete Chrome Temp Profiles

```bash
rm -rf artifacts/reports_pdf/.chrome-profile-*/
```

### 3.2 Delete Stale BLOCKED Reports

```bash
rm reports/*_BLOCKED.md
```

### 3.3 Move Debug Scripts

```
scripts/test_retrieval.py    → scripts/debug/test_retrieval.py
scripts/check_ocr_runtime.py → scripts/debug/check_ocr_runtime.py
```

### 3.4 Gitignore

Add:
```
artifacts/runs/
artifacts/reports_pdf/.chrome-profile-*/
artifacts/dev/
reports/*.md
!reports/eval/
```

### 3.5 Delete Root-Level Temp Files

Delete from repo root:
```
_audit_agent_*.txt
current_state_review_for_claude.md
CALCULATION_MODEL_AUDIT_PLAN_FOR_CLAUDE.md
FRONTEND_PLAN_FINROBOT_STYLE.md
```

### 3.6 Freeze Legacy Flat Dirs

Add `artifacts/README.md`:
```
Production runs write to artifacts/runs/{run_id}/.
Legacy flat directories (facts/, valuation/, forecast/, etc.) are frozen.
```

---

## Section 4: Tests & Validation

### 4.1 Baseline

Run `pytest tests/ -x` before any changes. All ~1345 tests must pass.

### 4.2 Tests to Update

Tests referencing old artifact paths or glob fallback → update paths to `artifacts/runs/{run_id}/`. Tests checking for separate forecast/fcff/blend files → check keys in `valuation.json`. Tests asserting handoff/agent_effectiveness files → assert trace.jsonl lines.

### 4.3 New Tests

| Test | File | Asserts |
|---|---|---|
| `test_gate_skip_is_fail` | `tests/unit/test_export_gate.py` | SKIP gates have passed=false; meta-gate blocks on any SKIP |
| `test_golden_override_warning` | `tests/unit/test_build_facts.py` | >2% logs warning; >10% adds blocking_reason |
| `test_core_conflict_blocks_valuation` | `tests/unit/test_completeness.py` | Conflict on CORE_FY_KEY → valuation_gate=fail |
| `test_no_glob_in_production` | `tests/unit/test_report_data_loader.py` | ValueError without manifest |
| `test_run_scoped_artifacts` | `tests/unit/test_tools_storage_path.py` | All files in artifacts/runs/{run_id}/ |
| `test_valuation_json_merged` | `tests/unit/test_valuation_artifact.py` | Single file has all expected keys |
| `test_evidence_json_merged` | `tests/unit/test_evidence_artifact.py` | Single file has claims, citations, source_manifest |
| `test_trace_jsonl_events` | `tests/unit/test_trace.py` | At least one line per kind |
| `test_export_gate_controls_html_pdf` | `tests/unit/test_export_gate.py` | Failed gate → no html/pdf; passed → both exist |
| `test_reports_dir_output_only` | `tests/unit/test_report_output.py` | No .md written to reports/ |

### 4.4 E2E Validation

After all changes, run:
```
python scripts/run_research.py --ticker DHG
```

Verify:
- `artifacts/runs/{run_id}/` has 7 mandatory files
- No new files in legacy flat dirs
- `trace.jsonl` has lines for every stage
- `manifest.json` lists correct paths
- All existing tests pass

---

## Implementation Order

1. **Section 3 (Physical cleanup)** — zero code risk, clears the ground
2. **Section 1 (Safety fixes)** — small targeted changes with tests
3. **Section 2 (Single production path)** — the main restructure
4. **Section 4 (E2E validation)** — confirms everything works

---

## Files Modified (Estimated)

| File | Changes |
|---|---|
| `backend/reporting/export_gate.py` | SKIP→FAIL meta-gate |
| `backend/facts/completeness.py` | Core conflict blocks valuation |
| `backend/reporting/report_data_loader.py` | Remove glob fallback |
| `backend/harness/tools.py` | Run-scoped output paths, merged artifacts |
| `backend/harness/runner.py` | trace.jsonl writer, remove handoff/audit writers, export-gate-controls-render |
| `scripts/build_facts.py` | Golden override logging, dev-only wrapper |
| `scripts/run_valuation.py` | Dev-only wrapper |
| `scripts/generate_report.py` | Dev-only wrapper |
| `scripts/render_report.py` | Dev-only wrapper |
| `scripts/evaluate_report.py` | Stale threshold fix |
| `.gitignore` | New entries |
| 10+ test files | Path updates + 10 new tests |
