# Data Promotion Policy

This document defines when OCR-extracted candidate facts are promoted to the canonical fact repository, and what conditions must be met depending on the data tier and metric criticality.

## Source Tiers

All financial facts are assigned a **source tier** that reflects the authority and reliability of the source:

### Tier 0: Official Audited BCTC PDF
- **Authority:** Highest. This is the audited annual financial statement (Báo cáo tài chính được kiểm toán)
- **Reliability:** Gold standard for historical financial facts
- **Typical use:** Primary source for annual statements
- **Example:** Official DHG audited BCTC for fiscal year 2021
- **Promotion rule:** Facts from Tier 0 PDFs are promoted with minimal secondary validation (may use missing_secondary_source if confidence >= 0.90)

### Tier 1: Official Unaudited BCTC PDF
- **Authority:** High, but unaudited
- **Reliability:** Official report structure, but lacks audit firm sign-off
- **Typical use:** Interim reports (quarterly), draft annual reports, or restatements
- **Example:** Official DHG unaudited Q3 2024 interim report
- **Promotion rule:** Facts may be promoted with matching secondary source or high confidence (>= 0.85) even if secondary is missing

### Tier 2: OCR-Extracted from Official PDF
- **Authority:** Moderate. Extracted via OCR from an official PDF document
- **Reliability:** Reduced by OCR error rate; dependent on document image quality and OCR engine accuracy
- **Typical use:** When official structured data is unavailable; requires secondary reconciliation or high confidence
- **Example:** DHG 2020 BCTC extracted via Tesseract from official PDF
- **Promotion rule:** Must pass OCR validation + reconciliation checks. Critical metrics require secondary match. Non-critical metrics may use missing_secondary_source if confidence >= 0.80

### Tier 3: CafeF/API Structured Data
- **Authority:** Moderate. Aggregated from company filings via third-party service
- **Reliability:** High structural accuracy (less OCR error), but lower authority than official PDF
- **Typical use:** Secondary confirmation source; sometimes primary when official PDF unavailable
- **Example:** CafeF quarterly earnings data for DHG
- **Promotion rule:** Accepted as secondary reconciliation source. Rarely promoted as primary source unless official PDF is permanently unavailable

### Tier 4: Third-Party or Derived
- **Authority:** Low. News sources, analyst estimates, calculated values
- **Reliability:** Variable; should not be treated as authoritative financial fact
- **Typical use:** Context, sentiment, forward guidance; never as canonical financial fact
- **Example:** Analyst revenue forecast, news article on market cap
- **Promotion rule:** Not promoted as canonical fact. May appear in report narrative with appropriate caveats

---

## When Official OCR Alone is Enough

An OCR-extracted fact **may be promoted without secondary reconciliation** if **all** of the following are true:

1. **Source is official PDF** (Tier 0 or Tier 1)
2. **Non-critical metric** (not in the 13 critical metrics list)
3. **High extraction confidence** >= 0.80 (confidence from OCR engine and validation checks)
4. **Passed all validation checks** (schema, period, sanity, no duplicates)
5. **No secondary conflict** (if secondary source is available, it must not contradict)

**Example:** OCR extracts "research_and_development.expense = 45.2 billion VND" from official 2021 BCTC with 0.88 confidence, passes validation. If no CafeF value exists or CafeF value matches, fact is promoted as:
- `reconciliation_status = "missing_secondary_source"`
- `source_tier = 2` (OCR from official PDF)
- High confidence despite missing secondary

---

## When Secondary Reconciliation is Required

**All 13 CRITICAL_METRICS** require secondary reconciliation before promotion:

### Critical Metrics List

```
1. revenue.net                  — Net revenue / top line
2. gross_profit.total           — Gross profit (revenue - COGS)
3. operating_profit.total       — Earnings before interest & tax (EBIT)
4. profit_before_tax.total      — Pre-tax profit
5. tax_expense.total            — Income tax expense
6. net_income.parent            — Net income (consolidated)
7. eps.basic                    — Earnings per share (basic)
8. total_assets.total           — Balance sheet total assets
9. equity.total                 — Total shareholders' equity
10. cash_and_equivalents.total  — Cash and cash equivalents
11. borrowings.total            — Total debt (short + long term)
12. operating_cash_flow.total   — Cash flow from operations
13. capex.total                 — Capital expenditure
```

**Promotion Rule for Critical Metrics:**

- `validation_status` must be "passed"
- `reconciliation_status` **must be "matched"** (secondary source must confirm within tolerance)
- If `reconciliation_status == "missing_secondary_source"` for any critical metric, fact is **blocked** from promotion

**Example:** OCR extracts "revenue.net = 1,234 billion VND" from 2021 BCTC. Secondary reconciliation compares against CafeF:
- If CafeF = 1,234 billion VND (within 1B VND absolute or 0.5% relative), status becomes "matched" → fact is promoted
- If CafeF = 1,200 billion VND (exceeds tolerance), status becomes "conflicted" → fact is blocked, requires manual review
- If no CafeF data available, status becomes "missing_secondary_source" → fact is blocked (critical metric cannot proceed without secondary)

---

## When Manual Review is Required

**Automatic promotion is blocked** in these cases:

### 1. Validation Failed
- Schema violation (metric_id not recognized)
- Period invalid (year out of range)
- Sanity check failed (value exceeds known bounds)
- Duplicate fact already exists
- **Action:** Review validation_warnings, correct OCR output or metric mapping, re-validate

### 2. Reconciliation Conflict
- Secondary source exists but contradicts OCR value (exceeds tolerance)
- **Example:** OCR = 1,234B VND, CafeF = 1,100B VND (134B difference, exceeds 1B tolerance)
- **Action:** Manual review to determine which source is correct. Check original PDF page. Check secondary source date/period alignment. Correct if needed, then re-reconcile.

### 3. Missing Secondary for Critical Metric
- Critical metric has no secondary source available
- OCR confidence is not high enough to skip secondary (< 0.90)
- **Action:** Attempt to obtain secondary source (e.g., query alternative data provider). If impossible, escalate to analyst for manual entry from official PDF.

### 4. Tax/Income Confusion False-Positive
- Validation detects `tax_expense.total == net_income.parent` (likely OCR confusion between line items)
- **Action:** Manually inspect original PDF page. If data genuinely matches (rare), override validation flag. More commonly, re-OCR or manually correct metric assignment.

### 5. Suspicious Pattern
- Multiple conflicted facts from same document
- High OCR error rate (> 5% of page confidence < 0.70)
- Systematic bias (all values consistently low or high)
- **Action:** Re-check PDF image quality. Re-run OCR with different parameters or manual inspection. Consider using secondary source as primary.

---

## Why LLM Must Not Repair Numbers

**Critical rule:** LLMs are **forbidden** from repairing, inferring, or interpolating financial fact values.

### Rationale

1. **Traceability:** All financial fact values must trace back to a source document page (PDF, structured export, or manual entry)
2. **Hallucination Risk:** LLMs may generate plausible-sounding numbers that do not appear anywhere in source documents
3. **Audit Trail:** Financial reports must be reproducible by independent auditors; invented numbers fail this requirement
4. **Regulatory Risk:** Financial statements are legal documents; unsupported values create liability
5. **Schema Enforcement:** Numeric inference violates the constraint that facts are **ingested**, not **computed**

### What LLMs Can Do

- Suggest which metric_id a raw OCR value corresponds to (schema mapping)
- Flag suspicious values for human review
- Explain why a value failed validation
- Recommend which secondary source to check

### What LLMs Cannot Do

- Change "1,234" to "12,340" to match a secondary source (must select one source as correct, not average or guess)
- Interpolate missing quarterly values from annual data
- Convert units automatically without explicit confirmation
- Adjust values based on "likely error patterns"
- Infer missing metrics from related metrics

### Enforcement

The promotion gate enforces this rule:
- Only values that passed validation and reconciliation checks are promoted
- Conflicted values are blocked (not auto-corrected)
- Missing-secondary facts below confidence threshold are blocked (not LLM-guessed)
- Promotion is deterministic — same input always produces same output

If an LLM user interface is added later, it must operate **only** on already-promoted canonical facts, not on raw OCR candidates.
