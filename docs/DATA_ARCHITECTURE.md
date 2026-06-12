# Data Architecture After System Rebuild

## Context

This document describes the active data architecture after the June 2026 rebuild and database/storage cutover. It supersedes earlier designs that described `v2_*` schemas, LangGraph-led workflows, loose artifact folders, or latest-file report resolution.

The production data layer is intentionally conservative: PostgreSQL/Supabase stores governed structured state, while storage buckets hold immutable source binaries and run-scoped large artifacts. The design optimizes for auditability, reproducibility, and financial correctness rather than real-time trading latency.

## Problem Statement

Equity research automation has three data risks that must be controlled before AI-generated narrative is acceptable:

| Risk | Failure mode | Architectural control |
|---|---|---|
| Source ambiguity | A report number cannot be traced to a filing, API payload, or approved manual source | `ingest.source_documents`, checksums, source tiers, source metadata |
| Fact instability | A report silently changes when live data changes | `research.snapshots`, run-scoped artifact manifest |
| AI numeric hallucination | LLM invents, repairs, or recalculates financial values | Deterministic fact promotion, Python analytics, citation and numeric gates |

The system therefore treats data as a governed research substrate:

```text
source document/API payload
-> raw observation
-> canonical fact
-> frozen research snapshot
-> deterministic analytics and valuation artifact
-> cited report claim
-> approved export
```

## Technical Deep-Dive

### Canonical Schemas

The active production schemas are:

| Schema | Responsibility | Runtime rule |
|---|---|---|
| `ref` | Company master data, metric dictionaries, peer groups, formula references | Seeded or administratively updated; not modified by LLM output |
| `ingest` | Source documents, connector runs, raw observations, document chunks | Stores provenance and extraction candidates, not canonical winners |
| `fact` | Canonical financial facts, price history, catalyst events | Source of truth for accepted financial data |
| `research` | Runs, stages, snapshots, manifests, run artifact metadata | Owns reproducibility and run lifecycle state |
| `valuation` | Valuation run metadata, assumptions, summaries | Stores approved assumptions and valuation metadata |
| `report` | Report records, claims, citations, gates, approvals | Enables claim-level audit and export control |
| `audit` | Immutable governance, migration, deletion, and cost events | Append-only; not used as mutable workflow state |

`archive_legacy` is a rollback and audit boundary only. Production code must not read from it.

### Storage Contract

The storage contract has four logical buckets:

| Bucket | Purpose | Example key |
|---|---|---|
| `sources` | Immutable official documents | `official_documents/DHG/2024/{source_doc_id}.pdf` |
| `runs` | Run-scoped artifacts | `{run_id}/manifest.json`, `{run_id}/valuation.json`, `{run_id}/report.html` |
| `exports` | Approved report copies | `approved_reports/DHG/{run_id}/report.pdf` |
| `archive` | Legacy/debug/failed-run retention | `legacy/...`, `debug/...`, `failed_runs/...` |

`backend.storage.layout` is the path-construction authority. Production code should not concatenate storage paths manually.

### Source Of Truth Matrix

| Data type | Source of truth | DB role | Storage/file role |
|---|---|---|---|
| Company and ticker master | PostgreSQL `ref` | Full record | None |
| Official PDF | `storage/sources` plus `ingest.source_documents` | Metadata, checksum, source tier | Binary file |
| Raw extracted financial line | PostgreSQL `ingest.observations` | Candidate value and provenance | Parser debug only |
| Canonical financial fact | PostgreSQL `fact.canonical_facts` | Accepted value and lineage | Snapshot export only |
| Frozen run snapshot | PostgreSQL metadata plus run artifact | Snapshot metadata and item refs | `facts_snapshot.json` |
| Full valuation output | Run artifact plus metadata | Summary and assumption metadata | `valuation.json` |
| Report claims and citations | PostgreSQL `report` | Claim ledger and source mapping | Rendered report only |
| HTML/PDF report | Run and export storage | Metadata and approval state | `report.html`, `report.pdf` |
| Audit/cost events | PostgreSQL `audit` | Append-only event log | Optional backup export |

### Data Flow

```text
vnstock / official PDFs / approved manual inputs
        |
        v
ingest.source_documents + ingest.observations
        |
        v
fact promotion and validation gates
        |
        v
fact.canonical_facts + fact.price_history
        |
        v
research snapshot freeze
        |
        v
analytics/valuation artifacts
        |
        v
evidence pack + claim ledger
        |
        v
report gates + HITL approval
        |
        v
approved export
```

### Document And Retrieval Layer

Official documents and report source material are registered with stable metadata:

```text
ticker
source_doc_id
source_type
source_tier
source_uri or storage path
source_title
published_at
fiscal_year
checksum
connector_name
fetch_status
```

Document chunks live in `ingest.document_chunks`. Migration 031 adds `pgvector` support so the same governed table can support both citation metadata and semantic retrieval. Embeddings support retrieval only; they are not a source of financial truth.

### OCR Layer

OCR is used for scanned Vietnamese financial PDFs and other documents without reliable text layers. The OCR runtime depends on:

| Component | Role |
|---|---|
| Tesseract OCR with Vietnamese language data | Recognize Vietnamese text |
| Poppler / `pdf2image` | Render PDF pages to images |
| `pytesseract` | Python OCR binding |
| `Pillow` | Image preprocessing |
| `pdfplumber` | Direct extraction for text-based PDFs |

OCR output is a staging artifact. It must pass validation and reconciliation before any value becomes a canonical fact. LLMs may help label or explain extraction issues, but must not repair or invent numeric facts.

### Research Snapshot Rule

Reports must never query live facts directly. A report is generated from a frozen snapshot and explicit artifacts:

```text
snapshot facts
market snapshot
evidence pack
financial analysis
forecast model
valuation artifact
claim ledger
quality gates
final report model
```

This rule prevents a report from changing simply because a connector refreshed data after the report run started.

### Artifact Manifest Rule

Every production artifact must be resolved by `run_id` and manifest entry. Timestamp-based latest-file selection and glob-based artifact discovery are prohibited in production because they can attach stale files to a new run.

### Data Quality Gates

The system evaluates data and report readiness through deterministic gates:

| Gate | Purpose |
|---|---|
| Source coverage | Required facts and evidence must have allowed sources |
| Period scope | Report period must match requested fiscal years |
| Unit consistency | Values must use explicit units and currencies |
| Numeric consistency | Report numbers must match canonical facts or valuation artifacts |
| Valuation reproducibility | Target price must reproduce from assumptions and artifacts |
| Citation coverage | Material factual and quantitative claims must have citations |
| Balance sheet identity | Forecast assets must reconcile with liabilities and equity |
| Freshness | Stale data must be flagged before export |

### Human Approval

Human approval is mandatory at judgment-heavy checkpoints:

| Approval stage | Reason |
|---|---|
| Valuation assumptions | WACC, terminal growth, forecast drivers, share count and peer assumptions require analyst judgment |
| Final report | The system must not publish financial analysis without reviewer approval |

Approval records should include reviewer, decision, timestamp, stage, and the artifact version approved.

## Strategic Recommendations

1. Treat PostgreSQL/Supabase as the source of truth for structured financial state and governance metadata.
2. Treat storage as the source of truth for source binaries and large run artifacts, never as an implicit data selector.
3. Keep `fact.canonical_facts` insulated from LLM output, report rendering, and valuation modules.
4. Require `run_id` and manifest lookup for any production artifact read.
5. Keep vector retrieval as an evidence access mechanism, not a financial fact store.
6. Preserve `archive_legacy` for rollback and audit only; it must not become a hidden runtime dependency.
7. When writing academic documentation, describe the system as a governed financial research data platform, not a generic RAG chatbot.
