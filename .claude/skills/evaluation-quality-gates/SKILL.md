---
name: evaluation-quality-gates
description: Use when working on offline evaluation, report quality gates, citation coverage, numeric consistency checks, eval datasets, regression baselines, or red-team tests. Enforces deterministic checks before LLM judging and machine-readable eval output.
---

# Evaluation and Quality Gates

## When to use

- Modifying `scripts/evaluate_report.py`.
- Adding a new quality gate or changing a gate threshold.
- Adding eval fixtures or golden datasets under `config/dataset/golden/`.
- Running regression evaluation after changes to parser, prompt, retrieval, or model.
- Debugging a gate `FAIL` or `WARN` result.
- Designing a new eval for hallucination, citation coverage, or numeric consistency.

---

## Minimum Context to Read

```
scripts/evaluate_report.py
backend/dataops/quality_report.py
backend/facts/completeness.py
config/dataset/golden/
tests/unit/test_data_quality.py
tests/unit/test_gate_validation_status.py
```

---

## Five Mandatory Evaluation Gates

| Gate | Type | Critical failure condition |
|---|---|---|
| `numeric_consistency` | Deterministic | Number in report differs from canonical fact or valuation artifact without footnote |
| `citation_coverage` | Deterministic | Quantitative claim lacks a valid `source_id` or `fact_id` |
| `citation_validity` | Deterministic | Cited `source_id` does not support the claim (wrong ticker, period, or metric) |
| `stale_data` | Deterministic | Report presents data from source older than freshness threshold as current |
| `unsupported_recommendation` | Heuristic / LLM-assisted | Report implies guaranteed return or gives strong buy/sell without evidence |

Gate output: `PASS`, `WARN`, or `FAIL`.

A single `FAIL` on `numeric_consistency`, `citation_coverage`, or `citation_validity` **blocks export**.

---

## Execution Procedure

```bash
python scripts/evaluate_report.py --report reports/DHG_full_report.md
```

Output must be machine-readable JSON saved to `artifacts/evaluation/<report_id>_eval.json`:

```json
{
  "report_id": "...",
  "ticker": "DHG",
  "gates": {
    "numeric_consistency": "PASS",
    "citation_coverage": "PASS",
    "citation_validity": "PASS",
    "stale_data": "PASS",
    "unsupported_recommendation": "WARN"
  },
  "overall": "WARN",
  "export_blocked": false,
  "details": [...]
}
```

---

## Gate Implementation Rules

### Numeric consistency
- Extract all numbers from report text.
- Look up each in the valuation artifact or fact store.
- Flag discrepancy > 0% for exact facts, > 1% for rounded display values.

### Citation coverage
- Parse all quantitative claims (sentences with numbers + assertions).
- Verify each has a `source_id` or `fact_id` in the citation map.
- Count uncited claims; `FAIL` if count > 0.

### Stale data
- Check `published_date` of every cited source.
- Financial statement data: flag if > 18 months old for a "current" claim.
- Market price data: flag if > 5 trading days old.

### Unsupported recommendation
- Flag strings matching patterns: `"guaranteed"`, `"chắc chắn tăng"`, `"100% upside"`, strong buy/sell with no valuation anchor.
- LLM judging is acceptable here but must be a separate step from the deterministic gates.

---

## Regression Evaluation Policy

**Any change to parser, prompt, retrieval logic, or LLM model requires regression eval:**

1. Run `evaluate_report.py` on existing golden reports → save as baseline.
2. Make the change.
3. Re-run on same golden reports.
4. Any new `FAIL` or score regression blocks promotion.

Golden reports: `config/dataset/golden/`

---

## Test Coverage Requirements

- [ ] All 5 gates exercised in `tests/unit/test_data_quality.py`.
- [ ] Gate returns `FAIL` for a known-bad fixture (number mismatch, missing citation).
- [ ] Gate returns `PASS` for a known-good fixture.
- [ ] Output is machine-readable JSON, not only human text.
- [ ] Thresholds are configurable constants, not hardcoded.

---

## Hard Constraints

- **Deterministic checks always run first.** LLM judging runs last, only for qualitative gates.
- **Do not optimize only for "nice writing"** — optimize for groundedness, accuracy, and regression stability.
- **Do not lower thresholds** to make a failing report pass — fix the report content instead.
- **Eval output must be saved** to `artifacts/evaluation/` for audit trail.
- **Do not delete golden fixtures** without explicit approval.
