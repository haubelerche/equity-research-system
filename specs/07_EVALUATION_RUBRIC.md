# 07 — Evaluation Rubric

**Date:** 2026-05-22
**Status:** Draft — update when evaluation harness is implemented (Phase 7)

---

## 1. Purpose

Every report must pass evaluation gates before it can be exported. The evaluation harness blocks export on critical failures. Human review may still override a block, but the block must be explicitly acknowledged.

---

## 2. Evaluation Gates

### Gate 1 — Numeric Consistency (CRITICAL)

**Check:** Every numeric value in the report body matches the corresponding canonical fact or valuation artifact value (within rounding tolerance).

**Pass condition:** All checked numbers match within ±0.5% or ±0.01 unit.

**Critical failure:** Any report number differs from its source fact by more than the tolerance without an explicit explanation note in the report.

**Automated:** Yes — compare extracted numbers against `financial_facts` and `valuation_artifact` JSON.

---

### Gate 2 — Citation Coverage (CRITICAL)

**Check:** Every quantitative claim in the report has an attached citation that resolves to either:
- a `financial_facts` row with `validation_status = accepted`, or
- a `document_chunk` with `grounding_status = pass`.

**Pass condition:** ≥ 90% of quantitative claims have valid citations.

**Critical failure:** Any uncited quantitative claim in sections 3.4 (Financial Performance) or 3.5 (Valuation).

**Automated:** Yes — regex extraction of claim patterns + citation lookup.

---

### Gate 3 — Citation Validity (CRITICAL)

**Check:** Each citation actually supports the claim it is attached to (semantic match).

**Pass condition:** Every citation excerpt contains or directly implies the claimed value.

**Critical failure:** A citation is attached but the cited source does not mention the claimed value.

**Automated:** Partially — deterministic check for numeric match; LLM-assisted for qualitative claims.

---

### Gate 4 — Stale Data Detection (CRITICAL)

**Check:** No financial fact used in the report is older than 18 months from the report generation date.

**Pass condition:** All `financial_facts` rows used have `effective_date` or `ingested_at` within 18 months.

**Warning (non-blocking):** Facts between 12–18 months old trigger a staleness warning in the report.

**Critical failure:** A fact older than 18 months is presented as current without a staleness disclaimer.

**Automated:** Yes — datetime comparison against `financial_facts.ingested_at`.

---

### Gate 5 — Valuation Reproducibility (CRITICAL)

**Check:** The valuation output (DCF target price, multiples, sensitivity table) can be exactly reproduced by running `scripts/run_valuation.py --ticker <TICKER>` with the assumptions stored in the `valuation_artifact`.

**Pass condition:** Recomputed values match artifact values within ±0.1%.

**Critical failure:** Valuation output cannot be reproduced from stored assumptions and input facts.

**Automated:** Yes — re-run valuation code with frozen assumptions, compare outputs.

---

### Gate 6 — Unsupported Recommendation Detection (CRITICAL)

**Check:** The report does not make absolute investment recommendations or imply guaranteed returns.

**Prohibited patterns:**
- "will definitely", "guaranteed", "certain to"
- Strong buy/sell without explicit uncertainty qualifier
- Price target stated as fact, not estimate

**Pass condition:** No prohibited patterns detected.

**Critical failure:** Any prohibited pattern found in the conclusion or executive summary.

**Automated:** Regex + LLM-assisted check.

---

## 3. Scoring Summary

| Gate | Type | Automatable | Blocks Export |
|---|---|---|---|
| 1 — Numeric Consistency | Deterministic | Yes | Yes |
| 2 — Citation Coverage | Deterministic | Yes | Yes |
| 3 — Citation Validity | Mixed | Partial | Yes |
| 4 — Stale Data | Deterministic | Yes | Yes |
| 5 — Valuation Reproducibility | Deterministic | Yes | Yes |
| 6 — Unsupported Recommendation | Mixed | Partial | Yes |

---

## 4. Evaluation Score Format

```json
{
  "report_id": "...",
  "ticker": "DHG",
  "evaluated_at": "2026-05-22T10:00:00Z",
  "overall_status": "pass" | "fail" | "warn",
  "gates": {
    "numeric_consistency": {
      "status": "pass",
      "checked": 12,
      "failed": 0,
      "details": []
    },
    "citation_coverage": {
      "status": "pass",
      "quantitative_claims": 18,
      "cited": 17,
      "coverage_ratio": 0.944,
      "details": ["Claim at line 42 missing citation"]
    },
    "citation_validity": {
      "status": "pass",
      "citations_checked": 17,
      "invalid": 0
    },
    "stale_data": {
      "status": "warn",
      "stale_facts": 2,
      "oldest_fact_date": "2024-09-30",
      "details": ["eps.basic/DHG/2023/Q3 is 20 months old"]
    },
    "valuation_reproducibility": {
      "status": "pass",
      "max_deviation_pct": 0.03
    },
    "unsupported_recommendation": {
      "status": "pass",
      "flagged_phrases": []
    }
  },
  "export_blocked": false,
  "block_reasons": []
}
```

---

## 5. Human Override

A human reviewer may override a critical failure gate with:
- explicit written justification in `feedback_patch`
- the report's `approval_status` updated to `approved_with_override`

The override is logged to the `approval_records` table and included in Appendix D.

---

## 6. Minimum Acceptable Report Thresholds

For a report to be approved without override:

| Metric | Threshold |
|---|---|
| Citation coverage | ≥ 90% |
| Numeric consistency failures | 0 |
| Stale facts (>18 months) | 0 (older than 12 months triggers warning only) |
| Valuation deviation | < 0.1% |
| Prohibited recommendation phrases | 0 |
