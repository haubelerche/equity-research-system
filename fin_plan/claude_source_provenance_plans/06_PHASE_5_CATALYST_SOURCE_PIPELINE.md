# 06 — Phase 5: Catalyst Source Ingestion Pipeline

## Goal

Build a controlled source ingestion pipeline for catalyst/event evidence.

This phase solves the problem:

```text
If report mentions a catalyst, event, regulation, tender, or news item,
the system must know exactly which source document/article it came from.
```

## Important Design Rule

Do not build a broad uncontrolled web crawler.

Build a controlled source pipeline:

```text
source_registry -> fetcher -> raw storage -> text extraction -> event extraction -> ticker mapping -> evidence store
```

## Source Registry

Create:

```text
config/source_registry.yaml
```

Each source must include:

```yaml
name:
source_type:
source_tier:
base_url:
allowed_event_types:
fetch_method:
enabled:
notes:
```

Initial source groups:

```text
exchange_disclosure
company_ir
regulatory_notice
official_tender
bhyt_policy
financial_media
broker_report
```

Initial source examples:

```text
HOSE listed company news
HNX disclosure
UPCoM/HNX company disclosure
Company IR website
Cục Quản lý Dược
BHXH Việt Nam
Hệ thống mạng đấu thầu quốc gia
Vietstock/CafeF/VietnamFinance as secondary context
```

## Required Tables

### source_documents

```text
id
source_name
source_type
source_tier
url
title
publisher
published_date
fetched_at
raw_content_hash
local_path
language
status
```

### catalyst_events

```text
id
ticker
company_name
event_date
event_type
event_title
event_summary
source_document_id
evidence_quote
evidence_span
impact_direction
impact_area
confidence
causality_level
created_at
```

## Event Types

Use this controlled taxonomy:

```text
financial_disclosure
annual_report
earnings_explanation
drug_recall
drug_registration
bidding_result
hospital_tender
bhyt_policy
regulatory_notice
factory_gmp
capacity_expansion
dividend_resolution
management_change
broker_report
media_article
```

## Required Modules

Create:

```text
backend/sources/source_registry.py
backend/sources/document_fetcher.py
backend/sources/document_store.py
backend/catalysts/event_extractor.py
backend/catalysts/ticker_mapper.py
```

## Required Script

Create:

```text
scripts/ingest_catalyst_sources.py
```

Expected usage:

```bash
python scripts/ingest_catalyst_sources.py --ticker DHG --limit 20
```

For MVP, allow manual URL list input:

```text
data/source_seed_urls/DHG_urls.txt
```

## Extraction Rule

A catalyst event is valid only if it has:

```text
event_title
event_date or published_date fallback
event_type
source_document_id
evidence_quote or evidence_span
ticker mapping or sector-level mapping
```

## Verification Gate

Create tests:

```text
tests/sources/test_source_registry.py
tests/sources/test_document_fetcher.py
tests/catalysts/test_event_extraction.py
```

Required test cases:

```text
1. Source registry loads and validates.
2. Disabled source is skipped.
3. Fetched document stores raw_content_hash.
4. Catalyst event requires source_document_id.
5. Catalyst event without evidence_quote/evidence_span is invalid.
6. Unknown event_type is rejected.
7. Ticker mapping must be explicit or marked sector-level.
```

Run:

```bash
pytest tests/sources/test_source_registry.py
pytest tests/sources/test_document_fetcher.py
pytest tests/catalysts/test_event_extraction.py
python scripts/ingest_catalyst_sources.py --ticker DHG --limit 20
```

## Output Artifact

Create:

```text
artifacts/catalysts/DHG_catalyst_source_ingestion.md
```

Must include:

```text
- Sources checked
- Documents fetched
- Documents failed
- Events extracted
- Events rejected
- Events mapped to ticker
- Events marked sector-level
```

## Exit Criteria

Phase 5 passes only if every catalyst/event stored in the system has a concrete source document or article.
