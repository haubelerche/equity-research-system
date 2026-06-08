# 01 — Phase 0: Citation and Provenance Audit

## Goal

Identify exactly where the current system incorrectly treats `vnstock`, `VCI`, `KBS`, or `TCBS` as final citation sources.

## Scope

Audit only. Do not change business logic in this phase.

## Files to Inspect

Prioritize:

```text
scripts/generate_report.py
scripts/evaluate_report.py
backend/citations/
backend/store/
backend/analytics/
migrations/
reports/
artifacts/reports/
```

Search for:

```text
vnstock
VCI
KBS
TCBS
Balance Sheet (VCI)
Income Statement (VCI)
Cash Flow (VCI)
Tier 3
source_title
source_tier
source_uri
citation_map
citation_records
report_claims
```

## Required Work

1. Find every code path that builds citation metadata.
2. Identify whether `source_title`, `source_tier`, and `source_uri` come from:
   - provider label,
   - API metadata,
   - database fact,
   - official document,
   - generated fallback.
3. Generate one DHG report using the current system.
4. Extract all footnotes/citation records from the generated report.
5. Classify each citation as:
   - official document,
   - reputable article,
   - regulatory source,
   - aggregated API/provider,
   - unknown/generic.

## Output Artifact

Create:

```text
artifacts/audit/current_citation_audit.md
```

The audit file must include:

```text
1. Citation generation code path
2. Current source fields and where they come from
3. Count of API/provider-only citations
4. Count of official-document citations
5. Count of unknown/generic citations
6. Examples of bad citations
7. Exact files/functions that must be fixed in later phases
```

## Verification Gate

Run:

```bash
python scripts/generate_report.py --ticker DHG
python scripts/evaluate_report.py --ticker DHG
```

Then verify that `artifacts/audit/current_citation_audit.md` exists and contains:

```text
- Total citation count
- Tier 3/API-only citation count
- Official-source citation count
- List of failing citation patterns
```

## Exit Criteria

Phase 0 passes only if the audit proves where the current citation system is wrong.

Do not proceed if the audit only says "citations improved" without showing source-level classification.
