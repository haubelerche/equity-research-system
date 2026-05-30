# Data Validation Report — DMC

> Generated: 2026-05-28 08:22:23 UTC  
> Snapshot: `val_5e1c9c420fc6da9f`  
> Overall Status: **⚠️ WARN**  
> Valuation Allowed: **YES**

---

## 1. Data Snapshot

| Field | Value |
|---|---|
| Ticker | DMC |
| Snapshot ID | `val_5e1c9c420fc6da9f` |
| Created At | 2026-05-28 08:22:23 UTC |
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
| IS_eps_reconciliation_check | 2022FY | ⚠️ WARN | EPS implied shares 34.73M diverges 15.0% from median 40.85M — check EPS or net_income |
| CF_fcf_sign_flip_check | 2024FY | ⚠️ WARN | FCF sign flip between 2023FY and 2024FY (141.61 → -25.93) — verify capex magnitude |
| CF_fcf_sign_flip_check | 2025FY | ⚠️ WARN | FCF sign flip between 2024FY and 2025FY (-25.93 → 124.66) — verify capex magnitude |
| TS_gross_margin_shift_check | 2023FY | ⚠️ WARN | gross_margin shift 2022FY→2023FY: 28.4% → 21.6% (-6.8 pp) exceeds ±5 pp threshold |
| TS_cfo_ni_ratio_check | 2024FY | ⚠️ WARN | CFO/NI ratio 0.08x in 2024FY is outside [0.5x, 2.0x] — verify operating cash flow quality |

---

## 5. Time-series Warnings

| Metric Check | Period | Threshold | Status | Message |
|---|---|---|---|---|
| TS_gross_margin_shift_check | 2023FY | — | ⚠️ WARN | gross_margin shift 2022FY→2023FY: 28.4% → 21.6% (-6.8 pp) exceeds ±5 pp threshold |
| TS_cfo_ni_ratio_check | 2024FY | — | ⚠️ WARN | CFO/NI ratio 0.08x in 2024FY is outside [0.5x, 2.0x] — verify operating cash flow quality |

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
  "ticker": "DMC",
  "snapshot_id": "val_5e1c9c420fc6da9f",
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
      "message": "EPS implied shares 34.73M diverges 15.0% from median 40.85M — check EPS or net_income"
    },
    {
      "check_id": "CF_fcf_sign_flip_check",
      "message": "FCF sign flip between 2023FY and 2024FY (141.61 → -25.93) — verify capex magnitude"
    },
    {
      "check_id": "CF_fcf_sign_flip_check",
      "message": "FCF sign flip between 2024FY and 2025FY (-25.93 → 124.66) — verify capex magnitude"
    },
    {
      "check_id": "TS_gross_margin_shift_check",
      "message": "gross_margin shift 2022FY→2023FY: 28.4% → 21.6% (-6.8 pp) exceeds ±5 pp threshold"
    },
    {
      "check_id": "TS_cfo_ni_ratio_check",
      "message": "CFO/NI ratio 0.08x in 2024FY is outside [0.5x, 2.0x] — verify operating cash flow quality"
    }
  ]
}
```
