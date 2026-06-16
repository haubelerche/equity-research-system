"""Extract financial facts from existing OCR page artifacts and export to golden CSV.

The OCR pipeline (ocr_official_document.py) successfully extracts raw page text
from scanned Vietnamese annual report PDFs. However, the text layout loses table
structure — labels and numeric values appear on separate lines rather than side-by-side.

This script applies a two-pass heuristic to reconstruct label-value pairs:
  Pass 1: Try _parse_ocr_text_to_rows() (works for text-based PDFs)
  Pass 2: Pair consecutive lines where one is a Vietnamese label and the
          next is a number group (works for scanned PDFs with columnar layout)

Usage:
    python scripts/extract_facts_from_ocr.py --ticker DHG --fiscal-year 2025
    python scripts/extract_facts_from_ocr.py --ticker DHG  # all available OCR runs
    python scripts/extract_facts_from_ocr.py --ticker DHG --dry-run

Output:
    mapped_candidate_facts.csv written to each OCR artifact directory
    Facts appended to config/benchmarks/shared/golden_financials/<TICKER>.csv
    Provenance JSON updated with source_tier=2 (OCR-extracted, pre-audit cross-check needed)
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.evaluation.benchmark_paths import GOLDEN_FINANCIALS_DIR

OCR_BASE = ROOT / "storage" / "sources" / "ocr_artifacts"
GOLDEN_DIR = GOLDEN_FINANCIALS_DIR
MAPPED_FACT_ROWS_FILENAME = "mapped_candidate_facts.csv"

GOLDEN_CSV_FIELDS = [
    "ticker", "fiscal_year", "period", "statement_type", "canonical_key",
    "raw_label", "value", "unit", "currency", "source_type", "source_uri",
    "source_title", "provider", "confidence", "validation_status",
]

# Numeric pattern for Vietnamese financial statement values (raw VND, thousands VND, or tỷ VND)
_NUM_RE = re.compile(r"^[\d,.]+$")
# Vietnamese thousands separator pattern: "6.136.905.368.338"
_VN_THOUSANDS_RE = re.compile(r"^\d{1,3}(?:\.\d{3})+$")
# Numbers in parentheses = negative: "(273,600)"
_NEG_RE = re.compile(r"^\([\d,.]+\)$")


def _slug_label(text: str) -> str:
    normalized = unicodedata.normalize("NFD", text)
    ascii_only = "".join(c for c in normalized if unicodedata.category(c) != "Mn")
    ascii_only = ascii_only.replace("đ", "d").replace("Đ", "D")
    ascii_only = ascii_only.replace("đ", "d").replace("Đ", "D")
    ascii_only = ascii_only.encode("ascii", errors="ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_only.lower().strip())


def _parse_vnd_raw(raw: str) -> Optional[float]:
    """Parse a raw Vietnamese financial value to tỷ VND.

    Handles:
    - Vietnamese dot-thousands separator: "6.136.905.368.338" → 6136.9 tỷ
    - Comma thousands: "4,127,400" → 4,127.4 tỷ (triệu → tỷ)
    - Negative in parens: "(273,600)"
    - Plain tỷ values already: "4127.4"
    """
    s = raw.strip()
    if not s or s in ("—", "-", "n/a", "N/A", ""):
        return None
    negative = False
    if s.startswith("(") and s.endswith(")"):
        negative = True
        s = s[1:-1]

    # Vietnamese dot-thousands: "6.136.905.368.338"
    if _VN_THOUSANDS_RE.match(s):
        # This is raw VND — convert to tỷ VND (÷ 1_000_000_000)
        val = float(s.replace(".", ""))
        return -(val / 1_000_000_000) if negative else (val / 1_000_000_000)

    # Comma thousands: "4,127,400" assumed triệu VND → ÷ 1000 to get tỷ
    has_commas = "," in s
    s_clean = s.replace(",", "")
    try:
        val = float(s_clean)
    except ValueError:
        return None
    if has_commas and val > 500:
        val = val / 1000  # triệu → tỷ
    return -val if negative else val


def _detect_statement_type(slug: str) -> Optional[str]:
    if any(k in slug for k in ("ket qua hoat dong", "doanh thu", "loi nhuan")):
        return "income_statement"
    if any(k in slug for k in ("can doi ke toan", "tai san", "nguon von")):
        return "balance_sheet"
    if any(k in slug for k in ("luu chuyen tien", "tien va tuong duong tien")):
        return "cash_flow_statement"
    return None


def _load_metric_patterns() -> dict[str, str]:
    """Load Vietnamese label → canonical_key mapping from pdf_extractor."""
    try:
        from backend.documents.pdf_extractor import _map_label_to_metric  # noqa: PLC0415
        return _map_label_to_metric
    except Exception:
        return {}


def _map_label(slug: str) -> Optional[str]:
    try:
        from backend.documents.pdf_extractor import _map_label_to_metric  # noqa: PLC0415
        return _map_label_to_metric(slug)
    except Exception:
        return None


def _is_numeric_line(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    s = s.lstrip("(").rstrip(")")
    return bool(_NUM_RE.match(s.replace(",", "").replace(".", "")))


def _extract_from_page_text(
    page_text: str,
    ticker: str,
    fiscal_year: int,
    page_number: int,
    statement_type: Optional[str],
) -> list[dict]:
    """Extract (label, value) pairs from OCR page text using two-pass heuristic."""
    # Pass 1: same-line pattern "LABEL  NUMBER"
    same_line_re = re.compile(r"^(.{5,80}?)\s{2,}([\d,.()—\-]+)\s*$")
    rows: list[dict] = []
    lines = [ln.strip() for ln in page_text.splitlines()]

    # Detect statement type from page if not provided
    page_slug = _slug_label(page_text[:500])
    stmt_type = statement_type or _detect_statement_type(page_slug)

    def _make_row(label: str, raw_val: str, stmt: str) -> Optional[dict]:
        slug = _slug_label(label)
        canonical_key = _map_label(slug)
        if canonical_key is None:
            return None
        val = _parse_vnd_raw(raw_val)
        if val is None:
            return None
        # Filter out Vietnamese Mã số codes (100, 200, ... 500 range) — these are template
        # line-item identifiers printed in the statement, NOT financial values.
        # Also filter suspiciously small values (< 0.5 tỷ) for balance-sheet metrics.
        if val == round(val) and 1 <= abs(val) <= 999:
            return None
        period = f"{fiscal_year}FY"
        return {
            "ticker": ticker,
            "fiscal_year": fiscal_year,
            "period": period,
            "statement_type": stmt,
            "canonical_key": canonical_key,
            "raw_label": label,
            "value": round(val, 6),
            "unit": "vnd_bn",
            "currency": "VND",
            "source_type": "ocr_extracted",
            "source_uri": f"ocr://pages/page_{page_number:03d}.txt",
            "source_title": f"OCR {ticker} FY{fiscal_year} p{page_number}",
            "provider": "tesseract_ocr",
            "confidence": 0.70,
            "validation_status": "accepted",
            "page_number": page_number,
        }

    # Pass 1: same-line
    for line in lines:
        m = same_line_re.match(line)
        if m and stmt_type:
            row = _make_row(m.group(1).strip(), m.group(2).strip(), stmt_type)
            if row:
                rows.append(row)

    if rows:
        return rows

    # Pass 2: consecutive-line for scanned PDFs (label on one line, value on next)
    # We track a "last label candidate" and pair it with the first numeric line after it.
    last_label: Optional[str] = None
    last_label_stmt: Optional[str] = None

    i = 0
    while i < len(lines):
        line = lines[i]
        slug = _slug_label(line)

        # Update statement type when we see a statement header
        detected = _detect_statement_type(slug)
        if detected:
            stmt_type = detected

        # Check if this line could be a label (non-numeric, min 5 chars, Vietnamese text)
        if len(line) >= 5 and not _is_numeric_line(line) and stmt_type:
            canonical_key = _map_label(slug)
            if canonical_key:
                last_label = line
                last_label_stmt = stmt_type
        elif _is_numeric_line(line) and last_label and last_label_stmt:
            row = _make_row(last_label, line, last_label_stmt)
            if row:
                rows.append(row)
            last_label = None  # consume the label

        i += 1

    return rows


def process_ocr_run(
    run_dir: Path,
    ticker: str,
    fiscal_year: int,
    *,
    dry_run: bool = False,
) -> list[dict]:
    """Process all page text files in an OCR artifact run directory."""
    pages_dir = run_dir / "pages"
    if not pages_dir.exists():
        print(f"  No pages/ dir in {run_dir.name}")
        return []

    page_files = sorted(pages_dir.glob("page_*.txt"))
    if not page_files:
        print(f"  No page_*.txt files in {run_dir.name}")
        return []

    print(f"  Processing {len(page_files)} pages in {run_dir.name} …")
    all_rows: list[dict] = []
    current_statement: Optional[str] = None

    for page_file in page_files:
        page_num = int(re.search(r"page_(\d+)", page_file.name).group(1))
        text = page_file.read_text(encoding="utf-8", errors="replace")
        page_slug = _slug_label(text[:500])
        detected = _detect_statement_type(page_slug)
        if detected:
            current_statement = detected
        rows = _extract_from_page_text(text, ticker, fiscal_year, page_num, current_statement)
        all_rows.extend(rows)

    # Deduplicate by (ticker, fiscal_year, canonical_key, page_number)
    seen: dict[tuple, dict] = {}
    for row in all_rows:
        key = (row["ticker"], row["fiscal_year"], row["canonical_key"])
        if key not in seen:
            seen[key] = row
    unique_rows = list(seen.values())

    print(f"  Extracted {len(unique_rows)} unique facts from {len(page_files)} pages.")

    if not dry_run:
        # Keep raw OCR parser artifacts and mapped fact exports separate. The
        # backend OCR artifact contract owns candidate_rows.csv as raw
        # page_number/raw_label/raw_value rows.
        cand_path = run_dir / MAPPED_FACT_ROWS_FILENAME
        with cand_path.open("w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=GOLDEN_CSV_FIELDS + ["page_number"])
            writer.writeheader()
            for row in unique_rows:
                writer.writerow({k: row.get(k, "") for k in GOLDEN_CSV_FIELDS + ["page_number"]})

        # Update metadata mapped_fact_count
        meta_path = run_dir / "metadata.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                meta["mapped_fact_count"] = len(unique_rows)
                meta["candidate_row_count"] = len(all_rows)
                meta["warnings"] = [w for w in meta.get("warnings", []) if w != "no_facts_extracted"]
                if not unique_rows:
                    meta["warnings"].append("no_facts_extracted")
                meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
            except Exception as exc:
                print(f"  Warning: could not update metadata.json: {exc}")

    return unique_rows


def export_to_golden_csv(rows: list[dict], ticker: str, fiscal_year: int) -> None:
    """Append OCR-extracted rows to the golden CSV for this ticker."""
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    out_path = GOLDEN_DIR / f"{ticker}.csv"

    existing: list[dict] = []
    if out_path.exists():
        with out_path.open(newline="", encoding="utf-8") as fh:
            existing = list(csv.DictReader(fh))

    # Keys that OCR covers — remove ANY existing rows for same (ticker, fiscal_year, canonical_key)
    # so OCR replaces VNStock Tier-3 data for those specific metrics (avoids duplicate_fact_count)
    ocr_keys = {(str(fiscal_year), r.get("canonical_key", "")) for r in rows}
    existing = [
        r for r in existing
        if not (
            str(r.get("fiscal_year")) == str(fiscal_year)
            and (str(fiscal_year), r.get("canonical_key", "")) in ocr_keys
        )
    ]

    all_rows = existing + rows
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=GOLDEN_CSV_FIELDS)
        writer.writeheader()
        for row in all_rows:
            writer.writerow({k: row.get(k, "") for k in GOLDEN_CSV_FIELDS})

    # Update provenance JSON
    prov_path = GOLDEN_DIR / f"{ticker}_golden_provenance.json"
    prov: dict = {}
    if prov_path.exists():
        try:
            prov = json.loads(prov_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    ocr_metrics = sorted({str(r.get("canonical_key") or "") for r in rows if r.get("canonical_key")})
    existing_metrics = list(prov.get("metrics_verified") or [])
    merged_metrics = sorted(set(existing_metrics) | set(ocr_metrics))

    # Only upgrade source_tier to 2 if currently 3 (OCR is better than pure aggregator)
    current_tier = int(prov.get("source_tier") or 3)
    new_tier = min(current_tier, 2) if rows else current_tier

    prov.update({
        "ticker": ticker,
        "source_tier": new_tier,
        "verified_by": prov.get("verified_by", "ocr_extraction"),
        "verification_date": prov.get("verification_date", datetime.now(timezone.utc).date().isoformat()),
        "source_document_type": prov.get("source_document_type", "ocr_extracted_annual_report"),
        "metrics_verified": merged_metrics,
        "ocr_export_at": datetime.now(timezone.utc).isoformat(),
        "ocr_facts_added": len(rows),
    })
    prov_path.write_text(json.dumps(prov, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Exported {len(rows)} OCR facts -> {out_path.name} (provenance tier={new_tier})")


def run_for_ticker(
    ticker: str,
    fiscal_year: Optional[int] = None,
    *,
    dry_run: bool = False,
) -> list[dict]:
    """Extract OCR facts for a ticker and export them to its golden CSV (benchmark dataset).

    Reads existing OCR page artifacts under storage/sources/ocr_artifacts/<TICKER>/.
    Returns the list of exported fact rows (empty if no OCR artifacts or no facts).
    Safe to call when a ticker has no OCR artifacts — returns [] without raising.
    """
    ticker = ticker.upper()
    ticker_ocr_dir = OCR_BASE / ticker
    if not ticker_ocr_dir.exists():
        print(f"No OCR artifacts for {ticker} at {ticker_ocr_dir}")
        return []

    all_exported: list[dict] = []
    year_dirs = sorted(ticker_ocr_dir.iterdir()) if ticker_ocr_dir.is_dir() else []
    for year_dir in year_dirs:
        if not year_dir.is_dir():
            continue
        try:
            fy = int(year_dir.name)
        except ValueError:
            continue
        if fiscal_year and fy != fiscal_year:
            continue

        run_dirs = sorted(year_dir.iterdir()) if year_dir.is_dir() else []
        for run_dir in run_dirs:
            if not run_dir.is_dir():
                continue
            print(f"[{ticker}/{fy}] {run_dir.name}")
            rows = process_ocr_run(run_dir, ticker, fy, dry_run=dry_run)
            all_exported.extend(rows)

    if not all_exported:
        print(f"No facts extracted for {ticker}. Check OCR page quality.")
        return []

    if not dry_run:
        # Group by fiscal year for export
        by_year: dict[int, list[dict]] = {}
        for row in all_exported:
            fy = int(row.get("fiscal_year") or 0)
            by_year.setdefault(fy, []).append(row)
        for fy, rows in by_year.items():
            export_to_golden_csv(rows, ticker, fy)

    print(f"\nTotal facts extracted: {len(all_exported)}")
    return all_exported


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", required=True, help="Ticker to process (e.g. DHG)")
    parser.add_argument("--fiscal-year", type=int, default=None, help="Specific fiscal year; defaults to all available")
    parser.add_argument("--dry-run", action="store_true", help="Parse and count facts without writing output")
    args = parser.parse_args()

    ticker = args.ticker.upper()
    if not (OCR_BASE / ticker).exists():
        print(f"No OCR artifacts for {ticker} at {OCR_BASE / ticker}")
        return 1
    run_for_ticker(ticker, args.fiscal_year, dry_run=args.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
