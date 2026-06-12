# Final Storage And Database Contract

## Context

The canonical business schemas are `ref`, `ingest`, `fact`, `research`, `valuation`, `report`, and `audit`. `archive_legacy` is a read-only rollback boundary and is not an active production schema.

## Technical Contract

| Layer | Ownership | Prohibited behavior |
| --- | --- | --- |
| `ref` | Master data, dictionaries, formulas, peer groups | Run state or observations |
| `ingest` | Source metadata, connector runs, raw observations | Canonical winners |
| `fact` | Accepted canonical facts, prices, catalysts | Narrative or raw parser output |
| `research` | Runs, steps, snapshots, manifests, artifact metadata | Large binary/JSON payloads |
| `valuation` | Run metadata, assumptions, summaries | Full model payloads |
| `report` | Claims, citations, gates, approvals | Generated report binaries |
| `audit` | Immutable governance and cost events | Mutable workflow state |

Production files are restricted to:

```text
storage/sources/official_documents/{ticker}/{year}/{source_doc_id}.pdf
storage/runs/{run_id}/...
storage/exports/approved_reports/{ticker}/{run_id}/...
```

`backend.storage.layout` is the path-construction authority. `backend.reporting.artifact_manifest` reads and writes `storage/runs/{run_id}/manifest.json`. All generated files must be registered in `research.run_artifacts`; approved exports additionally require report approval metadata.

## Reliability And Rollback

Storage migrations default to checksum verification, reject conflicting overwrites, emit migration manifests, and support dry-run execution. Rollback uses each manifest's source, destination, and SHA-256 fields. Database rollback requires the pre-cutover database backup or the preserved `archive_legacy` data where table-only recovery is sufficient.
