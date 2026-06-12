# Filesystem Storage Cleanup Inventory

## Context

The filesystem migration executed on June 9, 2026 and consolidated production data under the canonical `storage/` root. Loose root-level artifact directories are no longer valid production locations.

## Execution Results

| Measure | Final state |
| --- | ---: |
| Official source PDFs | 4 |
| Registered run directories | 162 |
| Registered run artifact files | 315 |
| Approved export files | 0 |
| Archived legacy/debug/failed-run files | 4,255 |
| Files under legacy `artifacts/` | 0 |
| Files under legacy `data/` | 0 |
| Files under legacy `reports/` | 0 |

The empty approved-export set is contract-compliant because no report currently has approval metadata.

## Canonical Layout

```text
storage/
  sources/official_documents/{ticker}/{year}/{source_doc_id}.pdf
  runs/{run_id}/...
  exports/approved_reports/{ticker}/{run_id}/...
  archive/{legacy,debug,failed_runs}/...
```

`python scripts/storage/validate_storage_layout.py --json` returned no missing required directories and no legacy file counts.

## Reliability Controls

Migration utilities use checksum verification, reject conflicting destinations, and write migration manifests. Canonical path construction is centralized in `backend.storage.layout`, and archived content is excluded from the intended production read contract. The remaining operational loose-path callers are documented as blockers in `audits/final_data_architecture_verification.md`.
