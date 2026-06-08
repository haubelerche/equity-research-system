# 08 — Phase 7: Final Evaluation Gates

## Goal

Rebuild the evaluator so reports cannot pass if source provenance is weak.

## Required Gates

Implement or refactor evaluator into these gates:

```text
Gate 1 — Citation Coverage
Gate 2 — Source Tier Validity
Gate 3 — Official Source Requirement
Gate 4 — Numeric Consistency
Gate 5 — Reconciliation Status
Gate 6 — Catalyst Evidence Validity
Gate 7 — Final Export Approval
```

## Gate 1 — Citation Coverage

Requirement:

```text
100% quantitative claims in final report must have citation.
100% catalyst/event claims in final report must have citation.
```

Fail if:

```text
claim has no citation
citation key not found
citation source missing
```

## Gate 2 — Source Tier Validity

Fail if:

```text
source_tier == Tier 4
source label is generic
source is LLM-generated
source is unknown
```

Warn in draft, fail in final if:

```text
source_tier == Tier 3
```

## Gate 3 — Official Source Requirement

For final quantitative claims:

```text
official_document_id is required
```

Fail if:

```text
claim.is_quantitative and official_document_id is null
```

## Gate 4 — Numeric Consistency

Compare report numbers against `verified_financial_facts`.

Fail if:

```text
wrong ticker
wrong fiscal year
wrong unit
value differs outside tolerance
metric_id cannot be resolved
```

## Gate 5 — Reconciliation Status

Pass only if:

```text
reconciliation_status in ["matched_official", "manual_reviewed"]
```

Fail if:

```text
missing_official
mismatch
manual_review_required
missing_api without official fallback explanation
```

## Gate 6 — Catalyst Evidence Validity

For each catalyst/event claim:

```text
source_document_id is required
event_type must be controlled taxonomy
evidence_quote or evidence_span is required
causality_level must be explicit
```

Fail if:

```text
catalyst claim has no source_document_id
event_type is unknown
causal wording is stronger than evidence level
```

## Gate 7 — Final Export Approval

Final export passes only if:

```text
Gate 1 pass
Gate 2 pass
Gate 3 pass
Gate 4 pass
Gate 5 pass
Gate 6 pass
No blocking issue remains
```

## Required Tests

Create:

```text
tests/evaluation/test_final_source_gates.py
tests/evaluation/test_numeric_claim_gates.py
tests/evaluation/test_catalyst_evidence_gates.py
```

Required test cases:

```text
1. Report with Tier 3-only quantitative claim fails final.
2. Report with official verified quantitative claim passes.
3. Report with missing citation fails.
4. Report with numeric mismatch fails.
5. Report with unreviewed reconciliation mismatch fails.
6. Report with catalyst but no source_document_id fails.
7. Report with catalyst source and evidence quote passes.
8. Draft report may contain warnings but cannot be marked final-approved.
```

## Required Commands

Run:

```bash
pytest tests/evaluation/test_final_source_gates.py
pytest tests/evaluation/test_numeric_claim_gates.py
pytest tests/evaluation/test_catalyst_evidence_gates.py
pytest
python scripts/generate_report.py --ticker DHG --mode final
python scripts/evaluate_report.py --ticker DHG
```

## Output Artifacts

Create:

```text
artifacts/evaluation/DHG_citation_coverage_gate.md
artifacts/evaluation/DHG_source_tier_gate.md
artifacts/evaluation/DHG_official_source_gate.md
artifacts/evaluation/DHG_numeric_consistency_gate.md
artifacts/evaluation/DHG_reconciliation_gate.md
artifacts/evaluation/DHG_catalyst_evidence_gate.md
artifacts/evaluation/DHG_final_approval_gate.md
```

## Final Exit Criteria

Phase 7 passes only if:

```text
1. Final evaluator blocks provider/API-only citations.
2. Final evaluator blocks unverified financial facts.
3. Final evaluator blocks catalyst claims without concrete source.
4. Final evaluator produces explicit artifacts explaining pass/fail.
5. DHG report can pass only when official financial sources and catalyst sources exist.
```
