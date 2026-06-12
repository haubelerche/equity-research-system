# Six-Agent Full Report Rebuild Audit

Audit date: 2026-06-10 Asia/Bangkok

## 1. Executive Conclusion

Decision: PARTIAL PASS

The rebuild has substantially cleaned the runtime architecture: the active agent registry contains exactly six configured agents, `RunType` is limited to `full_report`, `ResearchGraphRunner` no longer uses LangGraph or a compiled dynamic graph, and tool ownership is enforced through `ToolRegistry`.

However, the system does not yet satisfy the full acceptance criteria in `audit.md`. A real production CLI run was attempted and failed at `RESEARCH_MANAGER_PLAN` with `Connection error`; no research artifacts, valuation artifacts, report draft, claim ledger, critic review, HTML, or PDF were produced. Therefore the current state is best described as architecture cleanup plus partial harness hardening, not a verified senior-quality research system.

## 2. Actual Runtime Architecture

Observed architecture:

```text
API / batch
-> FullReportOrchestrator
-> ResearchGraphRunner
-> fixed GRAPH_STAGES
-> AgentRegistry
-> ToolRegistry
-> RuntimeStore / Supabase storage adapter
```

CLI exception:

```text
scripts/run_research.py
-> ResearchGraphRunner directly
```

This means API and batch use `FullReportOrchestrator`, but CLI bypasses it. The stage executor is still common, but the production call chain is not fully unified.

`ResearchGraphRunner` assessment:

| Required condition | Result | Evidence |
|---|---:|---|
| No LangGraph dependency | PASS | `requirements.txt` has no `langgraph`; runner imports `GRAPH_STAGES` only |
| No compiled dynamic graph | PASS | No `build_langgraph` or `_compiled_graph` references |
| No legacy five-role config loaded | PASS | `config/agents/agents.yml` has six agents only |
| No legacy coordinator/transfer concepts in runner | PASS | Runtime runner and active `config/harness/*` files use six-agent trace/manifest contracts |
| Fixed v1 full_report stages | PASS | `backend/harness/graph.py` defines fixed `GRAPH_STAGES` |
| New artifact set written | PARTIAL | Agent payloads, evidence packet, manifest, checkpoint hooks exist; live run did not reach them |
| No old report generation runtime path | PARTIAL | `generate_report_tool` removed from ToolRegistry; `scripts/generate_report.py` still exists as dev-only standalone script |
| No glob/latest production loading | PARTIAL | Production tests exclude debug/demo/storage paths; `scripts/render_report.py` still has debug `--allow-latest-artifacts` |

## 3. Production Call Chain

| Entry | Call chain | Status |
|---|---|---|
| API | `backend/api.py -> RunExecutor -> FullReportOrchestrator -> ResearchGraphRunner` | PASS |
| Batch | `backend/batch.py -> RunExecutor -> FullReportOrchestrator -> ResearchGraphRunner` | PASS |
| CLI | `scripts/run_research.py -> ResearchGraphRunner` | PARTIAL |

Required fix: change CLI to instantiate `FullReportOrchestrator` and submit the same `RunContext` path used by API/batch.

## 4. Legacy Residue Table

Repository-wide search terms from `audit.md` were executed over `backend scripts config tests README.md backend/README.md Dockerfile requirements.txt Makefile`.

| Search term / residue | Files found | Runtime reachable? | Keep/Delete/Fix | Reason |
|---|---|---:|---|---|
| Legacy five-role agent names and transfer artifacts | Former `config/harness/*` policy/docs | Rewritten to six-agent trace/manifest contracts | Fixed | Active harness config now matches six-agent architecture |
| `financial_analyst` | `backend/harness/gates.py`, `backend/harness/runner.py`, tests | Yes, as gate name/string | Fix | Gate is still named `financial_analyst_gate`; should be renamed to `financial_analysis_gate` to remove semantic residue |
| `news_editor` | `backend/database/migrations/032_news_research_schema.sql` | Migration history only | Keep | Historical schema/index name |
| `glob(` / latest artifacts | storage/debug scripts, `scripts/render_report.py`, `scripts/generate_report.py`, tests | Not in current production runner; manually reachable scripts remain | Fix/Isolate | Move dev-only report/render scripts under explicit legacy/dev namespace or remove |
| `generate_report.py` | standalone script and tests | Not ToolRegistry runtime | Fix/Isolate | Monolithic report pipeline still present as manual script |
| `legacy` | storage migration scripts, data warehouse legacy scripts | Operational/migration only | Keep with label | Acceptable if explicitly non-runtime |
| `OfflineEvaluator`, `RecomputePlanner`, `legacy_kwargs`, `legacy_aliases`, `generate_report_tool`, `LangGraph`, `langgraph`, `news_citation_gate` | No runtime references found | No | Pass | Removed from active runtime |

## 5. Agent Registry Verification

Command evidence:

```text
AGENTS 6 ['data_evidence', 'financial_analysis', 'forecast_valuation', 'research_manager', 'senior_critic', 'thesis_report']
RUNTYPES ['full_report']
```

Active agents:

| Agent | Role | Output schema | Tools |
|---|---|---|---|
| `research_manager` | `ResearchManagerAgent` | `ResearchManagerArtifact` | none |
| `data_evidence` | `DataEvidenceAgent` | `EvidencePack` | `auto_ingest`, `build_facts`, `build_index` |
| `financial_analysis` | `FinancialAnalysisAgent` | `FinancialAnalysis` | `read_snapshot`, `read_ratio_artifact` |
| `forecast_valuation` | `ForecastValuationAgent` | `ForecastValuationArtifact` | `run_valuation`, `read_valuation_artifact` |
| `thesis_report` | `ThesisReportAgent` | `ReportDraft` | none |
| `senior_critic` | `SeniorCriticAgent` | `CriticReview` | `evaluate_report_quality` |

Status: PASS for active registry. Gap: default model resolved to `claude-haiku-4-5-20251001`, not Sonnet 4.6. This may be intentional cost control, but the audit plan requested explicit support for Sonnet/current Anthropic model policy. The model policy should document why Haiku is default and when Sonnet is selected.

## 6. Tool Registry Verification

Observed tools:

| Tool | Owner | Permission | Output | Retry | Required refs | Cost |
|---|---|---|---|---|---:|---|
| `auto_ingest` | `data_evidence` | `read_write_artifact` | `ServiceNodeResult` | `no_retry` | false | metered |
| `build_facts` | `data_evidence` | `read_write_artifact` | `ServiceNodeResult` | `no_retry` | false | metered |
| `build_index` | `data_evidence` | `read_write_artifact` | `ServiceNodeResult` | `no_retry` | false | metered |
| `read_snapshot` | `financial_analysis` | `read_only` | `ServiceNodeResult` | `no_retry` | false | metered |
| `read_ratio_artifact` | `financial_analysis` | `read_only` | `ServiceNodeResult` | `no_retry` | false | metered |
| `run_valuation` | `forecast_valuation` | `read_write_artifact` | `ServiceNodeResult` | `no_retry` | false | metered |
| `read_valuation_artifact` | `forecast_valuation` | `read_only` | `ServiceNodeResult` | `no_retry` | false | metered |
| `evaluate_report_quality` | `senior_critic` | `read_only` | `ServiceNodeResult` | `no_retry` | false | metered |

Permission denial is tested in `tests/unit/test_tool_registry.py`.

Status: PARTIAL PASS. Governance exists and denies wrong owner/undeclared tools. Gap: `required_source_refs` is false for all tools; source whitelist enforcement is implemented indirectly in ingestion/source code, not exposed as explicit ToolRegistry policy.

## 7. Full-Report Run Trace Summary

Production command run:

```text
python scripts/run_research.py --ticker DHG --from-year 2021 --to-year 2025
```

Result:

```text
[run_research] harness run_id=run_dhg_20260609T174357_f2a4f8fe43
[run_research] graph pauses for deterministic gates and required HITL approvals
Failed to write run manifest ... <urlopen error [WinError 10061] No connection could be made because the target machine actively refused it>
```

Runtime store state:

| Field | Value |
|---|---|
| run_id | `run_dhg_20260609T174357_f2a4f8fe43` |
| status | `failed` |
| current_stage | `RESEARCH_MANAGER_PLAN` |
| blocking_reason | `RESEARCH_MANAGER_PLAN: Connection error.` |
| artifact keys | none |
| gate keys | none |
| trace length | 0 |
| saved artifacts | two `graph_state_snapshot` artifacts |

Conclusion: live full_report behavior is not verified beyond preflight/first agent call. No report-quality claims can be accepted from this run.

## 8. Fixed Stage Order

Observed `GRAPH_STAGES`:

```text
PREFLIGHT
RESEARCH_MANAGER_PLAN
DATA_AND_EVIDENCE
DATA_QUALITY_GATE
FINANCIAL_ANALYSIS
FINANCIAL_ANALYSIS_GATE
DRIVER_BASED_FORECAST
FORECAST_QUALITY_GATE
VALUATION_PROPOSAL
VALUATION_GATE
WAITING_ASSUMPTION_APPROVAL
VALUATION_EXECUTION
LOCK_RESEARCH_ARTIFACTS
RESEARCH_MANAGER_READINESS
THESIS_AND_REPORT
REPORT_ASSEMBLY
DETERMINISTIC_CONTENT_GATES
SENIOR_CRITIC_REVIEW
OPTIONAL_SINGLE_REPORT_REVISION
FINAL_EXPORT_GATE
CITATION_GATE
WAITING_FINAL_APPROVAL
RENDER_AND_PUBLISH
```

Status: PARTIAL PASS. The stage list is fixed and contains no old supervisor stages. Differences from `audit.md` target:

| Target stage | Observed |
|---|---|
| `OPTIONAL_DATA_FOLLOWUP_FOR_FINANCIAL` | Not a stage; implemented inside agent handling |
| `OPTIONAL_DATA_FOLLOWUP_FOR_VALUATION` | Not a stage; implemented inside agent handling |
| `CITATION_GATE` | Extra explicit stage after `FINAL_EXPORT_GATE` |

The differences may be acceptable if documented, but the current implementation is not an exact match to the specified order.

## 9. Approval Checkpoints

Observed code:

| Checkpoint | Status |
|---|---|
| `WAITING_ASSUMPTION_APPROVAL` pauses run | Implemented |
| `WAITING_FINAL_APPROVAL` pauses run | Implemented |
| rejected approval invalidates downstream sections | Partially implemented via `_invalidate_after_rejection` |
| approval records include artifact versions approved | Not proven |
| HTML/PDF cannot be created without final approval | Not proven; `RENDER_AND_PUBLISH` currently gates status but does not visibly call renderer |

Critical gap: `RENDER_AND_PUBLISH` does not appear to create `report.html` or `report.pdf`. Rendering still appears to be handled by `scripts/render_report.py`, a separate dev/manual entrypoint.

## 10. Artifact Inventory And Lineage

Required artifacts from `audit.md` were not produced by the live run. Only graph checkpoints were stored.

Code support:

| Artifact mechanism | Status |
|---|---|
| Agent artifact contracts | Present in `backend/harness/contracts.py` |
| Agent payload persistence | Present via `_write_agent_payload_artifact` |
| Evidence packet | Present via `_write_evidence_packet` |
| Manifest | Present via `_write_run_manifest`, but live run manifest upload failed |
| `final_report_model` | Present via `ReportAssembler`, not reached live |
| `trace.jsonl` | Not implemented as a persisted JSONL artifact; trace lives in state/checkpoints |
| `report.html` / `report.pdf` | Not produced by runner |

Status: FAIL for required artifact inventory in live behavior; PARTIAL PASS for contract scaffolding.

## 11. Forecast And Valuation Audit

Static gates exist:

| Requirement | Evidence | Status |
|---|---|---|
| Forecast by channel/product | `forecast_quality_gate` blocks missing decomposition | PASS at gate-test level |
| Working capital/capex/debt/cash/EPS required | `forecast_quality_gate` checks these fields | PASS at gate-test level |
| FCFF/FCFE target reconciliation | `valuation_reconciliation_gate` checks bridge, share count, weights, current price, recommendation | PASS at gate-test level |
| Net borrowing criticality | `valuation_reconciliation_gate` blocks missing `net_borrowing`; many debt tests exist | PASS at gate-test level |
| Recompute valuation from `forecast_model.json` and `approved_assumptions.json` | No successful run/artifacts available | NOT VERIFIED |

Status: PARTIAL PASS. The deterministic gates are materially stronger than before, but no live valuation reproducibility result exists.

## 12. Report Quality Benchmark

Report structure enforcement exists in:

- `backend/reporting/report_assembler.py`
- `backend/harness/gates.py::report_completeness_gate`
- `tests/unit/test_report_assembler.py`
- `tests/unit/test_production_gates.py`

However, no generated report was available for comparison against the FPTS-style DBD benchmark. Required depth, section quality, tables/charts, and Vietnamese analyst narrative were not verified.

Status: NOT VERIFIED.

## 13. Claim And Citation Audit

Static support:

| Requirement | Status |
|---|---|
| `ReportDraft` has typed `claims` | Present |
| `ReportClaim` requires `supporting_refs` and `source_artifact_refs` | Present |
| Citation gates exist | Present |
| Quantitative claim coverage from real report | Not verified |
| Claim ledger artifact from live run | Not produced |

Status: PARTIAL PASS for schema; FAIL/NOT VERIFIED for live claim/citation quality.

## 14. Observability Audit

| Requirement | Status |
|---|---|
| Root trace per run in Langfuse | Not verified |
| Child spans for every stage | Not verified |
| `trace.jsonl` persisted | Not implemented as standalone artifact |
| Business payload stored outside trace | Partially supported through artifact persistence, not verified live |

Status: NOT VERIFIED / PARTIAL.

## 15. Test Coverage Gap Table

| Requirement | Existing test? | Test name / evidence | Missing? | Add test |
|---|---:|---|---:|---|
| Six-agent registry only | Yes | `test_registry_contains_exactly_six_typed_agents` | No | No |
| Old agent names not runtime reachable | Partial | `test_tool_registry_*`, static audit | Yes | Add static test excluding stale `config/harness/*` |
| Research Manager called only twice | No | Runner code shows two calls | Yes | Add call-count workflow test with mocked adapter |
| One evidence follow-up only | Yes | `test_structured_evidence_followup_is_limited_to_one` | No | No |
| One critic revision only | Partial | code has `report_revision_count`; no explicit test | Yes | Add mocked workflow test |
| Non-whitelisted source rejected | Partial | ingestion code/gates; no direct harness test found | Yes | Add ToolRegistry/source policy test |
| Forecast requires channel decomposition | Yes | `test_forecast_quality_gate_blocks_missing_driver...` | No | No |
| Forecast requires product decomposition | Partial | gate checks product group; test focuses channel | Yes | Add explicit product decomposition failure test |
| FCFE fails without net borrowing | Yes | `test_production_gates.py`, debt tests | No | No |
| Valuation target price reconciles | Yes | `test_valuation_reconciliation_gate_*` | No | No |
| Report cannot render before final approval | Partial | `approval_path_gate`; no renderer integration | Yes | Add end-to-end render stage test |
| Report contains required sections | Yes | `test_report_completeness_gate_*`, `test_report_assembler.py` | No | No |
| Claim ledger covers quantitative claims | Partial | citation tests exist; no full ReportDraft ledger test | Yes | Add full report draft claim-ledger test |
| Critic low numeric integrity blocks publish | Yes | `test_senior_critic_gate_blocks_low_integrity_score_and_critical_finding` | No | No |
| ReportAssembler cannot invent missing content | Yes | `test_missing_required_section_fails...` | No | No |
| CLI/API/batch same runner | No | Static audit found CLI bypass | Yes | Add test asserting CLI uses `FullReportOrchestrator` |
| Artifact inventory matches required list | No | Live run failed | Yes | Add mocked successful-run artifact inventory test |
| Manifest lineage from PDF to facts/evidence | No | Not implemented/proven | Yes | Add lineage test after render integration |
| Langfuse spans exist | No | Not verified | Yes | Add adapter trace instrumentation test |

## 16. Verification Commands

Commands run:

```text
python -m pytest -q tests
python -m compileall -q backend scripts
python scripts/run_research.py --ticker DHG --from-year 2021 --to-year 2025
```

Test result:

```text
1124 passed, 1 warning
```

Live run result:

```text
status=failed
current_stage=RESEARCH_MANAGER_PLAN
blocking_reason=RESEARCH_MANAGER_PLAN: Connection error.
artifacts=[]
gates=[]
trace_len=0
```

## 17. Critical Blockers

1. A real `full_report` run did not complete beyond `RESEARCH_MANAGER_PLAN`; no report-quality or artifact-lineage acceptance criteria are proven.
2. CLI bypasses `FullReportOrchestrator`; API/batch and CLI are not the exact same call chain.
3. `RENDER_AND_PUBLISH` does not visibly create HTML/PDF artifacts.
4. Required artifact inventory is incomplete or unproven; `trace.jsonl`, `report.html`, `report.pdf`, `claim_ledger.json`, `approved_assumptions.json`, and `report_draft.md` are not proven from the runner.
5. Resolved: `config/harness/*` files now describe six-agent trace/manifest contracts.
6. Monolithic `scripts/generate_report.py` remains manually reachable, even if no longer registered as a production tool.
7. Supabase/storage manifest write failed during live run.
8. Langfuse trace and report benchmark quality were not verified.

## 18. Required Fixes

Priority order:

1. Make `scripts/run_research.py` use `FullReportOrchestrator` instead of instantiating `ResearchGraphRunner` directly.
2. Wire `RENDER_AND_PUBLISH` to deterministic renderer output and persist `report.html` and `report.pdf` only after final approval.
3. Add a mocked successful full-run test that proves required artifact inventory and manifest lineage.
4. Remove or quarantine stale `config/harness/agent_roles.md`, `evidence_packet_schema.json`, and unused export policy references, or rewrite them to match the new executable contracts.
5. Rename `financial_analyst_gate` to `financial_analysis_gate` and remove `financial_analyst_review` compatibility fallback from report assembly inputs.
6. Move `scripts/generate_report.py` and `scripts/render_report.py` into an explicit dev/legacy namespace or delete after replacement.
7. Persist `trace.jsonl` as a run artifact and verify Langfuse root/child spans.
8. Run a real successful `full_report` with working DB, Supabase/storage, and LLM credentials; capture artifact inventory and benchmark report quality.

## 19. P0-P5 Remediation Update (2026-06-10)

Final status remains **PARTIAL PASS**. P0-P4 production-path blockers were
materially remediated, but P5 acceptance is not met because no live run reached
`RENDER_AND_PUBLISH`.

### Remediation Status

| Priority | Result | Evidence |
|---|---|---|
| P0 Model diagnostics | PASS | Failures include provider, model, endpoint, client, timeout, retry count, exception cause chain, stage, agent, prompt size, and proxy configuration. |
| P1 Unified production call chain | PASS | CLI, API, batch, and approval CLI use `FullReportOrchestrator`; `ResearchGraphRunner` is internal execution machinery. |
| P2 Render/publish contract | PASS at test level | Approved `final_report_model` is rendered by `FinalReportPublisher`; strict HTML/PDF artifacts persist only after final approval. |
| P3 Legacy report isolation | PASS | Legacy report/render helpers are DEV-ONLY, reject production paths, and cannot create `report_type='full_report'`. |
| P4 Stale harness cleanup | PASS | Active harness config describes the six-agent path; stale DQ writer and tool contracts were removed. |
| P5 Live complete artifact set | FAIL / NOT VERIFIED | Live runs did not reach valuation, critic, final approval, or render/publish. |

### Runtime Defects Fixed

1. CLI exits non-zero when the orchestrator returns a failed state.
2. Failed stage labels no longer advance before stopping.
3. Anthropic diagnostics expose endpoint, proxy settings, and exception causes.
4. Anthropic client uses explicit timeout and bounded `retry_once`.
5. Run-scoped `run_log_json` artifacts use a unique version sequence.
6. Tool `SystemExit` becomes a checkpointable runtime failure.
7. `fact.production_facts` is no longer incorrectly filtered to
   `canonical_version='prod'`.
8. `build_facts` receives explicit `run_id` from the harness.
9. Legacy `research.data_quality_reports` persistence was removed.
10. Source registration upserts on deterministic `source_doc_id`.
11. Model adapter parses fenced/direct typed artifacts and supports larger output.

### Verification

```text
python -m pytest -q tests
1142 passed, 1 warning

python -m compileall -q backend scripts
PASS
```

### Live Run Evidence

Run `run_dhg_20260609T183453_1e746d94f1` completed:

```text
PREFLIGHT
RESEARCH_MANAGER_PLAN
DATA_AND_EVIDENCE
```

It persisted research-plan, facts-snapshot, evidence-pack, and graph-checkpoint
artifacts. Deterministic facts reported:

```text
periods_available = 2022FY, 2023FY, 2024FY, 2025FY
periods_missing = 2021FY
source_tier_coverage_status = fail
valuation_gate = fail
available financial facts = Tier-3 only
```

The initial generic connection failure was proven to be environment proxy
configuration:

```text
HTTPS_PROXY/HTTP_PROXY/ALL_PROXY = http://127.0.0.1:9
exception chain = APIConnectionError -> ConnectError -> ConnectionRefusedError
```

With proxy variables removed for the process, live runs reached the data path.
A later attempt recorded a transient
`APITimeoutError -> ReadTimeout -> TimeoutError`; bounded retry/timeout policy
was updated afterward.

### Artifact Inventory Result

Proven live: `research_plan`, `facts_snapshot.json`, `evidence_pack`, and
`graph_state_snapshot`.

Not produced or not verified live: `financial_analysis.json`,
`forecast_model.json`, `valuation_proposal.json`, `approved_assumptions.json`,
`valuation.json`, `readiness_review.json`, `report_draft.json`,
`report_draft.md`, `claim_ledger.json`, `quality_gate.json`,
`critic_review.json`, `chart_specs.json`, `table_specs.json`,
`final_report_model.json`, `trace.jsonl`, `report.html`, and `report.pdf`.

### Updated Acceptance Decision

The generic connection failure is now diagnosed rather than hidden, and the
production path is materially stronger. Acceptance remains **PARTIAL PASS**
because the live DHG dataset lacks 2021FY and Tier-0/1 validated facts, and no
real run has completed valuation, claim-ledger/critic gates, or final HTML/PDF
publication.

## 20. Acceptance Decision

Final decision: PARTIAL PASS.

Rationale:

- PASS: six active agents, single public `full_report` run type, fixed stage list, no LangGraph compiled graph, no legacy coordinator runtime path, governed ToolRegistry, deterministic report assembler, stronger forecast/valuation/critic gates, full tests pass.
- FAIL/NOT VERIFIED: live full report, artifact inventory, valuation reproducibility from produced artifacts, report quality benchmark, claim/citation coverage from produced report, Langfuse trace, final HTML/PDF rendering, and fully unified CLI/API/batch call chain.

The current implementation should not be described as “completed six-agent full-report research system.” It is a partially rebuilt architecture that still needs an end-to-end successful run and artifact/report-quality validation before production acceptance.
