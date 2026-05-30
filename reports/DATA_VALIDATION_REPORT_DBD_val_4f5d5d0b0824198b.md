# Data Validation Report — DBD

> Generated: 2026-05-28 08:22:29 UTC  
> Snapshot: `val_4f5d5d0b0824198b`  
> Overall Status: **⚠️ WARN**  
> Valuation Allowed: **YES**

---

## 1. Data Snapshot

| Field | Value |
|---|---|
| Ticker | DBD |
| Snapshot ID | `val_4f5d5d0b0824198b` |
| Created At | 2026-05-28 08:22:29 UTC |
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
| IS_eps_reconciliation_check | 2022FY | ⚠️ WARN | EPS implied shares 87.02M diverges 20.0% from median 108.78M — check EPS or net_income |
| TS_cfo_ni_ratio_check | 2025FY | ⚠️ WARN | CFO/NI ratio 2.11x in 2025FY is outside [0.5x, 2.0x] — verify operating cash flow quality |

---

## 5. Time-series Warnings

| Metric Check | Period | Threshold | Status | Message |
|---|---|---|---|---|
| TS_cfo_ni_ratio_check | 2025FY | — | ⚠️ WARN | CFO/NI ratio 2.11x in 2025FY is outside [0.5x, 2.0x] — verify operating cash flow quality |

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
  "ticker": "DBD",
  "snapshot_id": "val_4f5d5d0b0824198b",
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
      "check_id": "IS_eps_reconciliation_check",
      "message": "EPS implied shares 87.02M diverges 20.0% from median 108.78M — check EPS or net_income"
    },
    {
      "check_id": "TS_cfo_ni_ratio_check",
      "message": "CFO/NI ratio 2.11x in 2025FY is outside [0.5x, 2.0x] — verify operating cash flow quality"
    }
  ]
}
```
