# Claude Code Execution Plan — P5 OCR Productionization + Reconciliation Gate

## 0. Current Context

P0–P4 are complete.

Completed items:

* Golden baseline fixture:

  * `tests/fixtures/golden_facts/DHG_2021_facts.csv`
  * 8 manually verified DHG 2021 facts using canonical dot-notation `metric_id`.
* Regression tests:

  * `tests/unit/test_extractor_golden_baseline.py`
  * includes mapping tests and fixture consistency checks.
* Bug fixed:

  * `tax_expense.total` pattern previously matched `net_income.parent`.
  * fixed by anchoring patterns in `config/financial_metric_dictionary.yaml`.
* PDF/OCR foundation:

  * `PdfType` enum.
  * `detect_pdf_type(pdf_path)`.
  * `extract_from_pdf_ocr()`.
  * `_parse_ocr_text_to_rows()`.

Remaining blocker:

* DHG official financial statement PDFs are scanned images.
* OCR requires a reproducible runtime:

  * Tesseract binary.
  * Vietnamese language data.
  * Poppler tools.
* OCR output must not be promoted directly into canonical financial facts without validation and reconciliation.

## 1. Goal

Build a production-safe OCR ingestion path for scanned official BCTC PDFs.

The pipeline must:

```text
official PDF
  -> PDF type detection
  -> OCR runtime check
  -> OCR extraction
  -> raw OCR artifact persistence
  -> candidate fact extraction
  -> dictionary mapping
  -> validation
  -> reconciliation against secondary structured source where available
  -> promote only validated facts into canonical financial_facts
  -> block report export if unresolved OCR-derived quantitative facts remain
```

## 2. Non-Negotiable Constraints

1. OCR output must never write directly to canonical `financial_facts`.
2. Every OCR-derived candidate fact must retain:

   * source document id,
   * source path or URI,
   * page number,
   * raw label,
   * raw value,
   * normalized value,
   * metric id,
   * parser version,
   * extraction confidence,
   * reconciliation status.
3. If OCR runtime is missing, the system must fail with actionable diagnostics, not silently skip.
4. If OCR candidate facts are low-confidence, duplicated, missing required metrics, or unreconciled, they must remain in staging.
5. Report export must remain blocked if quantitative claims rely only on unresolved OCR candidates.
6. LLM must not infer, repair, or invent financial facts.

## 3. Target Implementation Phases

---

# Phase P5.1 — OCR Runtime Health Check

## Objective

Make OCR dependency availability explicit and testable.

## Files to inspect first

* `backend/documents/pdf_extractor.py`
* `scripts/auto_ingest_official_documents.py`
* `requirements.txt`
* `pyproject.toml` or equivalent dependency file
* `Dockerfile`
* `docker-compose.yml`
* `README.md` or setup docs
* existing test structure under `tests/unit/`

## Required implementation

Create:

```text
scripts/check_ocr_runtime.py
```

The script must check:

```text
tesseract --version
tesseract --list-langs
pdftoppm -h or pdftocairo -h
```

It must verify:

* Tesseract binary is installed.
* Vietnamese OCR language `vie` is available.
* Poppler is installed.
* Python packages are importable:

  * `pytesseract`
  * `pdf2image`
  * `PIL`

## Expected CLI behavior

Success:

```bash
python scripts/check_ocr_runtime.py
```

Output example:

```text
[ocr-runtime] OK
tesseract: found
language: vie found
poppler: found
python packages: OK
```

Failure example:

```text
[ocr-runtime] FAILED
Missing Vietnamese language data: vie
Install with:
  sudo apt-get install tesseract-ocr-vie
or provide TESSDATA_PREFIX pointing to tessdata containing vie.traineddata
```

## Acceptance criteria

* Missing Tesseract produces a clear error.
* Missing `vie` produces a clear error.
* Missing Poppler produces a clear error.
* Script exits with non-zero code when dependencies are missing.
* Script exits with zero when all OCR dependencies are available.

---

# Phase P5.2 — Docker and Environment Setup

## Objective

Make OCR runtime reproducible across local development and CI.

## Required implementation

Update Docker/dev setup to install:

```bash
tesseract-ocr
tesseract-ocr-vie
poppler-utils
```

If project uses Debian/Ubuntu image, add:

```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-vie \
    poppler-utils \
 && rm -rf /var/lib/apt/lists/*
```

Update Python dependencies if missing:

```text
pytesseract
pdf2image
Pillow
```

## Documentation update

Add a section:

```text
OCR Runtime Requirements
```

Include:

```bash
sudo apt-get update
sudo apt-get install -y tesseract-ocr tesseract-ocr-vie poppler-utils
pip install pytesseract pdf2image Pillow
python scripts/check_ocr_runtime.py
```

## Acceptance criteria

* Fresh environment can run `python scripts/check_ocr_runtime.py`.
* OCR dependencies are documented.
* Missing dependency instructions are actionable.

---

# Phase P5.3 — OCR Artifact Model

## Objective

Persist raw OCR outputs before parsing them into facts.

## Required design

Introduce an OCR artifact representation.

Preferred implementation if database migration exists:

```text
ocr_extraction_runs
ocr_pages
ocr_candidate_rows
```

If database schema is not ready, create filesystem artifacts first under:

```text
data/ocr_artifacts/{ticker}/{fiscal_year}/{document_id}/
```

Minimum artifact files:

```text
metadata.json
pages/page_001.txt
pages/page_002.txt
candidate_rows.csv
diagnostics.json
```

## Required metadata

Each OCR run must store:

```yaml
ocr_run_id:
document_id:
ticker:
fiscal_year:
source_uri:
source_checksum:
pdf_type:
ocr_engine:
ocr_lang:
dpi:
parser_version:
started_at:
completed_at:
status:
pages_processed:
pages_failed:
candidate_row_count:
mapped_fact_count:
warnings:
errors:
```

Each OCR page must store:

```yaml
page_number:
text_path:
image_dpi:
ocr_lang:
char_count:
numeric_token_count:
financial_label_hits:
status:
warnings:
```

## Acceptance criteria

* Running OCR creates raw text artifacts per page.
* Artifacts are deterministic by document checksum or run id.
* Artifacts include enough metadata to reproduce the extraction.
* OCR text is inspectable without rerunning OCR.

---

# Phase P5.4 — Candidate Fact Staging

## Objective

Separate OCR candidate extraction from canonical fact promotion.

## Required implementation

Create a staging data model or artifact:

```text
candidate_facts
```

Minimum fields:

```yaml
candidate_fact_id:
ocr_run_id:
document_id:
ticker:
fiscal_year:
period_type:
page_number:
statement_type:
raw_label:
normalized_label:
metric_id:
raw_value:
normalized_value:
unit:
currency:
confidence:
mapping_rule_id:
parser_version:
source_type: official_pdf_ocr
validation_status: pending | passed | failed
reconciliation_status: not_checked | matched | conflicted | missing_secondary_source
promotion_status: blocked | promoted
warnings:
created_at:
```

## Important rule

Do not insert OCR-derived facts into canonical `financial_facts` from `extract_from_pdf_ocr()`.

Instead:

```text
extract_from_pdf_ocr()
  -> raw OCR pages
  -> candidate rows
  -> candidate facts
```

Promotion must happen only via an explicit function:

```python
promote_candidate_facts(...)
```

or equivalent.

## Acceptance criteria

* OCR extraction creates candidate facts.
* Canonical `financial_facts` remains unchanged until promotion.
* Candidate facts retain raw label and page number.
* Candidate facts retain parser version and source document identity.

---

# Phase P5.5 — Validation Gate

## Objective

Reject low-quality OCR facts before reconciliation or promotion.

## Required validation rules

Implement deterministic validation before promotion:

1. Schema validation:

   * required fields not null.
   * `metric_id` must exist in canonical dictionary.
   * `normalized_value` must be numeric.

2. Period validation:

   * `fiscal_year` must match expected document year.
   * `period_type` must be FY unless explicitly configured otherwise.

3. Financial sanity:

   * revenue should generally be positive.
   * gross profit should not exceed revenue unless explicitly justified.
   * net income should not exceed revenue in normal cases.
   * tax expense should not equal or match net income parent line due to label confusion.
   * total assets should generally be greater than or equal to equity.
   * liabilities + equity should reconcile to total assets when available.

4. Duplicate detection:

   * same ticker/year/period/statement/metric must not have unresolved duplicate values.
   * if duplicates exist, mark as conflict.

5. Required metric coverage:

   * for DHG annual report, require at minimum:

     * `revenue.net`
     * `gross_profit.total`
     * `profit_before_tax.total`
     * `tax_expense.total`
     * `net_income.parent`
     * `total_assets.total`
     * `equity.total`
     * `liabilities.total`

## Output

Each candidate fact receives:

```text
validation_status = passed | failed
warnings = [...]
```

## Acceptance criteria

* Failed candidate facts cannot be promoted.
* Duplicate/conflicting facts cannot be promoted.
* Known false positive around `tax_expense.total` vs `net_income.parent` remains covered by regression tests.
* Required metrics missing leads to blocked promotion.

---

# Phase P5.6 — Reconciliation Gate Against CafeF/API

## Objective

Use secondary structured data to cross-check official OCR-derived facts.

## Required behavior

For each candidate fact, compare with existing structured facts from CafeF/API if available.

Suggested tolerance:

```text
absolute_tolerance = 1_000_000 VND
relative_tolerance = 0.5%
```

Status rules:

```text
matched:
  OCR value and secondary value are within tolerance.

conflicted:
  both sources exist but values differ beyond tolerance.

missing_secondary_source:
  no secondary fact exists.

not_checked:
  reconciliation not executed.
```

## Important trust policy

* Official OCR has higher source authority but lower extraction reliability.
* CafeF/API has lower authority but higher structural cleanliness.
* If official OCR and CafeF/API conflict, do not auto-promote.
* Store conflict details for manual review.

## Conflict artifact

Create a reconciliation report:

```text
data/reconciliation/{ticker}/{fiscal_year}/ocr_vs_structured.json
```

Minimum fields:

```yaml
ticker:
fiscal_year:
metric_id:
ocr_value:
secondary_value:
absolute_diff:
relative_diff:
ocr_source:
secondary_source:
status:
decision:
```

## Acceptance criteria

* Matched facts can proceed to promotion if validation also passed.
* Conflicted facts remain blocked.
* Missing secondary source does not automatically fail if official OCR is high-confidence, but must be flagged as `needs_review` unless metric is non-critical.
* Reconciliation report is saved and inspectable.

---

# Phase P5.7 — Promotion Into Canonical Facts

## Objective

Promote only validated and reconciled facts into canonical financial facts.

## Promotion rule

A candidate fact can be promoted only if:

```text
validation_status == passed
AND reconciliation_status in {matched, missing_secondary_source}
AND confidence >= configured threshold
AND no unresolved duplicate exists
AND source metadata is complete
```

For critical valuation metrics, prefer:

```text
reconciliation_status == matched
```

Critical valuation metrics include:

```text
revenue.net
gross_profit.total
operating_profit.total
profit_before_tax.total
tax_expense.total
net_income.parent
eps.basic
total_assets.total
equity.total
cash_and_equivalents.total
borrowings.total
operating_cash_flow.total
capex.total
```

## Required implementation

Promotion must write:

* canonical fact value,
* source document id,
* source URI/path,
* page number,
* parser version,
* confidence,
* ingestion run id,
* checksum/version.

## Acceptance criteria

* Promotion is explicit and testable.
* Promoted facts are traceable back to OCR page and source PDF.
* Promotion is idempotent.
* Re-running the same document does not create duplicated canonical facts.

---

# Phase P5.8 — Report Export Blocking

## Objective

Prevent final reports from using unresolved OCR-derived facts.

## Required behavior

Update quality gate / approval gate so that:

* Any quantitative claim using an unresolved candidate fact fails export.
* Any canonical fact without source metadata fails export.
* Any valuation artifact depending on unresolved facts fails export.
* The failure message lists exact blocking facts.

## Example failure output

```text
EXPORT BLOCKED: unresolved quantitative evidence

Ticker: DHG
Fiscal year: 2021

Blocking facts:
- metric_id: tax_expense.total
  reason: OCR candidate conflicted with secondary source
- metric_id: net_income.parent
  reason: duplicate OCR candidates unresolved

Action:
- inspect reconciliation report
- manually approve or correct candidate facts
- rerun promotion
```

## Acceptance criteria

* Report can still generate draft with warnings.
* Final export is blocked until facts are resolved.
* Blocking report is machine-readable and human-readable.

---

# Phase P5.9 — Test Expansion

## Objective

Prevent regression in OCR, extraction, validation, and promotion.

## Required tests

Add or update tests:

```text
tests/unit/test_ocr_runtime_check.py
tests/unit/test_pdf_type_detection.py
tests/unit/test_ocr_candidate_facts.py
tests/unit/test_ocr_validation_gate.py
tests/unit/test_ocr_reconciliation_gate.py
tests/unit/test_ocr_promotion_gate.py
tests/unit/test_report_export_blocks_unresolved_facts.py
```

## Required test cases

1. Runtime check:

   * missing tesseract fails.
   * missing vie language fails.
   * missing poppler fails.
   * all dependencies present passes.

2. PDF type detection:

   * text-based PDF classified as `TEXT_BASED`.
   * scanned PDF classified as `SCANNED`.
   * unreadable PDF classified as `UNKNOWN`.

3. Candidate staging:

   * OCR extraction writes candidate facts.
   * OCR extraction does not write canonical facts.

4. Validation:

   * missing required fields fail.
   * unknown metric id fails.
   * duplicate metric conflict fails.
   * tax expense does not match net income parent.

5. Reconciliation:

   * values within tolerance are `matched`.
   * values outside tolerance are `conflicted`.
   * missing secondary source is flagged.

6. Promotion:

   * valid matched facts are promoted.
   * conflicted facts are not promoted.
   * promotion is idempotent.

7. Export blocking:

   * final report export fails if unresolved quantitative facts exist.
   * export passes only after facts are promoted and cited.

## Existing test must continue passing

```bash
pytest tests/unit/test_extractor_golden_baseline.py
```

## Final test command

```bash
pytest tests/unit/test_extractor_golden_baseline.py \
       tests/unit/test_pdf_type_detection.py \
       tests/unit/test_ocr_candidate_facts.py \
       tests/unit/test_ocr_validation_gate.py \
       tests/unit/test_ocr_reconciliation_gate.py \
       tests/unit/test_ocr_promotion_gate.py \
       tests/unit/test_report_export_blocks_unresolved_facts.py
```

---

# Phase P5.10 — Documentation and Operator Guide

## Objective

Make this usable by future data ops / reviewer.

## Required docs

Create or update:

```text
docs/OCR_PIPELINE.md
docs/DATA_PROMOTION_POLICY.md
docs/OFFICIAL_PDF_INGESTION_RUNBOOK.md
```

## Required content

`docs/OCR_PIPELINE.md`:

* OCR dependencies.
* runtime check.
* PDF type detection.
* raw OCR artifact location.
* candidate facts.
* validation.
* reconciliation.
* promotion.

`docs/DATA_PROMOTION_POLICY.md`:

* source tiers.
* when official OCR is enough.
* when secondary reconciliation is required.
* when manual review is required.
* why LLM must not repair numbers.

`docs/OFFICIAL_PDF_INGESTION_RUNBOOK.md`:

* run command.
* inspect artifacts.
* inspect blocked facts.
* manually correct candidate fact.
* rerun promotion.
* rerun report gate.

## Acceptance criteria

* A new developer can reproduce OCR ingestion from docs.
* A reviewer can understand why a fact is blocked.
* A data ops user can inspect and correct OCR failures.

---

## 4. Suggested File-Level Changes

Likely files to modify or create:

```text
backend/documents/pdf_extractor.py
backend/documents/ocr_runtime.py
backend/documents/ocr_artifacts.py
backend/documents/ocr_candidate_facts.py
backend/documents/ocr_validation.py
backend/documents/ocr_reconciliation.py
backend/documents/fact_promotion.py

scripts/check_ocr_runtime.py
scripts/auto_ingest_official_documents.py

config/financial_metric_dictionary.yaml
config/ocr_policy.yaml

tests/unit/test_ocr_runtime_check.py
tests/unit/test_pdf_type_detection.py
tests/unit/test_ocr_candidate_facts.py
tests/unit/test_ocr_validation_gate.py
tests/unit/test_ocr_reconciliation_gate.py
tests/unit/test_ocr_promotion_gate.py
tests/unit/test_report_export_blocks_unresolved_facts.py

docs/OCR_PIPELINE.md
docs/DATA_PROMOTION_POLICY.md
docs/OFFICIAL_PDF_INGESTION_RUNBOOK.md
```

If the existing project has equivalent modules, reuse them instead of creating duplicated abstractions.

---

## 5. Configuration

Create:

```text
config/ocr_policy.yaml
```

Suggested content:

```yaml
ocr:
  enabled: true
  engine: tesseract
  languages:
    - vie
    - eng
  dpi: 300
  min_text_chars_per_page: 50
  min_numeric_tokens_per_statement_page: 5
  min_candidate_confidence: 0.80

promotion:
  require_reconciliation_for_critical_metrics: true
  absolute_tolerance_vnd: 1000000
  relative_tolerance: 0.005
  block_on_duplicate_metric: true
  block_on_missing_source_metadata: true

required_metrics:
  income_statement:
    - revenue.net
    - gross_profit.total
    - profit_before_tax.total
    - tax_expense.total
    - net_income.parent
  balance_sheet:
    - total_assets.total
    - liabilities.total
    - equity.total
```

---

## 6. Definition of Done

P5 is complete only when all conditions below are true:

1. OCR runtime is reproducible:

   * `python scripts/check_ocr_runtime.py` passes in target environment.

2. Scanned PDF path works:

   * scanned DHG PDF is classified as `SCANNED`.
   * OCR extraction runs.
   * raw OCR artifacts are persisted.

3. Candidate facts are staged:

   * OCR-derived facts appear in candidate/staging layer.
   * canonical `financial_facts` is not modified by raw OCR extraction.

4. Validation gate works:

   * invalid candidate facts are blocked.
   * false-positive tax-expense/net-income case remains blocked.

5. Reconciliation works:

   * OCR vs CafeF/API comparison produces matched/conflicted/missing statuses.
   * conflict report is saved.

6. Promotion is safe:

   * only validated, reconciled, traceable facts are promoted.
   * promotion is idempotent.

7. Report export is safe:

   * report draft may be generated with warnings.
   * final export is blocked if unresolved quantitative facts are used.

8. Regression tests pass:

   * golden baseline tests pass.
   * OCR validation/reconciliation/promotion/export-blocking tests pass.

9. Documentation exists:

   * OCR runtime setup.
   * OCR ingestion runbook.
   * data promotion policy.

---

## 7. Commands Claude Should Run Before and After

Before implementation:

```bash
git status
find . -maxdepth 3 -type f | sort | sed -n '1,200p'
pytest tests/unit/test_extractor_golden_baseline.py
python scripts/check_ocr_runtime.py || true
```

After implementation:

```bash
python scripts/check_ocr_runtime.py

pytest tests/unit/test_extractor_golden_baseline.py

pytest tests/unit/test_pdf_type_detection.py \
       tests/unit/test_ocr_candidate_facts.py \
       tests/unit/test_ocr_validation_gate.py \
       tests/unit/test_ocr_reconciliation_gate.py \
       tests/unit/test_ocr_promotion_gate.py \
       tests/unit/test_report_export_blocks_unresolved_facts.py
```

If there is an integration script:

```bash
python scripts/auto_ingest_official_documents.py --ticker DHG --from-year 2021 --to-year 2025
```

Then verify:

```text
- raw OCR artifacts exist
- candidate facts exist
- canonical facts contain only promoted facts
- blocked facts are listed if reconciliation failed
- final report export is blocked when facts are unresolved
```

---

## 8. Expected Claude Final Report Format

At the end, report using this structure:

```markdown
# P5 Implementation Report

## Summary
What was implemented.

## Files Changed
List files and purpose.

## Runtime Setup
Whether OCR runtime check passes.

## Pipeline Behavior
Describe scanned PDF -> OCR -> candidate facts -> validation -> reconciliation -> promotion.

## Tests
List test commands and pass/fail result.

## Remaining Blockers
Be explicit. Do not claim production readiness if OCR quality or reconciliation is still incomplete.

## Manual Follow-Up
What the user must inspect or approve next.
```
