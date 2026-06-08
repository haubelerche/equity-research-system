# Audit C: Source-to-Metric Audit
**Date:** 2026-06-07
**Scope:** How raw data enters the system, is normalized, and becomes a canonical fact

---

## C1. FactEntry Dataclass

**File:** `backend/facts/normalizer.py:33-56`

```python
@dataclass
class FactEntry:
    value: float                      # canonical numeric value
    fact_id: str | None               # database fact ID
    source_id: str | None             # source identifier (None for derived metrics)
    source_uri: str                   # document URL
    source_title: str                 # document title
    source_tier: int | None           # 0=audited, 1=verified manual, 2=semi-official, 3=API
    reliability_tier: int | None      # legacy field (same concept as source_tier)
    confidence: float | None          # 0.0–1.0 confidence score
    connector_version: str            # ingestion version string
    ingested_at: datetime | None      # ingestion timestamp

FactTable = dict[str, dict[str, FactEntry]]
# Structure: { line_item_code → { period_key → FactEntry } }
# Example:  { "revenue.net" → { "2025FY" → FactEntry(value=1865.38, ...) } }
```

---

## C2. Source Tier Hierarchy

**File:** `backend/facts/normalizer.py:113`

| Tier | Authority | Example sources |
|------|-----------|-----------------|
| 0 | Audited financial statements (official PDF) | BCTC kiểm toán, HoSE filings |
| 1 | Verified manual upload | Analyst-verified golden CSV |
| 2 | Semi-official / regulatory | CBTT, company announcements |
| 3 | API data (third-party) | vnstock, market data providers |

**Selection rule** (when multiple sources exist for same metric+period):
1. Lowest source_tier wins (Tier 0 overrides Tier 3)
2. Tie-break: highest confidence
3. Final tie-break: latest `ingested_at`

---

## C3. Normalization Flow

**File:** `backend/facts/normalizer.py:132` + `backend/facts/metric_metadata.py`

```
raw_value (from CSV/API)
  → validate_and_normalize(line_item_code, raw_value, raw_unit)
  → METRIC_METADATA lookup  (metric_metadata.py:159)
  → semantic type identified
  → unit multiplier applied
  → FactEntry created with full provenance
```

**Semantic types and canonical units:**

| Semantic Type | Canonical Unit | Example multiplier |
|--------------|---------------|-------------------|
| `MONETARY` | absolute VND | vnd_bn → × 1_000_000_000.0 |
| `PER_SHARE` | VND/share | nghìn đồng/cp → × 1_000.0 |
| `SHARE_COUNT` | absolute shares | triệu cp → × 1_000_000.0 |
| `PERCENTAGE` | decimal ratio | 18.5% → 0.185 |
| `RATIO` | dimensionless | pass-through |
| `MULTIPLE` | dimensionless multiplier | pass-through |
| `DAYS` | integer | pass-through |
| `OPERATIONAL` | pass-through | pass-through |

---

## C4. DBD Golden CSV — Verified Metrics (2025FY)

**File:** `config/dataset/golden/financials/DBD.csv`
**Provenance:** `config/dataset/golden/financials/DBD_golden_provenance.json`
**Verified by:** haubelerche  |  **Verification date:** 2026-06-03  |  **Source tier: 0**

| canonical_key | value | unit | confidence | notes |
|--------------|-------|------|-----------|-------|
| revenue.net | 1865.380 | vnd_bn | 0.95 | |
| cogs.total | -981.001 | vnd_bn | 0.95 | negative (cost) |
| gross_profit.total | 884.379 | vnd_bn | 0.95 | |
| selling_expense.total | -418.308 | vnd_bn | 0.95 | negative (expense) |
| admin_expense.total | -139.794 | vnd_bn | 0.95 | negative (expense) |
| ebit.total | 349.128 | vnd_bn | 0.95 | |
| profit_before_tax.total | 346.082 | vnd_bn | 0.95 | |
| net_income.parent | 291.940 | vnd_bn | 0.95 | |
| cash_and_equivalents.ending | 202.784 | vnd_bn | 0.95 | |
| short_term_investments.ending | 409.201 | vnd_bn | 0.95 | |
| short_term_debt.ending | 43.215 | vnd_bn | 0.95 | |
| long_term_debt.ending | 132.000 | vnd_bn | 0.95 | |
| equity.parent | 1736.000 | vnd_bn | 0.85 | |
| shares_outstanding.ending | 94,400,000 | shares | 0.85 | 94.4M absolute |
| dividends_per_share.cash | 2000 | vnd | 0.90 | |

Total debt = 43.215 + 132.000 = **175.215 VND bn**
Net cash = 202.784 + 409.201 − 175.215 = **436.770 VND bn**

---

## C5. Confidence Filtering

| Rule | Location | Threshold |
|------|---------|----------|
| Golden CSV minimum confidence | normalizer.py:452 | < 0.80 → rejected at load time |
| Multi-source conflict resolution | normalizer.py:113 | Lowest tier + highest confidence |
| FCFE publishability | debt_schedule.py:118-138 | All forecast rows must be confidence = "high" |
| Data quality gate | approval_gate.py | data_quality_passed must be True before valuation |

---

## C6. Sign Convention (DBD CSV)

- **Revenue, assets, equity:** positive
- **COGS, expenses (SG&A):** negative — stored as cost
- **Debt:** positive — absolute amount owed
- **Net income, gross profit, EBIT:** positive

Normalizer.py does NOT modify signs — trusts source data convention.
CAPEX is forced to positive via `abs()` in fcff.py:236 and fcfe.py.

---

## C7. Data Connectors

**Directory:** `scripts/connectors/`

| Connector | Source | CONNECTOR_VERSION |
|-----------|--------|-----------------|
| `vnstock_finance_connector.py` | vnstock API (Tier 3) | vn_finance_v2 |
| `vnstock_price_connector.py` | vnstock market prices | — |
| `vnstock_company_connector.py` | company fundamentals | — |
| `manual_upload_connector.py` | analyst-provided files | — |
| `catalyst_*.py` | event-based sources | — |

`vnstock_finance_connector.py` uses `_VND_BN_DIVISOR = 1_000_000_000.0` at ingestion.
MVP coverage: FY2021–FY2025.

---

## C8. LLM Barrier (Enforced)

All 19 analytics modules (`backend/analytics/`) explicitly state:
> "All arithmetic is deterministic Python — no LLM involvement."

LLM output is only used for draft narrative text. Numbers in reports come exclusively from
locked artifacts produced by deterministic Python code. This is verified across:
- `approval_gate.py`, `blend.py`, `fcff.py`, `fcfe.py`, `forecasting.py`, `ratios.py`
- And 13 additional modules
