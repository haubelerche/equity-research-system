# Data Validation Report — TRA

> Generated: 2026-05-28 08:22:27 UTC  
> Snapshot: `val_70655ea9168fb1dd`  
> Overall Status: **⚠️ WARN**  
> Valuation Allowed: **YES**

---

## 1. Data Snapshot

| Field | Value |
|---|---|
| Ticker | TRA |
| Snapshot ID | `val_70655ea9168fb1dd` |
| Created At | 2026-05-28 08:22:27 UTC |
| Historical Periods | 2022FY, 2023FY, 2024FY, 2025FY |
| Annual Reports Collected | 4 |
| Periods Missing | 2021FY |
| Latest FY | 2025 |
| Data Age (days) | 2 |

---

## 2. Source Coverage

**Source Tier Gate:** ✅ PASS

| Period | Has Tier 1/2 Source | Tier-3 Only | Notes |
|---|---|---|---|
| 2022FY | ✅ Yes | No |  |
| 2023FY | ✅ Yes | No |  |
| 2024FY | ✅ Yes | No |  |
| 2025FY | ✅ Yes | No |  |

---

## 3. Critical Fact Validation

**Source Validation Gate:** ✅ PASS

All core fact keys have `validation_status = accepted`.

---

## 4. Accounting Reconciliation

**Reconciliation Gate:** ⚠️ WARN

| Check | Period | Status | Message |
|---|---|---|---|
| IS_net_income_check | 2022FY | ⚠️ WARN | net_income mismatch likely explained by minority interest (implied NCI=24.37): expected 293.52, actual 269.14, diff -24.37 |
| IS_net_income_check | 2023FY | ⚠️ WARN | net_income mismatch likely explained by minority interest (implied NCI=22.02): expected 285.27, actual 263.25, diff -22.02 |
| IS_net_income_check | 2024FY | ⚠️ WARN | net_income mismatch likely explained by minority interest (implied NCI=18.34): expected 257.36, actual 239.02, diff -18.34 |
| IS_net_income_check | 2025FY | ⚠️ WARN | net_income mismatch likely explained by minority interest (implied NCI=28.71): expected 278.37, actual 249.65, diff -28.71 |

---

## 5. Time-series Warnings

No time-series anomalies detected.

---

## 6. Market Data Alignment

No market data alignment issues detected.

---

## 7. Valuation Readiness Gate

| Field | Value |
|---|---|
| Overall Status | **⚠️ WARN** |
| Valuation Allowed | **✅ YES** |
| Blocked by DQ Gate | False |
| Blocked by Reconciliation | False |
| Analyst Review Required | Recommended |

---

## 8. Machine-Readable Summary

```json
{
  "ticker": "TRA",
  "snapshot_id": "val_70655ea9168fb1dd",
  "validation_status": "VALUATION_READY",
  "valuation_allowed": true,
  "allowed_output": "full_pipeline",
  "coverage_gate": "pass",
  "core_keys_gate": "pass",
  "source_validation_gate": "pass",
  "source_tier_coverage_status": "pass",
  "reconciliation_gate": "warn",
  "valuation_gate": "pass",
  "critical_failures": [],
  "high_warnings": [
    {
      "check_id": "IS_net_income_check",
      "message": "net_income mismatch likely explained by minority interest (implied NCI=24.37): expected 293.52, actual 269.14, diff -24.37"
    },
    {
      "check_id": "IS_net_income_check",
      "message": "net_income mismatch likely explained by minority interest (implied NCI=22.02): expected 285.27, actual 263.25, diff -22.02"
    },
    {
      "check_id": "IS_net_income_check",
      "message": "net_income mismatch likely explained by minority interest (implied NCI=18.34): expected 257.36, actual 239.02, diff -18.34"
    },
    {
      "check_id": "IS_net_income_check",
      "message": "net_income mismatch likely explained by minority interest (implied NCI=28.71): expected 278.37, actual 249.65, diff -28.71"
    }
  ]
}
```
