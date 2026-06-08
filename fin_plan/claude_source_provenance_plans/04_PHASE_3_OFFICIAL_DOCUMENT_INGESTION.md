# 04 — Phase 3: Official Document Ingestion for Financial Facts

## Goal

Build a minimal official-document ingestion pipeline so financial facts can cite BCTC/BCTN/company/exchange sources instead of vnstock/provider labels.

## MVP Scope

Start with DHG only.

Target fiscal years:

```text
2021
2022
2023
2024
2025
```

Target source types:

```text
audited_financial_statement
annual_report
exchange_disclosure
company_ir
```

## Required Directory Structure

Create:

```text
data/official_documents/DHG/
  2021/
    metadata.json
    extracted_facts.csv
    source_document.pdf
  2022/
    metadata.json
    extracted_facts.csv
    source_document.pdf
  2023/
    metadata.json
    extracted_facts.csv
    source_document.pdf
  2024/
    metadata.json
    extracted_facts.csv
    source_document.pdf
  2025/
    metadata.json
    extracted_facts.csv
    source_document.pdf
```

If official files cannot be downloaded automatically, support manual placement first.

## metadata.json Schema

Each `metadata.json` must contain:

```json
{
  "ticker": "DHG",
  "company_name": "",
  "source_type": "",
  "issuer": "",
  "title": "",
  "url": "",
  "local_path": "",
  "published_date": "",
  "fiscal_year": 2025,
  "language": "vi",
  "file_hash": ""
}
```

## extracted_facts.csv Schema

Each file must contain:

```text
ticker
fiscal_year
period_type
statement_type
metric_id
value
unit
document_title
page_number
table_name
extracted_text
extraction_method
verified_by
verified_at
```

## Minimum Metrics

Extract at least:

```text
revenue_net
gross_profit
operating_profit
profit_before_tax
net_income
eps
total_assets
total_equity
short_term_debt
long_term_debt
operating_cash_flow
capex
```

## Required Code Updates

Add ingestion script:

```text
scripts/ingest_official_documents.py
```

Expected usage:

```bash
python scripts/ingest_official_documents.py --ticker DHG --from-year 2021 --to-year 2025
```

The script must:

```text
1. Read metadata.json.
2. Validate file hash.
3. Load extracted_facts.csv.
4. Insert official_documents records.
5. Insert official-source financial facts.
6. Produce ingestion summary artifact.
```

## Verification Gate

Create tests:

```text
tests/official_sources/test_official_document_ingestion.py
```

Required test cases:

```text
1. metadata.json is valid.
2. source document file exists.
3. file_hash is computed and stored.
4. extracted_facts.csv has required columns.
5. each extracted fact has document title, table name, and metric_id.
6. DHG has at least the minimum metrics for available years.
```

Run:

```bash
pytest tests/official_sources/test_official_document_ingestion.py
python scripts/ingest_official_documents.py --ticker DHG --from-year 2021 --to-year 2025
```

## Output Artifact

Create:

```text
artifacts/official_sources/DHG_official_document_ingestion.md
```

Must include:

```text
- Number of documents ingested
- Number of official facts extracted
- Missing years
- Missing metrics
- File hashes
- Failed records
```

## Exit Criteria

Phase 3 passes only if DHG has official-source facts that can replace API/provider citations for core financial metrics.
