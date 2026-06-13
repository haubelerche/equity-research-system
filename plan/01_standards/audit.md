Mục tiêu không phải chỉ xem “test pass”, mà phải xác minh hệ thống **thật sự đã chuyển sang six-agent full_report**, không còn cleanup hình thức, và đủ harness để sinh báo cáo chất lượng cao.

Điểm tôi thấy đáng nghi trong log của Codex: nó nói production path là **`FullReportOrchestrator -> ResearchGraphRunner`**. Trong plan trước, ta muốn bỏ compiled/legacy graph và dùng lifecycle-focused orchestrator. Nếu `ResearchGraphRunner` là tên mới nhưng ruột đã refactor thì được. Nếu vẫn là graph runner/legacy facade cũ thì chưa đạt.

````md
# AUDIT PLAN — Verify Six-Agent Full Report Rebuild

## 0. Objective

Audit whether the completed implementation truly matches the agreed PLAN.md:

- one production path for `full_report`;
- six real specialist agents;
- deterministic tools exposed through a governed registry;
- driver-based forecast harness;
- reproducible valuation;
- professional report contract;
- senior analyst critic rubric;
- artifact lineage;
- no hidden legacy pipeline;
- no fake/static evaluator;
- no report prose fallback.

Do not treat `pytest passed` as sufficient. Passing tests only proves the current tests match the current code. This audit must verify runtime behavior, contracts, artifacts, and generated report quality.

---

## 1. High-Risk Suspicion to Check First

The completion summary says production path is:

```text
FullReportOrchestrator -> ResearchGraphRunner
````

This is suspicious.

The target architecture requires a lifecycle-focused full-report orchestrator, not a legacy compiled graph runner or compatibility facade.

### Required audit question

Determine whether `ResearchGraphRunner` is:

1. a renamed/new lifecycle executor with no legacy graph behavior; or
2. the old graph runner still active under a new production path.

### Pass condition

`ResearchGraphRunner` may remain only if:

* it no longer depends on LangGraph;
* it does not load old 5-agent config;
* it does not use supervisor/handoff concepts;
* it does not support old artifact contracts;
* it executes the fixed v1 full_report stages;
* it writes the new artifact set;
* it does not contain compatibility branches for old pipelines.

### Fail condition

Fail the audit if `ResearchGraphRunner` still contains:

* supervisor routing;
* handoff artifacts;
* old agent names;
* legacy stage branches;
* old report generation path;
* dynamic graph behavior;
* compatibility kwargs;
* glob/latest artifact loading;
* fallback narrative generation.

---

## 2. Static Code Audit

## 2.1. Search for forbidden legacy residues

Run repository-wide searches, not only touched files.

Search terms:

```text
SupervisorAgent
supervisor
DataRetrievalAgent
data_retrieval
FinancialAnalystAgent
financial_analyst
ValuationAgent
ReportWriterCriticAgent
report_writer_critic
NewsEditorAgent
news_editor
news_agents
handoff
AGENT_HANDOFF_GATE
generate_report_tool
legacy
legacy_kwargs
legacy_aliases
compiled graph
LangGraph
langgraph
OfflineEvaluator
RecomputePlanner
news_citation_gate
glob(
latest artifact
latest_run
fallback prose
deterministic prose fallback
mock evaluator
static score
```

### Required output

Create a table:

| Search term | Files found | Runtime reachable? | Keep/Delete/Fix | Reason |
| ----------- | ----------- | ------------------ | --------------- | ------ |

### Pass condition

Any remaining occurrence must be clearly one of:

* migration history only;
* archived documentation explicitly marked non-runtime;
* test fixture intentionally checking removal;
* comment explaining removed behavior.

No runtime import path may reference legacy agents, old graph, fake evaluator, handoff, or monolithic report generation.

---

## 2.2. Validate active agent registry

Check:

```text
config/agents/agents.yml
config/agents/*.md
backend agent registry loader
tests around registry
```

### Expected agents only

```text
research_manager
data_evidence
financial_analysis
forecast_valuation
thesis_report
senior_critic
```

### Pass condition

* exactly six active agents;
* each has a prompt/config;
* no old prompt path is loaded;
* no news editor agent;
* no supervisor agent;
* no report writer critic hybrid;
* no data retrieval legacy agent;
* model policy explicitly supports Anthropic Claude Sonnet 4.6 or current configured Anthropic model;
* fallback model behavior is explicit and not silently OpenAI-only.

---

## 2.3. Validate tool governance

Inspect `ToolRegistry`.

### Required contract per tool

Each tool must declare:

```yaml
tool_name:
allowed_agent_roles:
input_schema:
output_schema:
side_effect_permission:
timeout_seconds:
retry_policy:
artifact_producer:
required_source_refs:
cost_policy:
```

### Required checks

* agents cannot call tools outside allowed roles;
* tools return typed outputs or artifact refs;
* source tools enforce whitelist;
* valuation/forecast tools are deterministic;
* renderer cannot invent missing content;
* report assembler reads artifacts, not glob/latest files.

### Pass condition

A unit or integration test must prove permission denial works.

Example required test:

```text
Thesis Report Agent cannot call valuation_execution_tool.
Data Evidence Agent cannot call render_report_tool.
Forecast Valuation Agent cannot call non-whitelisted source tool.
```

---

## 3. Workflow Runtime Audit

## 3.1. Verify actual production path

Run the same command used by CLI/API/batch to create a `full_report`.

Trace the call chain.

### Required output

Document the actual production call chain:

```text
CLI/API entry
-> orchestrator
-> stage executor
-> agents
-> tools
-> artifacts
-> gates
-> approvals
-> renderer
```

### Pass condition

CLI, API, and batch must all call the same production runner.

Fail if:

* CLI uses a different codepath from API;
* tests call a simplified path not used in production;
* report rendering can be invoked from old scripts;
* artifacts can be discovered via latest/glob fallback.

---

## 3.2. Verify fixed stage order

The full_report run must follow exactly:

```text
PREFLIGHT
RESEARCH_MANAGER_PLAN
DATA_AND_EVIDENCE
FINANCIAL_ANALYSIS
OPTIONAL_DATA_FOLLOWUP_FOR_FINANCIAL
DRIVER_BASED_FORECAST
VALUATION_PROPOSAL
WAITING_ASSUMPTION_APPROVAL
VALUATION_EXECUTION
OPTIONAL_DATA_FOLLOWUP_FOR_VALUATION
LOCK_RESEARCH_ARTIFACTS
RESEARCH_MANAGER_READINESS
THESIS_AND_REPORT
REPORT_ASSEMBLY
DETERMINISTIC_CONTENT_GATES
SENIOR_CRITIC_REVIEW
OPTIONAL_SINGLE_REPORT_REVISION
FINAL_EXPORT_GATE
WAITING_FINAL_APPROVAL
RENDER_AND_PUBLISH
```

### Pass condition

* stage order appears in trace;
* no old stage appears;
* no dynamic graph rewrite;
* no unlimited loop;
* no catalyst refresh branch in v1;
* no flash memo branch in v1.

---

## 3.3. Verify approval checkpoints

The run must pause at:

```text
WAITING_ASSUMPTION_APPROVAL
WAITING_FINAL_APPROVAL
```

### Pass condition

* valuation execution cannot lock final valuation without assumption approval;
* HTML/PDF cannot be created without final approval;
* approval records include artifact versions approved;
* modifying assumptions invalidates downstream valuation/report artifacts.

---

## 4. Artifact Contract Audit

## 4.1. Required artifacts

A successful run must create:

```text
manifest.json
research_plan.json
market_snapshot.json
facts_snapshot.json
evidence_pack.json
financial_analysis.json
forecast_model.json
valuation_proposal.json
approved_assumptions.json
valuation.json
readiness_review.json
report_draft.json
report_draft.md
claim_ledger.json
quality_gate.json
critic_review.json
chart_specs.json
table_specs.json
final_report_model.json
trace.jsonl
report.html
report.pdf
```

`report.html` and `report.pdf` must exist only after final approval.

### Pass condition

Each artifact must contain:

```yaml
schema_version:
run_id:
ticker:
producer:
input_refs:
version:
checksum:
created_at:
updated_at:
```

Fail if artifact content is only free-form text without typed structure.

---

## 4.2. Manifest lineage audit

`manifest.json` must map:

* artifact name;
* version;
* checksum;
* producer;
* dependencies;
* status;
* created_at.

### Pass condition

Given `report.pdf`, auditor can trace back to:

```text
report.pdf
-> final_report_model.json
-> report_draft.json
-> valuation.json
-> forecast_model.json
-> financial_analysis.json
-> facts_snapshot.json
-> evidence_pack.json
```

---

## 5. Agent Behavior Audit

## 5.1. Research Manager Agent

Verify:

* called only at plan and readiness;
* creates meaningful research questions;
* defines required sections/tables/charts;
* does not write report;
* does not calculate;
* does not modify specialist artifacts.

### Failure injection

Remove key evidence before readiness.

Expected:

```text
readiness_review.decision = human_review_required
```

or unresolved critical item is clearly listed.

---

## 5.2. Data & Evidence Agent

Verify:

* uses only whitelist sources;
* builds `business_evidence`;
* builds `pharma_catalyst_evidence`;
* detects conflicts;
* records missing evidence.

### Failure injection

Give it a non-whitelisted URL/source.

Expected:

```text
source rejected
evidence_pack.source_coverage marks item missing/invalid
trace records rejection reason
```

---

## 5.3. Financial Analysis Agent

Verify output contains:

* income statement analysis;
* balance sheet analysis;
* cash flow analysis;
* ratio diagnostics;
* segment/channel analysis;
* business interpretation.

### Quality requirement

Every major interpretation must follow:

```text
number -> business reason -> implication for forecast or valuation
```

Fail if it only lists numbers.

---

## 5.4. Forecast & Valuation Agent

Verify `forecast_model.json` includes:

* revenue by channel;
* revenue by product group;
* gross margin forecast;
* opex forecast;
* working capital forecast;
* capex/depreciation;
* debt/cash/interest;
* share count;
* EPS forecast;
* forecast quality checks.

Verify `valuation.json` includes:

* FCFF;
* FCFE;
* method weights;
* WACC components;
* terminal growth;
* shares outstanding;
* cash/debt treatment;
* target price bridge;
* sensitivity;
* sanity checks.

### Failure injection

Delete or null `net_borrowing`.

Expected:

* FCFE valuation fails or is marked incomplete;
* no silent default;
* HITL required if critical.

---

## 5.5. Thesis & Report Agent

Verify it writes all required sections:

```text
cover investment summary
trading snapshot
company overview
business model
recent financial performance
channel/product analysis
industry/catalyst analysis
driver-based forecast
valuation and recommendation
risks and monitoring factors
forecast financial summary
appendix
```

### Quality requirement

Each major section must contain:

```text
key message
supporting numbers
business explanation
implication
risk/caveat
```

Fail if section is generic or merely summarizes numbers.

---

## 5.6. Senior Critic Agent

Verify `critic_review.json` contains scorecard:

```text
thesis_strength
driver_logic
forecast_consistency
valuation_coherence
evidence_depth
sector_specificity
risk_balance
table_chart_completeness
narrative_quality
numeric_integrity
citation_integrity
```

### Pass condition

* critic can request one revision;
* critical unresolved issue after revision goes to HITL;
* critic does not self-edit facts/valuation;
* low numeric/citation integrity blocks publish.

---

## 6. Financial Harness Audit

## 6.1. Driver-based forecast

Check that forecast is not generic CAGR.

For pharma reports, forecast must include:

```text
ETC
OTC
oncology
antibiotics
dialysis solution
API cost trend
EU-GMP timeline
tender group impact
capacity expansion
working capital
capex
debt/cash
```

### Pass condition

Forecast assumptions must be linked to evidence refs.

Fail if forecast only says:

```text
revenue grows at X% CAGR
```

without channel/product decomposition.

---

## 6.2. Valuation reproducibility

Recompute valuation from `forecast_model.json` and `approved_assumptions.json`.

### Pass condition

Recomputed target price matches `valuation.json` within tolerance.

Required checks:

```text
FCFF value per share
FCFE value per share
weighted target price
rounded target price
upside/downside
EV to equity bridge
cash/debt treatment
shares outstanding
```

---

## 6.3. Financial statement consistency

Check:

* income statement forecast;
* balance sheet forecast;
* cash flow forecast;
* working capital days;
* capex/depreciation;
* debt schedule;
* EPS.

### Pass condition

* balance sheet balances;
* cash flow reconciles;
* EPS uses correct share count;
* working capital assumptions are explicit;
* debt and net borrowing are not fabricated.

---

## 7. Report Quality Audit Against Reference PDF

Use the FPTS-style DBD report as the reference quality benchmark.

The generated report does not need to copy the reference, but must match its analytical depth.

## 7.1. Required structure comparison

Check generated report against this structure:

```text
Cover / investment summary
Trading snapshot
Company overview
Recent performance update
Channel analysis
Product-line analysis
Industry/catalyst analysis
Forecast section
Valuation section
Recommendation history if available
Forecast financial summary
Appendix
Disclaimer
```

## 7.2. Required analytical depth

Report must contain:

* clear investment thesis headline;
* 3-5 key thesis bullets;
* company-specific competitive position;
* channel-level analysis;
* product group analysis;
* margin/cost driver analysis;
* catalyst timeline;
* driver-based forecast;
* valuation bridge;
* balanced risk factors;
* monitoring factors.

## 7.3. Required tables/charts

Minimum required:

```text
Trading snapshot table
Company overview table
Recent financial results table
Business plan completion table
Revenue by channel chart
Product group / market share chart
Gross margin / net margin trend chart
Forecast revenue chart
Forecast margin chart
Valuation summary table
DCF assumptions table
FCFF/FCFE bridge table
Forecast financial statement summary
Risk and monitoring table
Appendix evidence table
```

### Pass condition

Missing chart/table is acceptable only if:

```text
insufficient_evidence
```

is explicitly recorded in both report and quality gate.

---

## 8. Claim and Citation Audit

## 8.1. Claim ledger

Every factual or quantitative claim must appear in `claim_ledger.json`.

Each claim must map to:

```yaml
claim_id:
section:
text:
claim_type:
quantitative:
supporting_refs:
source_artifact_refs:
validation_status:
```

## 8.2. Citation validation

Check:

* source supports claim;
* source ticker matches;
* source period matches;
* source unit matches;
* source is whitelisted;
* stale source is flagged.

### Pass condition

100% quantitative claims have valid citations or are explicitly marked `insufficient_evidence`.

---

## 9. Observability Audit

## 9.1. Langfuse trace

Verify one root trace per run.

Required child spans:

```text
preflight
research_manager_plan
data_and_evidence_agent
tool_calls
financial_analysis_agent
forecast_valuation_agent
assumption_approval
valuation_execution
readiness_review
thesis_report_agent
report_assembly
gates
senior_critic_agent
revision
final_approval
render
```

## 9.2. trace.jsonl

Must contain metadata events only.

Business payload must be stored in artifacts, not only trace.

---

## 10. Test Suite Gap Audit

1124 tests passing is not enough.

Create a test coverage table:

| Requirement | Existing test? | Test name | Missing? | Add test |
| ----------- | -------------- | --------- | -------- | -------- |

Minimum required missing-test checks:

```text
six-agent registry only
old agent names not runtime reachable
Research Manager called only twice
one evidence follow-up only
one critic revision only
non-whitelisted source rejected
forecast requires channel decomposition
forecast requires product decomposition
FCFE fails without net borrowing assumption
valuation target price reconciles
report cannot render before final approval
report contains required sections
claim ledger covers quantitative claims
critic low numeric integrity blocks publish
ReportAssembler cannot invent missing content
CLI/API/batch same runner
```

---

## 11. Final Audit Deliverable

Codex/Claude must produce:

```text
audits/SIX_AGENT_FULL_REPORT_REBUILD_AUDIT.md
```

The report must contain:

1. Executive conclusion: PASS / PARTIAL PASS / FAIL.
2. Actual runtime architecture.
3. Production call chain.
4. Legacy residue table.
5. Agent registry verification.
6. Tool registry verification.
7. Full-report run trace summary.
8. Artifact inventory and lineage.
9. Forecast/valuation reproducibility results.
10. Report quality benchmark against reference PDF.
11. Claim/citation audit.
12. Test gap table.
13. Critical blockers.
14. Required fixes.
15. Re-run commands and evidence.

---

## 12. Acceptance Decision

### PASS only if

* no legacy production path remains;
* exactly six agents are active;
* full_report is the only v1 run type;
* fixed stage order is enforced;
* required artifacts are produced;
* valuation is reproducible;
* forecast is driver-based;
* report matches professional structure;
* quantitative claims are cited;
* critic rubric works;
* final PDF renders only after approval;
* CLI/API/batch use the same runner.

### PARTIAL PASS if

* architecture cleanup is mostly done;
* tests pass;
* but report quality harness, forecast harness, critic rubric, or artifact lineage is incomplete.

### FAIL if

* old graph/supervisor/handoff/report monolith remains runtime reachable;
* agents are only prompt wrappers without tool governance;
* valuation cannot be reproduced;
* report can render from incomplete artifacts;
* forecast is generic;
* report does not approach senior analyst quality.

```

Kết luận sơ bộ từ log Codex: **chưa nên tin là hoàn thành**, vì họ chủ yếu báo cleanup + tests pass. Cần bắt họ chứng minh bằng **một full_report run thật**, artifact inventory, valuation reproducibility, claim ledger, critic scorecard và benchmark report quality. Nếu không có những thứ đó thì mới chỉ là “code cleanup pass”, chưa phải “research system pass”.
```
