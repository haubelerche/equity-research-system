# Flow Consistency Audit and Improvement Plan

**Generated:** 2026-06-06
**Auditors:** 5 specialized subagents (flow-architecture, data-facts, valuation, report-citation, ops-eval)
**Scope:** Full codebase audit — no production code edited

---

## 1. Executive Summary

**Current state:** The system implements a real 16-stage sequential pipeline (`ResearchGraphRunner`) with deterministic Python analytics, LLM-drafted narratives, 11+ blocking gates, two HITL approval checkpoints, checkpoint/resume support, and budget tracking. The architecture correctly separates computation (Python) from reasoning (LLM agents). All 5 agent roles are defined with versioned prompts and tool permissions. The codebase has ~1,044+ tests across 89 test files.

**Production readiness: Medium.**

The core pipeline is architecturally sound but has critical gaps in data validation, citation visibility, and gate enforcement that can produce materially wrong or unauditable reports.

### Top 5 Critical Issues

| # | Issue | Severity | Area |
|---|-------|----------|------|
| 1 | No unit validation per metric — "vnd" and "vnd_bn" can coexist for same metric without gate rejection | P0 | Data/Facts |
| 2 | Golden CSV facts bypass promotion confidence gate — sub-0.80 confidence facts auto-locked | P0 | Data/Facts |
| 3 | Source tier coverage gate not enforced at export — Tier-3-only periods don't block valuation | P0 | Data/Facts |
| 4 | Citation traces not embedded in report — claim ledger exists internally but reader sees no footnotes or source appendix | P1 | Report |
| 5 | Dual gate systems (harness/gates.py vs reporting/export_gate.py) with overlapping but misaligned semantics | P1 | Ops |

---

## 2. Expected Target Flow

Per CLAUDE.md §4 and docs/SEQUENCE.md:

| Step | Stage | Input Artifact | Output Artifact |
|------|-------|----------------|-----------------|
| 1 | Analyst starts run | ticker, run_type, scenarios | run_id |
| 2 | Supervisor validates scope | run_id, policy | execution_plan |
| 3 | Data/Retrieval collects filings | ticker, year_range | raw_payload + source_versions |
| 4 | Parser/OCR extracts | raw PDFs, API data | candidate_facts |
| 5 | Fact promotion normalizes | candidate_facts | canonical_facts (FactTable) |
| 6 | Data quality gate | FactTable | gate_result (pass/fail) |
| 7 | Facts locked | FactTable | snapshot_id |
| 8 | Analytics computes | snapshot_id | ratios, forecast, valuation_artifact |
| 9 | Analyst approves assumptions | assumptions_table | HITL approval record |
| 10 | Retrieval builds evidence | facts + chunks | evidence_pack |
| 11 | Report Writer drafts | locked artifacts only | draft_report (Vietnamese) |
| 12 | Critic/export gates validate | draft_report + valuation | gate_results (11 gates) |
| 13 | Analyst approves final | draft_report | HITL approval record |
| 14 | Export renders | approved report | PDF/HTML |

---

## 3. Current Flow Observed

**Entry points:**
- `scripts/run_research.py` → `ResearchGraphRunner.execute()` (production)
- `scripts/run_valuation.py` → standalone valuation (CLI tool, ~900 lines)
- `scripts/run_full_pipeline.py` → **deprecated**, prints warning (stale code)

**Actual pipeline stages** (backend/harness/graph.py):
```
PREFLIGHT → SUPERVISOR_PLAN → DATA_RETRIEVAL_RUN → DATA_QUALITY_GATE
→ FINANCIAL_ANALYST_RUN → FINANCIAL_ANALYST_GATE → VALUATION_RUN → VALUATION_GATE
→ WAITING_ASSUMPTIONS_APPROVAL → VALUATION_LOCKED
→ REPORT_WRITER_CRITIC_RUN → QUALITY_EVALUATION → CITATION_GATE → EXPORT_GATE
→ WAITING_FINAL_APPROVAL → PUBLISHED
```

**Orchestration:** Custom sequential loop in `runner.py:run_until_pause()` (lines 99-127). LangGraph is compiled but NOT used for execution — retained as validation artifact only (line 103 comment).

**Agent reality:** 5 agent roles (supervisor, data_retrieval, financial_analyst, valuation, report_writer_critic) defined in `config/agents/agents.yml`. Each is a stateless single-shot Claude API call via `model_adapter.py` — no reasoning loops, no memory, no branching. All deterministic computation in `backend/analytics/` modules.

**State management:** `ResearchGraphState` (Pydantic, ~175 fields) checkpointed to PostgreSQL after every stage. Resume from checkpoint via `handle_approval()`. Rejection invalidates downstream artifacts.

**Relevant files:**
- `backend/harness/runner.py` — main orchestrator (904 lines)
- `backend/harness/graph.py` — stage definitions
- `backend/harness/state.py` — state model
- `backend/harness/gates.py` — 11 blocking gates
- `backend/harness/tools.py` — 9 registered tools
- `backend/harness/agent_registry.py` — agent config loader
- `backend/harness/model_adapter.py` — Anthropic Claude adapter
- `backend/reporting/export_gate.py` — separate 9-gate export system

---

## 4. Gap Analysis

| Area | Expected | Current | Gap | Severity | Evidence |
|------|----------|---------|-----|----------|---------|
| Unit validation | Reject conflicting units per metric | No unit whitelist enforcement | P0 — "vnd" and "vnd_bn" can coexist for same metric_id | P0 | normalizer.py: FactEntry has unit field but no schema constraint |
| Golden CSV confidence | Apply same promotion gate (≥0.80) | Golden CSV bypasses promote_candidate_fact() | P0 — sub-0.80 confidence facts auto-locked | P0 | normalizer.py:447; fact_promotion.py:141 only for OCR path |
| Source tier enforcement | Block Tier-3-only periods at export | Gate computed but not enforced in valuation_gate | P0 — Tier-3-only FY periods don't block | P0 | completeness.py:239; harness/gates.py:valuation_gate() |
| Citation visibility | 100% citation coverage in report | Claim ledger exists but not rendered in PDF/HTML | P1 — reader cannot verify claims | P1 | claim_ledger.py; no footnote injection in section_builder |
| Gate system unity | Single authoritative gate system | Two systems: harness/gates.py (11) and export_gate.py (9) | P1 — unclear which is authoritative | P1 | runner.py:372; export_gate.py:347 |
| FCFF/FCFE gap check | Blend blocked if gap >25% | price_fcfe never passed to blend_dcf() | P1 — gap gate never fires | P1 | blend.py:106; run_valuation.py:484 |
| Peer group data | Peer median P/E from dataset | Target P/E hardcoded (default 15.0) | P1 — no peer data loader | P1 | run_valuation.py:213; multiples.py:165 |
| Human review gate | Workflow sets approval_status | No upstream workflow; gate always FAILS | P1 — export always analyst_draft | P1 | export_gate.py:330-342 |
| Approval timestamps | When + how long to approve | Only reviewer + decision recorded | P1 — audit trail incomplete | P1 | runtime_store.py:459-466 |
| LLM cost tracking | Actual provider billing | Approximate formula (0.2¢/1K prompt) | P2 — cost estimates unreliable | P2 | services.py:24-58 |
| Resume CLI | `resume_run --run-id X` | Must reconstruct state manually | P2 — no documented recovery | P2 | runner.py:99 |
| Draft status leak | client_final → safe status only | status="NEEDS_REVIEW" can appear in HTML banner | P2 — internal term leakage | P2 | report.html.j2:49-52 |
| Checkpoint during tools | Sub-stage checkpoints for long tools | Tools are atomic (5-10 min, no internal checkpoint) | P2 — crash → full tool retry | P2 | tools.py; runner.py:434 |
| OfflineEvaluator | Real grounding/accuracy scoring | Stub returning static scores | P2 — no real evaluation | P2 | services.py:75-98 |

---

## 5. High-Risk Findings

### Finding HR-01: Unit Validation Missing Per Metric
- **Severity:** P0
- **Affected modules:** `backend/facts/normalizer.py`, `backend/documents/ocr_candidate_facts.py`
- **What is wrong:** FactEntry carries a `unit` field but no schema validates it against metric_id. A metric like `revenue.net` can be ingested as both "vnd" and "vnd_bn" without rejection.
- **Why it is risky:** 1000x magnitude error in valuation. Revenue stored as VND instead of VND bn produces nonsensical FCFF.
- **Example failure:** PDF parser extracts revenue as 5,000 (VND bn), CafeF reports 5,000,000 (VND mn). Both ingested — lower tier wins selection, but unit mismatch means value is 1000x wrong.
- **Recommended fix:** Add unit whitelist per metric_id in `financial_metric_dictionary.yaml`. Reject promotion if unit doesn't match. Validate in `build_fact_table()` and `promote_candidate_fact()`.
- **Acceptance criteria:** Ingesting same metric_id with different units raises ValidationError.
- **Suggested tests:**
  - [ ] Ingest revenue.net as "vnd" and "vnd_bn" in same batch → expect gate failure
  - [ ] Golden CSV with wrong unit for metric → expect rejection

### Finding HR-02: Golden CSV Bypasses Confidence Gate
- **Severity:** P0
- **Affected modules:** `backend/facts/normalizer.py:390-451`, `backend/documents/fact_promotion.py:141`
- **What is wrong:** `load_golden_csv_supplement()` returns facts that merge directly into `raw_facts` before `build_fact_table()`. These facts bypass `promote_candidate_fact()`, which enforces `min_confidence=0.80`. A golden CSV fact with confidence 0.75 is auto-locked.
- **Why it is risky:** Low-confidence facts in golden CSV enter valuation without review.
- **Example failure:** Analyst enters equity.parent with confidence 0.85 in CSV; no gate challenges it. If the value is wrong, valuation is wrong.
- **Recommended fix:** After golden CSV load, apply same confidence gate: facts <0.80 marked as "needs_review". Add `reconciliation_status="manual_reviewed"` flag.
- **Acceptance criteria:** Golden CSV fact with confidence <0.80 triggers NEEDS_REVIEW.
- **Suggested tests:**
  - [ ] Load golden CSV with confidence 0.75 → expect NEEDS_REVIEW status

### Finding HR-03: Source Tier Coverage Not Enforced at Export
- **Severity:** P0
- **Affected modules:** `backend/facts/completeness.py:223-239`, `backend/harness/gates.py`
- **What is wrong:** `check_source_tier_coverage()` identifies Tier-3-only periods but the result is only logged in the Data Validation Report. `valuation_gate()` does not check this. Final export can proceed with all material periods sourced only from API data.
- **Why it is risky:** Tier-3 data (CafeF API) is unaudited; basing valuation on it violates the source quality doctrine.
- **Example failure:** DBD 2025 data from CafeF only (Tier 3). Valuation runs, report exports — no blocking gate despite zero official source coverage.
- **Recommended fix:** Persist `source_tiers_by_period` in state artifacts. Add check to `valuation_gate()` or `export_gate()`: any material FY period with Tier-3-only sources → block final export.
- **Acceptance criteria:** Tier-3-only material period blocks export with explicit reason.
- **Suggested tests:**
  - [ ] Ingest 3 FY periods, all Tier-3 → expect export gate FAIL

### Finding HR-04: Citation Traces Not Visible in Report
- **Severity:** P1
- **Affected modules:** `backend/citations/claim_ledger.py`, `backend/reporting/section_builder.py`, `backend/reporting/templates/report.html.j2`
- **What is wrong:** `ClaimLedger` registers claims with fact/artifact/formula traces. `citation_artifact_writer.py` writes ledger JSON. But the rendered PDF/HTML contains pure prose — no footnotes, endnotes, or source appendix. The reader cannot verify which numbers are traced.
- **Why it is risky:** Violates CLAUDE.md §7: "Cite exact fact records or document chunks, not vague source names." Report looks professional but is not audit-proof.
- **Example failure:** Report states "Doanh thu 2025 đạt 2,500 tỷ đồng" — claim exists in ledger, but PDF reader has no way to verify source.
- **Recommended fix:** Extend `client_section_builder.py` to inject `[^N]` markdown footnotes. Add "Nguồn & Trích dẫn" appendix section listing claim_id → source mapping. Include in Page 8.
- **Acceptance criteria:** Every quantitative claim in client_final PDF has a visible footnote linking to source.
- **Suggested tests:**
  - [ ] Build report with 5 claims → verify footnote markers in rendered HTML
  - [ ] Verify appendix lists all claim sources with tier and URI

### Finding HR-05: Dual Gate Systems Misaligned
- **Severity:** P1
- **Affected modules:** `backend/harness/gates.py`, `backend/reporting/export_gate.py`
- **What is wrong:** Two independent gate implementations exist. `harness/gates.py` has 11 gates checking tool permissions, artifact manifests, formula traces, evidence packets, agent handoffs, and approval paths. `reporting/export_gate.py` has 9 gates checking source, reconciliation, numeric consistency, forecast, valuation, sensitivity, citation, layout, and human review. Both have an `export_gate()` function. Runner calls both systems.
- **Why it is risky:** Unclear which system is authoritative. A report could pass harness gates but fail export gates (or vice versa). Conflicting decisions create operator confusion.
- **Example failure:** Harness export_gate passes (all structural gates OK). But reporting export_gate fails on numeric_consistency. Report is in limbo.
- **Recommended fix:** Document authoritative scope: harness gates = structural/workflow integrity; reporting gates = content quality. Add integration test verifying both agree on final decision. Rename one to avoid `export_gate` collision.
- **Acceptance criteria:** Single documented decision path. Integration test confirms both systems produce consistent export/block decision.
- **Suggested tests:**
  - [ ] Run both gate systems on same artifacts → verify agreement
  - [ ] Rename harness export_gate to `workflow_export_gate()`

### Finding HR-06: FCFF/FCFE Gap Gate Never Fires
- **Severity:** P1
- **Affected modules:** `backend/analytics/blend.py:105-106`, `scripts/run_valuation.py:484`
- **What is wrong:** `blend_dcf()` accepts optional `price_fcfe` parameter and checks FCFF/FCFE gap (>25% → block). But `run_valuation.py` never passes `price_fcfe` to `blend_dcf()`. The gap gate never triggers.
- **Why it is risky:** Large FCFF/FCFE divergence (indicating model inconsistency) goes undetected. Per CLAUDE.md, FCFE is a "supplementary cross-check" — the cross-check doesn't happen.
- **Example failure:** FCFF yields 45,000 VND, FCFE yields 25,000 VND (44% gap). No warning. Blend uses FCFF+P/E only.
- **Recommended fix:** Pass `price_fcfe` to `blend_dcf()` in run_valuation.py. Add warning (not block) when gap >25%. Log to valuation artifact.
- **Acceptance criteria:** FCFF/FCFE gap >25% produces warning in valuation artifact.
- **Suggested tests:**
  - [ ] FCFF=100k, FCFE=70k (30% gap) → verify warning appended

### Finding HR-07: Default Target P/E Without Peer Data
- **Severity:** P1
- **Affected modules:** `scripts/run_valuation.py:213`, `backend/analytics/multiples.py:165-193`
- **What is wrong:** `target_pe=15.0` is hardcoded as CLI default. `multiples.py` blocks when `peer_data_source=None`, but `run_valuation.py` doesn't pass `peer_data_source`. Target P/E is silently treated as peer-derived.
- **Why it is risky:** Violates CLAUDE.md §6: "Target P/E must have a written rationale in the assumptions table — not reverse-engineered from a desired price."
- **Recommended fix:** Pass `peer_data_source="analyst_default_pending_peers"` when target_pe is CLI default. Set `relative_valuation_status="pending_peer_dataset"` in output artifact.
- **Acceptance criteria:** Default target P/E produces "pending_peer_dataset" status, not silent acceptance.
- **Suggested tests:**
  - [ ] Run valuation with default P/E → verify pending_peer_dataset status

### Finding HR-08: Human Review Gate Has No Upstream Workflow
- **Severity:** P1
- **Affected modules:** `backend/reporting/export_gate.py:330-342`
- **What is wrong:** `_human_review_gate()` FAILs unless `approval_status == "approved"`. No workflow sets this field — only `None`, `"pending"`, or missing. Every export defaults to analyst_draft.
- **Why it is risky:** The gate works correctly as a blocker, but there's no documented path to unblock it. Operators must manually patch the artifact.
- **Recommended fix:** Integrate with `handle_approval()` from runner.py. When final_report is approved, set `approval_status="approved"` in report artifact before export gate evaluation.
- **Acceptance criteria:** After `handle_approval(decision="approve")`, export gate human_review passes.
- **Suggested tests:**
  - [ ] Full pipeline → approve final → verify human_review_gate PASS

### Finding HR-09: Approval Audit Trail Missing Timestamps
- **Severity:** P1
- **Affected modules:** `backend/runtime_store.py:449-466`
- **What is wrong:** `add_approval()` stores run_id, stage, decision, reviewer, feedback_patch_json. No explicit approval_timestamp or session context. PostgreSQL may auto-record `created_at` but it's not exposed in the API.
- **Why it is risky:** Audit compliance requires "who approved what, when." Duration and timing cannot be reconstructed.
- **Recommended fix:** Add `approval_timestamp`, `approval_duration_minutes`, `session_id` columns. Expose in query results.
- **Acceptance criteria:** Approval records include ISO8601 timestamp queryable via API.
- **Suggested tests:**
  - [ ] Submit approval → query record → verify timestamp present

### Finding HR-10: Core P/E + Net Cash May Double-Strip Financial Income
- **Severity:** P1
- **Affected modules:** `backend/analytics/core_pe_net_cash.py:209-216`
- **What is wrong:** `core_eps = eps_forward - ati_per_share` (after-tax financial income per share). If `eps_forward` is derived from forecast net income that already excludes financial income, this double-strips.
- **Why it is risky:** Understates Core EPS → understates target price for cash-rich companies.
- **Recommended fix:** Verify whether forecast net_income includes or excludes financial income. Add explicit assertion/audit comment. If financial income is already excluded, skip the subtraction.
- **Acceptance criteria:** Core EPS derivation documented with explicit assumption about NI composition.
- **Suggested tests:**
  - [ ] Forecast NI includes financial income → core_eps correctly strips once
  - [ ] Forecast NI excludes financial income → core_eps does NOT double-strip

---

## 6. Optimization Opportunities

| Opportunity | Current Issue | Proposed Optimization | Impact | Effort | Priority |
|-------------|--------------|----------------------|--------|--------|----------|
| Remove stale pipeline script | `run_full_pipeline.py` deprecated but not deleted | Delete script + test | Reduce confusion | Low | P3 |
| Centralize model registry | Model names in agent_registry.py, pricing in model_adapter.py | Single ModelRegistry class | Reduce duplication | Low | P3 |
| Sub-stage checkpoints | Long tools (5-10 min) are atomic | Add checkpoint after each CSV/PDF in build_facts | Faster crash recovery | Medium | P2 |
| Configurable conflict thresholds | Hardcoded 2%/10% in normalizer.py | Add to settings.py | Analyst flexibility | Low | P2 |
| Real LLM cost tracking | Approximate formula-based | Use actual API response token counts | Accurate budget control | Medium | P2 |
| Resume CLI command | Manual state reconstruction | `run_research resume --run-id X` | Operator efficiency | Medium | P2 |
| Remove LangGraph build artifact | Compiled graph never executed | Delete or use for execution | Reduce confusion | Low | P3 |
| Implement OfflineEvaluator | Stub returning static scores | Real grounding/accuracy scoring | Pre-release quality | High | P2 |

---

## 7. Recommended Target Architecture

### API/BFF Layer
- FastAPI app (`backend/api.py`) for run submission, approval, status queries
- CLI scripts for analyst workflows (`run_research.py`, `approve_report_cli.py`)
- **Should be:** Thin routing layer, no business logic

### Orchestrator/State Machine
- `ResearchGraphRunner` with 16 linear stages
- **Should be:** Deterministic sequential executor (current design is correct)
- **Remove or integrate:** Unused LangGraph compilation; decide whether it's validation-only or execution engine

### Data Plane
- PDF extractor, CafeF connector, OCR pipeline → candidate facts → promotion → canonical FactTable
- **Should be:** Deterministic service with explicit gates at each transition
- **Fix:** Add unit validation, enforce confidence gate for golden CSV, enforce tier coverage at export

### Agent/Service Layer
- 5 agent roles as stateless LLM calls with versioned prompts
- Analytics modules as pure Python functions
- **Should be:** Agents = reasoning/interpretation ONLY; services = computation ONLY (current design is correct)
- **Clarify:** Agents do NOT compute — they interpret. This boundary is properly maintained.

### Evaluation/Gate Layer
- Harness gates (11): structural/workflow integrity
- Export gates (9): content quality
- **Should be:** Single unified gate registry with clear scope documentation
- **Fix:** Rename harness `export_gate` → `workflow_export_gate`; document scope separation; add integration test for agreement

### Export Layer
- HTMLRenderer → PDFRenderer with Vietnamese font stack and forbidden-term preflight
- **Should be:** Gated by unified export decision; no internal terms in output
- **Fix:** Add citation footnotes to rendered report; enforce status codes in client_final mode

### What Should Be Agents vs Services
| Component | Type | Rationale |
|-----------|------|-----------|
| Supervisor plan | Agent | Requires reasoning about scope and routing |
| Data retrieval review | Agent | Interprets data quality narrative |
| Financial analyst review | Agent | Interprets ratio patterns and anomalies |
| Valuation review | Agent | Reviews assumptions and model limitations |
| Report writer critic | Agent | Drafts Vietnamese narrative from artifacts |
| Fact normalization | Service | Deterministic selection rules |
| Analytics (ratios, FCFF, etc.) | Service | Pure Python computation |
| Gates | Service | Deterministic pass/fail checks |
| PDF/HTML rendering | Service | Template-based output |
| Citation mapping | Service | Deterministic claim-to-fact linking |

---

## 8. Refactor Plan

### Phase 1 — Block Correctness Risks (P0 fixes)

**Task 1.1: Unit validation per metric**
- Objective: Prevent mixed units for same metric_id
- Files: `backend/facts/normalizer.py`, `backend/documents/fact_promotion.py`, `config/financial_metric_dictionary.yaml`
- Implementation: Add `expected_unit` field to metric dictionary. Validate in `build_fact_table()` and `promote_candidate_fact()`.
- Acceptance: Conflicting units raise ValidationError
- Tests: `test_unit_validation_per_metric`

**Task 1.2: Golden CSV confidence gate**
- Objective: Apply min_confidence=0.80 to golden CSV facts
- Files: `backend/facts/normalizer.py:390-451`
- Implementation: After `load_golden_csv_supplement()`, filter facts with confidence <0.80 to "needs_review" status
- Acceptance: Sub-0.80 golden facts trigger NEEDS_REVIEW
- Tests: `test_golden_csv_confidence_gate`

**Task 1.3: Source tier coverage enforcement**
- Objective: Block final export when material periods are Tier-3-only
- Files: `backend/harness/gates.py`, `backend/harness/runner.py`
- Implementation: Persist `source_tiers_by_period` in state. Add check to `export_gate()`.
- Acceptance: Tier-3-only material period blocks final export
- Tests: `test_tier_3_only_blocks_export`

**Task 1.4: FCFE cross-check activation**
- Objective: Enable FCFF/FCFE gap warning in blend
- Files: `scripts/run_valuation.py:484`, `backend/analytics/blend.py`
- Implementation: Pass `price_fcfe` to `blend_dcf()`. Log warning (not block) when gap >25%.
- Acceptance: FCFF/FCFE divergence produces warning in valuation artifact
- Tests: `test_blend_fcfe_gap_warning`

### Phase 2 — Normalize Workflow and Artifacts

**Task 2.1: Unify gate systems**
- Objective: Clear scope for harness gates vs export gates
- Files: `backend/harness/gates.py`, `backend/reporting/export_gate.py`
- Implementation: Rename harness `export_gate` → `workflow_export_gate`. Document scope in CLAUDE.md. Add integration test.
- Acceptance: No naming collision. Both systems produce consistent decisions.
- Tests: `test_dual_gate_systems_agree`

**Task 2.2: Citation footnotes in report**
- Objective: Make claim traces visible to report reader
- Files: `backend/reporting/section_builder.py`, `backend/reporting/templates/report.html.j2`, `backend/citations/claim_ledger.py`
- Implementation: Inject `[^N]` footnotes for quantitative claims. Add "Nguồn & Trích dẫn" appendix.
- Acceptance: Client-final PDF has footnotes linking to source tier and URI
- Tests: `test_citations_appended_as_footnotes`

**Task 2.3: Human review gate integration**
- Objective: Connect handle_approval() to export gate human_review_gate
- Files: `backend/harness/runner.py`, `backend/reporting/export_gate.py`
- Implementation: When final_report approved, set `approval_status="approved"` in report artifact.
- Acceptance: Approval → human_review_gate PASS → client_final export allowed
- Tests: `test_human_review_gate_blocks_without_approval`

**Task 2.4: Default P/E peer data source**
- Objective: Flag default target P/E as pending peer data
- Files: `scripts/run_valuation.py:213`, `backend/analytics/multiples.py`
- Implementation: Pass `peer_data_source="analyst_default_pending_peers"`. Set status accordingly.
- Acceptance: Default P/E → "pending_peer_dataset" in artifact
- Tests: `test_peer_data_source_blocking`

**Task 2.5: Status code sanitization in client_final**
- Objective: Prevent internal status codes in client-facing HTML
- Files: `backend/reporting/html_renderer.py`, `backend/reporting/templates/report.html.j2`
- Implementation: Enforce `status ∈ {"FINAL_EXPORTABLE", "PUBLISHED"}` when render_mode="client_final"
- Acceptance: Status "NEEDS_REVIEW" in client_final raises error
- Tests: `test_status_code_censored_in_client_final`

### Phase 3 — Hardening and Observability

**Task 3.1: Approval timestamps**
- Objective: Record when approvals happen
- Files: `backend/runtime_store.py`
- Implementation: Add `approval_timestamp`, `session_id` to run_approvals table. Expose in queries.
- Acceptance: Approval records include ISO8601 timestamp
- Tests: `test_approval_timestamp_recorded`

**Task 3.2: Resume CLI**
- Objective: Enable run recovery without manual state reconstruction
- Files: `scripts/run_research.py`, `backend/harness/runner.py`
- Implementation: Add `--resume --run-id X` flag. Load latest_graph_state(), call run_until_pause(state, start_stage).
- Acceptance: Crashed run resumes from last checkpoint
- Tests: `test_checkpoint_recovery_after_crash`

**Task 3.3: Sub-stage checkpoints for long tools**
- Objective: Reduce blast radius of mid-tool crashes
- Files: `backend/harness/tools.py`
- Implementation: Add checkpoint callback for tools that process multiple files (build_facts, auto_ingest).
- Acceptance: Crash during build_facts resumes from last processed file
- Tests: `test_tool_long_running_checkpoint`

**Task 3.4: Actual LLM cost tracking**
- Objective: Replace approximate cost formula with real token counts
- Files: `backend/harness/model_adapter.py`, `backend/services.py`
- Implementation: Extract `usage.input_tokens`, `usage.output_tokens` from Claude API response. Store actual counts in budget_ledger.
- Acceptance: Budget ledger shows real token counts per call
- Tests: `test_budget_guard_actual_tokens`

**Task 3.5: Core P/E + Net Cash double-strip audit**
- Objective: Verify financial income handling in Core EPS
- Files: `backend/analytics/core_pe_net_cash.py:209-216`
- Implementation: Add assertion verifying NI composition. Document assumption.
- Acceptance: Explicit comment and test confirming correct stripping behavior
- Tests: `test_core_eps_no_double_strip`

### Phase 4 — Evaluation and Regression Safety

**Task 4.1: Integration test for approval flow**
- Objective: End-to-end approval cycle test
- Files: `tests/integration/test_harness_approval_resume.py`
- Implementation: Submit run → gate fails → approve → verify resume
- Acceptance: Full cycle passes in CI
- Tests: New integration test file

**Task 4.2: Implement OfflineEvaluator**
- Objective: Replace stub with real grounding/accuracy scoring
- Files: `backend/services.py:75-98`
- Implementation: Parse report claims, cross-check against evidence_packet, compute coverage %
- Acceptance: Real scores >0.8 for well-cited reports, <0.5 for hallucinated
- Tests: `test_offline_evaluator_actual_grounding`

**Task 4.3: OCR cross-PDF reconciliation**
- Objective: Detect conflicts when two PDFs cover same FY
- Files: `backend/documents/ocr_reconciliation.py`
- Implementation: Accept optional `fact_table` parameter. Fall back to FactTable lookup when secondary source missing.
- Acceptance: Second PDF for same FY conflicts against first PDF's promoted facts
- Tests: `test_ocr_vs_existing_facttable`

**Task 4.4: Derived metric versioning**
- Objective: Track formula version for derived metrics
- Files: `backend/facts/normalizer.py:292-379`
- Implementation: Add `derivation_version` field to FactEntry. Include formula_checksum.
- Acceptance: YAML formula change increments version
- Tests: `test_derived_formula_versioning`

**Task 4.5: Adversarial/red-team tests**
- Objective: Test edge cases that can produce wrong output
- Files: `tests/`
- Implementation: Zero-debt company, missing entire FY, extreme forecast horizon, malicious PDF input
- Acceptance: All edge cases handled gracefully (block or warn, never wrong output)
- Tests: Multiple edge case test files

---

## 9. Concrete TODO Checklist for Coding Agent

### Phase 1 — P0 Correctness (do first)
- [x] Add unit whitelist per metric_id — `backend/facts/metric_metadata.py` with METRIC_METADATA registry
- [x] Validate unit in `build_fact_table()` — reject mismatches via `validate_and_normalize()`
- [x] Apply confidence ≥0.80 gate to golden CSV facts in `load_golden_csv_supplement()`
- [x] Source tier coverage enforced in `data_quality_gate()` → flows to `export_gate()`
- [x] Pass `price_fcfe` to `blend_dcf()` in run_valuation.py; gap warning enabled

### Phase 2 — P1 Workflow (do second)
- [x] Rename harness `export_gate()` → `workflow_export_gate()` to avoid collision
- [x] Add "Nguồn & Trích dẫn" appendix via `build_citations_appendix()` in section_builder
- [x] Connect `handle_approval()` to set `approval_status="approved"` in report artifact
- [x] Pass `peer_data_source="analyst_default_pending_peers"` when target_pe is default
- [x] Enforce safe status codes in client_final render mode — status sanitized in html_renderer + section_builder
- [x] Add `approved_at` timestamp to `add_approval()` in runtime_store
- [ ] Document gate scope: harness = structural, reporting = content quality
- [ ] Add integration test: both gate systems agree on export decision

### Phase 3 — P2 Hardening (do third)
- [x] Audit Core P/E + Net Cash double-strip; add `financial_income_already_excluded` parameter
- [x] Delete `scripts/run_full_pipeline.py` and its test
- [x] Actual token counts already extracted from Claude API in model_adapter.py (lines 105-107)
- [ ] Add `--resume --run-id X` flag to run_research.py
- [ ] Add checkpoint callback for build_facts_tool (per-file checkpoints)
- [ ] Make conflict thresholds configurable via settings.py

### Phase 4 — Evaluation (do last)
- [x] Add integration test: full approval cycle (6 tests in test_approval_flow.py)
- [x] Add adversarial tests: zero-debt, missing FY, negative equity, zero revenue, extreme forecasts (8 tests in test_adversarial.py)
- [ ] Implement real OfflineEvaluator (grounding/accuracy scoring)
- [ ] Add FactTable parameter to `reconcile_candidate_facts()` for cross-PDF reconciliation
- [ ] Add `derivation_version` field to FactEntry for derived metrics
- [ ] Add `test_graph_execution_consistency` comparing LangGraph structure with GRAPH_STAGES loop

---

## 10. Definition of Done

- [ ] End-to-end flow is consistent: 16 stages execute in documented order with no skipped gates
- [ ] No LLM-generated financial facts exist: all numbers computed in `backend/analytics/`
- [ ] Valuation is reproducible from locked artifacts: same inputs → same FCFF/FCFE/blend/sensitivity
- [ ] Report numbers match structured data: every quantitative claim traces to canonical fact or formula
- [ ] Citations are validatable: reader can verify claim sources via footnotes or appendix
- [ ] HITL gates work: assumptions approval and final approval both block and resume correctly
- [ ] Retry/resume/partial recompute is tested: integration test for approval rejection → invalidation → re-execution
- [ ] Evaluation report exists before export: OfflineEvaluator produces real scores, not stubs
- [ ] Audit trail and cost ledger are available: approval timestamps, actual token counts, per-stage cost breakdown
- [ ] Unit validation enforced: no mixed units per metric_id
- [ ] Source tier coverage enforced: Tier-3-only periods block final export
- [ ] Gate systems documented: harness gates vs export gates have clear, non-overlapping scope
