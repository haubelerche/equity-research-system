# 05 — Phase 4: Financial Fact Reconciliation

## Goal

Compare vnstock/provider-derived facts with official-document facts and promote only verified facts into final-report usage.

## Required Module

Create:

```text
backend/reconciliation/financial_fact_reconciler.py
```

## Reconciliation Input

Each reconciliation job compares:

```text
api_fact:
- ticker
- fiscal_year
- metric_id
- value
- unit
- acquisition_source_id
- provider

official_fact:
- ticker
- fiscal_year
- metric_id
- value
- unit
- official_document_id
- page_number
- table_name
```

## Reconciliation Output

Store result in:

```text
fact_reconciliation_results
```

Allowed status:

```text
matched_official
mismatch
missing_official
missing_api
manual_review_required
manual_reviewed
```

## Tolerance Rule

Default:

```text
diff_pct <= 0.5% -> matched_official
diff_pct > 0.5% -> manual_review_required
```

Allow metric-specific tolerance config later, but start simple.

## Promotion Rule

Only promote to `verified_financial_facts` if:

```text
status == matched_official
or status == manual_reviewed
```

Never promote if:

```text
missing_official
mismatch
manual_review_required without review
```

## Required Script

Create:

```text
scripts/reconcile_financial_facts.py
```

Expected usage:

```bash
python scripts/reconcile_financial_facts.py --ticker DHG --from-year 2021 --to-year 2025
```

## Verification Gate

Create tests:

```text
tests/reconciliation/test_financial_fact_reconciliation.py
```

Required test cases:

```text
1. API value equals official value -> matched_official.
2. API value differs within tolerance -> matched_official.
3. API value differs outside tolerance -> manual_review_required.
4. API exists but official fact missing -> missing_official.
5. Official fact exists but API missing -> missing_api.
6. Only matched_official/manual_reviewed facts are promoted.
7. Unreviewed mismatch cannot be used in final report.
```

Run:

```bash
pytest tests/reconciliation/test_financial_fact_reconciliation.py
python scripts/reconcile_financial_facts.py --ticker DHG --from-year 2021 --to-year 2025
```

## Output Artifact

Create:

```text
artifacts/reconciliation/DHG_financial_fact_reconciliation.md
```

Must include:

```text
- Total facts compared
- Matched facts
- Mismatched facts
- Missing official facts
- Missing API facts
- Manual review required facts
- Promoted verified facts
```

## Exit Criteria

Phase 4 passes only if final-report facts come from verified official-source facts, not raw vnstock/provider facts.
