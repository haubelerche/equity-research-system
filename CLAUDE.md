# CLAUDE.md

## 1. Project Identity

This repository is for the capstone project:

**Vietnam Pharma Equity Research Agent**

The system is an evidence-grounded equity research workflow for Vietnamese listed pharmaceutical and healthcare stocks.

It is **not**:

- an autonomous trading bot,
- a stock-picking chatbot,
- a generic financial Q&A assistant,
- a report writer that invents numbers.

It is a controlled research copilot that helps analysts produce auditable equity research reports by combining:

1. Vietnam-local financial data ingestion,
2. canonical financial facts,
3. deterministic valuation logic,
4. grounded report generation,
5. citation validation,
6. human review and approval.

The core pipeline is:

```text
Scope
→ Data contracts
→ Ingestion
→ Canonical facts
→ Data quality gates
→ Code-first valuation
→ Evidence retrieval
→ Report generation
→ Evaluation gate
→ Human approval
→ Export
```

Do not violate this dependency order.

---

## 2. Repository Context

The repository may contain the following important folders:

```text
FinRobot/
vnstock/
frontend/
scripts/
specs/
backend/
reports/
```

### 2.1 `FinRobot/`

`FinRobot/` is a cloned reference project.

Use it only as an architectural and conceptual reference.

You may inspect it to understand:

- financial agent abstractions,
- report generation flow,
- workflow decomposition,
- financial analysis examples,
- evaluation or prompt patterns.

Do not blindly copy FinRobot code.

Do not couple this project directly to FinRobot internals.

Do not turn this project into a smaller FinRobot clone.

This project has a different domain scope:

- Vietnamese pharma/y tế stocks,
- local data sources,
- citation-first reporting,
- code-first valuation,
- human approval before final export.

### 2.2 `vnstock/`

`vnstock/` is a local reference/library for Vietnamese stock market data.

Use it as a reference for:

- Vietnamese ticker handling,
- financial statement retrieval,
- market data retrieval,
- local data access patterns.

Build a clean connector layer around `vnstock`.

The rest of the codebase must depend on our connector abstraction, not directly on `vnstock` internals.

Preferred pattern:

```text
backend/connectors/base.py
backend/connectors/vnstock_connector.py
backend/ingestion/ingestion_service.py
```

### 2.3 `frontend/`

The frontend is secondary in the early phases.

Do not prioritize UI until the backend research pipeline works end-to-end for at least one ticker.

### 2.4 `specs/`

`specs/` is the canonical location for product, architecture, data, report, and evaluation specifications.

Important expected files:

```text
specs/00_REPO_AUDIT.md
specs/01_IMPLEMENTATION_ROADMAP.md
specs/02_ARCHITECTURE_DECISIONS.md
specs/03_DATA_CONTRACTS.md
specs/04_CANONICAL_FACT_SCHEMA.md
specs/05_SOURCE_METADATA_SCHEMA.md
specs/06_REPORT_TEMPLATE.md
specs/07_EVALUATION_RUBRIC.md
```

Always read relevant specs before implementation.

If implementation and specs conflict, stop and update or flag the spec mismatch before coding.

---

## 3. Source of Truth Priority

When making decisions, follow this priority order:

1. `CLAUDE.md`
2. `specs/` documents
3. existing implementation in this repository
4. local reference code in `vnstock/`
5. conceptual patterns from `FinRobot/`
6. external assumptions

Do not introduce large architectural changes without documenting them in:

```text
specs/02_ARCHITECTURE_DECISIONS.md
```

---

## 4. MVP Scope

Start with the MVP ticker universe:

```text
DHG
IMP
DMC
TRA
DBD
```

The first end-to-end implementation should focus on **one ticker**, preferably:

```text
DHG
```

Do not scale to all 23 tickers before the one-ticker pipeline is reliable.

The correct build order is:

```text
1 ticker end-to-end
→ 5 ticker MVP
→ 23 ticker universe
```

---

## 5. Non-Negotiable Engineering Principles

### 5.1 Facts Before Narrative

Financial facts must be ingested, normalized, validated, and stored before being used in reports.

LLMs must not invent:

- revenue,
- profit,
- EPS,
- margins,
- cash flow,
- debt,
- valuation multiples,
- target prices,
- financial ratios.

If a value is unavailable, mark it as missing.

Do not fabricate.

### 5.2 Code-First Valuation

All valuation logic must be deterministic Python code.

This includes:

- revenue growth,
- gross margin,
- net margin,
- ROE,
- ROA,
- leverage,
- EPS growth,
- DCF,
- P/E valuation,
- EV/EBITDA valuation,
- sensitivity table.

LLMs may explain valuation outputs, but must not compute or alter the source numbers.

### 5.3 Citation-First Reporting

Every important factual claim must trace back to either:

1. a canonical fact record, or
2. a source document chunk.

Quantitative claims require citations.

Unsupported claims must be removed or marked as:

```text
Insufficient evidence
```

Fake citations are a critical failure.

### 5.4 Human-in-the-Loop

The system must require human approval for:

- valuation assumptions,
- final report,
- final conclusion wording,
- any investment-style recommendation.

The system must not autonomously publish final reports.

### 5.5 Evaluation Before Scaling

Do not expand scope until evaluation gates exist.

Minimum evaluation gates:

- numeric consistency,
- citation coverage,
- citation validity,
- stale data detection,
- valuation reproducibility,
- unsupported recommendation detection.

### 5.6 Do Not Over-Agentize

Not every module should be an agent.

Keep deterministic services separate from LLM agents.

Correct separation:

```text
service/module = deterministic technical capability
workflow node = one step in the run lifecycle
agent role = LLM-assisted reasoning role
```

Examples:

- ingestion should be a service, not an LLM agent;
- fact normalization should be deterministic;
- valuation should be deterministic;
- citation validation should be mostly deterministic;
- LLMs should be used for grounded synthesis, not source-of-truth computation.

---

## 6. Target Architecture

Preferred high-level structure:

```text
backend/
  connectors/
    base.py
    vnstock_connector.py

  ingestion/
    ingestion_service.py
    source_registry.py

  facts/
    taxonomy.py
    normalizer.py
    repository.py

  quality/
    data_quality.py
    fact_validators.py

  valuation/
    ratios.py
    dcf.py
    multiples.py
    sensitivity.py
    artifact.py

  retrieval/
    chunker.py
    indexer.py
    retriever.py

  citations/
    citation_map.py
    validator.py

  reporting/
    templates.py
    context_builder.py
    section_writer.py
    report_builder.py
    export_markdown.py
    export_pdf.py

  evaluation/
    numeric_consistency.py
    citation_coverage.py
    stale_data.py
    valuation_reproducibility.py
    unsupported_claims.py
    report_rubric.py

  orchestration/
    state.py
    workflow.py
    checkpoints.py

  agents/
    supervisor.py
    research_agent.py
    auditor_agent.py

  review/
    review_state.py
    approval.py

scripts/
  ingest_ticker.py
  build_facts.py
  run_valuation.py
  build_index.py
  generate_report.py
  evaluate_report.py
  run_research.py
  approve_report.py

specs/
reports/
tests/
```

If the existing repository already has a different backend convention, adapt carefully instead of creating duplicate structures.

---

## 7. Data Model Requirements

### 7.1 Ticker Universe

Each ticker entry should support:

```yaml
ticker:
company_name:
exchange:
sector:
sub_sector:
peer_group:
active:
```

### 7.2 Source Metadata

Each source must track:

```yaml
source_id:
ticker:
source_type:
source_title:
source_url_or_path:
published_date:
fiscal_year:
quarter:
reliability_tier:
checksum:
ingested_at:
```

### 7.3 Raw Payload

Raw data must be saved before normalization.

Required fields:

```yaml
raw_payload_id:
source_id:
payload_type:
storage_path:
checksum:
parser_version:
created_at:
```

### 7.4 Canonical Financial Fact

Required fields:

```yaml
fact_id:
ticker:
fiscal_year:
quarter:
metric_name:
value:
unit:
currency:
source_id:
confidence:
created_at:
```

### 7.5 Document Chunk

Required fields:

```yaml
chunk_id:
source_id:
ticker:
text:
section:
fiscal_year:
metadata:
embedding_id:
```

### 7.6 Valuation Artifact

Required fields:

```yaml
valuation_id:
ticker:
method:
assumptions:
input_facts:
output_values:
sensitivity_table:
created_at:
```

### 7.7 Report Artifact

Required fields:

```yaml
report_id:
ticker:
report_type:
sections:
citation_map:
evaluation_summary:
approval_status:
created_at:
```

### 7.8 Run State

Required fields:

```yaml
run_id:
run_type:
ticker:
status:
current_stage:
checkpoints:
errors:
cost_ledger:
trace:
created_at:
updated_at:
```

---

## 8. Workflow Phases

Work phase by phase.

Do not skip foundational phases.

### Phase 0 — Repository Audit

Goal: understand the repo before implementation.

Expected outputs:

```text
specs/00_REPO_AUDIT.md
specs/01_IMPLEMENTATION_ROADMAP.md
specs/02_ARCHITECTURE_DECISIONS.md
```

Do not implement backend logic in this phase.

### Phase 1 — Data Contracts and Schema Foundation

Expected outputs:

```text
specs/03_DATA_CONTRACTS.md
specs/04_CANONICAL_FACT_SCHEMA.md
specs/05_SOURCE_METADATA_SCHEMA.md
specs/06_REPORT_TEMPLATE.md
specs/07_EVALUATION_RUBRIC.md
```

### Phase 2 — Vnstock-Based Data Ingestion MVP

Build a connector abstraction around `vnstock`.

Expected command:

```bash
python scripts/ingest_ticker.py --ticker DHG --years 5
```

Expected output:

- raw data saved,
- source metadata saved,
- ingestion run logged,
- data inventory generated.

### Phase 3 — Canonical Facts and Data Quality Gates

Expected command:

```bash
python scripts/build_facts.py --ticker DHG
```

Expected output:

- canonical facts,
- validation report,
- completeness/freshness score.

### Phase 4 — Code-First Financial Analysis and Valuation

Expected command:

```bash
python scripts/run_valuation.py --ticker DHG
```

Expected output:

- ratio table,
- DCF artifact,
- multiples artifact,
- sensitivity table,
- explicit assumptions.

### Phase 5 — Evidence Retrieval and Citation Pipeline

Expected commands:

```bash
python scripts/build_index.py --ticker DHG
python scripts/test_retrieval.py --ticker DHG
```

Expected output:

- chunked documents,
- evidence packs,
- citation map format,
- citation validation baseline.

### Phase 6 — Report Generation Baseline

Expected command:

```bash
python scripts/generate_report.py --ticker DHG --report-type full_report
```

Expected output:

- markdown report,
- evidence appendix,
- valuation appendix,
- citation map.

### Phase 7 — Evaluation Harness

Expected command:

```bash
python scripts/evaluate_report.py --report reports/DHG_full_report.md
```

Expected output:

- evaluation summary,
- pass/fail gates,
- blocked export if critical gates fail.

### Phase 8 — Stateful Workflow and Agent Boundaries

Expected command:

```bash
python scripts/run_research.py --ticker DHG --report-type full_report
```

Expected output:

- run trace,
- data inventory,
- facts,
- valuation artifact,
- report draft,
- evaluation summary,
- final workflow status.

### Phase 9 — Human Review and Export

Expected command:

```bash
python scripts/approve_report.py --report-id <REPORT_ID>
```

Expected output:

- approval record,
- final report export,
- artifact version record.

---

## 9. Agent Boundaries

The intended logical roles are:

### 9.1 Supervisor

Responsibilities:

- control run lifecycle,
- call services in correct order,
- record trace,
- handle retry/resume,
- block unsafe export.

The Supervisor must not write long reports directly.

### 9.2 Data Agent or Data Service

Responsibilities:

- ingestion,
- data inventory,
- source metadata,
- retrieval preparation.

This role must not create financial claims.

### 9.3 Quant / Valuation Service

Responsibilities:

- ratios,
- valuation,
- sensitivity analysis,
- reproducible artifacts.

This role must not use LLMs for arithmetic.

### 9.4 Research Agent

Responsibilities:

- synthesize narrative from locked facts, valuation artifacts, and evidence packs.

This role must not introduce unsupported claims.

### 9.5 Auditor Agent

Responsibilities:

- check citation coverage,
- check numeric consistency,
- detect unsupported recommendations,
- flag stale data,
- produce evaluation summary.

The Auditor must be able to block export.

---

## 10. Report Requirements

A full report should follow this structure:

```text
1. Executive Summary
2. Company Overview
3. Industry and Market Context
4. Financial Performance
5. Valuation
6. Investment Thesis
7. Key Risks
8. Conclusion
9. Appendix
   - assumptions
   - valuation tables
   - evidence table
   - evaluation summary
```

Report language should be:

- professional,
- cautious,
- analyst-style,
- evidence-grounded,
- clear about uncertainty.

Avoid:

- guaranteed returns,
- absolute buy/sell claims,
- unsupported upside/downside claims,
- invented catalysts,
- fake citations.

---

## 11. Evaluation Requirements

Every report must be evaluated before final export.

Minimum checks:

### 11.1 Numeric Consistency

Compare report numbers against canonical facts and valuation artifacts.

Critical failure:

- report number differs from source fact without explanation.

### 11.2 Citation Coverage

All quantitative claims must have valid citations or fact references.

Critical failure:

- quantitative claim without citation.

### 11.3 Citation Validity

A citation must support the claim it is attached to.

Critical failure:

- citation exists but does not support claim.

### 11.4 Stale Data Detection

Reports must flag stale financial data or outdated sources.

Critical failure:

- report presents stale data as current.

### 11.5 Valuation Reproducibility

Valuation output must be reproducible from assumptions and input facts.

Critical failure:

- valuation cannot be recomputed.

### 11.6 Unsupported Recommendation Detection

Reports must avoid unsupported or absolute investment advice.

Critical failure:

- report says or implies guaranteed return,
- report gives strong buy/sell instruction without sufficient support,
- report hides uncertainty.

---

## 12. Testing and Smoke Commands

Whenever implementing code, provide at least one smoke command.

Preferred script pattern:

```bash
python scripts/ingest_ticker.py --ticker DHG --years 5
python scripts/build_facts.py --ticker DHG
python scripts/run_valuation.py --ticker DHG
python scripts/build_index.py --ticker DHG
python scripts/generate_report.py --ticker DHG --report-type full_report
python scripts/evaluate_report.py --report reports/DHG_full_report.md
python scripts/run_research.py --ticker DHG --report-type full_report
```

If tests exist, run the relevant subset.

Do not claim a phase is complete unless:

- code runs,
- output artifact is generated,
- errors are documented,
- limitations are stated.

---

## 13. Implementation Protocol

For every task:

1. Inspect relevant files first.
2. Summarize the current state briefly.
3. Identify exact files to create or modify.
4. Implement the smallest useful change.
5. Avoid broad rewrites.
6. Add or update specs when behavior changes.
7. Add simple tests or smoke scripts.
8. Run available checks when feasible.
9. Summarize:
   - what changed,
   - how to run it,
   - what remains incomplete,
   - risks or blockers.

Do not modify unrelated files.

Do not delete `FinRobot/` or `vnstock/`.

Do not perform large formatting-only rewrites.

---

## 14. Coding Standards

Use Python for backend and research pipeline logic.

Prefer:

- clear module boundaries,
- typed functions where practical,
- dataclasses or Pydantic models for structured artifacts,
- deterministic services for data and valuation,
- explicit error handling,
- reproducible scripts,
- small composable functions.

Avoid:

- hidden global state,
- hardcoded ticker-specific logic outside config,
- direct LLM calls deep inside data services,
- direct dependency on external reference project internals,
- silent exception swallowing,
- untracked generated artifacts.

---

## 15. Data and Artifact Discipline

Generated outputs should be saved under clear locations, for example:

```text
data/raw/
data/processed/
data/facts/
reports/
artifacts/valuation/
artifacts/evaluation/
artifacts/runs/
```

If these folders do not exist, propose the structure before creating many files.

Each generated artifact should include:

- ticker,
- timestamp,
- source version or checksum where applicable,
- generation method,
- relevant assumptions.

---

## 16. Cost and Model Governance

If LLM integration is implemented later:

- use cheaper models for extraction/routing/simple checks,
- use stronger models only for complex synthesis or critique,
- log model name,
- log token usage if available,
- log cost estimate if available,
- cache reusable intermediate outputs,
- never expose API keys,
- never commit secrets.

Do not hardcode API keys.

Use environment variables.

Example:

```text
OPENAI_API_KEY
ANTHROPIC_API_KEY
```

---

## 17. Security and Compliance Rules

Do not:

- commit secrets,
- expose API keys,
- generate fake disclosures,
- bypass approval gates,
- output final investment advice as certainty,
- create autonomous trading logic,
- imply regulatory approval.

Reports should include appropriate limitations and evidence appendix.

---

## 18. Licensing and Attribution

Before reusing non-trivial code from `FinRobot/` or `vnstock/`:

1. inspect license files,
2. prefer conceptual adaptation over code copying,
3. document any direct adaptation,
4. preserve attribution where required.

For this capstone, the preferred approach is:

- use FinRobot as conceptual reference,
- use vnstock through a clean connector abstraction,
- implement project-specific pipeline logic ourselves.

---

## 19. Definition of Done

A phase is done only when:

1. expected files are created or updated,
2. relevant scripts run or limitations are documented,
3. output artifacts are generated where applicable,
4. specs reflect the implementation,
5. failure modes are documented,
6. next step is clear.

The full MVP is done only when one ticker can complete:

```text
ingestion
→ canonical facts
→ valuation
→ evidence retrieval
→ report generation
→ evaluation
→ human approval
→ export
```

---

## 20. Current Priority

The current priority is to build a reliable one-ticker end-to-end pipeline.

Do not prioritize:

- full frontend,
- all 23 tickers,
- complex autonomous multi-agent behavior,
- overly broad data sources,
- advanced UI,
- unnecessary abstraction.

Prioritize:

- data contracts,
- ingestion,
- canonical facts,
- deterministic valuation,
- citation mapping,
- evaluation gates,
- traceable artifacts.

---

## 21. Response Format for Claude Code

When completing a task, always respond with:

```text
## Summary
- What was done.

## Files Changed
- List exact files.

## How to Run
- Commands.

## Validation
- What was tested.
- What passed.
- What failed or was not run.

## Risks / Limitations
- Remaining issues.

## Next Step
- One recommended next action.
```

Be concise but precise.

Do not overstate completion.

Do not claim production readiness unless the full pipeline and evaluation gates work.

---

## 22. First Recommended Prompt

After placing this file at the repository root, use the following first prompt for Claude Code:

```text
Read CLAUDE.md carefully.

Start with Phase 0 only: repository audit and planning.

Do not implement backend logic yet.

Inspect:
- root repository structure,
- FinRobot/ as conceptual reference,
- vnstock/ as Vietnam data reference,
- existing specs/ if present,
- existing scripts/ and backend/ if present.

Create or update:
- specs/00_REPO_AUDIT.md
- specs/01_IMPLEMENTATION_ROADMAP.md
- specs/02_ARCHITECTURE_DECISIONS.md

After finishing, summarize:
- what you inspected,
- what FinRobot concepts are useful,
- what vnstock capabilities are useful,
- what should be built from scratch,
- proposed folder structure,
- next implementation phase,
- risks and blockers.

Do not modify unrelated files.
```
