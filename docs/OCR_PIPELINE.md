# OCR Pipeline Documentation

## OCR Dependencies

The OCR pipeline requires the following system and Python dependencies:

- **tesseract-ocr** — Core OCR engine
- **tesseract-ocr-vie** — Vietnamese language data for Tesseract
- **poppler-utils** — PDF rendering and manipulation utilities
- **pytesseract** — Python binding for Tesseract OCR
- **pdf2image** — Convert PDF pages to PIL Image objects
- **Pillow** — Python Imaging Library for image processing

On Windows, install via Chocolatey or pre-built binaries. On Ubuntu/Debian:
```bash
sudo apt-get install tesseract-ocr tesseract-ocr-vie poppler-utils
pip install pytesseract pdf2image Pillow
```

On macOS:
```bash
brew install tesseract tesseract-lang poppler
pip install pytesseract pdf2image Pillow
```

## Runtime Check

Verify that all OCR dependencies are properly installed and configured:

```bash
python scripts/check_ocr_runtime.py
```

This script confirms:
- Tesseract binary is on PATH
- Vietnamese language pack is available
- Poppler utilities are accessible
- Python OCR libraries are installed

## PDF Type Detection

The pipeline automatically classifies PDFs before processing:

```python
from backend.documents.pdf_extractor import detect_pdf_type

pdf_type = detect_pdf_type(pdf_path)
# Returns one of:
# - PDFType.TEXT_BASED    — digital PDF with embedded text (no OCR needed)
# - PDFType.SCANNED       — scanned document or image-only PDF (OCR required)
# - PDFType.UNKNOWN       — unable to determine type
```

**Scanned PDFs** trigger the OCR path and full candidate fact extraction. **Text-based PDFs** use direct text extraction with minimal preprocessing.

## Raw OCR Artifact Location

OCR output is stored in a structured artifact directory:

```
data/ocr_artifacts/{ticker}/{fiscal_year}/{document_id}/
├── metadata.json          # OCR run metadata
├── pages/
│   ├── page_001.txt       # Extracted text from page 1
│   ├── page_002.txt
│   └── ...
├── candidate_rows.csv     # Extracted table rows (candidates for fact extraction)
└── diagnostics.json       # Confidence scores, processing notes, warnings
```

Each artifact is keyed by:
- **ticker** — Stock symbol (e.g., DHG, IMP, DMC)
- **fiscal_year** — Annual reporting period
- **document_id** — Unique identifier for the source document

The `metadata.json` file contains:
- OCR engine version and parameters
- PDF type detected
- Number of pages processed
- Overall confidence score
- Processing timestamp

## Candidate Facts

OCR extraction produces **CandidateFact** objects in a staging layer. These are **not yet canonical facts**.

**CandidateFact** fields:

```python
candidate_fact_id: str          # Unique identifier
metric_id: str                  # Financial metric (e.g., revenue.net)
fiscal_year: int
quarter: int | None             # Q1-Q4, or None for annual
ticker: str
extracted_value: float | str    # Raw extracted value (may be string)
normalized_value: float | None  # Normalized numeric value
unit: str                        # Currency or unit (VND, billions, %)
extraction_confidence: float    # 0.0-1.0 confidence from OCR
source_page: int               # PDF page number
source_document_id: str        # Which document

# Validation, reconciliation, promotion status
validation_status: str          # pending, passed, failed
validation_warnings: list[str]  # Schema, sanity check failures
reconciliation_status: str      # pending, matched, conflicted, missing_secondary_source
reconciliation_tolerance: float # Absolute or % tolerance for secondary check
promotion_status: str           # pending, promoted, blocked
promotion_warnings: list[str]   # Reason for blocking promotion
```

## Validation

Validation applies multiple checks to each candidate fact:

```python
from backend.documents.ocr_candidate_facts import validate_candidate_facts

results = validate_candidate_facts(candidate_facts)
```

**Checks performed:**

1. **Schema Check** — Does metric_id match CRITICAL_METRICS or known optional metrics?
2. **Period Check** — Is fiscal_year and quarter valid (year > 1990, quarter 1-4 or None)?
3. **Financial Sanity Check** — Does the value fall within expected ranges for the metric type?
   - Revenue: >= 0, <= 100 trillion VND
   - Profit: no constraint (can be negative)
   - Assets: >= 0, <= 1 quadrillion VND
4. **Duplicate Check** — Is this (ticker, fiscal_year, metric_id) already present?

**Known False-Positive:** 
- Validation blocks cases where `tax_expense.total == net_income.parent`, as this indicates OCR confusion between two different line items. This is a heuristic block and may require manual override if the data is genuinely correct.

After validation, each fact has:
- `validation_status` → "passed" or "failed"
- `validation_warnings` → list of check failures (if any)

## Reconciliation

Reconciliation compares OCR-extracted values against a secondary source (e.g., CafeF API or structured quarterly data):

```python
from backend.documents.fact_promotion import reconcile_candidate_facts

reconciliation_results = reconcile_candidate_facts(
    candidate_facts, 
    secondary_source="cafef"  # or "api", "manual"
)
```

**Reconciliation Tolerances:**
- **Absolute tolerance:** 1 billion VND (accounts for rounding and unit differences)
- **Relative tolerance:** 0.5% (accounts for reporting vs. accounting period misalignment)

**Reconciliation Status Values:**
- `matched` — Secondary source confirms OCR value (within tolerance)
- `conflicted` — Secondary source contradicts OCR value (exceeds tolerance)
- `missing_secondary_source` — No secondary source available for this metric/period
- `pending` — Reconciliation not yet attempted

## Promotion

Promotion advances validated and reconciled facts to the canonical fact repository. **Promotion is idempotent** — running it twice with the same input produces the same result.

```python
from backend.documents.fact_promotion import promote_candidate_facts

fact_table, promotion_results = promote_candidate_facts(
    candidate_facts,
    require_secondary_confirmation=False  # For critical metrics, set to True
)
```

**Promotion Rules:**

1. **Non-Critical Metrics:** If validation_status == "passed" and confidence >= 0.80, may be promoted even if `reconciliation_status == "missing_secondary_source"`.

2. **Critical Metrics (13 total):** Must have:
   - `validation_status == "passed"`
   - `reconciliation_status == "matched"` (cannot use missing_secondary_source alone)
   
   Critical metrics: revenue.net, gross_profit.total, operating_profit.total, profit_before_tax.total, tax_expense.total, net_income.parent, eps.basic, total_assets.total, equity.total, cash_and_equivalents.total, borrowings.total, operating_cash_flow.total, capex.total

3. **Conflicted Facts:** Are **not** promoted automatically. Manual review required.

4. **Promotion Result:** Successfully promoted facts receive:
   - `promotion_status = "promoted"`
   - A canonical fact ID and timestamp
   - Source tier assignment (Tier 2 for OCR from official PDF)

Facts that fail promotion receive:
- `promotion_status = "blocked"`
- Promotion warnings explaining why (failed validation, missing critical secondary, conflict)
- No canonical fact record is created
