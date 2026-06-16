"""Ingest AGM (ĐHCĐ) decision PDFs into research.agm_resolutions on Supabase.

The 2026 annual-general-meeting packets in ``config/dataset/DHCD/`` carry the
shareholder-APPROVED forward plan (nghị quyết + báo cáo HĐQT/ban giám đốc + KQKD 2025 +
kế hoạch 2026 + tờ trình). For each ticker we:

  1. resolve + group the (possibly multi-part) PDFs;
  2. load page text — pdfplumber for text-layer, Tesseract OCR (vie+eng, cached) for scans;
  3. extract the two-layer agm_pack (approved_resolutions + forward drivers dug out of the
     backing tờ trình) with a production LLM (gpt-5-mini);
  4. upsert it (one row per ticker-meeting) — additive, forward-only; historical
     vnstock/PDF facts are untouched. The forecast path reads it as a PRIORITY driver.

Usage:
    python scripts/ingest_agm.py --ticker DHG,DBD
    python scripts/ingest_agm.py --ticker DHG --dry-run
    python scripts/ingest_agm.py --all
"""
from __future__ import annotations

import argparse
import hashlib
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

DHCD_DIR = ROOT / "config" / "dataset" / "DHCD"
ARTIFACT_DIR = ROOT / "artifacts" / "official_sources"
OCR_CACHE_DIR = ROOT / "storage" / "sources" / "agm_ocr"
MEETING_YEAR = 2026


# ---------------------------------------------------------------------------
# Filesystem resolution + page loading (offline; the backend run-path never globs)
# ---------------------------------------------------------------------------

def resolve_agm_files(directory: Path) -> dict[str, list[Path]]:
    """Glob *.pdf in *directory* and group them by ticker (base file first)."""
    from backend.documents.agm_source import group_agm_files

    return group_agm_files(sorted(directory.glob("*.pdf")))


def load_agm_pages(
    paths: list[Path], ticker: str, meeting_year: int, *, lang: str = "vie+eng"
) -> tuple[list[tuple[int, str]], str, dict[int, str]]:
    """Load concatenated page text across the ticker's part files.

    Returns (pages, kind, page_source_map): pages are continuously numbered across
    parts; kind is 'text' if any part had a text layer else 'ocr'; page_source_map
    maps each page number to the originating filename."""
    from scripts.pdf_pages import load_pdf_pages

    pages: list[tuple[int, str]] = []
    page_source: dict[int, str] = {}
    kinds: set[str] = set()
    next_no = 1
    for path in paths:
        cache_dir = OCR_CACHE_DIR / ticker.upper() / str(meeting_year) / path.stem
        part_pages, kind = load_pdf_pages(path, cache_dir=cache_dir, lang=lang)
        kinds.add(kind)
        for _orig_no, text in part_pages:
            pages.append((next_no, text))
            page_source[next_no] = path.name
            next_no += 1
    kind = "text" if "text" in kinds else ("ocr" if kinds else "missing")
    return pages, kind, page_source


@dataclass
class AgmOutcome:
    ticker: str
    meeting_year: int = MEETING_YEAR
    source_kind: str = "missing"          # text | ocr | missing
    files: list[str] = field(default_factory=list)
    pages: int = 0
    approved_resolutions: int = 0
    drivers: dict = field(default_factory=dict)   # counts per driver section
    errors: list[str] = field(default_factory=list)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def run_ticker(
    ticker: str, paths: list[Path], *, dry_run: bool
) -> AgmOutcome:
    from backend.documents.agm_extractor import extract_agm_from_pdf

    out = AgmOutcome(ticker=ticker, files=[p.name for p in paths])
    if not paths:
        out.errors.append("no AGM PDF found")
        return out

    try:
        pages, kind, _page_source = load_agm_pages(paths, ticker, MEETING_YEAR)
        out.source_kind, out.pages = kind, len(pages)
    except Exception as exc:  # noqa: BLE001
        out.errors.append(f"page_load: {type(exc).__name__}: {exc}")
        return out

    try:
        pack = extract_agm_from_pdf(pages, ticker, MEETING_YEAR)
    except Exception as exc:  # noqa: BLE001
        out.errors.append(f"llm_extract: {type(exc).__name__}: {exc}")
        return out

    out.approved_resolutions = len(pack.get("approved_resolutions") or [])
    out.drivers = {
        k: len(pack.get(k) or [])
        for k in ("dividend_plan", "borrowing_plan", "investment_plan",
                  "rnd_and_product_focus", "business_direction")
    }
    out.drivers["targets_2026"] = 1 if pack.get("targets_2026") else 0

    if dry_run:
        return out

    source_docs = [
        {"file": p.name, "sha256": _sha256(p)} for p in paths
    ]
    try:
        from backend.database.agm_dal import upsert_agm_resolutions

        upsert_agm_resolutions(
            ticker, MEETING_YEAR, pack, source_docs=source_docs, model="gpt-5-mini"
        )
    except Exception as exc:  # noqa: BLE001
        out.errors.append(f"upsert: {type(exc).__name__}: {exc}")
    return out


def _write_report(ticker: str, outcome: AgmOutcome) -> Path:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    path = ARTIFACT_DIR / f"{ticker}_agm_result.json"
    payload = {
        "ticker": ticker,
        "generated_at": datetime.now(UTC).isoformat(),
        "outcome": asdict(outcome),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _select(args: argparse.Namespace, grouped: dict[str, list[Path]]) -> list[str]:
    if args.all:
        return sorted(grouped)
    requested = [t.strip().upper() for e in args.tickers for t in str(e).split(",") if t.strip()]
    return requested


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ticker", "--tickers", dest="tickers", nargs="*", default=[])
    parser.add_argument("--all", action="store_true")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    args = parser.parse_args(argv)

    grouped = resolve_agm_files(DHCD_DIR)
    tickers = _select(args, grouped)
    if not tickers:
        parser.error("provide --ticker or --all")

    for ticker in tickers:
        paths = grouped.get(ticker, [])
        print(f"[agm] {ticker}: files={len(paths)} extracting…", flush=True)
        outcome = run_ticker(ticker, paths, dry_run=args.dry_run)
        report = _write_report(ticker, outcome)
        print(
            f"[agm] {ticker}: source={outcome.source_kind} pages={outcome.pages} "
            f"resolutions={outcome.approved_resolutions} drivers={outcome.drivers}"
            + (f" errors={outcome.errors}" if outcome.errors else "")
            + f" report={report}"
        )

    try:
        from backend.harness.model_adapter import flush_traces

        flush_traces()
    except Exception:  # noqa: BLE001
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
