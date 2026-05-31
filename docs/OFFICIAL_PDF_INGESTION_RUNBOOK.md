# Official PDF Ingestion Runbook

This runbook provides step-by-step procedures for running the OCR pipeline on official Vietnamese pharmaceutical company financial PDFs (BCTC documents), inspecting artifacts, diagnosing issues, and promoting facts to the canonical repository.

## Run Command

### 1. Verify OCR Runtime Dependencies

Before running the pipeline, confirm all OCR dependencies are properly installed:

```bash
python scripts/check_ocr_runtime.py
```

Expected output:
```
Tesseract binary: /usr/bin/tesseract (version 5.x.x)
Vietnamese language pack: Found
Poppler utilities: Found
Python packages: pytesseract, pdf2image, Pillow — all installed
✓ OCR runtime is ready
```

If any dependency is missing, see `docs/OCR_PIPELINE.md` for installation instructions.

### 2. Run OCR Extraction

Extract candidate facts from an official PDF:

```bash
python -c "
from pathlib import Path
from backend.documents.pdf_extractor import extract_pdf_text, detect_pdf_type
from backend.documents.ocr_candidate_facts import extract_candidate_facts_from_text

pdf_path = Path('data/original_documents/DHG/2021/DHG_2021_BCTC.pdf')

# Detect PDF type
pdf_type = detect_pdf_type(pdf_path)
print(f'PDF Type: {pdf_type}')

# Extract text (will use OCR for scanned PDFs)
extracted_text = extract_pdf_text(pdf_path)
print(f'Extracted {len(extracted_text)} pages')

# Extract candidate facts
candidate_facts = extract_candidate_facts_from_text(
    extracted_text,
    ticker='DHG',
    fiscal_year=2021
)
print(f'Found {len(candidate_facts)} candidate facts')

# Save to staging
from backend.documents.ocr_candidate_facts import save_candidate_facts
staging_path = Path('data/candidate_facts/DHG/2021/facts.json')
staging_path.parent.mkdir(parents=True, exist_ok=True)
save_candidate_facts(candidate_facts, staging_path)
print(f'Saved to {staging_path}')
"
```

---

## Inspect Artifacts

### Raw OCR Text

View the extracted text from a specific PDF page:

```bash
cat "data/ocr_artifacts/DHG/2021/document_id_12345/pages/page_001.txt"
```

This file contains the raw OCR output for the first page of the document. Check for:
- Character encoding issues (Vietnamese diacritics should be readable)
- OCR confidence (page should be mostly legible)
- Table structure preservation (financial tables should show rows and columns)

### Candidate Rows CSV

View extracted table data in CSV format:

```bash
head -20 "data/ocr_artifacts/DHG/2021/document_id_12345/candidate_rows.csv"
```

Columns:
- `row_number` — Position in extracted table
- `metric_id` — Identified financial metric (e.g., revenue.net)
- `fiscal_year`, `quarter` — Reporting period
- `value` — Extracted numeric value (may be string)
- `unit` — Currency or multiplier
- `confidence` — OCR confidence (0.0–1.0)
- `source_page` — PDF page number

### Metadata

View processing metadata:

```bash
python -c "
import json
meta_path = 'data/ocr_artifacts/DHG/2021/document_id_12345/metadata.json'
with open(meta_path) as f:
    meta = json.load(f)
print(json.dumps(meta, indent=2))
"
```

Expected fields:
- `ocr_engine`: 'tesseract'
- `ocr_version`: version number
- `pdf_type`: 'SCANNED' or 'TEXT_BASED'
- `pages_processed`: number of pages
- `overall_confidence`: average confidence across pages
- `processing_timestamp`: ISO datetime
- `vietnamese_lang_pack`: true/false

---

## Inspect Blocked Facts

View candidate facts that failed validation or reconciliation:

```python
from pathlib import Path
from backend.documents.ocr_candidate_facts import load_candidate_facts, filter_by_status

# Load candidate facts from staging
facts = load_candidate_facts(Path("data/candidate_facts/DHG/2021/facts.json"))

# Filter by promotion status
blocked = filter_by_status(facts, promotion_status="blocked")

# Inspect each blocked fact
for fact in blocked:
    print(f"Metric: {fact.metric_id}")
    print(f"  Validation Status: {fact.validation_status}")
    print(f"  Validation Warnings: {fact.validation_warnings}")
    print(f"  Reconciliation Status: {fact.reconciliation_status}")
    print(f"  Reconciliation Warnings: {fact.reconciliation_warnings}")
    print(f"  Value: {fact.normalized_value}")
    print(f"  Confidence: {fact.extraction_confidence}")
    print(f"  Source Page: {fact.source_page}")
    print()
```

For each blocked fact, review:
1. **Validation warnings** — Does the metric_id or value make sense? Is it in the correct range?
2. **Reconciliation status** — Is there a conflicting secondary value? Is secondary source missing?
3. **Source page** — Check the original PDF page to verify the OCR output
4. **Confidence score** — Low confidence (< 0.70) indicates poor OCR quality for that row

---

## Manually Correct a Candidate Fact

If OCR misread a value or metric assignment, correct it manually:

```python
from pathlib import Path
from backend.documents.ocr_candidate_facts import load_candidate_facts, save_candidate_facts

# Load facts
facts_path = Path("data/candidate_facts/DHG/2021/facts.json")
facts = load_candidate_facts(facts_path)

# Find the fact to correct
target_fact = next(
    (f for f in facts if f.metric_id == "revenue.net" and f.fiscal_year == 2021),
    None
)

if target_fact:
    # Correct the value
    target_fact.normalized_value = 1234.5  # New corrected value (in billions VND)
    target_fact.extraction_confidence = 0.95  # Mark as manually verified
    
    # Re-validate
    target_fact.validation_status = "passed"
    target_fact.validation_warnings = ["manually_corrected"]
    
    # Mark for reconciliation check
    target_fact.reconciliation_status = "pending"
    
    # Save corrected facts
    save_candidate_facts(facts, facts_path)
    print(f"Corrected {target_fact.metric_id}: {target_fact.normalized_value}")
```

After manual correction:
1. Re-run reconciliation to confirm against secondary source
2. Re-run promotion gate
3. Document the manual override in a review log or commit message

---

## Rerun Promotion

After correcting blocked facts or updating reconciliation, promote candidate facts to canonical repository:

```python
from pathlib import Path
from backend.documents.ocr_candidate_facts import load_candidate_facts
from backend.documents.fact_promotion import promote_candidate_facts

# Load corrected candidate facts
facts_path = Path("data/candidate_facts/DHG/2021/facts.json")
candidate_facts = load_candidate_facts(facts_path)

# Promote to canonical
fact_table, promotion_results = promote_candidate_facts(
    candidate_facts,
    require_secondary_confirmation=True  # Strict: critical metrics need secondary match
)

# Inspect results
print(f"Promoted: {promotion_results['promoted_count']}")
print(f"Blocked: {promotion_results['blocked_count']}")

if promotion_results['blocked_reasons']:
    print("\nBlocked reasons:")
    for reason, count in promotion_results['blocked_reasons'].items():
        print(f"  {reason}: {count}")

# View promoted facts
for fact in fact_table:
    print(f"{fact['metric_id']}: {fact['value']} {fact['unit']}")
```

Expected output:
- Promoted facts are now in the canonical fact repository
- Blocked facts remain in staging with promotion_status = "blocked"
- Promotion results log lists all blocked reasons

---

## Rerun Report Gate

After promotion, verify that the report gate passes (sufficient facts for report generation):

```python
from pathlib import Path
from backend.harness.gates import ocr_export_gate
from backend.documents.ocr_candidate_facts import load_candidate_facts

# Load candidate facts from staging
facts = load_candidate_facts(Path("data/candidate_facts/DHG/2021/facts.json"))

# Run report gate in draft mode (no export block)
draft_result = ocr_export_gate(facts, report_mode="draft")
print("Draft Mode Report Gate:")
print(f"  Status: {draft_result['status']}")
print(f"  Critical Facts Available: {draft_result['critical_facts_available_count']}")
print(f"  Critical Facts Required: {draft_result['critical_facts_required_count']}")
print(f"  Coverage: {draft_result['coverage_percentage']}%")

# Run report gate in final mode (blocks if gate fails)
final_result = ocr_export_gate(facts, report_mode="final")
print("\nFinal Mode Report Gate:")
print(f"  Status: {final_result['status']}")

if final_result['status'] == 'FAILED':
    print("  ✗ Report gate failed. Cannot export.")
    print(f"  Missing: {final_result['missing_facts']}")
else:
    print("  ✓ Report gate passed. Export is permitted.")
```

**Gate Status Values:**
- `PASSED` — Sufficient facts available (>= 80% of critical metrics)
- `PASSED_WITH_WARNINGS` — Facts available but some optional metrics missing
- `FAILED` — Insufficient facts (<80% of critical metrics); export blocked

---

## Troubleshooting

### OCR Confidence is Low (< 0.70)

**Problem:** Many facts extracted with low confidence scores.

**Cause:** PDF image quality is poor (faint text, low resolution, rotated pages).

**Solution:**
1. Check original PDF: Is it clearly readable?
2. Re-scan or request a clearer version from company IR
3. Retry OCR with preprocessing:
   ```python
   from backend.documents.pdf_extractor import extract_pdf_text
   extracted = extract_pdf_text(pdf_path, preprocess=True, dpi=300)
   ```
4. Manually review low-confidence facts and correct if needed

### Reconciliation Conflicts

**Problem:** Many facts show `reconciliation_status = "conflicted"`.

**Cause:** OCR values differ from secondary source (CafeF/API) beyond tolerance.

**Solution:**
1. Check if secondary source is for the same fiscal year/quarter
2. Check if OCR metric_id is correctly assigned (e.g., consolidated vs. separate statements)
3. Manually inspect original PDF page to see which source is correct
4. Override and re-promote if PDF is source of truth
5. Block from promotion if secondary source is more reliable

### Missing Secondary Source

**Problem:** Cannot reconcile critical metric; secondary source unavailable.

**Cause:** CafeF/API does not have data for this ticker/period.

**Solution:**
1. Try alternative secondary sources (e.g., HNX official site, alternative data API)
2. If no secondary available, promote only if OCR confidence >= 0.90
3. Escalate to analyst for manual verification from original PDF

### Metric Assignment Errors

**Problem:** OCR assigned wrong metric_id (e.g., confusion between revenue and gross profit).

**Cause:** Table header misread or inconsistent formatting in PDF.

**Solution:**
1. Check source_page in candidate fact
2. Manually inspect that page in original PDF
3. Correct metric_id:
   ```python
   fact.metric_id = "correct_metric_id"
   fact.validation_status = "pending"
   ```
4. Re-validate and re-reconcile

---

## Example: End-to-End Ingestion Workflow

```bash
# 1. Verify runtime
python scripts/check_ocr_runtime.py

# 2. Extract candidate facts
python -c "
from pathlib import Path
from backend.documents.pdf_extractor import detect_pdf_type, extract_pdf_text
from backend.documents.ocr_candidate_facts import extract_candidate_facts_from_text, save_candidate_facts

pdf_path = Path('data/original_documents/DHG/2021/DHG_2021_BCTC.pdf')
extracted_text = extract_pdf_text(pdf_path)
candidate_facts = extract_candidate_facts_from_text(extracted_text, ticker='DHG', fiscal_year=2021)
staging = Path('data/candidate_facts/DHG/2021/facts.json')
staging.parent.mkdir(parents=True, exist_ok=True)
save_candidate_facts(candidate_facts, staging)
print(f'Extracted {len(candidate_facts)} candidates')
"

# 3. Inspect and correct blocked facts (if any)
python -c "
from pathlib import Path
from backend.documents.ocr_candidate_facts import load_candidate_facts, filter_by_status
facts = load_candidate_facts(Path('data/candidate_facts/DHG/2021/facts.json'))
blocked = filter_by_status(facts, promotion_status='blocked')
print(f'Blocked facts: {len(blocked)}')
for f in blocked[:3]:
    print(f'  {f.metric_id}: {f.validation_status}, {f.reconciliation_status}')
"

# 4. Promote to canonical
python -c "
from pathlib import Path
from backend.documents.ocr_candidate_facts import load_candidate_facts
from backend.documents.fact_promotion import promote_candidate_facts
facts = load_candidate_facts(Path('data/candidate_facts/DHG/2021/facts.json'))
fact_table, results = promote_candidate_facts(facts, require_secondary_confirmation=True)
print(f'Promoted: {results[\"promoted_count\"]}, Blocked: {results[\"blocked_count\"]}')
"

# 5. Run report gate
python -c "
from pathlib import Path
from backend.harness.gates import ocr_export_gate
from backend.documents.ocr_candidate_facts import load_candidate_facts
facts = load_candidate_facts(Path('data/candidate_facts/DHG/2021/facts.json'))
result = ocr_export_gate(facts, report_mode='final')
print(f'Report Gate: {result[\"status\"]} ({result[\"coverage_percentage\"]}% coverage)')
"
```

If all steps succeed, the OCR ingestion is complete and the report can proceed to the next phase (evidence retrieval and generation).
