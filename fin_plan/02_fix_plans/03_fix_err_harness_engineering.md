# ERR Harness Engineering Audit Plan

> **Project:** Vietnam Pharma Equity Research Multi-Agent / ERR cổ phiếu dược Việt Nam  
> **Primary MVP ticker:** DHG  
> **Audit purpose:** Kiểm định lại toàn bộ dự án theo tư duy **Harness Engineering**: không chỉ kiểm tra prompt/model, mà kiểm tra toàn bộ môi trường vận hành quanh agent gồm tools, state, provenance, formula execution, evaluation gates, context handoff và export control.

---

## Table of Contents

1. [Audit Philosophy](#1-audit-philosophy)
2. [Core Problem Statement](#2-core-problem-statement)
3. [Non-Negotiable Project Invariants](#3-non-negotiable-project-invariants)
4. [Audit Scope](#4-audit-scope)
5. [Expected Repository Areas](#5-expected-repository-areas)
6. [Severity Taxonomy](#6-severity-taxonomy)
7. [Phase 0 — Read-Only Baseline Audit](#7-phase-0--read-only-baseline-audit)
8. [Phase 1 — Data Provenance Audit](#8-phase-1--data-provenance-audit)
9. [Phase 2 — Source Discovery and Ingestion Audit](#9-phase-2--source-discovery-and-ingestion-audit)
10. [Phase 3 — PDF/OCR Extraction Audit](#10-phase-3--pdfocr-extraction-audit)
11. [Phase 4 — Reconciliation Audit](#11-phase-4--reconciliation-audit)
12. [Phase 5 — Formula and Financial Logic Audit](#12-phase-5--formula-and-financial-logic-audit)
13. [Phase 6 — Forecast and Valuation Audit](#13-phase-6--forecast-and-valuation-audit)
14. [Phase 7 — Narrative and Citation Audit](#14-phase-7--narrative-and-citation-audit)
15. [Phase 8 — Evaluation Gate Audit](#15-phase-8--evaluation-gate-audit)
16. [Phase 9 — Agent Workflow and State Management Audit](#16-phase-9--agent-workflow-and-state-management-audit)
17. [Phase 10 — Harness Engineering Remediation Plan](#17-phase-10--harness-engineering-remediation-plan)
18. [Required Output Files](#18-required-output-files)
19. [Definition of Done](#19-definition-of-done)
20. [Claude Code Execution Prompt](#20-claude-code-execution-prompt)

---

## 1. Audit Philosophy

This audit treats the model as an unreliable reasoning component that must be constrained by a deterministic, inspectable harness.

The project must not rely on the agent's verbal confidence. Every material output must be grounded in:

- typed source metadata;
- verifiable financial facts;
- deterministic formula traces;
- reconciliation against trusted sources;
- explicit citation mapping;
- hard export gates;
- reproducible run state.

The guiding rule is:

> If an agent can make a mistake once, the harness must be modified so that the same mistake is detected or blocked automatically next time.

---

## 2. Core Problem Statement

The current project risk is not simply that the model may hallucinate. The deeper risk is that the system may allow hallucinated, weakly sourced, incorrectly calculated, or poorly interpreted content to pass as a professional equity research report.

The audit must answer these questions:

1. Can the system prove where every material number came from?
2. Can the system prove whether a number was extracted from official documents, CafeF, vnstock, or another provider?
3. Can the system detect when sources disagree?
4. Can the system block final report export when facts are unverified?
5. Can the system prove every formula output from deterministic code, not free-form LLM arithmetic?
6. Can the system prevent reports with missing debt forecast, N/A valuation fields, unsupported claims, or generic citations from passing?
7. Can another agent session resume the project without losing the current state, known failures, and acceptance criteria?

---

## 3. Non-Negotiable Project Invariants

These invariants must be treated as hard constraints. Any violation is a critical issue.

### 3.1 Periodicity

- The project must use **FY data only**.
- Required coverage is **FY2021–FY2025 inclusive** where data is available.
- Quarterly data must not be mixed into the final historical financial fact table.
- If only quarterly data exists, four quarters must be explicitly aggregated into one FY period and marked as aggregated.

### 3.2 Source Trust Hierarchy

Recommended source tiers:

| Tier | Source Type | Trust Level | Expected Usage |
|---|---|---:|---|
| Tier 1 | Official audited financial statements, annual reports, exchange disclosures | Highest | Primary source for material financial facts |
| Tier 2 | CafeF / reputable financial portals with structured statements | Medium | Secondary verification and fallback |
| Tier 3 | vnstock / convenience APIs / market data libraries | Lower | Convenience source only; not sufficient alone for material final claims |

Hard rule:

> Material quantitative claims must not rely only on Tier-3 sources in the final report unless explicitly marked as unverified and excluded from valuation-critical conclusions.

### 3.3 Formula Execution

- LLMs must not perform final financial calculations in prose.
- FCFF, FCFE, DCF, WACC, terminal value, growth rates, margins, valuation multiples and sensitivity matrices must be produced by deterministic Python functions.
- Every calculated output must include a formula ID, inputs, units, periods and trace.

### 3.4 Report Export

The final report must not be exported if any of the following conditions exist:

- material metric has no source trace;
- material metric is sourced only from Tier 3;
- official document and secondary source discrepancy is unresolved;
- FCFF/FCFE/DCF input has N/A;
- debt forecast is missing or N/A where valuation requires it;
- citation map does not connect claim → metric → source → formula trace;
- evaluation result is purely LLM-asserted without deterministic gate evidence.

---

## 4. Audit Scope

Audit these dimensions:

1. **Data architecture** — schema, facts, source versions, lineage, constraints.
2. **Source acquisition** — automatic discovery, download, hashing, metadata, provider fallback.
3. **Document processing** — PDF classification, text extraction, OCR, table parsing.
4. **Financial fact normalization** — canonical metric IDs, units, periods, statement type.
5. **Reconciliation** — official vs CafeF vs vnstock discrepancies.
6. **Financial computation** — ratios, forecasts, FCFF, FCFE, DCF, multiples, sensitivity.
7. **Report generation** — evidence-grounded narrative, citation quality, chart selection.
8. **Evaluation** — deterministic gates, adversarial audit, false-pass prevention.
9. **Agent workflow** — task registry, progress state, known failures, session handoff.
10. **Harness design** — tool boundaries, permissioning, context management, export control.

---

## 5. Expected Repository Areas

Inspect these files/directories if present. If missing, record as an architectural gap.

```text
backend/
  analytics/
  citations/
  documents/
  eval/
  valuation/
  report/
config/
  financial_metric_dictionary.yaml
  formula_registry.yaml
scripts/
  auto_ingest_official_documents.py
  ingest_ticker.py
  run_research.py
  generate_report.py
  check_ocr_runtime.py
backend/database/
  migrations/
tests/
  unit/
  integration/
  fixtures/
reports/
outputs/
harness/
.claude/
```

---

## 6. Severity Taxonomy

Use the following severity levels.

| Severity | Definition | Example |
|---|---|---|
| Critical | Can produce a false or unverifiable final report while still passing | Report exports with Tier-3-only revenue facts |
| High | Can materially distort valuation or investment thesis | FCFE formula uses wrong sign for debt/capex/NWC |
| Medium | Reduces trust, auditability, or maintainability | Citation says only “vnstock” without endpoint/run/source ID |
| Low | Cosmetic or minor developer-experience issue | Inconsistent naming in logs |

Every issue must include:

```text
issue_id
severity
component
observed_behavior
expected_behavior
evidence
risk
recommended_fix
acceptance_test
```

---

## 7. Phase 0 — Read-Only Baseline Audit

### Objective

Create a truthful baseline of the current project without modifying code.

### Actions

1. Inspect repository structure.
2. Identify current pipeline entry points.
3. Identify report generation path.
4. Identify current source providers.
5. Identify current database schema and migrations.
6. Identify existing tests and quality gates.
7. Identify generated reports and latest run artifacts.
8. Identify agent workflow files, if any.

### Required Checks

- Is there a single canonical pipeline command?
- Is `scripts/run_research.py` the production entry point or only a wrapper?
- Does `auto_ingest_official_documents.py` run automatically before valuation?
- Does the report generator consume verified facts or raw/unverified DB facts?
- Are migrations versioned and reproducible?
- Does the pipeline write a run manifest?

### Output

Create:

```text
audits/00_baseline_audit.md
```

Minimum content:

```markdown
# Baseline Audit

## Entry Points
## Data Flow
## Report Flow
## Database Schema
## Existing Gates
## Existing Tests
## Current Artifacts
## Immediate Risks
```

---

## 8. Phase 1 — Data Provenance Audit

### Objective

Verify whether every financial fact can be traced to a concrete source.

### Actions

Inspect tables/models related to:

- `financial_facts`
- `source_versions`
- `official_documents`
- `fact_reconciliation`
- `price_history`
- `catalyst_events`
- any lineage/audit tables

### Required Checks

For each material fact, verify whether the system stores:

```text
metric_id
company_ticker
period
period_type
statement_type
value
unit
source_tier
source_name
source_version_id
document_id
page/table/row reference where applicable
retrieved_at
parser_version
ingestion_batch_id
confidence
verification_status
```

### Hard Fail Conditions

- `financial_facts.source_version_id` has no FK or equivalent integrity constraint.
- Fact has no source version.
- Fact has source name but no retrieval metadata.
- Material fact has no verification status.
- FY and quarter data are mixed without explicit period type enforcement.
- Report uses facts without checking source tier.

### Output

Create:

```text
audits/01_data_provenance_audit.md
```

Include a table:

| Requirement | Present | Evidence | Risk | Required Fix |
|---|---:|---|---|---|

---

## 9. Phase 2 — Source Discovery and Ingestion Audit

### Objective

Verify whether the project can automatically find, download, register and ingest public company documents instead of requiring manual PDF placement.

### Actions

Inspect official document ingestion logic:

- source discovery search logic;
- download logic;
- document hashing;
- duplicate detection;
- provider fallback;
- CafeF fallback;
- vnstock fallback;
- run manifest;
- failure statuses.

### Required Checks

The system should support:

```text
source_discovery(ticker, year)
download_document(url)
register_document(document_id, hash, source_url, source_tier)
classify_pdf_type(document)
extract_facts(document)
reconcile_facts(primary, secondary, tertiary)
```

### Hard Fail Conditions

- Pipeline requires a human to manually search and place official PDFs for normal production runs.
- Downloaded documents are not hashed.
- Same document can be ingested multiple times without deduplication.
- Provider fallback is silent and not recorded.
- CafeF or vnstock data can overwrite official data without reconciliation.

### Output

Create:

```text
audits/02_source_ingestion_audit.md
```

---

## 10. Phase 3 — PDF/OCR Extraction Audit

### Objective

Verify whether official PDFs can be processed safely and whether OCR/scanned PDF handling is robust.

### Actions

Inspect:

- PDF type detection;
- pdfplumber extraction;
- OCR pipeline;
- Vietnamese text normalization;
- financial metric mapping;
- table parsing;
- confidence scoring;
- parser fallback;
- test fixtures.

### Required Checks

For each extracted row, the output should include:

```text
document_id
page_number
table_id
row_label_raw
row_label_normalized
metric_id
period
value
unit
extraction_method
parser_version
confidence
bbox_or_text_span
```

### Hard Fail Conditions

- OCR output is ingested without confidence flag.
- OCR output can overwrite text-based extraction without review.
- Vietnamese metric mapping uses broad regex that can match wrong line items.
- Negative values, parentheses, commas, dots, and unit scaling are not tested.
- Extraction result has no page/table trace.

### Required Tests

Add or verify tests for:

```text
text-based PDF extraction
scanned PDF detection
OCR dependency missing path
Vietnamese label normalization
metric_id mapping
unit scaling
negative values
ambiguous rows
false-positive regex match
```

### Output

Create:

```text
audits/03_pdf_ocr_extraction_audit.md
```

---

## 11. Phase 4 — Reconciliation Audit

### Objective

Verify whether the system compares financial facts across sources and detects discrepancies.

### Actions

Inspect reconciliation logic between:

- official PDF facts;
- CafeF facts;
- vnstock facts;
- manually verified golden facts, if any.

### Required Checks

For each canonical fact:

```text
metric_id
period
official_value
secondary_value
tertiary_value
absolute_difference
relative_difference
tolerance
status
selected_value
selection_reason
```

### Status Values

Recommended statuses:

```text
verified
minor_discrepancy
major_discrepancy
missing_primary_source
missing_secondary_source
tier3_only
needs_human_review
```

### Hard Fail Conditions

- Report uses facts without reconciliation status.
- Discrepancy exists but selected value is not justified.
- Tier-3-only facts are treated as verified.
- Reconciliation is performed after report writing instead of before report writing.
- Final export is allowed despite `major_discrepancy` in material facts.

### Output

Create:

```text
audits/04_reconciliation_audit.md
```

---

## 12. Phase 5 — Formula and Financial Logic Audit

### Objective

Verify that all financial calculations are deterministic, traceable and aligned with the project formula registry.

### Actions

Inspect modules such as:

```text
backend/analytics/ratios.py
backend/valuation/dcf.py
backend/valuation/fcff.py
backend/valuation/fcfe.py
backend/valuation/forecasting.py
backend/valuation/debt_schedule.py
backend/valuation/dividend_schedule.py
backend/valuation/multiples.py
```

### Required Formula Trace

Every formula output should include:

```text
formula_id
formula_version
input_fact_ids
input_values
units
periods
calculation_steps
output_value
validation_warnings
```

### Required Formula Areas

Audit at least:

```text
revenue_growth_yoy
gross_margin
ebit_margin
net_margin
roe
roa
working_capital
capex
fcff
fcfe
wacc
terminal_value
dcf_enterprise_value
equity_value
shares_outstanding
fair_value_per_share
sensitivity_matrix
```

### Hard Fail Conditions

- Agent computes final values in natural language.
- Formula IDs do not match the canonical formula registry.
- Units are mixed, e.g. VND vs billion VND.
- Periods are misaligned, e.g. FY2024 revenue with FY2025 working capital.
- FCFF/FCFE signs are wrong for capex, debt, or net working capital.
- Terminal value dominates valuation without warning.
- Sensitivity analysis uses inconsistent base case assumptions.

### Required Tests

Add or verify golden tests for:

```text
FCFF formula
FCFE formula
DCF bridge
WACC
terminal value
sensitivity matrix
unit scaling
period alignment
N/A input handling
```

### Output

Create:

```text
audits/05_formula_logic_audit.md
```

---

## 13. Phase 6 — Forecast and Valuation Audit

### Objective

Verify whether forecasts are economically justified and not arbitrary extrapolations.

### Actions

Inspect forecast logic for:

- revenue drivers;
- gross margin;
- SG&A;
- EBITDA/EBIT;
- tax;
- capex;
- depreciation and amortization;
- working capital;
- debt schedule;
- dividend schedule;
- FCFF/FCFE bridge.

### Required Driver-Based Forecast Contract

Each forecast assumption should include:

```text
assumption_id
metric_id
forecast_period
base_historical_periods
driver_name
driver_value
method
rationale
source_or_evidence
sensitivity_range
confidence
```

### Hard Fail Conditions

- Debt forecast is N/A while FCFE or equity value depends on debt.
- Working capital forecast is missing for FCFF.
- Forecast period starts without historical base.
- Growth assumptions have no rationale.
- Forecast uses stale or unverified historical facts.
- Valuation uses forecast assumptions not included in the evidence packet.

### Output

Create:

```text
audits/06_forecast_valuation_audit.md
```

---

## 14. Phase 7 — Narrative and Citation Audit

### Objective

Verify whether the report tells a defensible financial story grounded in evidence rather than generic commentary.

### Actions

Inspect latest generated reports and report templates.

For each major section, identify:

```text
investment thesis
business overview
industry context
historical financial analysis
ratio analysis
forecast assumptions
valuation result
risk factors
catalysts
recommendation
```

### Claim-Level Citation Requirements

Every material claim should map to:

```text
claim_id
claim_text
claim_type
supporting_metric_ids
supporting_source_ids
formula_trace_ids
citation_display_text
verification_status
```

### Claim Types

Use:

```text
quantitative_fact
calculated_metric
forecast_assumption
valuation_result
qualitative_event
risk_statement
investment_judgment
```

### Hard Fail Conditions

- Claim says revenue/profit/margin changed but does not cite source facts.
- Claim says a movement is due to an event but cites no article/disclosure/evidence.
- Citation only says “vnstock” or “database” without source details.
- Narrative contradicts table values.
- Investment recommendation is not connected to valuation output and risk assessment.
- Report contains generic filler instead of explaining the story behind the numbers.

### Output

Create:

```text
audits/07_narrative_citation_audit.md
```

---

## 15. Phase 8 — Evaluation Gate Audit

### Objective

Verify whether evaluation can prevent false positives, not merely produce a reassuring “passed” result.

### Actions

Inspect:

```text
approval_gate.py
latest_quality_gate.json
latest_quality_gate.md
backend/eval/
tests/unit/test_*gate*.py
```

### Required Gate Types

The project should have deterministic gates for:

```text
data_provenance_gate
source_reconciliation_gate
formula_consistency_gate
forecast_completeness_gate
citation_coverage_gate
narrative_grounding_gate
export_gate
```

### Required Gate Output

Each gate should return:

```json
{
  "gate_name": "citation_coverage_gate",
  "status": "fail",
  "severity": "critical",
  "issues": [
    {
      "issue_id": "CIT-001",
      "claim_id": "...",
      "message": "Material quantitative claim has no source trace",
      "blocking": true
    }
  ]
}
```

### Hard Fail Conditions

- LLM evaluator can mark final report as passed without deterministic checks.
- Evaluation passes when citations are generic.
- Evaluation passes with missing valuation-critical data.
- Evaluation passes with unresolved source discrepancies.
- Evaluation passes with no golden test fixtures.
- Evaluation does not produce machine-readable issue codes.

### False-Pass Tests

Create adversarial tests where report must fail:

```text
report with fake vnstock-only revenue
report with missing debt forecast
report with FCFF formula sign error
report with citation omitted for valuation driver
report with official-vnstock discrepancy
report with narrative contradiction
```

### Output

Create:

```text
audits/08_evaluation_gate_audit.md
```

---

## 16. Phase 9 — Agent Workflow and State Management Audit

### Objective

Verify whether the project can survive long-running multi-session agent work without losing task state or declaring success prematurely.

### Actions

Inspect whether the project has:

```text
task registry
progress file
known failures file
run state schema
agent role definitions
tool contracts
acceptance criteria per task
session handoff summary
```

### Recommended Harness State Files

If missing, propose adding:

```text
config/harness/run_state_schema.json
config/harness/task_registry.json
config/harness/known_failures.json
config/harness/agent_roles.md
config/harness/tool_contracts.md
config/harness/export_gate_policy.yml
```

### Hard Fail Conditions

- Agent progress exists only in chat history.
- No durable task registry.
- No machine-readable status per task.
- No blocked_by dependencies.
- No known-failures registry.
- Agent can modify gates or thresholds without test updates.
- Agent can claim success without running required checks.

### Output

Create:

```text
audits/09_agent_workflow_state_audit.md
```

---

## 17. Phase 10 — Harness Engineering Remediation Plan

### Objective

Convert audit findings into an implementable remediation plan.

### Required Remediation Structure

Create:

```text
audits/10_harness_remediation_plan.md
```

Use this structure:

```markdown
# Harness Remediation Plan

## Critical Fixes
## High Priority Fixes
## Medium Priority Fixes
## Low Priority Fixes
## Proposed Implementation Order
## Required Schema Changes
## Required Code Changes
## Required Tests
## Required Golden Fixtures
## Risk After Remediation
```

### Prioritization Rule

Fix in this order:

1. Export gate blocking false-pass reports.
2. Evidence packet generation.
3. Source provenance and reconciliation.
4. Formula trace enforcement.
5. Forecast completeness.
6. Citation and narrative grounding.
7. Agent task registry and session handoff.
8. Internal benchmark scenarios.

---

## 18. Required Output Files

The audit must produce the following files:

```text
audits/00_baseline_audit.md
audits/01_data_provenance_audit.md
audits/02_source_ingestion_audit.md
audits/03_pdf_ocr_extraction_audit.md
audits/04_reconciliation_audit.md
audits/05_formula_logic_audit.md
audits/06_forecast_valuation_audit.md
audits/07_narrative_citation_audit.md
audits/08_evaluation_gate_audit.md
audits/09_agent_workflow_state_audit.md
audits/10_harness_remediation_plan.md
```

Optional machine-readable output:

```text
audits/audit_findings.json
```

Recommended schema:

```json
{
  "project": "ERR Vietnam Pharma Equity Research",
  "audit_date": "YYYY-MM-DD",
  "findings": [
    {
      "issue_id": "ERR-AUDIT-001",
      "severity": "critical",
      "component": "export_gate",
      "observed_behavior": "...",
      "expected_behavior": "...",
      "evidence": "...",
      "risk": "...",
      "recommended_fix": "...",
      "acceptance_test": "..."
    }
  ]
}
```

---

## 19. Definition of Done

The audit is complete only when:

- All audit files are produced.
- Every critical/high issue has evidence.
- Every critical/high issue has an acceptance test.
- The project has a clear list of false-pass scenarios.
- The project has a proposed export gate policy.
- The remediation plan is sorted by implementation priority.
- The audit distinguishes between actual implemented behavior and desired behavior.
- No issue is marked resolved without code evidence or test evidence.

The project should be considered production-blocked if any of the following remain true:

```text
final report can export with Tier-3-only material facts
final report can export with missing valuation-critical fields
final report can export with unresolved source discrepancy
final report can export with formula trace missing
final report can export with generic citations only
final report can export based only on LLM self-evaluation
```

---

## 20. Claude Code Execution Prompt

Use this prompt for Claude Code or another coding agent.

```text
You are auditing the Vietnam Pharma Equity Research Multi-Agent project using the attached 03_fix_err_harness_engineering.md.

Your task is audit-only first. Do not modify production code in the first pass.

Follow the phases exactly:
1. Baseline audit
2. Data provenance audit
3. Source discovery and ingestion audit
4. PDF/OCR extraction audit
5. Reconciliation audit
6. Formula and financial logic audit
7. Forecast and valuation audit
8. Narrative and citation audit
9. Evaluation gate audit
10. Agent workflow and state management audit
11. Harness remediation plan

For every issue, include:
- issue_id
- severity
- component
- observed_behavior
- expected_behavior
- evidence with file path and line reference where possible
- risk
- recommended_fix
- acceptance_test

Do not claim a component works unless you can point to code, tests, or run artifacts.
Do not mark the project as production-ready if final report export can pass with unverified data, missing valuation-critical fields, unresolved source discrepancy, formula trace gaps, or generic citations.

After completing the audit, create all files under audits/ and produce a final summary with:
- critical blockers
- high-risk issues
- recommended implementation order
- tests that must be added before refactoring
```

---

## Appendix A — Recommended Internal Benchmark Scenarios

Create a mini benchmark suite for the project.

| Case ID | Scenario | Expected Result |
|---|---|---|
| ERR-BENCH-001 | Official PDF, CafeF and vnstock agree for DHG FY2024 revenue | Pass |
| ERR-BENCH-002 | Only vnstock has revenue, no official source | Fail export |
| ERR-BENCH-003 | Official PDF and vnstock revenue differ materially | Fail export or needs review |
| ERR-BENCH-004 | OCR extracts wrong net profit due to table misread | Fail reconciliation |
| ERR-BENCH-005 | Report cites database but no source document | Fail citation gate |
| ERR-BENCH-006 | FCFF formula uses wrong sign for change in working capital | Fail formula gate |
| ERR-BENCH-007 | Debt forecast is N/A but FCFE is calculated | Fail forecast gate |
| ERR-BENCH-008 | Narrative says margin improved while table shows margin declined | Fail narrative consistency gate |
| ERR-BENCH-009 | Terminal value contributes excessive percentage without warning | Fail or warn depending threshold |
| ERR-BENCH-010 | Report recommendation not connected to valuation output | Fail narrative grounding gate |

---

## Appendix B — Recommended Gate Policy

```yaml
export_gate_policy:
  block_on:
    - missing_source_trace_for_material_claim
    - tier3_only_material_fact
    - unresolved_major_source_discrepancy
    - missing_formula_trace
    - missing_forecast_driver
    - missing_debt_forecast_when_required
    - unresolved_na_in_valuation
    - generic_citation_only
    - llm_only_evaluation_pass
  warn_on:
    - minor_source_discrepancy
    - low_confidence_ocr_fact
    - terminal_value_dominance
    - weak_qualitative_event_evidence
  require_machine_readable_result: true
```

---

## Appendix C — Recommended Evidence Packet Contract

```json
{
  "run_id": "...",
  "ticker": "DHG",
  "periods": ["2021FY", "2022FY", "2023FY", "2024FY", "2025FY"],
  "source_documents": [],
  "canonical_facts": [],
  "reconciliation_results": [],
  "formula_traces": [],
  "forecast_assumptions": [],
  "valuation_outputs": [],
  "citation_map": [],
  "quality_gate_results": [],
  "known_limitations": []
}
```

The report writer should consume this evidence packet only. It should not independently invent, infer or fetch material numbers outside the harness.
