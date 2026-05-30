# Data Validation Report — IMP

> Generated: 2026-05-28 08:22:20 UTC  
> Snapshot: `val_a1c1ee1102db60ea`  
> Overall Status: **⚠️ WARN**  
> Valuation Allowed: **YES**

---

## 1. Data Snapshot

| Field | Value |
|---|---|
| Ticker | IMP |
| Snapshot ID | `val_a1c1ee1102db60ea` |
| Created At | 2026-05-28 08:22:20 UTC |
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
| IS_eps_reconciliation_check | 2022FY | ⚠️ WARN | EPS implied shares 75.75M diverges 39.0% from median 124.22M — check EPS or net_income |
| IS_eps_reconciliation_check | 2023FY | ⚠️ WARN | EPS implied shares 82.36M diverges 33.7% from median 124.22M — check EPS or net_income |
| IS_eps_reconciliation_check | 2024FY | ⚠️ WARN | EPS implied shares 166.08M diverges 33.7% from median 124.22M — check EPS or net_income |
| IS_eps_reconciliation_check | 2025FY | ⚠️ WARN | EPS implied shares 176.69M diverges 42.2% from median 124.22M — check EPS or net_income |
| CF_fcf_sign_flip_check | 2023FY | ⚠️ WARN | FCF sign flip between 2022FY and 2023FY (279.25 → -103.06) — verify capex magnitude |
| CF_fcf_sign_flip_check | 2024FY | ⚠️ WARN | FCF sign flip between 2023FY and 2024FY (-103.06 → 119.50) — verify capex magnitude |
| TS_cfo_ni_ratio_check | 2023FY | ⚠️ WARN | CFO/NI ratio -0.13x in 2023FY is outside [0.5x, 2.0x] — verify operating cash flow quality |
| TS_cfo_ni_ratio_check | 2025FY | ⚠️ WARN | CFO/NI ratio 0.16x in 2025FY is outside [0.5x, 2.0x] — verify operating cash flow quality |

---

## 5. Time-series Warnings

| Metric Check | Period | Threshold | Status | Message |
|---|---|---|---|---|
| TS_cfo_ni_ratio_check | 2023FY | — | ⚠️ WARN | CFO/NI ratio -0.13x in 2023FY is outside [0.5x, 2.0x] — verify operating cash flow quality |
| TS_cfo_ni_ratio_check | 2025FY | — | ⚠️ WARN | CFO/NI ratio 0.16x in 2025FY is outside [0.5x, 2.0x] — verify operating cash flow quality |

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
  "ticker": "IMP",
  "snapshot_id": "val_a1c1ee1102db60ea",
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
      "message": "EPS implied shares 75.75M diverges 39.0% from median 124.22M — check EPS or net_income"
    },
    {
      "check_id": "IS_eps_reconciliation_check",
      "message": "EPS implied shares 82.36M diverges 33.7% from median 124.22M — check EPS or net_income"
    },
    {
      "check_id": "IS_eps_reconciliation_check",
      "message": "EPS implied shares 166.08M diverges 33.7% from median 124.22M — check EPS or net_income"
    },
    {
      "check_id": "IS_eps_reconciliation_check",
      "message": "EPS implied shares 176.69M diverges 42.2% from median 124.22M — check EPS or net_income"
    },
    {
      "check_id": "CF_fcf_sign_flip_check",
      "message": "FCF sign flip between 2022FY and 2023FY (279.25 → -103.06) — verify capex magnitude"
    },
    {
      "check_id": "CF_fcf_sign_flip_check",
      "message": "FCF sign flip between 2023FY and 2024FY (-103.06 → 119.50) — verify capex magnitude"
    },
    {
      "check_id": "TS_cfo_ni_ratio_check",
      "message": "CFO/NI ratio -0.13x in 2023FY is outside [0.5x, 2.0x] — verify operating cash flow quality"
    },
    {
      "check_id": "TS_cfo_ni_ratio_check",
      "message": "CFO/NI ratio 0.16x in 2025FY is outside [0.5x, 2.0x] — verify operating cash flow quality"
    }
  ]
}
```
