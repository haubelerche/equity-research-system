# Data Lineage Audit — Phase 0

**Date:** 2026-05-30  
**Scope:** Trace 10 representative fact-based claims from a DHG report back to their data origin. Mark exactly where the chain breaks.

---

## The Ideal Chain

```
Raw Source
  → Raw Payload (ingest.raw_payloads, checksum)
    → Parser Run (which connector, version, when)
      → Fact Observation (all candidates per metric)
        → Canonical Fact (selected winner with decision reason)
          → Derived Metric (if applicable)
            → Valuation Artifact (locked, versioned)
              → Report Claim (one object per quantitative sentence)
                → Citation Record (claim → fact → document)
                  → Evaluation Gate Result
```

---

## Claim Traces

### Claim 1: "Doanh thu thuần 2023FY"

| Step | Status | Evidence |
|---|---|---|
| Raw Source | ⚠️ | `ingest.sources` row exists with `source_id = sha256(...)` and `source_uri = "vnstock://..."` |
| Raw Payload | ⚠️ | `ingest.raw_payloads` row exists, but `connector_name` / `connector_version` are stored only in the source row, not the payload row; `ingest.raw_payloads` has no `connector_name` column |
| Parser Run | ❌ | No `parser_runs` table. Cannot identify which parser version extracted the value. |
| Fact Observation | ❌ | No `fact_observations` table. All candidates are collapsed to one row in `fact.financial_facts` via the unique index `uq_fact_current_accepted`. |
| Canonical Fact | ⚠️ | `fact.financial_facts` stores one row per `(ticker, fiscal_year, fiscal_period, line_item_code)` with `validation_status='accepted'`. The `source_id` is present in the row. |
| Source metadata | ⚠️ | The `ingest.sources` row has `source_title`, `source_uri`, and `reliability_tier`. But `reliability_tier` is 1–3 scale (not the 0–4 taxonomy required by the plan). No `source_tier` column. |
| **Normalization gap** | ❌ | `backend/facts/normalizer.py:53` — `table[line_item_code][period] = float(row["value"])`. The `source_id` is discarded here. From this point on, no downstream code carries source metadata. |
| Derived Metric | ❌ | Derived metrics are computed in memory by `compute_derived()` with no lineage to input fact IDs. |
| Valuation Artifact | ⚠️ | `artifacts/valuation/DHG_*_valuation.json` contains numeric outputs but no `input_fact_ids` or source provenance per metric. |
| Report Claim | ❌ | No `report_claims` table. Claims are embedded directly into rendered Markdown text. Not trackable as individual objects. |
| Citation Record | ⚠️ | `_build_citation_map()` in `scripts/generate_report.py:158` builds an in-memory dict keyed by `{ticker}/{year}FY/{metric}`. It includes `source_id` and `source_uri`. BUT: `source_title` is resolved by `_resolve_source_title()` which maps all `financial_statement` / `vnstock_finance` source_types to the hardcoded label `"Báo cáo tài chính (vnstock API)"`. There is no `citation_records` table; the map is only saved as a JSON file. |
| Evaluation Gate | ⚠️ | Gate passes if citation key exists in the map. Does not verify the source document is real, the tier is acceptable, or the value matches. |

**Chain break summary for Claim 1:**
- Step 3 (Parser Run): no table
- Step 4 (Fact Observation): no table; only one winner is retained
- Step 6 (Normalization): `source_id` is discarded at `normalizer.py:53`
- Step 8 (Report Claim): no structured object; embedded in Markdown
- Step 9 (Citation Record): only a JSON file artifact, not a DB record; source title is hardcoded generic label

---

### Claim 2: "Lợi nhuận gộp 2023FY"

Same break pattern as Claim 1. Specific note: `gross_profit.total` may be a directly ingested metric OR derived (`revenue.net - COGS`). If derived, `compute_derived()` in `normalizer.py` computes it in-memory with no record of which input fact IDs were used.

---

### Claim 3: "Dòng tiền hoạt động 2023FY (operating_cash_flow.total)"

Same break pattern. Additional finding: `operating_cash_flow.total` is a direct fact from the cash flow statement. The `source_uri` should be `"vnstock://kbs/finance/cashflow/DHG?period=year"`. However, the citation footnote in the report shows `"Báo cáo tài chính (vnstock API)"` regardless — the specific statement type (income, balance sheet, cash flow) is not reflected in the label.

---

### Claim 4: "EPS cơ bản (eps.basic) 2023FY"

Same break pattern. Additional finding: `eps.basic` may be ingested directly from vnstock or derived as `net_income.parent / shares_outstanding`. If derived, there is no record of which formula was used. The `compute_derived()` function in `normalizer.py` does not compute EPS — meaning `eps.basic` would only be present if explicitly ingested from the API. If the API returns null EPS for a period, the system silently omits it with no warning.

---

### Claim 5: "Tổng tài sản 2024FY (total_assets.ending)"

Same break pattern. Additional finding: the `_ALLOWED_FY_RE` filter in `build_facts.py` already enforces 2021–2025FY at the artifact level. But the DB row for this metric carries `is_current=TRUE` — there is no `canonical_version` field to distinguish "the value used for report v1" from "the value used for report v2". If the value is re-ingested and changes, the old report's citation now points to a different value.

---

### Claim 6: "BHYT policy event in 2023"

| Step | Status | Evidence |
|---|---|---|
| Raw Source | ✅ | `fact.catalyst_events` row with `source_id` FK, `occurred_at`, `event_type`, `materiality_hint` |
| Source metadata | ✅ | `ingest.sources` row for the catalyst connector run |
| Report rendering | ❌ | **Not linked to financial facts or reports.** Catalyst events are stored but `scripts/generate_report.py` does not query `fact.catalyst_events` and render them as context per fiscal year. |
| Causality level | ❌ | No `causality_level` field on `fact.catalyst_events`. All events are treated the same. |

**Chain break for Claim 6:** Events are correctly ingested but completely siloed from the report generation pipeline.

---

### Claim 7: "Vốn chủ sở hữu 2021FY (equity.parent)"

Same break pattern as Claims 1–5. Additional finding: 2021FY data comes from `dataset/golden/financials/DHG.csv` fallback (`_load_golden_fallback()` in `build_facts.py`). The golden source produces a fact row with `source_id = f"golden_csv_{ticker}_{fy}FY"` — this is a synthetic source ID, not registered in `ingest.sources`. **The fact references a source_id that does not exist in the source registry.** This means the source_id FK from `fact.financial_facts` to `ingest.sources` would fail if enforced, but `_load_golden_fallback()` creates the fact dict in memory and never inserts it into the DB — it is merged with DB facts and passed directly to `build_fact_table()`.

---

### Claim 8: "DCF intrinsic value per share"

| Step | Status | Evidence |
|---|---|---|
| Input facts | ⚠️ | Valuation engine reads from `fact_table` (bare floats after normalization). No source lineage. |
| Valuation artifact | ✅ | `artifacts/valuation/DHG_*_valuation.json` exists with `dcf.base.intrinsic_value_per_share_vnd` |
| Formula reproducibility | ⚠️ | The artifact includes `assumptions` block but no `formula_version`, `input_fact_ids`, or `canonical_version`. Cannot definitively reproduce from the artifact alone. |
| Report claim | ❌ | Target price appears in Markdown but is not a `report_claims` DB record. If the valuation artifact is updated, there is no mechanism to detect the discrepancy with the existing report. |

---

### Claim 9: "Sensitivity table — WACC vs terminal growth"

Same break pattern as Claim 8. The sensitivity table is rendered from the valuation artifact. No `derived_metrics` table; sensitivity matrix is in the JSON artifact as nested arrays with no input fact IDs or formula references.

---

### Claim 10: "Revenue growth rate 2022–2024 CAGR"

This is a derived metric computed in the report writer from the `fact_table` floats. There is no record of:
- Which fact IDs were used as inputs
- Which formula computed the CAGR
- Whether a claim object was created

The CAGR is rendered as an inline number in Markdown with no citation tag.

---

## Summary: Where the Chain Breaks

| Break point | File | Line | Impact |
|---|---|---|---|
| **Source ID discarded at normalization** | `backend/facts/normalizer.py` | 53 | All downstream analysis loses source provenance |
| **No `parser_runs` table** | `scripts/db/migrations/002_ingest_schema.sql` | — | Cannot trace which parser/version extracted each value |
| **No `fact_observations` table** | `scripts/db/migrations/003_fact_schema.sql` | — | Multiple sources for same metric → only winner stored; conflict not recorded |
| **Generic source label hardcoded** | `scripts/generate_report.py` | 79–90 | All vnstock facts show "Báo cáo tài chính (vnstock API)" regardless of statement type |
| **Catalyst events not linked to reports** | `scripts/generate_report.py` | entire file | Events stored but never rendered as fiscal-year context |
| **No `causality_level` on events** | `scripts/db/migrations/003_fact_schema.sql` | — | Cannot prevent causal language overstatement |
| **Golden CSV source_id not in registry** | `scripts/build_facts.py` | 116–128 | 2021FY facts have synthetic source IDs that don't exist in `ingest.sources` |
| **No `report_claims` table** | — | — | Claims are not trackable objects; cannot validate claim→fact mapping |
| **No `citation_records` table** | — | — | Citation map is a JSON file only; not queryable for gate auditing |
| **No `canonical_version` / `run_id` on valuation** | `scripts/run_valuation.py` | — | Cannot detect if a report was generated from an older valuation artifact |
| **`reliability_tier` uses 1–3 scale, plan needs 0–4** | `scripts/db/migrations/002_ingest_schema.sql` | 28 | Current Tier 1 ≠ plan's Tier 0 (audited filings) |

---

## Key Finding

The lineage chain currently works for steps 1–2 (raw source registration + payload storage) and partially for step 5 (one canonical value per metric/period in the DB). **Steps 3, 4, 6, 7, 8, 9, and 10 are either missing or broken.** The most critical break is at `normalizer.py:53` because it permanently severs the source connection for all downstream processing.
