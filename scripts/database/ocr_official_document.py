"""OCR an existing governed official PDF into page artifacts for build_index."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.documents.ocr_artifacts import (
    compute_file_checksum,
    finalize_ocr_run,
    init_ocr_run,
    save_page_text,
)


def _find_tesseract() -> str:
    found = shutil.which("tesseract")
    common = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
    if found:
        return found
    if common.exists():
        return str(common)
    raise RuntimeError("tesseract executable not found")


def _find_poppler_bin() -> str:
    found = shutil.which("pdftoppm")
    if found:
        return str(Path(found).parent)
    winget = Path.home() / "AppData" / "Local" / "Microsoft" / "WinGet" / "Packages"
    matches = list(winget.glob("oschwartz10612.Poppler_*/*/Library/bin/pdftoppm.exe"))
    if matches:
        return str(matches[0].parent)
    raise RuntimeError("pdftoppm executable not found")


def _tesseract_config() -> str:
    tessdata_dir = ROOT / "storage" / "tessdata"
    if tessdata_dir.is_dir():
        return f'--tessdata-dir "{tessdata_dir}"'
    return ""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", required=True, type=Path)
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--fiscal-year", required=True, type=int)
    parser.add_argument("--lang", default="eng")
    parser.add_argument("--dpi", default=200, type=int)
    args = parser.parse_args()

    import pytesseract
    from pdf2image import convert_from_path

    pdf_path = args.pdf.resolve()
    checksum = compute_file_checksum(pdf_path)
    document_id = f"{args.ticker.upper()}_{args.fiscal_year}_{checksum[:12]}"
    base_dir = ROOT / "storage" / "sources" / "ocr_artifacts"
    metadata, run_dir = init_ocr_run(
        ticker=args.ticker.upper(),
        fiscal_year=args.fiscal_year,
        document_id=document_id,
        source_uri=str(pdf_path),
        source_checksum=checksum,
        pdf_type="scanned",
        ocr_lang=args.lang,
        dpi=args.dpi,
        base_dir=base_dir,
    )
    pytesseract.pytesseract.tesseract_cmd = _find_tesseract()
    images = convert_from_path(str(pdf_path), dpi=args.dpi, poppler_path=_find_poppler_bin())
    failures: list[str] = []
    processed = 0
    tess_config = _tesseract_config()
    for page_number, image in enumerate(images, start=1):
        try:
            text = pytesseract.image_to_string(image, lang=args.lang, config=tess_config)
            save_page_text(run_dir, page_number, text)
            processed += 1
            print(f"OCR page={page_number} chars={len(text)}")
        except Exception as exc:
            failures.append(f"page={page_number}: {type(exc).__name__}: {exc}")
    finalize_ocr_run(
        run_dir,
        metadata,
        pages_processed=processed,
        pages_failed=len(failures),
        candidate_row_count=0,
        mapped_fact_count=0,
        warnings=["english_only_ocr"] if args.lang == "eng" else [],
        errors=failures,
        status="completed" if processed > 0 else "failed",
    )
    print(f"artifact_dir={run_dir} pages_processed={processed} pages_failed={len(failures)}")
    return 0 if processed > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
