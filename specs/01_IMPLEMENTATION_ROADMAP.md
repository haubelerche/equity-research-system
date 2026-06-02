# 01 — Implementation Roadmap

**Date:** 2026-05-22
**Status:** Active

---

## Guiding Constraints

1. One ticker (DHG) end-to-end before scaling to 5 tickers.
2. Every phase must produce runnable, artifact-generating scripts.
3. Do not claim a phase complete unless the smoke command succeeds and an output artifact exists.
4. Facts before narrative. Code-first valuation. Citation-first reporting.

---

## Phase 0 — Repository Audit and Planning ✅ (Current)

**Goal:** Understand the existing codebase and document what to build.

**Outputs:**
- [x] `specs/00_REPO_AUDIT.md`
- [x] `specs/01_IMPLEMENTATION_ROADMAP.md`
- [x] `specs/02_ARCHITECTURE_DECISIONS.md`

**No backend code changes in this phase.**

---

## Phase 1 — Data Contracts and Schema Foundation

**Goal:** Document data contracts so every future module knows its inputs and outputs.

**Outputs:**
- [ ] `specs/03_DATA_CONTRACTS.md`
- [ ] `specs/04_CANONICAL_FACT_SCHEMA.md`
- [ ] `specs/05_SOURCE_METADATA_SCHEMA.md`
- [ ] `specs/06_REPORT_TEMPLATE.md`
- [ ] `specs/07_EVALUATION_RUBRIC.md`

**Notes:**
- `config/dataset/contracts/*.schema.json` already exists — Phase 1 formalizes and cross-references these.
- Schemas should reference the existing JSON Schema files.
- The taxonomy files are the source of truth for canonical metric names.

---

## Phase 2 — Vnstock-Based Data Ingestion MVP

**Goal:** One command that ingests all available data for a single ticker.

**Smoke command:**
```bash
python scripts/ingest_ticker.py --ticker DHG --years 5
```

**Expected output:**
- Raw snapshots saved under `data/raw/`
- Source versions registered in `source_versions` table
- Financial facts upserted into `financial_facts` table
- Price rows upserted into `price_history` table
- Company profile upserted into `company_profiles` table
- Catalyst events upserted into `catalyst_events` table
- Data inventory JSON printed to stdout and saved

**Files to create:**
- [ ] `scripts/ingest_ticker.py` — unified entry point orchestrating all connectors

**Files already available:**
- `scripts/connectors/vnstock_finance_connector.py` ✅
- `scripts/connectors/vnstock_price_connector.py` ✅
- `scripts/connectors/vnstock_company_connector.py` ✅
- `backend/database/fact_store.py` ✅
- `backend/database/source_registry.py` ✅

**Pre-requisites:**
- PostgreSQL running at `DATABASE_URL` (default: `postgresql://maer:maer_local@localhost:5432/maer_dev`)
- vnstock installed (`pip install vnstock`)

---

## Phase 3 — Canonical Facts and Data Quality Gates

**Goal:** Normalize raw data into canonical facts with quality checks.

**Smoke command:**
```bash
python scripts/build_facts.py --ticker DHG
```

**Expected output:**
- Canonical facts with validation status
- Validation report (missing fields, outliers, staleness)
- Completeness score per metric group

**Files to create:**
- [ ] `scripts/build_facts.py`
- [ ] `backend/facts/normalizer.py`
- [ ] `backend/facts/repository.py`
- [ ] `backend/quality/fact_validators.py`

**Notes:**
- The DQF framework in `backend/dataset/dqf.py` already validates individual facts.
- This phase wraps DQF into a per-ticker report.

---

## Phase 4 — Code-First Financial Analysis and Valuation

**Goal:** Deterministic valuation from canonical facts.

**Smoke command:**
```bash
python scripts/run_valuation.py --ticker DHG
```

**Expected output:**
- Ratio table (gross margin, net margin, ROE, ROA, leverage, EPS growth)
- DCF artifact (explicit assumptions, WACC, terminal value)
- Multiples artifact (P/E, EV/EBITDA vs peers)
- Sensitivity table
- JSON artifact saved to `artifacts/valuation/`

**Files to create:**
- [ ] `scripts/run_valuation.py`
- [ ] `backend/valuation/ratios.py`
- [ ] `backend/valuation/dcf.py`
- [ ] `backend/valuation/multiples.py`
- [ ] `backend/valuation/sensitivity.py`
- [ ] `backend/valuation/artifact.py`

---

## Phase 5 — Evidence Retrieval and Citation Pipeline

**Goal:** Index source documents; retrieve grounding evidence for report claims.

**Smoke commands:**
```bash
python scripts/build_index.py --ticker DHG
python scripts/test_retrieval.py --ticker DHG
```

**Expected output:**
- Document chunks indexed in Milvus
- Evidence packs per claim
- Citation map format
- Citation validation baseline

**Files to create:**
- [ ] `scripts/build_index.py`
- [ ] `scripts/test_retrieval.py`
- [ ] `backend/retrieval/chunker.py`
- [ ] `backend/retrieval/indexer.py`
- [ ] `backend/retrieval/retriever.py`
- [ ] `backend/citations/citation_map.py`
- [ ] `backend/citations/validator.py`

---

## Phase 6 — Report Generation Baseline

**Goal:** Generate a grounded markdown equity research report.

**Smoke command:**
```bash
python scripts/generate_report.py --ticker DHG --report-type full_report
```

**Expected output:**
- Markdown report with 8 sections
- Evidence appendix
- Valuation appendix
- Citation map

**Files to create:**
- [ ] `scripts/generate_report.py`
- [ ] `backend/reporting/context_builder.py`
- [ ] `backend/reporting/section_writer.py`
- [ ] `backend/reporting/report_builder.py`
- [ ] `backend/reporting/export_markdown.py`

---

## Phase 7 — Evaluation Harness

**Goal:** Gate-check every report before it can be exported.

**Smoke command:**
```bash
python scripts/evaluate_report.py --report reports/DHG_full_report.md
```

**Expected output:**
- Evaluation summary JSON
- Pass/fail per gate
- Blocked export flag if any critical gate fails

**Files to create:**
- [ ] `scripts/evaluate_report.py`
- [ ] `backend/evaluation/numeric_consistency.py`
- [ ] `backend/evaluation/citation_coverage.py`
- [ ] `backend/evaluation/stale_data.py`
- [ ] `backend/evaluation/valuation_reproducibility.py`
- [ ] `backend/evaluation/unsupported_claims.py`
- [ ] `backend/evaluation/report_rubric.py`

---

## Phase 8 — Stateful Workflow and Agent Boundaries

**Goal:** Wire all phases into the existing orchestrator for traceable end-to-end runs.

**Smoke command:**
```bash
python scripts/run_research.py --ticker DHG --report-type full_report
```

**Expected output:**
- Run trace JSON
- Data inventory
- Facts
- Valuation artifact
- Report draft
- Evaluation summary
- Final workflow status

---

## Phase 9 — Human Review and Export

**Goal:** Human approval gate before final export.

**Smoke command:**
```bash
python scripts/approve_report.py --report-id <REPORT_ID>
```

**Expected output:**
- Approval record
- Final report export (Markdown + PDF)
- Artifact version record

---

## Current Status

| Phase | Status | Blocker |
|---|---|---|
| 0 — Audit | In Progress | — |
| 1 — Data Contracts | Not Started | Waiting for Phase 0 |
| 2 — Ingestion MVP | Connectors ready; entry point missing | `scripts/ingest_ticker.py` |
| 3 — Facts + DQF | Not Started | Waiting for Phase 2 |
| 4 — Valuation | Not Started | Waiting for Phase 3 |
| 5 — Retrieval | Not Started | Waiting for Phase 4 |
| 6 — Report Generation | Not Started | Waiting for Phase 5 |
| 7 — Evaluation | Not Started | Waiting for Phase 6 |
| 8 — Workflow | Not Started | Waiting for Phase 7 |
| 9 — Human Review | Not Started | Waiting for Phase 8 |

---

## Next Immediate Action

Create `scripts/ingest_ticker.py` to complete Phase 2.
