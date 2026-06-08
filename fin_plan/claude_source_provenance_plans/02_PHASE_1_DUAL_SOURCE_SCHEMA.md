# 02 — Phase 1: Dual-Source Schema

## Goal

Separate data acquisition provenance from final verification provenance.

The system must distinguish:

```text
acquisition_source = where the data was collected from
verification_source = official source used to prove the data in report
```

## Core Design Rule

`vnstock`, `VCI`, `KBS`, and `TCBS` are acquisition sources, not final verification sources.

## Required Schema

Add or update migrations for these tables.

### 1. acquisition_sources

Stores how data entered the system.

Required fields:

```text
id
connector
provider
endpoint_or_method
request_params
retrieved_at
raw_payload_hash
raw_payload_path
status
created_at
```

Examples:

```text
connector = vnstock
provider = VCI
endpoint_or_method = finance.income_statement(period="year")
```

### 2. official_documents

Stores official documents and trusted external sources.

Required fields:

```text
id
ticker
company_name
source_type
source_tier
issuer
title
url
local_path
published_date
fiscal_year
language
file_hash
fetched_at
status
created_at
```

Allowed `source_type` examples:

```text
audited_financial_statement
annual_report
exchange_disclosure
company_ir
regulatory_notice
official_tender
bhyt_policy
news_article
broker_report
```

### 3. verified_financial_facts

Stores financial facts that are allowed to be used in final reports.

Required fields:

```text
id
ticker
fiscal_year
period_type
statement_type
metric_id
value
unit
acquisition_source_id
official_document_id
page_number
table_name
extracted_text
extraction_method
reconciliation_status
confidence
verified_by
verified_at
created_at
```

### 4. fact_reconciliation_results

Stores comparison between provider/API data and official-source data.

Required fields:

```text
id
ticker
fiscal_year
metric_id
api_value
official_value
diff_abs
diff_pct
status
acquisition_source_id
official_document_id
notes
checked_at
```

Allowed `status`:

```text
matched_official
mismatch
missing_official
missing_api
manual_review_required
manual_reviewed
```

## Required Code Updates

1. Add data models or repository methods for all new tables.
2. Ensure report generation does not treat `acquisition_sources` as final citations.
3. Ensure `verified_financial_facts.official_document_id` is mandatory for final-report facts.

## Verification Gate

Create tests:

```text
tests/schema/test_dual_source_schema.py
```

Required test cases:

```text
1. acquisition_source can store vnstock/VCI metadata.
2. official_document can store a BCTC/BCTN/official disclosure.
3. verified_financial_fact requires official_document_id.
4. verified_financial_fact can optionally reference acquisition_source_id.
5. provider-only fact cannot be marked final-verified.
```

Run:

```bash
pytest tests/schema/test_dual_source_schema.py
```

## Output Artifact

Create:

```text
artifacts/audit/dual_source_schema_verification.md
```

Must include:

```text
- Migration files added/changed
- Tables created/changed
- Tests run
- Test result summary
```

## Exit Criteria

Phase 1 passes only if the database can represent acquisition source and verification source separately.
