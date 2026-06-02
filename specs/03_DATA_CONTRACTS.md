# 03 — Data Contracts

**Date:** 2026-05-22
**Status:** Active

All contracts are enforced at ingestion time via `backend/dataset/dqf.py`.
JSON Schema files live in `config/dataset/contracts/`.

---

## 1. Entities and Their Contracts

### 1.1 Ticker Universe

**Source:** `config/dataset/universe/pharma_vn_universe.csv`

| Field | Type | Required | Notes |
|---|---|---|---|
| `ticker` | string | Yes | 2–10 chars, uppercase |
| `company_name` | string | Yes | Full Vietnamese name |
| `exchange` | string | Yes | e.g. HOSE, HNX |
| `segment` | string | Yes | `pharma` or `healthcare_services` |
| `is_mvp` | boolean | Yes | `true` for DHG, IMP, DMC, TRA, DBD |
| `notes` | string | No | Free text |

**MVP tickers:** DHG, IMP, DMC, TRA, DBD (as per `config/dataset/mvp/mvp5_scope.yaml`)

---

### 1.2 Source Version

**Schema:** `config/dataset/contracts/source_version.schema.json`
**Store:** `source_versions` Postgres table via `SourceRegistry`

| Field | Type | Required | Notes |
|---|---|---|---|
| `source_id` | string | Yes | Logical source name, e.g. `bctc_disclosure`, `price_history` |
| `source_uri` | string (URI) | Yes | e.g. `vnstock://kbs/finance/income_statement/DHG?period=quarter` |
| `source_type` | enum | Yes | `financial_statement`, `market_reference`, `catalyst_tender`, `catalyst_policy`, `catalyst_regulatory`, `catalyst_company_news` |
| `effective_date` | date | No | Date the data is valid as-of |
| `published_at` | datetime | Yes | When source published the data |
| `ingested_at` | datetime | Yes | When our system ingested it |
| `checksum` | string (sha256) | Yes | SHA-256 hex of raw payload bytes |
| `connector_version` | string | Yes | e.g. `vnstock_finance_connector_v1` |
| `ingestion_run_id` | string | No | Links to ingestion run |
| `notes` | string | No | Provider, parameters, etc. |

**Deduplication rule:** A source version with an identical `(source_id, source_uri, checksum)` triple is a duplicate and is silently skipped on `ON CONFLICT DO NOTHING`.

---

### 1.3 Raw Payload

Raw data is saved to disk before normalization.

**Storage path pattern:**
```text
data/raw/bctc/<ticker>/<statement>_quarter.json        # financial statements
data/raw/market/<date>/<ticker>_quote_history.json     # price history
data/raw/market/<date>/<ticker>_<endpoint>.json        # company profile/news
```

Each raw file has a companion `.sha256` sidecar.

---

### 1.4 Canonical Financial Fact

**Schema:** `config/dataset/contracts/financial_fact.schema.json`
**Store:** `financial_facts` Postgres table via `PostgresFactStore`

| Field | Type | Required | Notes |
|---|---|---|---|
| `company_ticker` | string | Yes | Uppercase ticker |
| `fiscal_year` | integer | Yes | 2000–2100 |
| `fiscal_period` | enum | Yes | `FY`, `Q1`, `Q2`, `Q3`, `Q4` |
| `taxonomy_key` | string | Yes | Matches key in `financial_taxonomy_vn_pharma.yaml` |
| `value` | number | Yes | Numeric value |
| `unit` | enum | Yes | `vnd`, `vnd_bn`, `ratio`, `percent`, `shares` |
| `currency` | enum | Yes | Always `VND` |
| `source_version_id` | string | Yes | FK to `source_versions` |
| `parser_version` | string | Yes | e.g. `vnstock_financial_parser_v1` |
| `validation_status` | enum | Yes | `accepted`, `accepted_with_warning`, `needs_review`, `rejected` |
| `confidence` | float [0,1] | Yes | DQF-assigned confidence |
| `effective_date` | date | No | |
| `ingested_at` | datetime | Yes | |

**Upsert key:** `(company_ticker, fiscal_year, fiscal_period, taxonomy_key, source_version_id)`

**DQF rules:**
- Missing required fields → `rejected`, confidence 0.0
- `abs(value) > 1_000_000_000_000` → `needs_review`, confidence 0.5
- All fields present and value in range → `accepted`, confidence 0.98

---

### 1.5 Price Row

**Store:** `price_history` Postgres table

| Field | Type | Required |
|---|---|---|
| `ticker` | string | Yes |
| `date` | date | Yes |
| `open` | float | No |
| `high` | float | No |
| `low` | float | No |
| `close` | float | No |
| `volume` | integer | No |
| `value` | float | No |
| `source_version_id` | string | No |
| `ingested_at` | datetime | Yes |

**Upsert key:** `(ticker, date)`

---

### 1.6 Company Profile

**Store:** `company_profiles` Postgres table

| Field | Type | Required |
|---|---|---|
| `ticker` | string | Yes |
| `company_name` | string | No |
| `exchange` | string | No |
| `segment` | string | No |
| `overview_json` | jsonb | No |
| `shareholders_json` | jsonb | No |
| `officers_json` | jsonb | No |
| `last_synced_at` | datetime | Yes |

**Upsert key:** `ticker`

---

### 1.7 Catalyst Event

**Schema:** `config/dataset/contracts/catalyst_event.schema.json`
**Store:** `catalyst_events` Postgres table

| Field | Type | Required | Notes |
|---|---|---|---|
| `event_id` | string | Yes | SHA-256 of `ticker|title|occurred_at|source_url` |
| `event_type` | string | Yes | e.g. `company_announcement`, `regulatory_recall`, `tender_award` |
| `title` | string | Yes | |
| `summary` | string | No | Truncated to 3000 chars |
| `occurred_at` | datetime | Yes | |
| `effective_date` | date | No | |
| `company_ticker` | string | No | Null for market-wide events |
| `materiality_hint` | enum | No | `high`, `medium`, `low` |
| `source_url` | string | Yes | |
| `source_version_id` | string | Yes | |
| `confidence` | float [0,1] | No | |
| `validation_status` | enum | Yes | |
| `ingested_at` | datetime | Yes | |

**Upsert key:** `event_id`

---

### 1.8 Document Chunk

**Schema:** `config/dataset/contracts/document_chunk.schema.json`
**Store:** Milvus vector collection (Phase 5+)

| Field | Type | Required | Notes |
|---|---|---|---|
| `chunk_id` | string | Yes | |
| `source_version_id` | string | Yes | FK to `source_versions` |
| `chunk_type` | enum | Yes | `section`, `table`, `note`, `regulatory_clause` |
| `page` | integer | No | |
| `section_name` | string | No | |
| `table_id` | string | No | |
| `content` | string | Yes | |
| `content_hash` | string (sha256) | Yes | |
| `embedding_model` | string | Yes | |
| `language` | enum | Yes | `vi` or `en` |
| `ingested_at` | datetime | Yes | |

---

### 1.9 Citation

**Schema:** `config/dataset/contracts/citation.schema.json`

| Field | Type | Required | Notes |
|---|---|---|---|
| `citation_id` | string | Yes | |
| `run_id` | string | Yes | |
| `claim_id` | string | Yes | |
| `claim_type` | enum | Yes | `quantitative` or `qualitative` |
| `chunk_id` | string | Yes | FK to document chunk |
| `source_version_id` | string | Yes | |
| `page` | integer | No | |
| `excerpt` | string | No | |
| `grounding_status` | enum | Yes | `pass`, `fail`, `manual_review` |
| `confidence` | float [0,1] | Yes | |

---

## 2. Data Flow Dependencies

```text
source_versions
  ├── financial_facts          (FK: source_version_id)
  ├── price_history            (FK: source_version_id)
  ├── catalyst_events          (FK: source_version_id)
  └── document_chunks          (FK: source_version_id)
        └── citations          (FK: chunk_id, source_version_id)
```

Every fact or chunk must trace back to a registered source version.
No orphaned facts are permitted.

---

## 3. Contract Validation

Contracts are validated at ingestion time by `backend/dataset/dqf.py`.

To validate a payload against a contract schema:
```python
from backend.dataset.dqf import validate_financial_fact, validate_catalyst_event
result = validate_financial_fact(payload)
# result.status: "accepted" | "needs_review" | "rejected"
```

Full contract schema validation:
```bash
python backend/dataset/validate_contracts.py
```
