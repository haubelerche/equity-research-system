"""LLM-direct ingestion of user-collected official PDFs into Supabase canonical facts.

Honours the operator decision (2026-06-15): the manually-collected audited PDFs in
``data/official_documents/<T>/<YEAR>/source_document.pdf`` are the authoritative
source. We do NOT call CafeF/vnstock. For each ticker-year we:

  1. ensure the company exists in ref.companies (auto-register, FK prerequisite);
  2. load page text — pdfplumber for text-layer PDFs, Tesseract OCR (vie+eng, 300dpi,
     cached) for scanned PDFs;
  3. extract financial facts with a production LLM (gpt-5-mini) mapped to the 44
     canonical ref.line_items codes (backend.documents.llm_fact_extractor);
  4. write them straight to fact.canonical_facts via upsert_canonical_fact
     (source_tier=1 official PDF, reconciliation_status=missing_api, quality=accepted).

Usage:
    python scripts/ingest_pdf_llm.py --ticker AGP --from-year 2022 --to-year 2025
    python scripts/ingest_pdf_llm.py --ticker AGP --from-year 2024 --to-year 2024 --dry-run
    python scripts/ingest_pdf_llm.py --all --from-year 2022 --to-year 2025
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

OFFICIAL_DOCS_DIR = ROOT / "data" / "official_documents"
OCR_CACHE_DIR = ROOT / "storage" / "sources" / "llm_ocr"
ARTIFACT_DIR = ROOT / "artifacts" / "official_sources"

_PER_SHARE = {"eps.basic", "dividends_per_share.cash", "market_price.close"}
_SHARES = {"shares_outstanding.ending", "shares_outstanding.weighted_avg"}


def _unit_for(metric: str) -> str:
    if metric in _PER_SHARE:
        return "vnd_per_share"
    if metric in _SHARES:
        return "shares"
    return "vnd_bn"


@dataclass
class YearOutcome:
    fiscal_year: int
    source_kind: str = "missing"   # text | ocr | missing
    pages: int = 0
    facts_extracted: int = 0
    facts_written: int = 0          # gaps filled (metrics vnstock lacked)
    facts_skipped: int = 0          # already present in production (vnstock) — left untouched
    metrics: list[str] = field(default_factory=list)
    facts_detail: list[dict] = field(default_factory=list)
    evidence_topics: int = 0        # qualitative evidence topics extracted (Phase 1)
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Company auto-registration (FK prerequisite for fact.canonical_facts)
# ---------------------------------------------------------------------------

def ensure_company(ticker: str, *, dry_run: bool = False) -> None:
    """Insert ticker into ref.companies if absent. Idempotent. No-op on dry-run."""
    ticker = ticker.upper()
    name_vi, name_en, exchange = ticker, None, "UPCOM"
    try:
        from backend.documents.company_registry import get_company, has_company

        if has_company(ticker):
            rec = get_company(ticker)
            name_vi = rec.company_name_vi or ticker
            name_en = getattr(rec, "company_name_en", None)
            exchange = (rec.exchange or "UPCOM").upper() or "UPCOM"
    except Exception:  # noqa: BLE001 — registry optional
        pass
    if dry_run:
        return
    from backend.database.canonical.connection import get_conn

    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ref.companies (ticker, company_name_vi, company_name_en, exchange, sector)
                VALUES (%s, %s, %s, %s, 'pharma')
                ON CONFLICT (ticker) DO NOTHING
                """,
                (ticker, name_vi, name_en, exchange),
            )


# ---------------------------------------------------------------------------
# Page text loading (pdfplumber for text-layer, Tesseract OCR for scanned)
# ---------------------------------------------------------------------------

def load_page_texts(
    pdf_path: Path, ticker: str, fiscal_year: int, *, lang: str = "vie+eng"
) -> tuple[list[tuple[int, str]], str]:
    """Return (pages, kind). kind is 'text' (pdfplumber) or 'ocr' (Tesseract, cached)."""
    import pdfplumber

    with pdfplumber.open(str(pdf_path)) as pdf:
        text_pages = [((i + 1), (p.extract_text() or "")) for i, p in enumerate(pdf.pages)]
    total_chars = sum(len(t) for _, t in text_pages)
    if total_chars > 200:
        return text_pages, "text"

    # Scanned → OCR (with on-disk cache so reruns skip re-OCR).
    cache_dir = OCR_CACHE_DIR / ticker / str(fiscal_year)
    cached = sorted(cache_dir.glob("page_*.txt")) if cache_dir.exists() else []
    if cached:
        pages = []
        for f in cached:
            n = int(f.stem.split("_")[1])
            pages.append((n, f.read_text(encoding="utf-8", errors="replace")))
        return pages, "ocr"

    import pytesseract  # type: ignore
    from pdf2image import convert_from_path  # type: ignore
    from backend.documents.pdf_extractor import _find_tesseract_cmd, _tesseract_config

    cmd = _find_tesseract_cmd()
    if cmd:
        pytesseract.pytesseract.tesseract_cmd = cmd
    config = _tesseract_config()
    images = convert_from_path(str(pdf_path), dpi=300)
    cache_dir.mkdir(parents=True, exist_ok=True)
    pages = []
    for n, image in enumerate(images, start=1):
        try:
            txt = pytesseract.image_to_string(image, lang=lang, config=config)
        except Exception:  # noqa: BLE001
            txt = ""
        (cache_dir / f"page_{n:03d}.txt").write_text(txt, encoding="utf-8")
        pages.append((n, txt))
    return pages, "ocr"


# ---------------------------------------------------------------------------
# Per-ticker run
# ---------------------------------------------------------------------------

def run_year(ticker: str, fiscal_year: int, *, dry_run: bool) -> YearOutcome:
    from backend.documents.llm_fact_extractor import extract_facts_targeted
    from backend.database.canonical.fact_dal import get_production_facts, upsert_canonical_fact

    out = YearOutcome(fiscal_year=fiscal_year)
    pdf_path = OFFICIAL_DOCS_DIR / ticker / str(fiscal_year) / "source_document.pdf"
    if not pdf_path.is_file():
        out.errors.append("source_document.pdf missing (run staging)")
        return out

    try:
        pages, kind = load_page_texts(pdf_path, ticker, fiscal_year)
        out.source_kind, out.pages = kind, len(pages)
    except Exception as exc:  # noqa: BLE001
        out.errors.append(f"page_load: {type(exc).__name__}: {exc}")
        return out

    try:
        facts = extract_facts_targeted(pages, ticker, fiscal_year)
    except Exception as exc:  # noqa: BLE001
        out.errors.append(f"llm_extract: {type(exc).__name__}: {exc}")
        return out
    out.facts_extracted = len(facts)
    out.metrics = sorted(f.metric for f in facts)
    out.facts_detail = [
        {"metric": f.metric, "value": f.value, "unit": _unit_for(f.metric),
         "page": f.page_number, "label": f.source_label, "confidence": f.confidence}
        for f in sorted(facts, key=lambda x: (x.statement_type, x.metric))
    ]

    if dry_run:
        return out

    # Additive-only gap-fill: vnstock is the primary source. Only write a metric that
    # production does NOT already have for this period — never overwrite structured data
    # (OCR can mis-scale, e.g. revenue 4884 → 4.88, and would corrupt good vnstock data).
    existing = {
        (r["period"], r["metric"])
        for r in get_production_facts(ticker=ticker, from_year=fiscal_year, to_year=fiscal_year)
    }
    written = skipped = 0
    for f in facts:
        if (f.period, f.metric) in existing:
            skipped += 1
            continue
        try:
            upsert_canonical_fact(
                ticker=ticker,
                period=f.period,
                metric=f.metric,
                value=f.value,
                unit=_unit_for(f.metric),
                source_tier=1,                       # official audited PDF (LLM-extracted)
                confidence=round(f.confidence, 4),
                quality_status="accepted",
                reconciliation_status="missing_api",
            )
            written += 1
        except Exception as exc:  # noqa: BLE001
            out.errors.append(f"upsert {f.metric}: {type(exc).__name__}: {exc}")
    out.facts_written = written
    out.facts_skipped = skipped

    # Phase 1: also extract + persist the qualitative evidence pack (business segments,
    # market share, catalysts, risks, borrowing/investment plans) from the same PDF.
    # Additive and PDF-sourced; non-fatal so it never blocks fact ingestion.
    try:
        from backend.documents.llm_evidence_extractor import extract_evidence_from_pdf
        from backend.database.company_evidence_dal import upsert_company_evidence

        evidence = extract_evidence_from_pdf(pages, ticker, fiscal_year)
        topics = len(evidence.get("business_evidence") or {}) + len(evidence.get("company_plans") or {})
        upsert_company_evidence(ticker, fiscal_year, evidence, model="gpt-5-mini")
        out.evidence_topics = topics
    except Exception as exc:  # noqa: BLE001 — evidence is additive; never block facts
        out.errors.append(f"evidence: {type(exc).__name__}: {exc}")
    return out


def run_ticker(
    ticker: str, from_year: int, to_year: int, *, dry_run: bool
) -> list[YearOutcome]:
    ticker = ticker.upper()
    print(f"[pdf-llm] {ticker}: ensuring company registration…")
    try:
        ensure_company(ticker, dry_run=dry_run)
    except Exception as exc:  # noqa: BLE001
        print(f"[pdf-llm] {ticker}: company registration failed: {exc}", file=sys.stderr)

    outcomes: list[YearOutcome] = []
    for fy in range(from_year, to_year + 1):
        print(f"[pdf-llm] {ticker} {fy}: extracting…", flush=True)
        out = run_year(ticker, fy, dry_run=dry_run)
        print(
            f"[pdf-llm] {ticker} {fy}: source={out.source_kind} extracted={out.facts_extracted} "
            f"filled={out.facts_written} skipped(already in vnstock)={out.facts_skipped} "
            f"evidence_topics={out.evidence_topics}"
            + (f" errors={len(out.errors)}" if out.errors else "")
        )
        outcomes.append(out)
    return outcomes


def _write_report(ticker: str, outcomes: list[YearOutcome]) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    out = ARTIFACT_DIR / f"{ticker}_pdf_llm_result.json"
    payload = {
        "ticker": ticker,
        "generated_at": datetime.now(UTC).isoformat(),
        "years": [asdict(o) for o in outcomes],
        "total_written": sum(o.facts_written for o in outcomes),
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def _select_tickers(args: argparse.Namespace) -> list[str]:
    if args.all:
        return sorted(p.name.upper() for p in OFFICIAL_DOCS_DIR.iterdir() if p.is_dir())
    return [t.strip().upper() for e in args.tickers for t in str(e).split(",") if t.strip()]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", "--tickers", dest="tickers", nargs="*", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--from-year", type=int, required=True, dest="from_year")
    parser.add_argument("--to-year", type=int, required=True, dest="to_year")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    args = parser.parse_args(argv)

    tickers = _select_tickers(args)
    if not tickers:
        parser.error("provide --ticker or --all")

    grand = 0
    for ticker in tickers:
        outcomes = run_ticker(ticker, args.from_year, args.to_year, dry_run=args.dry_run)
        report = _write_report(ticker, outcomes)
        written = sum(o.facts_written for o in outcomes)
        grand += written
        print(f"[pdf-llm] {ticker}: total_written={written} report={report}")

    try:
        from backend.harness.model_adapter import flush_traces

        flush_traces()
    except Exception:  # noqa: BLE001
        pass
    print(f"[pdf-llm] DONE tickers={len(tickers)} total_written={grand}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
