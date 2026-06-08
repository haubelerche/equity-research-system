# DATA_LAYER_AUDIT_REPORT.md

**Date:** 2026-06-07
**Auditor:** Claude Code (Opus 4.6)
**Scope:** Full data layer audit — storage locations, pipeline flow, scripts, quality controls, Supabase vs local, Data Agent role, blocked reports, dirty data handling, cleanup plan.

---

## 1. Executive Summary

### Is the current data layer coherent or fragmented?

**Partially coherent with significant fragmentation.** The architecture has a well-designed intended flow (documented in `docs/DATA_ARCHITECTURE.md`) but the implementation has drifted:

- **PostgreSQL is the intended source of truth** for canonical facts (`fact.financial_facts`, `fact.accepted_financial_facts`), but the DB requires a running Postgres instance that is not always available.
- **Golden CSV files** (`config/dataset/golden/financials/`) act as a **parallel source of truth** — they bypass the DB and inject facts directly into `build_fact_table()`. This is intentional (offline development), but creates ambiguity about which source wins.
- **Artifact JSON files** (`artifacts/facts/`, `artifacts/valuation/`) are **run-scoped outputs**, not sources of truth. However, `render_report.py` reads them via glob fallback when no `run_id` is provided, creating a risk of stale artifact reuse.
- **Supabase is not active.** The `.env` has empty Supabase keys. All DB access uses `psycopg2` to `postgresql://maer:maer_local@localhost:5432/maer_dev`. Supabase migrations exist only in a worktree (`feat-data-ingestion`), not on `main`.

### Current source of truth

| Data type | Authoritative source | Fallback | Risk |
|---|---|---|---|
| Financial facts | PostgreSQL `fact.financial_facts` | Golden CSV merge | Golden CSV can override DB silently |
| Frozen snapshots | PostgreSQL `research.snapshots` | None (DB-only) | No snapshot = no valuation |
| Valuation artifacts | `artifacts/valuation/*.json` | Glob latest | Stale artifact reuse if no run_id |
| Report drafts | `reports/*.md` | None | BLOCKED reports accumulate |
| Published reports | `artifacts/reports_html/*.html` + `artifacts/reports_pdf/*.pdf` | None | Not versioned by run_id consistently |
| Run state/approvals | PostgreSQL `research.runs`, `research.run_approvals` | None | DB-only |

### Highest-risk data correctness issues

1. **Golden CSV override is silent.** `build_facts.py` appends golden CSV facts to DB facts before `build_fact_table()`. If golden CSV has a wrong value with Tier 1 confidence, it will silently override the correct DB value with no warning.
2. **No snapshot = pipeline fails.** Without a running PostgreSQL, `create_snapshot()` and `load_snapshot_facts()` fail. The pipeline cannot run end-to-end from raw inputs without a DB.
3. **Artifact glob fallback.** `report_data_loader.py` falls back to globbing `artifacts/` for the latest file when no `run_id` is provided. This can silently reuse a stale artifact from a previous run.
4. **Blocked reports accumulate without cleanup.** 14 BLOCKED `.md` files in `reports/` with no lifecycle policy.
5. **Source/reconciliation gates are SKIPPED, not FAILED.** The export gate for DHG shows `source_gate: SKIP`, `reconciliation_gate: SKIP` — these gates silently pass when artifacts are missing, rather than blocking.

### Does the data pipeline actually work end-to-end?

**Yes, when PostgreSQL is running.** The canonical path is:

```
run_research.py → ResearchGraphRunner.execute()
  → auto_ingest_tool() → build_facts_tool() → build_index_tool()
  → run_valuation_tool() → generate_report_tool() → evaluate_quality_tool()
  → gates → HITL approval → export
```

Each tool calls a script function that reads from DB, computes deterministically, and writes JSON artifacts. **Without a running DB, only the render path works** (reading pre-existing artifacts).

---

## 2. Data Inventory

| Location | File types | Purpose | Producer | Consumer | Source of truth? | Keep/Move/Delete | Notes |
|---|---|---|---|---|---|---|---|
| `data/official_documents/{ticker}/{year}/` | CSV, JSON | Extracted facts + metadata from official PDFs | `ingest_official_documents.py` | `auto_ingest_official_documents.py` | No — staging area | Keep | Only DHG has data; DBD dirs empty |
| `data/raw/official_documents/{ticker}/{year}/` | PDF, SHA256 | Raw official PDFs + integrity checksums | Manual placement / `discover_official_documents.py` | `pdf_extractor.py` | Yes — immutable raw zone | Keep | Only DHG has 4 PDFs (2022-2025) |
| `data/promoted_facts/{ticker}/{year}/` | JSON | OCR-promoted facts with provenance | `fact_promotion.py` | `build_facts.py` (indirectly via DB) | No — intermediate | Keep | Written by promotion gate |
| `config/dataset/contracts/` | JSON | Schema definitions for data types | Manual | Validation scripts | Yes — schema contracts | Keep | 7 JSON schemas |
| `config/dataset/golden/financials/` | CSV, JSON | Manually verified financial facts + provenance | Manual curation | `build_facts.py`, `normalizer.py` | **Yes — Tier 0/1 override** | Keep | DBD.csv, DHG.csv + provenance JSONs |
| `config/dataset/mvp/` | CSV, YAML | Templates and MVP scope | Manual | Reference only | Yes — config | Keep | eps_actuals_template, golden_facts_spec |
| `config/dataset/sources/` | YAML | Data source catalog | Manual | Connectors, validation | Yes — source registry | Keep | source_catalog.yaml |
| `config/dataset/taxonomy/` | YAML | Metric and catalyst taxonomies | Manual | `pdf_extractor.py`, normalizer | Yes — taxonomy | Keep | financial_taxonomy_vn_pharma.yaml |
| `config/dataset/universe/` | CSV | Company universe (23 pharma tickers) | Manual | `load_universe_rows()`, report_data_loader | Yes — universe | Keep | pharma_vn_universe.csv |
| `artifacts/facts/` | JSON | Canonical fact reports per run | `build_facts.py` | `run_valuation.py`, report generation | No — run output | Keep (with lifecycle) | ~10 files, 50 KB each |
| `artifacts/forecast/` | JSON | FCFF, FCFE, blend, forecast models | `run_valuation.py` | Report generation | No — run output | Keep (with lifecycle) | ~87 files |
| `artifacts/valuation/` | JSON | Valuation artifacts + gate results | `run_valuation.py` | `render_report.py`, `evaluate_quality.py` | No — run output | Keep (with lifecycle) | ~40 files |
| `artifacts/valuation_results/` | JSON | Final valuation result summaries | `run_valuation.py` | Report data loader | No — run output | Keep (with lifecycle) | ~12 files |
| `artifacts/evidence_packets/` | JSON | Citation evidence for report sections | `ResearchGraphRunner` | Export gate, report | No — run output | Keep (with lifecycle) | ~26 files |
| `artifacts/reports/` | JSON | Export gate results, layout audits, report artifacts | `export_gate.py`, `layout_audit.py` | Render pipeline | No — run output | Keep (with lifecycle) | ~30+ files |
| `artifacts/reports_html/` | HTML | Client-ready rendered reports | `render_report.py` | End user / analyst | No — final output | Keep (with lifecycle) | 8 HTML files |
| `artifacts/reports_pdf/` | PDF | Final PDF exports + Chrome profiles | `pdf_renderer.py` | End user / analyst | No — final output | Keep PDFs, delete Chrome profiles | 6 PDFs + 60+ Chrome temp dirs |
| `artifacts/charts/` | PNG | Report visualizations | `generate_charts.py` | HTML/PDF reports | No — run output | Keep (with lifecycle) | 13 PNGs |
| `artifacts/audits/` | JSON | Agent effectiveness audits | `ResearchGraphRunner` | Observability | No — audit trail | Keep | ~14 files |
| `artifacts/handoffs/` | JSON | Agent-to-agent state handoffs | `ResearchGraphRunner` | Gate checks | No — run output | Keep (with lifecycle) | |
| `artifacts/manifests/` | JSON | Artifact manifests per run | `ResearchGraphRunner` | `report_data_loader.py` | No — run index | Keep | |
| `reports/` | MD | Draft report narratives (BLOCKED) | `generate_report.py` | Manual review | No — draft output | Keep (with lifecycle) | 14 BLOCKED files |
| `reports/eval/` | JSON, MD | Quality gate evaluation results | `evaluate_report_quality.py` | Manual review | No — eval output | Keep | 2 files |
| PostgreSQL `fact.*` | DB tables | Canonical financial facts, price history, catalysts | Connectors, ingestion scripts | `build_facts.py`, snapshots | **Yes — primary SoT** | Keep | Requires running DB |
| PostgreSQL `research.*` | DB tables | Runs, steps, approvals, artifacts, snapshots | `RuntimeStore`, harness | Pipeline state management | **Yes — run state SoT** | Keep | Requires running DB |
| PostgreSQL `ingest.*` | DB tables | Sources, parser runs, document chunks | Connectors, ingestion | Source lineage | **Yes — source registry** | Keep | Requires running DB |
| PostgreSQL `ref.*` | DB tables | Companies, universe | `upsert_company_snapshot()` | Report generation | **Yes — reference data** | Keep | Requires running DB |

---

## 3. Actual Data Flow

### DBD End-to-End Trace

```
1. Raw PDF placement
   → data/raw/official_documents/DBD/{year}/*.pdf
   → CURRENTLY EMPTY — no official PDFs placed for DBD

2. Auto-ingest (scripts/auto_ingest_official_documents.py)
   → Attempts CafeF web scrape + PDF extraction
   → Writes to data/official_documents/DBD/{year}/
   → Currently fails (no official docs) → falls back to Tier 3

3. API ingestion (scripts/ingest_ticker.py)
   → scripts/connectors/vnstock_finance_connector.py
   → Reads from VCI/KBS API via vnstock library
   → Writes to PostgreSQL fact.financial_facts (source_tier=3)

4. Golden CSV merge (scripts/build_facts.py)
   → Reads config/dataset/golden/financials/DBD.csv
   → Reads config/dataset/golden/financials/DBD_golden_provenance.json (Tier 0)
   → Appends golden facts to DB facts before build_fact_table()
   → build_fact_table() selects winner per (metric, period): lowest tier wins
   → Golden CSV (Tier 0) overrides VCI API (Tier 3) for 2025FY

5. Fact normalization (backend/facts/normalizer.py)
   → build_fact_table(raw_facts) → FactTable[metric][period] = FactEntry
   → validate_and_normalize() checks metric semantics via metric_metadata.py
   → compute_derived() adds gross_margin, net_margin, ebitda_margin, etc.
   → Conflict report generated (build_source_conflict_report)

6. Completeness gate (backend/facts/completeness.py)
   → Checks: ≥3 FY periods, core keys present, validation_status=accepted
   → Source tier coverage check per period
   → Output: valuation_gate = pass/fail

7. Research snapshot (backend/dataops/snapshot.py)
   → create_snapshot() freezes accepted facts into research.snapshots
   → Only created if valuation_gate == "pass"
   → Snapshot ID used for all downstream reads

8. Fact artifact (artifacts/facts/DBD_{ts}_fact_report.json)
   → JSON with full FactTable, conflicts, tier coverage, validation report
   → ~50 KB per run

9. Valuation (scripts/run_valuation.py)
   → load_snapshot_facts(snapshot_id) from DB
   → Runs: forecasting → FCFF → FCFE → blend → sensitivity
   → Output: artifacts/valuation/DBD_{ts}_valuation.json

10. Report generation (scripts/generate_report.py)
    → Reads snapshot + valuation artifact
    → Builds Vietnamese narrative via section_builder / narrative_builder
    → Writes: reports/DBD_{ts}_full_report_draft_BLOCKED.md

11. Export gate (backend/reporting/export_gate.py)
    → 9-gate check: source, reconciliation, numeric, forecast, valuation, sensitivity, citation, layout, human_review
    → Output: artifacts/reports/DBD_{ts}_export_gate.json
    → render_mode = "analyst_draft" (blocked) or "client_final" (exportable)

12. Render (scripts/render_report.py)
    → Loads ReportContext via report_data_loader.py
    → Renders HTML → artifacts/reports_html/DBD_report.html
    → Optionally renders PDF → artifacts/reports_pdf/DBD_report.pdf
```

### DHG End-to-End Trace

Same flow as DBD, with key differences:
- **Official PDFs exist:** `data/raw/official_documents/DHG/2022-2025/` has 4 annual report PDFs + SHA256 checksums
- **Extracted facts exist:** `data/official_documents/DHG/2022/extracted_facts.csv`, `extracted_facts_pdf.csv`, `metadata.json`
- **Golden CSV exists:** `config/dataset/golden/financials/DHG.csv` + provenance JSON
- **Latest run:** Jun 6 artifacts present

### Transition Detail

| Stage | Script/Module | Input | Output | Schema | Validation | Failure behavior |
|---|---|---|---|---|---|---|
| Raw → Extracted | `pdf_extractor.py` | PDF file | `ExtractedRow` objects | YAML metric dictionary | Regex label matching | Missing metrics logged |
| Extracted → Candidate | `ocr_candidate_facts.py` | ExtractedRow | `CandidateFact` | Schema validation, period check | Financial sanity, duplicate detection | Status = "failed" |
| Candidate → Promoted | `fact_promotion.py` | CandidateFact | `FactEntry` | Confidence ≥ 0.80, reconciliation matched | 4-rule gate | Status = "blocked" |
| Promoted → DB | `PostgresFactStore.upsert_financial_facts()` | FactEntry | DB row | UPSERT on (ticker, year, period, metric, source_id) | DB constraint | Upsert overwrites |
| DB → Snapshot | `create_snapshot()` | DB query | `research.snapshots` row | Snapshot ID = hash(ticker, years, date) | Idempotent per day | Exception |
| Snapshot → FactTable | `build_fact_table()` | Snapshot facts | `FactTable` | Tier→confidence→recency selection | Unit normalization | Rejects bad units |
| FactTable → Forecast | `forecasting.py` | FactTable + assumptions | `ForecastArtifact` | 5-year projection | Revenue/margin bounds | Missing input → block |
| Forecast → Valuation | `fcff.py`, `blend.py` | Forecast + WACC | `FCFFResult`, `BlendResult` | FCFF formula, 60/40 blend | Gap checks, terminal value weight | Warning or block |
| Valuation → Report | `generate_report.py` | Snapshot + valuation JSON | Markdown report | Vietnamese sections | Citation mapping | BLOCKED status |
| Report → Export | `export_gate.py` | Report + all artifacts | Gate result JSON | 9-gate evaluation | Each gate pass/fail/skip | render_mode = analyst_draft |

---

## 4. Supabase vs Local Files

### What is stored where?

| Storage | What | Authoritative? |
|---|---|---|
| **PostgreSQL (local)** | Financial facts, price history, catalyst events, company profiles, snapshots, run state, approvals, audit events, budget ledger, document chunks | **Yes — primary SoT for all structured data** |
| **Local files: `config/dataset/golden/`** | Manually verified facts with provenance | **Yes — Tier 0/1 override for golden data** |
| **Local files: `artifacts/`** | Run-scoped outputs (fact reports, valuations, forecasts, evidence packets, reports) | **No — derived outputs, reproducible from DB** |
| **Local files: `data/raw/`** | Immutable raw PDFs + checksums | **Yes — raw zone (immutable originals)** |
| **Local files: `data/official_documents/`** | Extracted facts staging | **No — intermediate processing** |
| **Local files: `reports/`** | Draft markdown reports | **No — output artifacts** |

### Supabase status

**Supabase is NOT active on `main`.** Evidence:
- `.env` has empty `SUPABASE_PROJECT_ID`, `SUPABASE_PUBLIC_KEY`, `SUPABASE_SECRET_KEY`
- No `supabase/` directory on `main` branch
- Supabase migrations (`001_ref_schema.sql` through `006_ops_schema.sql`) exist only in `.worktrees/feat-data-ingestion/supabase/migrations/`
- All Python code uses `psycopg2.connect(DATABASE_URL)` directly — no Supabase client SDK

### Can a report be regenerated from DB alone?

**Yes**, if:
1. PostgreSQL is running with `fact.*`, `research.*`, `ingest.*` schemas populated
2. Golden CSV files are present in `config/dataset/golden/financials/`
3. Raw PDFs are present in `data/raw/official_documents/` (for official document ingestion)

The command would be: `python scripts/run_research.py --ticker DHG`

### Can a report be regenerated from artifacts alone?

**Partially.** `render_report.py` with `--allow-latest-artifacts` (debug mode) can render HTML/PDF from the latest `artifacts/` files without a DB. But:
- No snapshot creation (requires DB)
- No approval recording (requires DB)
- No run state tracking (requires DB)
- Stale artifact risk (no validation)

### Are there duplicate or divergent copies?

**Yes — Golden CSV + DB facts.** `build_facts.py` merges golden CSV facts with DB facts. If the same metric/period exists in both, `build_fact_table()` selects the one with the lowest `source_tier`. This is the designed behavior (golden overrides API), but:
- There is no reconciliation report comparing golden vs DB values
- A golden CSV error would silently override correct DB data
- The golden CSV confidence gate (≥ 0.80) is the only safety check

---

## 5. Data Agent Reality Check

### What does the Data Agent actually do?

The "Data Agent" is the `data_retrieval` agent in the harness. Based on code evidence from `backend/harness/runner.py:264-286`:

```python
elif stage == "DATA_RETRIEVAL_RUN":
    # Step 1: auto_ingest_tool (non-blocking)
    auto_result = self._run_tool(state, "data_retrieval", "auto_ingest", ...)
    # Step 2: build_facts_tool (reads DB → builds fact table)
    result = self._run_tool(state, "data_retrieval", "build_facts", ...)
    # Step 3: build_index_tool (builds evidence index)
    index_result = self._run_tool(state, "data_retrieval", "build_index", ...)
    # Step 4: LLM agent call — REVIEW ONLY
    agent_result = self._run_agent(state, "data_retrieval",
        "Review data inventory, source coverage, and retrieval readiness.")
```

**The Data Agent (LLM call) does NOT:**
- Parse PDFs — that's `pdf_extractor.py` (deterministic Python)
- Write canonical facts — that's `PostgresFactStore.upsert_financial_facts()` (deterministic)
- Create snapshots — that's `create_snapshot()` (deterministic)
- Compute anything — tools do all computation
- Write to Supabase or any database — tools handle DB writes

**The Data Agent DOES:**
- Review data quality summaries produced by tools
- Summarize source coverage and retrieval readiness
- Flag concerns (as an LLM review, not a gate decision)
- Produce a text payload stored in `state.artifacts["data_retrieval_review"]`

### Which services do the real data work?

| Function | File | What it does |
|---|---|---|
| `auto_ingest_tool()` | `backend/harness/tools.py:76` | Calls `auto_ingest_official_documents.py` for CafeF + PDF + OCR |
| `build_facts_tool()` | `backend/harness/tools.py:38` | Calls `build_facts()` → DB read → normalize → validate → snapshot |
| `build_index_tool()` | `backend/harness/tools.py:149` | Calls `build_index()` → evidence chunk indexing |
| `PostgresFactStore` | `backend/database/fact_store.py:47` | All DB reads/writes for facts, prices, catalysts |
| `create_snapshot()` | `backend/dataops/snapshot.py:45` | Freezes accepted facts into immutable snapshot |
| `build_fact_table()` | `backend/facts/normalizer.py:94` | Tier→confidence→recency selection, unit normalization |
| `promote_candidate_facts()` | `backend/documents/fact_promotion.py` | 4-rule gate for OCR fact promotion |
| `VietnameseBCTCExtractor` | `backend/documents/pdf_extractor.py` | PDF → ExtractedRow via pdfplumber |

**Conclusion:** The Data Agent is a **review-only LLM call**. All deterministic data work is done by Python tools and services. This is correct architecture per CLAUDE.md: "Agent = stateful reasoning/coordination. Module/service = deterministic computation or I/O."

---

## 6. Script Classification

| Script | Purpose | Category | Called by pipeline? | Reads data? | Writes artifacts? | Touches DB? | Recommended action |
|---|---|---|---|---|---|---|---|
| `run_research.py` | Canonical harness entrypoint | Production CLI | Yes (main entry) | No | Indirectly (via tools) | Yes | Keep |
| `build_facts.py` | Canonical fact report builder | Production CLI | Yes (via `build_facts_tool`) | DB + golden CSV | `artifacts/facts/` | Yes (read + DQ write) | Keep |
| `run_valuation.py` | Valuation engine | Production CLI | Yes (via `run_valuation_tool`) | DB (snapshot) | `artifacts/valuation/` | Yes (read) | Keep |
| `generate_report.py` | Report narrative generator | Production CLI | Yes (via `generate_report_tool`) | DB (snapshot) + artifacts | `reports/` + `artifacts/citation/` | Yes (read) | Keep |
| `render_report.py` | HTML/PDF renderer | Production CLI | No (manual step) | Artifacts | `artifacts/reports_html/`, `reports_pdf/` | Optional | Keep |
| `approve_report.py` | HITL approval CLI | Production CLI | No (manual step) | DB (run state) | No | Yes (write approval) | Keep |
| `ingest_ticker.py` | Unified ticker ingestion | Ingestion utility | No (pre-pipeline) | vnstock API | No | Yes (write facts) | Keep |
| `ingest_official_documents.py` | Official document ingestion | Ingestion utility | No (pre-pipeline) | PDF files | `artifacts/official_sources/` | Yes (write facts) | Keep |
| `auto_ingest_official_documents.py` | Auto-ingest orchestrator | Ingestion utility | Yes (via `auto_ingest_tool`) | CafeF + PDFs | CSV artifacts | Yes (write facts) | Keep |
| `ingest_catalyst_sources.py` | Catalyst source ingestion | Ingestion utility | No (pre-pipeline) | Source registry | `artifacts/catalysts/` | Yes (write events) | Keep |
| `build_index.py` | Evidence index builder | Production CLI | Yes (via `build_index_tool`) | DB + docs | `artifacts/index/` | Yes (write chunks) | Keep |
| `validate_data.py` | Standalone data validation | Validation utility | No | DB (snapshot) | `reports/` | Yes (read) | Keep |
| `validate_phase1.py` | Phase 1 smoke test | Validation utility | No | DB schema | No | Yes (read) | Keep |
| `validate_phase2.py` | Phase 2 smoke test | Validation utility | No | Fact artifact | No | No | Keep |
| `validate_phase3.py` | Phase 3 smoke test | Validation utility | No | Fact artifact + provenance | No | No | Keep |
| `evaluate_report.py` | Report evaluation harness | Evaluation utility | No | Report + artifacts | `artifacts/evaluation/` | Optional | Keep |
| `evaluate_report_quality.py` | Quality gate script | Evaluation utility | Yes (via `evaluate_quality_tool`) | Valuation artifact | `reports/eval/` | No | Keep |
| `evaluate_citations.py` | Citation coverage gate | Evaluation utility | No | Report + citation map | No | No | Keep |
| `smoke_official_doc_e2e.py` | Official doc E2E test | Validation utility | No | DB + docs | No | Yes (read) | Keep |
| `reconcile_financial_facts.py` | Fact reconciliation | Reconciliation utility | No | DB (vnstock vs official) | `artifacts/reconciliation/` | Yes (read) | Keep |
| `cleanup_financial_facts.py` | Remove quarterly facts | Admin CLI | No | DB | No | Yes (delete) | Keep |
| `discover_official_documents.py` | Document discovery | Ingestion utility | No | Web (company IR, HOSE) | `data/discovered_documents/` | No | Keep |
| `generate_charts.py` | Chart generation | Rendering utility | No | Valuation + facts artifacts | `artifacts/charts/` | Yes (read) | Keep |
| `test_retrieval.py` | Evidence retrieval test | Debug script | No | DB chunks | No | Yes (read) | Move to `scripts/debug/` |
| `check_ocr_runtime.py` | OCR runtime check | Debug script | No | N/A | No | No | Move to `scripts/debug/` |
| `setup_fonts.py` | Font installation | Admin CLI | No | N/A | System fonts | No | Keep |
| `admin/manual_refresh.py` | Manual data refresh | Admin CLI | No | vnstock API | No | Yes (write) | Keep |
| `admin/weekly_sync.py` | Weekly data sync | Admin CLI | No | All connectors | No | Yes (write) | Keep |
| `admin/chunk_pipeline.py` | Chunk embedding pipeline | Admin CLI | No | PDFs + docs | Milvus vectors | Optional | Keep |
| `admin/validate_contracts.py` | Schema contract validation | Admin CLI | No | YAML/JSON configs | No | No | Keep |
| `admin/validate_universe.py` | Universe CSV validation | Admin CLI | No | CSV | No | No | Keep |
| `admin/offline_eval.py` | Offline evaluation | Admin CLI | No | Artifacts | No | No | Keep |
| `connectors/vnstock_finance_connector.py` | Financial statement connector | Connector utility | Yes (via `ingest_ticker`) | vnstock API | No | Yes (write facts) | Keep |
| `connectors/vnstock_price_connector.py` | Price history connector | Connector utility | Yes (via `ingest_ticker`) | vnstock API | No | Yes (write prices) | Keep |
| `connectors/vnstock_company_connector.py` | Company profile connector | Connector utility | Yes (via `ingest_ticker`) | vnstock API | No | Yes (write profiles) | Keep |
| `connectors/catalyst_bhyt_connector.py` | BHYT catalyst connector | Connector utility | No | Web | No | Yes (write events) | Keep |
| `connectors/catalyst_dav_connector.py` | DAV catalyst connector | Connector utility | No | Web | No | Yes (write events) | Keep |
| `connectors/catalyst_hose_connector.py` | HOSE catalyst connector | Connector utility | No | Web | No | Yes (write events) | Keep |
| `connectors/catalyst_tender_connector.py` | Tender result connector | Connector utility | No | Web | No | Yes (write events) | Keep |
| `connectors/manual_upload_connector.py` | Manual upload handler | Connector utility | No | Manual files | No | Minimal | Keep |
| `debug/_vnstock_path.py` | Path fix utility | Debug script | No (imported) | N/A | No | No | Keep |
| `debug/_debug_recon.py` | Debug reconciliation query | Debug script | No | DB | No | Yes (read) | Keep |
| `debug/debug_vnstock_financial_coverage.py` | vnstock coverage matrix | Debug script | No | vnstock API | `artifacts/data_quality/` | No | Keep |
| `demo/demo_render_dhg.py` | DHG demo render | Demo script | No | Hardcoded data | HTML output | No | Keep (gitignore output) |
| `demo/demo_render_dhg_client.py` | FPTS-style demo render | Demo script | No | DB + artifacts | HTML output | Yes (read) | Keep |

**Summary:** 42 scripts total. 6 production CLI, 5 ingestion, 8 validation/evaluation, 3 retrieval, 2 reconciliation, 5 admin, 8 connectors, 3 debug, 2 demo.

---

## 7. Data Quality Controls

| Control | Implemented? | Enforced? | Where? | Test coverage | Remaining risk |
|---|---|---|---|---|---|
| **Unit validation** | Yes | Yes (reject on invalid) | `backend/facts/metric_metadata.py` `validate_and_normalize()` | Yes (`test_metric_metadata.py`) | FactEntry has no `unit` field — semantics derived from metric_id |
| **Source tier validation** | Yes | Yes (Tier 3 blocked for final export) | `backend/citations/source_tier_policy.py`, `backend/reporting/export_gate.py` | Yes (`test_source_provenance_gate.py`, `test_final_source_gates.py`) | Gates SKIP when artifacts missing (should FAIL) |
| **Confidence threshold** | Yes | Yes (≥ 0.80 for promotion, ≥ 0.80 for golden CSV) | `backend/documents/fact_promotion.py`, `backend/facts/normalizer.py` | Yes (`test_ocr_promotion_gate.py`) | Tier 3 capped at 0.85 without cross-check |
| **Duplicate detection** | Yes | Yes (within OCR candidates) | `backend/documents/ocr_validation.py` | Yes (`test_ocr_validation_gate.py`) | No cross-run duplicate detection |
| **Stale data detection** | Partial | No (30-day threshold too aggressive) | `evaluate_report.py` gate G4 | Minimal | Staleness policy not enforced at export |
| **Cross-source reconciliation** | Yes | Yes (OCR vs API within tolerance) | `backend/documents/ocr_reconciliation.py` | Yes (`test_ocr_reconciliation_gate.py`) | Tolerance 0.5% may be too tight for VND rounding |
| **Cross-PDF reconciliation** | No | No | Not implemented | None | Two PDFs for same period could produce different facts |
| **Schema validation** | Yes | Yes | `config/dataset/contracts/*.json`, `admin/validate_contracts.py` | Partial | Contracts validated offline, not at ingestion time |
| **Missing period handling** | Yes | Yes (blocks if < 3 FY) | `backend/facts/completeness.py` | Yes (unit tests) | Missing periods are logged but not auto-fetched |
| **Conflict threshold** | Yes | Yes (> 2% flagged, > 10% requires review) | `backend/facts/normalizer.py` `build_source_conflict_report()` | Yes (unit tests) | Conflicts logged but don't block valuation |
| **Golden CSV override control** | Partial | Yes (provenance JSON → Tier 0/1) | `build_facts.py` `_load_golden_fallback()` | Yes | No provenance = Tier 3 (safe default) |
| **Source checksum** | Yes | Yes (SHA256 for raw PDFs) | `data/raw/official_documents/**/*.sha256` | Manual | No automated checksum verification in pipeline |
| **Ticker mismatch detection** | Partial | No explicit gate | Ticker passed as parameter, not validated against document content | None | Wrong ticker → wrong facts silently |
| **Period mismatch detection** | Partial | Yes (FY filter in `build_facts.py`) | `_filter_facts()` rejects non-FY periods | Yes | Q periods silently dropped |
| **Accounting reconciliation** | Yes | Yes (5 checks) | `backend/facts/reconciliation.py` | Yes (unit tests) | Warns but doesn't always block |

---

## 8. Dirty Data Handling

| Dirty data case | Current behavior | Gate/warning/block? | Evidence | Recommended fix |
|---|---|---|---|---|
| **PDF/OCR extracts wrong unit** | `validate_and_normalize()` checks unit semantics per metric_id; rejects if incompatible | Block (reject fact) | `metric_metadata.py` NormResult with status="reject" | Adequate — already blocks |
| **Same metric in CSV and PDF with conflicting values** | `build_fact_table()` selects lowest tier → highest confidence → latest ingested_at | Warning (conflict report) | `normalizer.py:155-213` ConflictRecord generated, > 10% = requires_review | Should block valuation if conflict on core metric |
| **Missing fiscal year** | Missing periods tracked in `periods_missing`; blocks valuation if < 3 FY | Block (valuation_gate fail) | `completeness.py` build_fy_validation_report | Adequate |
| **Tier-3-only source** | Allowed for draft; blocked for final export | Block (export gate) | `source_tier_policy.py`, `export_gate.py` source_gate | Source gate currently SKIPs when manifest missing — should FAIL |
| **Stale annual report** | 30-day threshold in evaluator (too aggressive for FY data) | Warning only | `evaluate_report.py` G4 | Change to 18-month threshold for FY data |
| **Mismatched ticker** | No automatic detection | No gate | N/A | Add ticker verification against document content |
| **Duplicate document** | SHA256 checksum prevents re-ingestion of identical PDFs | Dedup | `data/raw/*/SHA256` files | No automated enforcement — manual checksums only |
| **Corrupted PDF** | pdfplumber raises exception; logged and skipped | Warning (non-blocking) | `pdf_extractor.py` try/except | Adequate — pipeline continues with Tier 3 |
| **Old artifact reused accidentally** | Glob fallback selects latest file by name sort | No gate | `report_data_loader.py:56` `sorted(glob(...))[-1]` | Eliminate glob fallback; require run_id always |
| **Golden CSV contains low-confidence fact** | Rejected if confidence < 0.80 | Block (reject fact) | `normalizer.py:453` and `build_facts.py:173` | Adequate |
| **Source checksum changes** | No automated detection | No gate | SHA256 files exist but not checked by pipeline | Add checksum verification at ingestion |
| **Manual override conflicts with official source** | Golden CSV (Tier 0/1) overrides API (Tier 3) by design | Intentional override | `build_fact_table()` tier selection | Add reconciliation report for golden vs DB values |

---

## 9. End-to-End Smoke Test

**Cannot run a clean E2E test in this session** because:
1. PostgreSQL is not confirmed running (`DATABASE_URL=postgresql://maer:maer_local@localhost:5432/maer_dev`)
2. The pipeline requires a live DB for snapshot creation, fact reading, and run state tracking
3. Running `run_research.py` would make API calls (vnstock, Anthropic) with real cost

### What we CAN verify from existing artifacts:

**DBD — Latest run artifacts (Jun 5, 2026):**
- `artifacts/facts/DBD_*_fact_report.json` — exists, 50 KB
- `artifacts/valuation/DBD_*_valuation.json` — exists
- `reports/DBD_20260605T074641_full_report_draft_BLOCKED.md` — BLOCKED
- Export gate: `forecast_gate=FAIL`, `human_review_gate=FAIL`
- Blocking reasons: unapproved WACC, unapproved tax rate, unapproved terminal growth, unapproved forecast model, unapproved debt/dividend schedules

**DHG — Latest run artifacts (Jun 5-6, 2026):**
- `artifacts/facts/DHG_20260606T111855_fact_report.json` — exists
- `artifacts/valuation/DHG_*_valuation.json` — exists
- `reports/DHG_20260605T101829_full_report_draft_BLOCKED.md` — BLOCKED
- Export gate: `forecast_gate=FAIL` (dividend_schedule missing), `human_review_gate=FAIL`
- render_mode = `analyst_draft` (not exportable)
- 4 raw PDFs with SHA256 checksums for DHG (2022-2025)

### Blocked reports — why they're blocked

All 14 blocked reports in `reports/` share these common blocking reasons:

| Gate | Status | Reason |
|---|---|---|
| `forecast_gate` | FAIL | Dividend schedule missing; debt schedule uses proxy |
| `human_review_gate` | FAIL | No analyst approval for assumptions or final report |
| `source_gate` | SKIP | Source manifest not provided |
| `reconciliation_gate` | SKIP | Reconciliation artifact not provided |
| `citation_gate` | SKIP | Claim ledger not provided |

**Key insight:** Most gates SKIP (artifact not provided) rather than FAIL. This is an observability gap — a SKIP should be treated as FAIL for production readiness assessment.

---

## 10. Cleanup and Reorganization Plan

### Phase 1: Artifact Lifecycle Policy (Low risk, immediate)

**Problem:** 378+ artifact files with no cleanup policy.

**Actions:**
1. Delete all Chrome profile directories in `artifacts/reports_pdf/.chrome-profile-*/` (60+ temp dirs)
2. Add `.gitignore` entries for `artifacts/reports_pdf/.chrome-profile-*/`
3. Implement artifact retention: keep last 3 runs per ticker, archive older ones
4. Add `scripts/admin/cleanup_artifacts.py` with `--dry-run` and `--confirm` flags

### Phase 2: Gate SKIP → FAIL Policy (Medium risk)

**Problem:** Gates return SKIP when artifacts are missing, which doesn't block export.

**Actions:**
1. In `backend/reporting/export_gate.py`, change all `status: SKIP` results to `passed: false` (currently `passed: false` but not always)
2. Add a meta-gate: if any gate has status SKIP, overall is FAIL
3. Add test: assert no gate can SKIP in production pipeline

### Phase 3: Eliminate Glob Fallback (Medium risk)

**Problem:** `report_data_loader.py` falls back to globbing latest artifact when no run_id.

**Actions:**
1. Remove `allow_latest_artifacts` parameter from `_resolve_artifact()`
2. Always require `run_id` for production rendering
3. Keep glob fallback only in `demo/` scripts (clearly labeled)

### Phase 4: Run-Scoped Artifact Organization (Medium risk)

**Current:** Artifacts are in flat directories (`artifacts/facts/`, `artifacts/valuation/`), distinguished only by timestamp in filename.

**Target:**
```
artifacts/
  runs/{run_id}/
    manifest.json              # artifact manifest
    fact_report.json           # canonical facts
    valuation.json             # valuation result
    forecast.json              # forecast artifact
    fcff.json                  # FCFF artifact
    blend.json                 # blend artifact
    evidence_packet.json       # evidence packet
    export_gate.json           # export gate result
    report_draft.md            # draft report
    report.html                # rendered HTML
    report.pdf                 # rendered PDF
    citation_map.json          # citation map
    agent_effectiveness.json   # agent audit
  latest -> runs/{latest_run_id}/  # symlink for convenience
```

**Migration:**
1. New runs write to `artifacts/runs/{run_id}/`
2. Old artifacts remain in flat dirs (backward compat)
3. Manifest-based resolution (`artifact_manifest.py`) already supports this
4. Update `report_data_loader.py` to prefer run-scoped paths

### Phase 5: Data Directory Cleanup (Low risk)

**Current state → Target:**
```
data/
  raw/official_documents/{ticker}/{year}/*.pdf   → KEEP (immutable raw zone)
  raw/official_documents/{ticker}/{year}/*.sha256 → KEEP (integrity)
  official_documents/{ticker}/{year}/*.csv        → KEEP (extracted facts staging)
  promoted_facts/{ticker}/{year}/*.json           → KEEP (promotion results)
```

No changes needed — the `data/` structure is clean.

### Phase 6: Script Organization (Low risk)

**Move:**
- `scripts/test_retrieval.py` → `scripts/debug/test_retrieval.py`
- `scripts/check_ocr_runtime.py` → `scripts/debug/check_ocr_runtime.py`

**No deletions recommended.** All 42 scripts serve a purpose. The classification in Section 6 provides the organizational guide.

### Phase 7: Golden CSV Reconciliation (Medium risk)

**Problem:** Golden CSV can silently override DB facts with no reconciliation report.

**Actions:**
1. Add a reconciliation check in `build_facts.py` that compares golden CSV values against DB values and logs any overrides
2. If a golden CSV value differs from DB value by > 2%, flag as conflict requiring review
3. Add provenance validation: reject golden CSV without provenance JSON (currently defaults to Tier 3)

### Phase 8: Blocked Report Cleanup (Low risk)

**Actions:**
1. Archive reports older than 7 days: `reports/archive/{date}/`
2. Keep only the latest 2 per ticker in `reports/`
3. Each blocked report already has a paired `*_export_gate.json` in `artifacts/reports/`

### Tests Required Before Cleanup

```
pytest tests/ -x                    # All 1345+ tests must pass
pytest tests/unit/ -k "gate"        # All gate tests
pytest tests/unit/ -k "export"      # Export gate tests
pytest tests/unit/ -k "manifest"    # Manifest tests
pytest tests/unit/ -k "normalizer"  # Fact normalization tests
```

### Rollback Plan

All changes are additive (new directories, new scripts) or involve only moving files. Git tracks all changes, so rollback = `git checkout main -- <file>`.

---

## Appendix A: Database Schema (Current on Main)

The following schemas are used by `psycopg2` code but migrations exist only in the worktree:

```
ref.companies                    — Company master data
fact.financial_facts             — Raw financial facts (with source_id)
fact.accepted_financial_facts    — View/table of accepted-only facts
fact.canonical_facts             — Phase 2 canonical facts (may not exist yet)
fact.fact_observations           — Phase 2 observation layer (may not exist yet)
fact.price_history               — Daily price data
fact.catalyst_events             — Corporate events
ingest.sources                   — Source registry with tier/URI
ingest.company_snapshots         — Point-in-time company data
ingest.document_chunks           — Text chunks for evidence retrieval
ingest.parser_runs               — Parser execution log
research.snapshots               — Immutable fact snapshots
research.snapshot_items           — Snapshot membership
research.runs                    — Research run lifecycle
research.run_steps               — Step execution log
research.run_artifacts           — Artifact references
research.run_approvals           — HITL approval records
research.run_audit_events        — Audit trail
research.run_budget_ledger       — Cost tracking
research.data_quality_reports    — DQ gate results
public.schema_migrations         — Migration version tracking
```

---

## Appendix B: Recommended Folder Structure (Target)

```
data/
  raw/
    official_documents/{ticker}/{year}/*.pdf, *.sha256
  official_documents/{ticker}/{year}/*.csv, *.json       # extracted facts staging
  promoted_facts/{ticker}/{year}/*.json                  # promotion results

config/
  dataset/
    contracts/                  # JSON schemas
    golden/financials/          # Tier 0/1 golden facts
    mvp/                        # MVP templates
    sources/                    # Source catalog
    taxonomy/                   # Metric taxonomies
    universe/                   # Company universe
  agents/                       # Agent configurations
  metrics/                      # Metric dictionary YAML
  harness/                      # Harness policies

artifacts/
  runs/{run_id}/                # Run-scoped artifacts (NEW)
    manifest.json
    fact_report.json
    valuation.json
    ...
  facts/                        # Legacy flat (keep for backward compat)
  valuation/                    # Legacy flat
  forecast/                     # Legacy flat
  charts/                       # Generated charts
  reports/                      # Export gate results
  reports_html/                 # Rendered HTML
  reports_pdf/                  # Rendered PDF (no Chrome profiles)

reports/
  drafts/                       # BLOCKED report drafts
  eval/                         # Evaluation gate results

scripts/
  cli/                          # Production: run_research, approve_report
  ingest/                       # Ingestion: ingest_ticker, auto_ingest, etc.
  validate/                     # Validation: validate_data, validate_phase*, etc.
  evaluate/                     # Evaluation: evaluate_report, evaluate_citations, etc.
  admin/                        # Admin: manual_refresh, weekly_sync, etc.
  connectors/                   # Data connectors (keep as-is)
  debug/                        # Debug scripts (keep as-is)
  demo/                         # Demo scripts (keep as-is)
```

---

*End of audit. No code was changed. All findings are based on file reads, grep searches, and agent explorations.*
