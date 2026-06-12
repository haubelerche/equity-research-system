# Semantic Data Model Audit

## Context

This audit evaluates the live canonical schemas after the namespace and filesystem
cutover. It focuses on semantic ownership, sparse columns, constant columns,
unused scaffolding, reference-data quality, and whether runtime behavior matches
the database contract.

## Executive Findings

The live database is structurally consolidated but not yet semantically minimal.
Several tables were copied from legacy structures or created for future workflow
states without being integrated into production execution.

| Finding | Evidence | Assessment |
| --- | --- | --- |
| Peer groups lack a governed taxonomy | Three groups were copied from legacy `segment` values; memberships overlap without documented rules | Redesign required |
| Valuation-method policy is stored on peer membership | `enabled_methods` is not read by production code | Remove from membership |
| Boolean lifecycle columns are constant | `is_active` is always true in four `ref` tables and is not read by production code | Remove unless a real deactivation workflow is implemented |
| Source registry mixes multiple entity types | API responses, news feeds, regulatory endpoints, and PDFs share `source_documents` | Normalize into a base source registry plus document-specific metadata |
| Source metadata contains deterministic defects | 15 source records linked to observations had recoverable but missing tickers; DAV feeds were misclassified | Repair immediately |
| Governance schemas are mostly disconnected | 162 runs and 315 artifacts exist, while snapshots, valuation metadata, reports, claims, citations, and gates contain zero rows | Wire into pipeline or remove speculative tables |
| Official-source verification is not operational | All 480 canonical facts have observations, but all 480 lack `official_document_id` | Governance promise not met |

## Applied Cleanup

The following low-ambiguity cleanup was applied live through
`029_semantic_reference_cleanup`:

- reduced peer groups to one documented `vn_pharma_listed` group containing all
  six current companies;
- reduced peer membership to the composite key `(peer_group_id, ticker)`;
- removed `enabled_methods`, membership `is_active`, and migration-only `added_at`;
- removed unused `is_active` columns from companies, line items, and formulas;
- removed all-NULL descriptions from line items and peer groups;
- removed constant formula version;
- repaired deterministic source metadata.

Post-cleanup source quality:

| Measure | Before | After |
| --- | ---: | ---: |
| NULL ticker | 30 | 10 |
| NULL source title | 48 | 0 |
| NULL connector name | 57 | 0 |
| DAV rows misclassified as financial | 6 | 0 |

The remaining ten NULL tickers are global DAV regulatory feeds and are
semantically valid because they do not belong to one company.

## Reference Schema

### `ref.companies`

Keep `ticker`, names, exchange, sector, subsector, currency, and timestamps.
`company_name_en` being NULL for one company is a content-quality issue, not a
schema defect. `sector` and `currency` are currently constant but remain valid
master-data attributes if the universe expands.

Remove `is_active` unless a documented deactivate/reactivate workflow and query
filter exist. The current value is always true and production code does not read it.

### `ref.line_items`

Keep the metric code, statement classification, labels, canonical unit, and
`is_derived`. These fields enforce fact semantics and are actively referenced.

Remove `description` because it is NULL for all 32 rows. Remove `is_active`
because it is always true and unused. A retired metric should be versioned through
a controlled dictionary migration rather than silently hidden by a boolean.

### `ref.formulas`

The table is currently a governance/catalog artifact; production calculations do
not load formulas from it. Keep it only if formula-to-code reconciliation is
implemented. Remove constant `version='v1'` and `is_active=true`; formula version
belongs to calculation artifacts and run metadata.

### Peer Groups

The composite key `(peer_group_id, ticker)` is correct because it prevents duplicate
membership. The pre-cleanup peer-group content was not correct:

- IDs and names are identical machine slugs.
- `sector` is repeated and does not define membership.
- `description` is NULL for every group.
- `enabled_methods` mixes valuation execution policy into reference membership.
- `is_active` is always true.
- `added_at` is identical migration time, not meaningful business history.

Live membership now contains only:

```text
ref.peer_groups(peer_group_id, display_name)
ref.peer_group_members(peer_group_id, ticker)
```

Method selection belongs in `research.runs.config_snapshot_json` for run-specific
policy, or a dedicated valuation-policy table if reusable policy is required.
The live interim taxonomy is one documented `vn_pharma_listed` group. More
specialized groups should be added only when a documented peer-selection rule
exists.

## Ingest Schema

### Source Registry

`ingest.source_documents` is semantically overloaded. Only six rows represent
annual reports or audited statements; the remaining rows represent API endpoints,
news feeds, price feeds, company endpoints, and regulatory feeds. Consequently,
NULL `issuer`, `fiscal_year`, `local_path`, and `published_at` are often valid for
non-document sources.

Recommended normalized model:

```text
ingest.sources
  source_id, ticker, source_type, source_tier, uri, title,
  publisher, published_at, acquired_at, checksum,
  connector_name, connector_version, metadata_json

ingest.source_documents
  source_id, fiscal_year, fiscal_period, local_path, language, fetch_status
```

Observations should reference `ingest.sources.source_id`. This removes misleading
document terminology and eliminates document-only NULL columns from API sources.

### Observations

All 480 observations have source lineage, but none uses `page_number`,
`table_name`, or `extracted_text`. Those fields are legitimate for document
extraction but sparse for structured APIs. Move them to an optional
`ingest.observation_evidence` subtype when document extraction becomes active.

### Connector Runs

`ingest.connector_runs` is empty despite active connectors. Either wire every
connector invocation into this table or remove it. Keeping an empty audit table
creates false confidence about ingestion observability.

## Fact Schema

All 480 canonical facts link to observations, which is correct. However, every
fact lacks official-document verification. The official verification columns are
therefore not operational.

`fact.price_history` has no values for `adjusted_close`, `traded_value`,
`market_cap`, or `source_doc_id`. Either populate source lineage and supported
market fields or remove unsupported columns from the production table.

## Research, Valuation, And Report Schemas

The live workflow contains 162 imported runs and 315 registered artifacts, but:

- all runs lack snapshots, idempotency keys, completion timestamps, and config snapshots;
- every artifact is typed only as `legacy_artifact`;
- `research.run_steps`, snapshots, and approvals are empty;
- all valuation tables are empty;
- all report metadata, claims, citations, gates, and approval tables are empty.

This is not a NULL-density problem. It is a contract-integration problem.
The pipeline must either write these tables as part of each run or the unused
tables must be removed until the capability exists.

## Audit Schema

Audit tables contain real rows, but several optional fields are unused.
`audit.events.run_id` and `target_id` are NULL for every current event because the
events are schema-level operations. These NULLs are semantically valid.

## Strategic Recommendations

1. Deterministic source-metadata repair was applied live: ticker NULLs decreased
   from 30 to 10, title NULLs from 48 to 0, connector NULLs from 57 to 0, and
   six DAV records were corrected from `vnstock_financial` to `regulatory_notice`.
2. Remove valuation methods and lifecycle booleans from peer membership.
3. Define and seed an explicit peer taxonomy; do not derive peer groups from a free-text segment.
4. Split the general source registry from document-specific metadata.
5. Wire snapshots, valuation metadata, report governance, and connector runs into production before retaining them as authoritative tables.
6. Remove all-null and unsupported columns only after their intended feature is either integrated or formally rejected.

## Iron Triangle Assessment

| Dimension | Current risk | Target outcome |
| --- | --- | --- |
| Scalability | Sparse polymorphic tables and free-text taxonomy increase branching and cleanup cost | Normalize source subtypes and governed peer taxonomy |
| Reliability | Empty governance tables imply controls that are not actually enforced | Make persistence mandatory in pipeline transitions |
| Latency | Excess columns are not the primary latency risk at current scale | Favor semantic correctness; add indexes only for measured query paths |
