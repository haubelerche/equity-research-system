# 06 — Report Template

**Date:** 2026-05-22
**Status:** Draft — update when report generation is implemented (Phase 6)

---

## 1. Report Types

| `report_type` | Description |
|---|---|
| `full_report` | Full 8-section equity research report |
| `flash_memo` | 1–2 page summary with key facts and thesis |
| `catalyst_refresh` | Update memo triggered by a specific event |

---

## 2. Full Report Structure

```text
# [TICKER] — [Company Name]
## Equity Research Report | [Date]
### [Exchange] | [Sector] | [Report Type]

---

1. Executive Summary          (~200 words)
2. Company Overview           (~400 words)
3. Industry and Market Context (~400 words)
4. Financial Performance       (~600 words + tables)
5. Valuation                   (~500 words + tables)
6. Investment Thesis           (~400 words)
7. Key Risks                   (~300 words)
8. Conclusion                  (~150 words)

Appendix A — Valuation Assumptions
Appendix B — Valuation Tables
Appendix C — Evidence Table (citation map)
Appendix D — Evaluation Summary
```

---

## 3. Section Requirements

### 3.1 Executive Summary
- 3–5 bullet points on key findings
- Analyst rating label if present (with full uncertainty disclaimer)
- Must cite at least one canonical fact

### 3.2 Company Overview
- Business description
- Exchange, market cap, major shareholder structure
- Key products and revenue composition
- All numbers must cite `company_profiles` or `financial_facts`

### 3.3 Industry and Market Context
- Vietnam pharma sector structure
- BHYT reimbursement context
- Regulatory environment (DAV)
- Peer positioning
- May cite catalyst events or qualitative sources

### 3.4 Financial Performance
- 3–5 year trend table: revenue, gross profit, net income, EPS, OCF
- Gross margin, net margin, ROE trends
- Qualitative narrative grounded in table numbers
- All numbers must trace to `financial_facts` rows with `validation_status = accepted`

### 3.5 Valuation
- DCF summary (WACC, terminal growth, implied price range)
- Multiples comparison (P/E, EV/EBITDA vs peer median)
- Sensitivity table (bull/base/bear)
- Must note all assumptions explicitly
- Must cite `valuation_artifact` for every number

### 3.6 Investment Thesis
- 2–3 key drivers
- Must be grounded in facts from sections 3.4 and 3.5
- No invented catalysts

### 3.7 Key Risks
- 3–5 specific risks (regulatory, operational, market)
- Each risk should reference a source (catalyst event or fact)

### 3.8 Conclusion
- Cautious, analyst-style conclusion
- Must NOT state guaranteed returns
- Must include uncertainty qualifier
- Investment rating (if given) must be clearly labelled as an opinion, not advice

---

## 4. Citation Format

Every quantitative claim must end with an inline citation:

```text
DHG reported net revenue of VND 4,234 billion in FY2023 [fact:revenue.net/DHG/2023/FY].
```

Citation format:
```
[fact:<taxonomy_key>/<ticker>/<fiscal_year>/<fiscal_period>]
[chunk:<chunk_id>]
[source:<source_version_id>]
```

---

## 5. Prohibited Content

Reports must NOT contain:
- Guaranteed returns or price targets stated as certainties
- Numbers not in `financial_facts` or `valuation_artifact`
- References to events not in `catalyst_events`
- Invented analyst names or fictitious firm references
- Statements implying regulatory approval of the report

---

## 6. Uncertainty Disclosure (Required Boilerplate)

Every report must end with or include:

```text
---
DISCLAIMER: This report is produced by an AI-assisted research system and has been
reviewed by a human analyst. It is intended for informational purposes only and does
not constitute investment advice. Financial projections involve assumptions and
uncertainties. Past performance is not indicative of future results. All quantitative
claims are grounded in source data registered in the system's fact store; citation
references are available in Appendix C.
```

---

## 7. Artifact Schema

See `backend/schemas.py` — `ArtifactItem` with `artifact_type = "published_report"`.

The full report artifact includes:
```yaml
report_id: <uuid>
ticker: DHG
report_type: full_report
sections:
  executive_summary: <text>
  company_overview: <text>
  ...
citation_map:
  - citation_id: ...
    claim_id: ...
    grounding_status: pass
evaluation_summary:
  grounding: 0.95
  accuracy: 0.90
  citation_coverage: 0.88
approval_status: approved | pending | rejected
created_at: <datetime>
approved_by: <reviewer>
approved_at: <datetime>
```
