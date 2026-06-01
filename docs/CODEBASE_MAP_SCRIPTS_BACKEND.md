# Codebase Map: `scripts/` and `backend/`

## Scope

This document maps the primary Python code under `scripts/` and `backend/`.
It focuses on executable Python modules and package-level support files.
SQL migrations under `scripts/db/migrations/` are noted separately at the end rather than enumerated one by one.

## High-Level Assessment

### Overall state

- The codebase contains real domain logic, especially in `backend/analytics`, `backend/facts`, `backend/documents`, and the deterministic report-generation path.
- The current architecture is **partly clean in core finance logic**, but **mixed/dirty at integration boundaries** because many scripts combine CLI concerns, environment bootstrapping, direct database access, filesystem IO, logging, and domain orchestration in the same module.
- The codebase is also **partly overengineered in orchestration**, especially around the multi-agent harness, where the abstraction depth is higher than the actual decision complexity currently implemented.

### What is working well

- Deterministic valuation and analytics modules are mostly well-separated from transport and UI concerns.
- Fact normalization, reconciliation, validation, and source-tier logic show strong product thinking around data trust and publish safety.
- Snapshotting and artifact persistence create a reproducible pipeline foundation.

### What is not yet optimal

- Large script files such as `scripts/generate_report.py`, `scripts/run_valuation.py`, `scripts/build_index.py`, and `scripts/auto_ingest_official_documents.py` are doing too much at once.
- Repeated bootstrap code for `.env`, `sys.path`, stdout configuration, and ad hoc CLI behavior appears across many files.
- Several `script` entry points also behave like libraries, but still call `sys.exit()` internally, which makes reuse brittle.
- The LangGraph-style harness currently adds architectural weight, but much of the actual business execution still delegates to synchronous deterministic script functions.

### Strategic reading of the architecture

| Area | Assessment | Why |
|---|---|---|
| Deterministic finance logic | Good | Core valuation, forecasting, ratios, and gates are explicit and auditable. |
| Data-trust layer | Promising but dense | Good source-tier and reconciliation ideas, but spread across many modules. |
| Script layer | Dirty | Too much repeated bootstrapping and mixed responsibilities. |
| Harness/orchestration layer | Overengineered relative to current logic | Extra graph/agent abstractions exist without equivalent operational sophistication underneath. |
| Persistence model | Serviceable | Runtime and snapshot persistence are useful, but some contracts are inconsistent between legacy and new paths. |

## File Map

### `scripts/`

| File | Purpose |
|---|---|
| `scripts/__init__.py` | Package marker for script imports. |
| `scripts/_debug_recon.py` | Ad hoc local debugging script for reconciliation and canonical fact inspection. |
| `scripts/_vnstock_path.py` | Reorders import resolution so installed `vnstock` wins over the local reference folder. |
| `scripts/approve_report.py` | Human review CLI for final approval, rejection, and export of generated reports. |
| `scripts/auto_ingest_official_documents.py` | End-to-end orchestrator for discovering, fetching, OCR-processing, validating, reconciling, and promoting official-document facts. |
| `scripts/build_facts.py` | Builds canonical FY fact artifacts, runs completeness and reconciliation gates, and creates research snapshots. |
| `scripts/build_index.py` | Builds retrieval chunks from official PDFs, OCR artifacts, catalyst events, synthetic facts, and text documents. |
| `scripts/check_ocr_runtime.py` | Verifies OCR runtime dependencies such as Tesseract, Poppler, and Python packages. |
| `scripts/cleanup_financial_facts.py` | Deletes quarterly fact rows to enforce the current FY-only MVP data policy. |
| `scripts/debug_vnstock_financial_coverage.py` | Empirically probes coverage and quality of vnstock financial data across tickers, providers, and statement types. |
| `scripts/discover_official_documents.py` | CLI to discover and optionally fetch official filings and annual-report candidates. |
| `scripts/evaluate_citations.py` | Citation-coverage evaluation gate for report grounding quality. |
| `scripts/evaluate_report.py` | Full report evaluation harness for quality, citation, consistency, and publication readiness. |
| `scripts/evaluate_report_quality.py` | Deterministic quality gate for report numerical consistency and valuation/report coherence. |
| `scripts/generate_report.py` | Large deterministic Markdown report generator with forecast, valuation, citations, catalyst sections, and export gating. |
| `scripts/ingest_catalyst_sources.py` | Orchestrates ingestion of catalyst/event sources into the database. |
| `scripts/ingest_official_documents.py` | Ingests official documents and extracted facts into registry/storage layers. |
| `scripts/ingest_ticker.py` | Main single-ticker ingestion entry point that coordinates market, finance, and document ingestion. |
| `scripts/reconcile_financial_facts.py` | Reconciles provider financial facts against official-document facts. |
| `scripts/run_research.py` | Legacy pipeline runner plus newer harness entry point for end-to-end research execution. |
| `scripts/run_valuation.py` | Main deterministic valuation runner for ratios, DCF, FCFF, FCFE, multiples, sensitivities, and confidence. |
| `scripts/smoke_official_doc_e2e.py` | Narrow smoke test for official-document ingestion and OCR/reconciliation flow. |
| `scripts/test_retrieval.py` | Smoke test for retrieval quality and evidence chunk access. |
| `scripts/validate_data.py` | Standalone data validation CLI and markdown validation-report producer. |
| `scripts/validate_phase1.py` | Smoke test for early source-tier and migration assumptions. |
| `scripts/validate_phase2.py` | Smoke test for fact-artifact provenance structure. |
| `scripts/validate_phase3.py` | Smoke test for source-tier coverage and golden-provenance behavior. |

### `scripts/connectors/`

| File | Purpose |
|---|---|
| `scripts/connectors/__init__.py` | Package marker for ingestion connectors. |
| `scripts/connectors/catalyst_bhyt_connector.py` | Scrapes and normalizes BHYT-related catalyst events. |
| `scripts/connectors/catalyst_dav_connector.py` | Scrapes DAV-related catalyst events and maps them to tracked tickers. |
| `scripts/connectors/catalyst_hose_connector.py` | Scrapes HOSE/HNX disclosure-style catalyst events. |
| `scripts/connectors/catalyst_tender_connector.py` | Scrapes procurement/tender events as company catalysts. |
| `scripts/connectors/manual_upload_connector.py` | Registers manually uploaded documents and provenance metadata into the source registry. |
| `scripts/connectors/vn_market_data_adapter.py` | Adapter that reshapes market and financial datasets into peer-analysis friendly tables. |
| `scripts/connectors/vnstock_company_connector.py` | Pulls company profile/news/event data through vnstock and writes normalized company/event records. |
| `scripts/connectors/vnstock_finance_connector.py` | Pulls financial statements from vnstock, maps labels to canonical metrics, and persists normalized facts. |
| `scripts/connectors/vnstock_price_connector.py` | Pulls price history from vnstock and syncs normalized price rows. |

### `scripts/dataset/`

| File | Purpose |
|---|---|
| `scripts/dataset/__init__.py` | Package marker for dataset helpers. |
| `scripts/dataset/bootstrap_mvp_facts.py` | Bootstraps MVP financial datasets for initial system bring-up. |
| `scripts/dataset/check_golden_facts.py` | Verifies expected golden dataset artifacts and fact coverage. |
| `scripts/dataset/chunk_pipeline.py` | Utility pipeline for chunk generation and offline retrieval/eval preparation. |
| `scripts/dataset/config_io.py` | Loads dataset/universe configuration such as tracked tickers. |
| `scripts/dataset/dqf.py` | Data-quality-framework helpers, including recompute invalidation logic used by services. |
| `scripts/dataset/manual_refresh.py` | Manual refresh helper for dataset/universe state. |
| `scripts/dataset/offline_eval.py` | Offline evaluation utilities for dataset-driven testing. |
| `scripts/dataset/validate_contracts.py` | Validates dataset and contract assumptions used by the pipeline. |
| `scripts/dataset/validate_universe.py` | Validates ticker-universe definitions and consistency. |
| `scripts/dataset/weekly_sync.py` | Weekly synchronization utility for dataset maintenance. |

### `scripts/db/`

| File | Purpose |
|---|---|
| `scripts/db/__init__.py` | Package marker for DB utilities. |
| `scripts/db/fact_store.py` | PostgreSQL access layer for financial facts, prices, and related research data. |
| `scripts/db/migrate.py` | Applies and validates database migrations. |
| `scripts/db/milvus_store.py` | Milvus vector-store wrapper for chunk indexing and retrieval experiments. |
| `scripts/db/official_documents.py` | Registry layer for official-document metadata and status tracking. |
| `scripts/db/source_registry.py` | Registry layer for source-version metadata and provenance persistence. |

### `backend/`

| File | Purpose |
|---|---|
| `backend/__init__.py` | Package identity for the backend system. |
| `backend/api.py` | FastAPI app factory and HTTP endpoints for research run lifecycle operations. |
| `backend/batch.py` | Batch submitter that launches full-report runs across the configured ticker universe. |
| `backend/executor.py` | Thread-pool executor that submits asynchronous research runs. |
| `backend/main.py` | Minimal entry point for serving the backend app. |
| `backend/orchestrator.py` | Backward-compatible supervisor facade over the newer harness runner. |
| `backend/retrieval.py` | Database-backed retrieval service for evidence chunks and citation lookups. |
| `backend/runtime_store.py` | Main persistence layer for runs, steps, artifacts, approvals, budgets, and audit events. |
| `backend/schemas.py` | Pydantic/FastAPI request and response schemas for the API surface. |
| `backend/services.py` | Cross-cutting services such as budget control, recompute planning, and lightweight offline evaluation. |
| `backend/settings.py` | Central settings object and environment-backed runtime configuration. |
| `backend/utils.py` | Small shared helpers such as deterministic IDs and utility transforms. |

### `backend/agents/`

| File | Purpose |
|---|---|
| `backend/agents/__init__.py` | Legacy import-compatibility package placeholder. |

### `backend/analytics/`

| File | Purpose |
|---|---|
| `backend/analytics/__init__.py` | Package marker for deterministic analytics engines. |
| `backend/analytics/approval_gate.py` | Blocks publish-grade recommendations until assumptions and review prerequisites are approved. |
| `backend/analytics/blend.py` | Blends FCFF and FCFE outputs into a combined DCF target price. |
| `backend/analytics/dcf.py` | Simplified deterministic DCF model and scenario runner. |
| `backend/analytics/debt_schedule.py` | Historical and forecast debt schedule builder. |
| `backend/analytics/dividend_schedule.py` | Dividend payout history and forecast policy builder. |
| `backend/analytics/fcfe.py` | Driver-based FCFE valuation engine. |
| `backend/analytics/fcff.py` | Driver-based FCFF valuation engine. |
| `backend/analytics/forecasting.py` | Main deterministic forecast engine for future financial statements and drivers. |
| `backend/analytics/multiples.py` | Relative valuation using market multiples such as P/E and EV/EBITDA. |
| `backend/analytics/ratios.py` | Historical ratio calculations, market ratios, and abnormal-movement detection. |
| `backend/analytics/sensitivity.py` | Sensitivity-table builders for DCF, blend, P/E, and EV/EBITDA scenarios. |
| `backend/analytics/tax_policy.py` | Tax-policy derivation and forecast assumptions. |
| `backend/analytics/valuation_confidence.py` | Final confidence grading for valuation outputs. |

### `backend/catalysts/`

| File | Purpose |
|---|---|
| `backend/catalysts/__init__.py` | Package marker for catalyst processing. |
| `backend/catalysts/event_extractor.py` | Normalizes raw source documents into structured catalyst events. |
| `backend/catalysts/ticker_mapper.py` | Maps catalyst headlines and source hints to canonical tickers. |

### `backend/citations/`

| File | Purpose |
|---|---|
| `backend/citations/__init__.py` | Package marker for grounding and citation logic. |
| `backend/citations/citation_map.py` | Builds structured citation maps from fact tables and converts between new and legacy formats. |
| `backend/citations/driver_evidence.py` | Renders catalyst and driver evidence blocks for reports. |
| `backend/citations/event_linker.py` | Links catalyst events to fiscal periods for narrative grounding. |
| `backend/citations/source_tier_policy.py` | Enforces source-tier policy and export blocking rules. |
| `backend/citations/validator.py` | Deterministic validators for citation coverage, tier quality, numeric consistency, and causality language. |

### `backend/dataops/`

| File | Purpose |
|---|---|
| `backend/dataops/__init__.py` | Package marker for operational data utilities. |
| `backend/dataops/quality_report.py` | Persists data-quality reports to research tables. |
| `backend/dataops/snapshot.py` | Creates and loads frozen research snapshots of accepted facts. |

### `backend/documents/`

| File | Purpose |
|---|---|
| `backend/documents/__init__.py` | Package marker for document-processing logic. |
| `backend/documents/company_registry.py` | Provides company metadata needed during official-document discovery. |
| `backend/documents/document_candidate_ranker.py` | Scores and ranks discovered filing/document candidates. |
| `backend/documents/fact_promotion.py` | Promotes validated OCR candidate facts into canonical fact entries. |
| `backend/documents/ocr_artifacts.py` | Persists OCR run artifacts and extracted page outputs. |
| `backend/documents/ocr_candidate_facts.py` | Defines and stores OCR candidate-fact staging objects. |
| `backend/documents/ocr_reconciliation.py` | Reconciles OCR facts against secondary/official sources. |
| `backend/documents/ocr_validation.py` | Validates OCR candidate facts with schema, period, sanity, and duplicate rules. |
| `backend/documents/official_document_discovery.py` | Orchestrates official-document discovery across connectors and ranking logic. |
| `backend/documents/pdf_extractor.py` | Extracts tabular financial facts from Vietnamese PDFs, with OCR fallback support. |

### `backend/documents/connectors/`

| File | Purpose |
|---|---|
| `backend/documents/connectors/__init__.py` | Package marker for document discovery connectors. |
| `backend/documents/connectors/base.py` | Shared connector base classes, candidate models, heuristics, and HTTP helpers. |
| `backend/documents/connectors/cafef_connector.py` | Structured Tier-2 financial connector using CafeF-style sources. |
| `backend/documents/connectors/company_ir_connector.py` | Connector for company investor-relations pages. |
| `backend/documents/connectors/hnx_disclosure_connector.py` | Connector for HNX/UPCoM disclosure pages. |
| `backend/documents/connectors/hose_disclosure_connector.py` | Connector for HOSE disclosure pages. |
| `backend/documents/connectors/ssc_disclosure_connector.py` | Connector for SSC/IDS disclosure pages. |

### `backend/evaluation/`

| File | Purpose |
|---|---|
| `backend/evaluation/__init__.py` | Package marker for evaluation gates. |
| `backend/evaluation/source_provenance_gates.py` | Final publish-time provenance gates for official-source coverage. |

### `backend/facts/`

| File | Purpose |
|---|---|
| `backend/facts/__init__.py` | Package marker for fact modeling and validation. |
| `backend/facts/completeness.py` | Completeness, freshness, source-tier, and valuation-readiness scoring for canonical facts. |
| `backend/facts/normalizer.py` | Normalizes raw financial facts into canonical tables and derived metrics. |
| `backend/facts/reconciliation.py` | Runs accounting and time-series reconciliation checks. |
| `backend/facts/validation_report.py` | Builds markdown validation reports for data quality and publish review. |

### `backend/harness/`

| File | Purpose |
|---|---|
| `backend/harness/__init__.py` | Package marker for the agent/harness execution layer. |
| `backend/harness/agent_registry.py` | Loads agent configs/prompts and validates allowed roles/tools. |
| `backend/harness/gates.py` | Defines deterministic pass/fail gates between harness stages. |
| `backend/harness/graph.py` | Defines stage order and optional LangGraph compilation. |
| `backend/harness/model_adapter.py` | Wraps OpenAI chat calls and maps model output into internal agent-result objects. |
| `backend/harness/runner.py` | Main stage runner that executes deterministic tools, agent reviews, approvals, and checkpoints. |
| `backend/harness/state.py` | Defines the research graph state and shared result/reference models. |
| `backend/harness/tools.py` | Adapts deterministic scripts into harness-compatible service-node tools. |

### `backend/jobs/`

| File | Purpose |
|---|---|
| `backend/jobs/__init__.py` | Package marker for scheduled jobs. |
| `backend/jobs/scheduler.py` | Schedules recurring ingestion, validation, and operational maintenance jobs. |

### `backend/reconciliation/`

| File | Purpose |
|---|---|
| `backend/reconciliation/__init__.py` | Package marker for reconciliation workflows. |
| `backend/reconciliation/financial_fact_reconciler.py` | Reconciles provider facts with official-document observations and writes reconciliation status. |

### `backend/sources/`

| File | Purpose |
|---|---|
| `backend/sources/__init__.py` | Package marker for external source-management utilities. |
| `backend/sources/document_fetcher.py` | Controlled fetcher for remote source documents. |
| `backend/sources/document_store.py` | Filesystem/storage helper for fetched documents. |
| `backend/sources/source_registry.py` | Loads and resolves configured catalyst/source metadata. |

### `backend/validation/`

| File | Purpose |
|---|---|
| `backend/validation/__init__.py` | Package marker for data-validation formulas. |
| `backend/validation/confidence.py` | Computes confidence scores for facts based on provenance and validation state. |
| `backend/validation/market_alignment.py` | Validates alignment between fundamentals and market data. |
| `backend/validation/report_builder.py` | Builds the final standalone data-validation report artifact. |

## Note on SQL Migrations

The folder `scripts/db/migrations/` and `scripts/db/migrations/_legacy/` contains schema history for:

- reference schema bootstrap
- ingest schema
- fact schema
- research/runtime schema
- source-document and official-document support
- claim/citation support
- fact reconciliation support

If needed, a follow-up document can enumerate each SQL migration file individually.
