# Data Validation Report — DHG

> Generated: 2026-05-27 08:51:45 UTC  
> Snapshot: `val_2c601064ef1185fe`  
> Overall Status: **⚠️ WARN**  
> Valuation Allowed: **YES**

---

## 1. Data Snapshot

| Field | Value |
|---|---|
| Ticker | DHG |
| Snapshot ID | `val_2c601064ef1185fe` |
| Created At | 2026-05-27 08:51:45 UTC |
| Historical Periods | 2021FY, 2022FY, 2023FY, 2024FY, 2025FY |
| Annual Reports Collected | 5 |
| Periods Missing | None |
| Latest FY | 2025 |
| Data Age (days) | 0 |

---

## 2. Source Coverage

**Source Tier Gate:** ✅ PASS

| Period | Has Tier 1/2 Source | Tier-3 Only | Notes |
|---|---|---|---|
| 2021FY | ✅ Yes | No |  |
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
| IS_net_income_check | 2021FY | ⚠️ WARN | one side missing: cannot fully reconcile net_income |
| CF_fcf_sign_flip_check | 2023FY | ⚠️ WARN | FCF sign flip between 2022FY and 2023FY (667.29 → -246.17) — verify capex magnitude |
| CF_fcf_sign_flip_check | 2024FY | ⚠️ WARN | FCF sign flip between 2023FY and 2024FY (-246.17 → 1228.88) — verify capex magnitude |
| TS_net_margin_shift_check | 2024FY | ⚠️ WARN | net_margin shift 2023FY→2024FY: 20.9% → 15.9% (-5.1 pp) exceeds ±5 pp threshold |
| TS_cfo_ni_ratio_check | 2023FY | ⚠️ WARN | CFO/NI ratio 0.23x in 2023FY is outside [0.5x, 2.0x] — verify operating cash flow quality |

---

## 5. Time-series Warnings

| Metric Check | Period | Threshold | Status | Message |
|---|---|---|---|---|
| TS_net_margin_shift_check | 2024FY | — | ⚠️ WARN | net_margin shift 2023FY→2024FY: 20.9% → 15.9% (-5.1 pp) exceeds ±5 pp threshold |
| TS_cfo_ni_ratio_check | 2023FY | — | ⚠️ WARN | CFO/NI ratio 0.23x in 2023FY is outside [0.5x, 2.0x] — verify operating cash flow quality |

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
  "ticker": "DHG",
  "snapshot_id": "val_2c601064ef1185fe",
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
      "message": "one side missing: cannot fully reconcile net_income"
    },
    {
      "check_id": "CF_fcf_sign_flip_check",
      "message": "FCF sign flip between 2022FY and 2023FY (667.29 → -246.17) — verify capex magnitude"
    },
    {
      "check_id": "CF_fcf_sign_flip_check",
      "message": "FCF sign flip between 2023FY and 2024FY (-246.17 → 1228.88) — verify capex magnitude"
    },
    {
      "check_id": "TS_net_margin_shift_check",
      "message": "net_margin shift 2023FY→2024FY: 20.9% → 15.9% (-5.1 pp) exceeds ±5 pp threshold"
    },
    {
      "check_id": "TS_cfo_ni_ratio_check",
      "message": "CFO/NI ratio 0.23x in 2023FY is outside [0.5x, 2.0x] — verify operating cash flow quality"
    }
  ]
}
```
