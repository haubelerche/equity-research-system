# 00 — Master Execution Order: Source Provenance & Citation Rebuild

## Objective

Rebuild the data provenance and citation system so that:

- `vnstock`, `VCI`, `KBS`, `TCBS` are treated as data acquisition / cross-check providers only.
- Final research reports cite official documents, company disclosures, regulatory sources, or specific news/articles.
- Quantitative claims cannot pass final export if they only cite aggregated API providers.
- Catalyst/event claims must cite a concrete source document/article/regulatory notice.

## Execution Rule

Claude must execute phases in order.

```text
Phase 0 -> Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5 -> Phase 6 -> Phase 7
```

Do not proceed to the next phase unless the current phase passes its verification gate.

## Phase List

| Phase | File | Purpose |
|---|---|---|
| Phase 0 | `01_PHASE_0_CITATION_AUDIT.md` | Audit current citation/provenance failure |
| Phase 1 | `02_PHASE_1_DUAL_SOURCE_SCHEMA.md` | Separate acquisition source from verification source |
| Phase 2 | `03_PHASE_2_SOURCE_TIER_AND_EXPORT_GATES.md` | Treat vnstock/provider as Tier 3 and block final export |
| Phase 3 | `04_PHASE_3_OFFICIAL_DOCUMENT_INGESTION.md` | Build official document ingestion for financial facts |
| Phase 4 | `05_PHASE_4_FINANCIAL_FACT_RECONCILIATION.md` | Reconcile vnstock facts with official facts |
| Phase 5 | `06_PHASE_5_CATALYST_SOURCE_PIPELINE.md` | Build source ingestion pipeline for catalyst/event evidence |
| Phase 6 | `07_PHASE_6_REPORT_CITATION_INTEGRATION.md` | Render official citations in report |
| Phase 7 | `08_PHASE_7_FINAL_EVALUATION_GATES.md` | Rebuild final evaluator and approval gates |

## Final Acceptance Criteria

The whole task is complete only if:

1. No final quantitative claim cites only `vnstock`, `VCI`, `KBS`, or `TCBS`.
2. Every final quantitative claim has an official verification source.
3. Every catalyst/event claim has a concrete `source_document_id`.
4. Reports can distinguish:
   - acquisition source,
   - verification source,
   - citation source,
   - event evidence source.
5. A DHG final report can be generated and evaluated with official-source citations.
6. Draft reports may contain unverified Tier 3 facts, but final export must fail if they remain unverified.
7. Evaluation artifacts clearly show which facts are verified, unverified, mismatched, or missing source.
