# Audit: Remove Human Review from Runtime Pipeline

**Date:** 2026-06-11
**Scope:** Remove all HITL/human-review/approval concepts from the automated multi-agent harness pipeline.

## Summary

All human-review, HITL, and manual-approval concepts have been removed from the automated pipeline runtime (`backend/harness/`). The pipeline now uses only machine states: `completed`, `failed`, `skipped`, `blocked`.

## Files Changed

### Core State Model — `backend/harness/state.py`
- `NodeStatus`: removed `"needs_review"` → now `Literal["completed", "failed", "skipped"]`
- `RunDbStatus`: replaced `"needs_human_review"` with `"blocked"`
- `AgentResult`: removed `requires_human: bool` and `review_reason: str | None`
- `ResearchGraphState`: removed `requires_human`, `approvals`, `human_review_decisions`, `next_resume_stage`

### Pipeline Runner — `backend/harness/runner.py`
- `run_until_pause`: checks `blocking_reason` instead of `requires_human`
- `_run_stage` exception handler: always sets `status = "failed"` (no conditional on `requires_human`)
- `_execute_stage`: all `enforce_review=False` parameters removed from `_merge_agent_result` calls
- `_record_gate`: sets `status = "blocked"` on critical gate failure; checks severity before blocking
- `_merge_agent_result`: simplified — no `requires_human`/`enforce_review` logic
- `_run_agent` ValidationError handler: `completed` + warnings if payload exists, `failed` if no payload
- `_handle_evidence_request`: no `requires_human` escalation
- `_charge_agent_step`: raises `RuntimeError` on budget breach instead of setting `requires_human`
- `_render_and_publish_final_report`: uses `blocked`/`failed` states only
- `workflow_export_gate`: called without `final_approval_required` parameter

### LLM Adapter — `backend/harness/model_adapter.py`
- Removed `requires_human` and `review_reason` from LLM output template
- Malformed JSON → `status="failed"` with `blocking_reason` (was `needs_review` + `requires_human=True`)
- Status normalization: `completed` if payload exists, `failed` if not — for any non-standard status
- Removed `requires_human` and `review_reason` from `AgentResult` construction

### Gates — `backend/harness/gates.py`
- `financial_analyst_gate`: removed `requires_human` check; now only fails if `status == "failed"` AND no payload
- `approval_path_gate`: removed entirely
- `workflow_export_gate`: removed `final_approval_required` parameter, removed `APPROVAL_PATH_GATE` requirement, removed human-approval checks

### API Schemas — `backend/schemas.py`
- `RunStatus.NEEDS_REVIEW` → `RunStatus.BLOCKED`
- Removed `ApprovalRequest` class

### DB Status Mapping — `backend/runtime_store.py`
- `"needs_human_review": "NEEDS_REVIEW"` → `"blocked": "BLOCKED"` in both mapping dicts

### Tests Updated
- `tests/unit/test_report_assembler.py` — Updated assertion from `needs_human_review` to `failed`, removed `requires_human` check

## Concepts NOT Removed (Data-Layer, Out of Scope)

The following use `needs_review` as a **data validation status** for individual facts, not as a pipeline HITL concept:
- `backend/validation/confidence.py` — confidence scoring status
- `backend/documents/ocr_reconciliation.py` — reconciliation decision
- `backend/database/canonical/fact_promotion.py` — fact quality status
- `backend/documents/document_candidate_ranker.py` — document ranking
- Connector scripts — validation status values
- `backend/reporting/export_gate.py` — reporting-layer gate (not used by harness)
- `backend/reporting/section_builder.py` — display field in quality summary table

## Verification

### Tests
- **1057 tests pass** (0 failures)
- No test references `requires_human`, `needs_human_review`, or `review_reason` in the harness context

### Invariants Proven
1. No human/HITL/manual approval states are required in the pipeline
2. Recoverable schema warnings continue (`completed` + warning if payload exists)
3. Invalid valuation/citation/numeric artifacts still block export (gate severity checks)
4. Final report can be exported only when automated gates pass
5. Budget exhaustion raises `RuntimeError` (no human escalation)

## Pipeline State Machine (Post-Refactor)

```
INIT → INGEST → ANALYZE → FORECAST_AND_VALUE → SYNTHESIZE → REVIEW → EXPORT_GATES → PUBLISH
                                                                                        ↓
                                                                                    completed | failed | blocked
```

- `completed` — all stages passed, report exported
- `failed` — unrecoverable error or critical gate failure with no payload
- `blocked` — critical gate failure with actionable data (e.g., missing required components)
