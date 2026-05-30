# 05 — Source Metadata Schema

**Date:** 2026-05-22
**Schema:** `dataset/contracts/source_version.schema.json`
**Implementation:** `scripts/db/source_registry.py`

---

## 1. Purpose

Every piece of data ingested into the system must be traceable to a registered source version. This enables:
- Citation validation (reports can cite exact source versions)
- Deduplication (same data re-ingested produces no duplicate rows)
- Audit trail (raw snapshot + checksum proves data integrity)

---

## 2. Source Version Fields

| Field | Type | Description |
|---|---|---|
| `id` | string (sha256) | Deterministic ID: sha256(`source_id|source_uri|checksum`) |
| `source_id` | string | Logical source name (stable across syncs) |
| `source_uri` | string (URI) | Parameterized URI identifying the exact data pull |
| `source_type` | enum | Classification of source (see below) |
| `effective_date` | date | The date the data is valid as-of |
| `published_at` | datetime | When the source published the data |
| `ingested_at` | datetime | When our system wrote this record |
| `checksum` | string (sha256-hex) | SHA-256 of raw payload bytes |
| `connector_version` | string | Version identifier of the connector that produced this |
| `raw_path` | string | Local path to the raw snapshot file |
| `notes` | string | Provider name, fetch parameters, etc. |

---

## 3. Source ID Registry

| `source_id` | Description |
|---|---|
| `bctc_disclosure` | Financial statements from vnstock BCTC feed |
| `price_history` | EOD price history from vnstock quote feed |
| `listing_metadata` | Company profile, shareholders, officers |
| `company_news` | Company news and events from vnstock |
| `hose_disclosure` | HOSE regulatory disclosure feed |
| `bhyt_policy` | BHYT reimbursement policy feed |
| `tender_award` | Public procurement tender awards |
| `dav_regulatory` | DAV drug authority announcements |

---

## 4. Source Type Enum

| value | When to use |
|---|---|
| `financial_statement` | Income statement, balance sheet, cash flow, ratios |
| `market_reference` | Price history, company profile, listing data |
| `catalyst_tender` | Public tender / procurement data |
| `catalyst_policy` | Government or BHYT policy changes |
| `catalyst_regulatory` | Drug approval, recall, suspension |
| `catalyst_company_news` | Company-issued press releases, events |

---

## 5. Source URI Convention

URIs use the `vnstock://` scheme for vnstock-sourced data:

```
vnstock://<provider>/<domain>/<endpoint>/<ticker>?<params>

Examples:
vnstock://kbs/finance/income_statement/DHG?period=quarter
vnstock://vci/finance/balance_sheet/IMP?period=quarter
vnstock://kbs/quote/history/DHG?start=2020-01-01&end=2025-01-01&interval=1D
vnstock://kbs/company/overview/DHG
```

For external feed sources, use `https://` with the canonical URL of the source.

---

## 6. Deduplication Rule

The `id` of a source version is computed as:
```python
sha256(f"{source_id}|{source_uri}|{checksum}")
```

Insert uses `ON CONFLICT (id) DO NOTHING`. If the same data (same content = same checksum) is re-ingested for the same URI, the version record is silently skipped. This means:
- Re-running ingestion is safe and idempotent.
- Only genuinely new data creates new source versions.

The `vnstock_price_connector` has an additional early-exit: it checks the latest registered checksum for a URI before even saving the file, and skips upsert if unchanged.

---

## 7. Raw Snapshot Storage

Every source version has a corresponding raw file on disk:

```text
dataset/raw/bctc/<ticker>/income_statement_quarter.json   ← raw bytes
dataset/raw/bctc/<ticker>/income_statement_quarter.json.sha256  ← checksum sidecar
```

The checksum sidecar allows integrity verification without re-reading the database.

---

## 8. Reliability Tiers (Advisory)

| Tier | Source types | Use in reports |
|---|---|---|
| 1 — Primary | `financial_statement` (KBS/VCI BCTC) | Required for quantitative claims |
| 2 — Secondary | `market_reference` (price, profile) | Market context claims |
| 3 — Supplemental | Catalyst feeds | Qualitative / narrative claims |

Tier 1 sources are required for any valuation computation. Tier 3 sources alone are insufficient to support quantitative claims.
