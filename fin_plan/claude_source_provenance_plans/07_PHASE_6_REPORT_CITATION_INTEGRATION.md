# 07 — Phase 6: Report Citation Integration

## Goal

Modify report generation so final reports cite official financial sources and concrete catalyst sources.

## Core Rule

Report writer must not render provider/API labels as final citations.

Allowed final citation sources:

```text
official_documents
verified_financial_facts linked to official_documents
source_documents linked to catalyst_events
```

Disallowed final citation sources:

```text
vnstock alone
VCI alone
KBS alone
TCBS alone
Balance Sheet (VCI)
Income Statement (VCI)
Cash Flow (VCI)
generic source labels
unknown source
LLM-generated source
```

## Required Report Behavior

### Quantitative Claim

Must cite:

```text
verified_financial_facts.official_document_id
```

Footnote format:

```text
[^metric_year]: {metric_name} năm {year} được trích từ {document_title}, {issuer}, kỳ {fiscal_year}FY, bảng {table_name}, trang {page_number}. Dữ liệu đã được đối soát với {provider} qua vnstock tại thời điểm ingest nếu có.
```

### Catalyst Claim

Must cite:

```text
catalyst_events.source_document_id
```

Footnote format:

```text
[^event_key]: {event_title}, {publisher}, ngày {published_date}. Evidence: "{evidence_quote}".
```

### Unverified Claim

If a claim only has Tier 3 data:

```text
- Allowed in draft mode
- Must show "chưa kiểm chứng bằng nguồn chính thức"
- Must fail final export
```

## Required Code Updates

Update:

```text
scripts/generate_report.py
backend/citations/citation_map.py
backend/citations/validator.py
backend/reporting/
```

Expected changes:

```text
1. Report generator reads verified_financial_facts for final numeric claims.
2. Report generator reads catalyst_events for catalyst section.
3. Citation map distinguishes:
   - acquisition_source
   - verification_source
   - catalyst_source
4. Final footnotes show official document/article metadata.
5. Draft mode clearly labels unverified API/provider facts.
```

## Verification Gate

Generate DHG draft and final reports:

```bash
python scripts/generate_report.py --ticker DHG --mode draft
python scripts/generate_report.py --ticker DHG --mode final
```

Then run:

```bash
python scripts/evaluate_report.py --ticker DHG
```

Required checks:

```text
1. Final report has no footnote whose only source is vnstock/VCI/KBS/TCBS.
2. Final quantitative claims cite official document titles.
3. Final catalyst claims cite source document/article titles.
4. Draft report may show unverified Tier 3 facts, clearly labeled.
5. If official source is missing, final generation fails or produces non-exportable report.
```

## Output Artifacts

Create:

```text
artifacts/reports/DHG_final_citation_map.json
artifacts/reports/DHG_final_citation_audit.md
```

Audit file must include:

```text
- Total quantitative claims
- Quantitative claims with official source
- Quantitative claims with Tier 3 only
- Catalyst claims
- Catalyst claims with source_document_id
- Final export decision
```

## Exit Criteria

Phase 6 passes only if final report citations are rendered from official/catalyst evidence sources, not provider labels.
