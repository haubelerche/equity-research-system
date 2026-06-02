# 04 — Canonical Fact Schema

**Date:** 2026-05-22
**Source of truth:** `config/dataset/taxonomy/financial_taxonomy_vn_pharma.yaml`
**JSON Schema:** `config/dataset/contracts/financial_fact.schema.json`

---

## 1. Design Principles

- Every ingested financial number becomes a `FinancialFact` row.
- The `taxonomy_key` field maps raw label strings to a canonical, stable identifier.
- Alias matching is done via `_build_alias_map()` in `vnstock_finance_connector.py`.
- Facts from different sources for the same `(ticker, fiscal_year, fiscal_period, taxonomy_key)` are stored separately by `source_version_id` — the most recent accepted value is used in reports.

---

## 2. Taxonomy Keys (MVP Required Set)

These keys are required for all 5 MVP tickers per `config/dataset/mvp/mvp5_scope.yaml`.

### Income Statement

| taxonomy_key | Vietnamese label | Unit | aliases |
|---|---|---|---|
| `revenue.net` | Doanh thu thuan | vnd_bn | doanh_thu_thuan, net_revenue, sales_revenue |
| `cogs.total` | Gia von hang ban | vnd_bn | gia_von_hang_ban, cost_of_goods_sold |
| `gross_profit.total` | Loi nhuan gop | vnd_bn | loi_nhuan_gop |
| `sga.total` | Chi phi ban hang va QLDN | vnd_bn | chi_phi_ban_hang, chi_phi_qldn |
| `ebit.total` | Loi nhuan truoc lai vay va thue | vnd_bn | ebit, operating_profit |
| `ebitda.total` | EBITDA | vnd_bn | ebitda |
| `net_income.parent` | Loi nhuan sau thue co dong cong ty me | vnd_bn | lnst_co_dong_me, net_income, npat |
| `eps.basic` | EPS co ban | vnd | eps, eps_co_ban |

### Balance Sheet

| taxonomy_key | Vietnamese label | Unit |
|---|---|---|
| `cash_and_equivalents.ending` | Tien va tuong duong tien cuoi ky | vnd_bn |
| `inventory.ending` | Hang ton kho | vnd_bn |
| `total_debt.ending` | Tong no vay | vnd_bn |
| `equity.parent` | Von chu so huu cong ty me | vnd_bn |

### Cash Flow Statement

| taxonomy_key | Vietnamese label | Unit |
|---|---|---|
| `capex.total` | Chi tieu von | vnd_bn |
| `operating_cash_flow.total` | Luu chuyen tien thuan tu HDKD | vnd_bn |

### Derived (Computed, Not Stored as Facts)

These are computed by the valuation module from stored facts — they are not stored as raw `financial_facts` rows.

| Key | Formula | Unit |
|---|---|---|
| `free_cash_flow.total` | `operating_cash_flow.total - capex.total` | vnd_bn |
| `gross_margin` | `gross_profit.total / revenue.net` | percent |
| `ebitda_margin` | `ebitda.total / revenue.net` | percent |
| `net_margin` | `net_income.parent / revenue.net` | percent |
| `debt_to_equity` | `total_debt.ending / equity.parent` | ratio |

---

## 3. Fiscal Period Encoding

| Code | Meaning |
|---|---|
| `FY` | Full fiscal year |
| `Q1` | January–March |
| `Q2` | April–June |
| `Q3` | July–September |
| `Q4` | October–December |

vnstock returns quarterly data by default. FY rows are the annual summation/snapshot, provided by vnstock as a separate period column.

---

## 4. Validation Status Lifecycle

```text
raw label ingested
  → alias matched in taxonomy → FinancialFact created
    → DQF check:
        missing required fields   → rejected    (confidence: 0.0)
        |value| > 1 trillion VND  → needs_review (confidence: 0.5)
        all ok                    → accepted    (confidence: 0.98)
```

Facts with status `rejected` are still stored (for audit) but excluded from valuation.

---

## 5. Alias Mapping Logic

1. Raw label from vnstock is slugified: lowercased, non-alphanumeric replaced with `_`, consecutive underscores collapsed.
2. The slugified label is looked up in the alias map built from the taxonomy YAML.
3. If no match → the row is silently skipped (not ingested as a fact, raw data still saved).
4. If matched → fact is created with the canonical `taxonomy_key`.

This means: only taxonomy-registered metrics are stored as canonical facts. New metrics must be added to the taxonomy file first.

---

## 6. Adding New Taxonomy Keys

Edit `config/dataset/taxonomy/financial_taxonomy_vn_pharma.yaml`:

```yaml
taxonomy:
  new_metric.key:
    label_vi: Ten chỉ số tiếng Việt
    statement: income_statement  # or balance_sheet, cash_flow, derived
    unit: vnd_bn                 # or vnd, ratio, percent, shares
    aliases:
      - alternative_name
      - another_alias
```

Then re-run ingestion — the new key will be picked up on the next sync.
