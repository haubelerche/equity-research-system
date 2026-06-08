# 03 — Phase 2: Source Tier Policy and Export Gates

## Goal

Prevent aggregated API/provider sources from passing as final report citations.

## Required Source Tier Policy

Implement this policy exactly:

```text
Tier 1 = Official source
Examples: audited financial statements, annual reports, HOSE/HNX/UPCoM disclosures, company IR, SSC/company official documents.

Tier 2 = Trusted contextual source
Examples: reputable financial media, broker reports, regulatory articles, official industry announcements.

Tier 3 = Aggregated API/provider
Examples: vnstock, VCI, KBS, TCBS, provider-returned financial tables.

Tier 4 = Unknown or generated source
Examples: missing source, generic label, LLM-created citation, unknown provider.
```

## Hard Rules

1. Tier 3 can be used for draft generation and cross-checking.
2. Tier 3 cannot be the only source for a final quantitative claim.
3. Tier 4 is always blocked.
4. Final report export fails if any material quantitative claim lacks Tier 1 verification.
5. Catalyst/event claims may use Tier 1 or Tier 2, but must have concrete document/article evidence.

## Required Code Updates

Update citation validator and final export evaluator.

Expected behavior:

```python
if claim.is_quantitative and claim.only_has_tier3_source:
    fail("Quantitative claim cites only aggregated API/provider source.")

if claim.source_tier == "TIER_4_UNKNOWN":
    fail("Claim has unknown or generated source.")

if report.mode == "final" and claim.is_quantitative and not claim.official_document_id:
    fail("Final quantitative claim requires official verification source.")
```

## Bad Patterns to Block

```text
vnstock
VCI
KBS
TCBS
Balance Sheet (VCI)
Income Statement (VCI)
Cash Flow (VCI)
Báo cáo tài chính (vnstock API)
Nguồn không xác định
Generated citation
```

## Verification Gate

Create tests:

```text
tests/citations/test_source_tier_policy.py
tests/citations/test_tier3_cannot_pass_final.py
```

Required test cases:

```text
1. "Balance Sheet (VCI) [Tier 3]" fails final export.
2. "Income Statement (KBS) [Tier 3]" fails final export.
3. Quantitative claim with only vnstock source fails final export.
4. Quantitative claim with official_document_id passes source-tier gate.
5. Draft report may contain Tier 3 with "unverified" status.
6. Unknown/generic source fails in both draft approval and final export.
```

Run:

```bash
pytest tests/citations/test_source_tier_policy.py
pytest tests/citations/test_tier3_cannot_pass_final.py
```

## Output Artifact

Create:

```text
artifacts/evaluation/source_tier_gate_result.md
```

Must include:

```text
- Number of Tier 1 claims
- Number of Tier 2 claims
- Number of Tier 3 claims
- Number of Tier 4 claims
- Export decision
- Blocking reasons
```

## Exit Criteria

Phase 2 passes only if final export is impossible with provider/API-only citations.
