# Source Of Truth Matrix

## Context

The production data layer uses PostgreSQL for governed structured state and `storage/` for immutable source binaries and run-scoped large artifacts. Files under `storage/archive/` are retained only for audit and rollback; production code must never read them.

## Source-Of-Truth Contract

| Data type | Source of truth | File allowed? | DB allowed? |
| --- | --- | --- | --- |
| Company/ticker master | PostgreSQL `ref` | No | Yes |
| Official PDF document | `storage/sources` + `ingest.source_documents` metadata | Yes | Metadata only |
| Raw extracted financial line | PostgreSQL `ingest.observations` | Temporary parser debug only | Yes |
| Canonical financial fact | PostgreSQL `fact.canonical_facts` | Snapshot export only | Yes |
| Frozen run snapshot | PostgreSQL metadata + `storage/runs/{run_id}/facts_snapshot.json` | Yes | Yes |
| Valuation assumptions | PostgreSQL `valuation.assumptions` | Optional run export | Yes |
| Full valuation output | `storage/runs/{run_id}/valuation.json` + `research.run_artifacts` | Yes | Summary only |
| Report claims/citations | PostgreSQL `report` | No | Yes |
| Report markdown/html/pdf | `storage/runs/{run_id}` and approved copies in `storage/exports` | Yes | Metadata only |
| Audit/cost events | PostgreSQL `audit` | Optional backup export | Yes |
| Debug output | `storage/archive/debug` | Yes | No production DB |

## Governance Rules

1. Run artifacts are resolved by `run_id` and manifest entry; timestamp or latest-file selection is prohibited.
2. Source PDFs are immutable and named by SHA-256-derived `source_doc_id`.
3. Canonical facts are promoted from observations; CSV files cannot override accepted facts.
4. `storage/archive` is outside every production read path.
