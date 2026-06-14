"""Phase 5  Evidence Index Builder.

Synthesizes grounded text evidence chunks from accepted canonical financial
facts and catalyst events, then stores them in ingest.document_chunks so the
report generator can cite them.

Sources indexed (in priority order):
  1. Official PDF pages  text extracted by pdfplumber, page by page
  2. OCR page artifacts  data/ocr_artifacts/{ticker}/{year}/{doc_id}/pages/
  3. External .txt documents  data/documents/{ticker}/
  4. Synthetic fact chunks  built from accepted canonical facts in DB

All chunks include metadata_json with extraction_method, page_number (where
applicable), source_tier, and document_id for downstream citation resolution.

Usage:
    python scripts/build_index.py --ticker DHG
    python scripts/build_index.py --ticker DHG --from-year 2022 --to-year 2025
    python scripts/build_index.py --ticker DHG --years 2022 2023 2024 2025
    python scripts/build_index.py --ticker DHG --doc-dir data/documents/DHG
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import textwrap
from datetime import UTC, datetime
from pathlib import Path

_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

_env_file = Path(__file__).resolve().parents[1] / ".env"
if _env_file.exists():
    for _line in _env_file.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip(chr(34)).strip(chr(39)))

import psycopg2
import psycopg2.extras

from backend.database.canonical.source_dal import upsert_source_document
from backend.database.config import connect_with_retry, require_database_url
from backend.period_scope import DEFAULT_FROM_YEAR, DEFAULT_TO_YEAR

ROOT = Path(__file__).resolve().parents[1]
DOC_DIR = ROOT / "storage" / "sources" / "documents"
OCR_ARTIFACTS_DIR = ROOT / "storage" / "sources" / "ocr_artifacts"
OFFICIAL_DOCS_DIR = ROOT / "storage" / "sources" / "official_documents"


_FACT_LABEL = {
    "revenue.net": "Doanh thu thuần",
    "gross_profit.total": "Lợi nhuận gộp",
    "net_income.parent": "Lợi nhuận sau thuế (cổ đông công ty mẹ)",
    "operating_cash_flow.total": "Dòng tiền từ hoạt động kinh doanh",
    "free_cash_flow.total": "Dòng tiền tự do",
    "total_assets.ending": "Tổng tài sản",
    "equity.parent": "Vốn chủ sở hữu (cổ đông công ty mẹ)",
    "eps.basic": "EPS cơ bản",
    "ebitda.total": "EBITDA",
    "capex.total": "Chi đầu tư TSCĐ (CAPEX)",
    "total_liabilities.ending": "Tổng nợ phải trả",
    "cash_and_equivalents.ending": "Tiền và tương đương tiền",
    "short_term_debt.ending": "Vay ngắn hạn",
    "interest_expense.total": "Chi phí lãi vay",
    "depreciation.total": "Khấu hao",
    "profit_before_tax.total": "Lợi nhuận trước thuế",
    "cogs.total": "Giá vốn hàng bán",
    "sga.total": "Chi phí bán hàng và quản lý",
    "inventory.ending": "Hàng tồn kho",
    "accounts_receivable.ending": "Phải thu khách hàng",
}

_STATEMENT_CONTEXT = {
    "income_statement": "Báo cáo kết quả kinh doanh",
    "balance_sheet": "Bảng cân đối kế toán",
    "cash_flow": "Báo cáo lưu chuyển tiền tệ",
}


def _dsn() -> str:
    return require_database_url()


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def _get_accepted_facts(conn, ticker: str, years: list[int]) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            WITH ranked_facts AS (
                SELECT ff.*,
                       ROW_NUMBER() OVER (
                           PARTITION BY ff.ticker, ff.period, ff.metric
                           ORDER BY ff.source_tier ASC NULLS LAST,
                                    ff.confidence DESC NULLS LAST,
                                    ff.updated_at DESC,
                                    ff.fact_id DESC
                       ) AS winner_rank
                FROM fact.production_facts ff
                WHERE ff.ticker = %s
                  AND CAST(SUBSTRING(ff.period, 1, 4) AS SMALLINT) = ANY(%s)
            )
            SELECT ff.fact_id AS id, ff.ticker,
                   CAST(SUBSTRING(ff.period, 1, 4) AS SMALLINT) AS fiscal_year,
                   'FY' AS fiscal_period,
                   ff.metric AS line_item_code, ff.value, ff.unit, ff.currency,
                   li.statement_type
            FROM ranked_facts ff
            LEFT JOIN ref.line_items li ON li.line_item_code = ff.metric
            WHERE ff.winner_rank = 1
            ORDER BY ff.period, ff.metric
            """,
            (ticker, years),
        )
        return [dict(r) for r in cur.fetchall()]


def _get_catalyst_events(conn, ticker: str) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT event_id, ticker, event_type, occurred_at AS event_date,
                   title, summary AS description, source_url AS source_uri
            FROM fact.catalyst_events
            WHERE ticker = %s
            ORDER BY occurred_at DESC
            LIMIT 50
            """,
            (ticker,),
        )
        return [dict(r) for r in cur.fetchall()]


def _ensure_synthetic_source(conn, ticker: str) -> str:
    source_uri = f"internal://canonical_facts/{ticker}"
    checksum = _sha(source_uri)
    return upsert_source_document(
        ticker=ticker,
        source_type="vnstock_financial",
        source_tier=3,
        source_uri=source_uri,
        checksum=checksum,
        source_title=f"Synthetic evidence from canonical financial facts - {ticker}",
        connector_version="1.0",
        metadata={"synthetic": True},
    )


def _ensure_doc_source(conn, ticker: str, doc_path: Path) -> str:
    checksum = _sha(str(doc_path))
    return upsert_source_document(
        ticker=ticker,
        source_type="annual_report",
        source_tier=1,
        source_uri=str(doc_path),
        checksum=checksum,
        source_title=doc_path.stem,
        connector_version="1.0",
        metadata={"local_path": str(doc_path)},
    )


def _build_fact_chunks(facts: list[dict]) -> list[tuple[str, str, int | None]]:
    """Group facts by fiscal_year and build one narrative chunk per year."""
    by_year: dict[int, list[dict]] = {}
    for f in facts:
        by_year.setdefault(f["fiscal_year"], []).append(f)

    chunks: list[tuple[str, str, int | None]] = []  # (section_title, chunk_text, fiscal_year)
    for year in sorted(by_year):
        year_facts = by_year[year]
        lines = [f"## Tóm tắt tài chính {ticker_placeholder} năm {year} (FY)\n"]
        for f in sorted(year_facts, key=lambda x: x["line_item_code"]):
            label = _FACT_LABEL.get(f["line_item_code"], f["line_item_code"])
            unit = f.get("unit", "")
            val = f["value"]
            if unit == "vnd_bn":
                formatted = f"{val:,.1f} tỷ VND"
            elif unit == "vnd":
                formatted = f"{val:,.0f} VND"
            elif unit == "ratio":
                formatted = f"{val:.4f}"
            elif unit == "percent":
                formatted = f"{val:.2%}"
            else:
                formatted = str(val)
            currency = f.get("currency", "VND")
            stmt = _STATEMENT_CONTEXT.get(f.get("statement_type") or "", "")
            lines.append(f"- {label} ({stmt}): {formatted} ({currency})")
        lines.append(f"\nDữ liệu từ báo cáo tài chính kiểm toán năm {year}.")
        chunks.append((f"Financial Data {year}FY", "\n".join(lines), year))
    return chunks


def _build_catalyst_chunk(events: list[dict]) -> tuple[str, str, int | None] | None:
    if not events:
        return None
    lines = ["## Sự kiện doanh nghiệp và môi trường kinh doanh\n"]
    for ev in events[:20]:
        date_str = str(ev.get("event_date", ""))[:10]
        event_type = ev.get("event_type", "")
        title = ev.get("title", "")
        desc = (ev.get("description") or "")[:200]
        lines.append(f"- [{date_str}] ({event_type}) {title}: {desc}")
    return ("Catalyst Events", "\n".join(lines), None)


def _ensure_ocr_source(conn, ticker: str, fiscal_year: int, document_id: str, meta: dict) -> str:
    """Register an OCR document in ingest.source_documents. Returns source_doc_id."""
    source_uri = meta.get("source_uri", f"ocr://{ticker}/{fiscal_year}/{document_id}")
    raw_checksum = meta.get("source_checksum", "")
    checksum = (raw_checksum if len(raw_checksum) == 64
                else hashlib.sha256(f"ocr_{ticker}_{fiscal_year}_{document_id}".encode()).hexdigest())
    return upsert_source_document(
        ticker=ticker,
        source_type="annual_report",
        source_tier=1,
        source_uri=source_uri,
        checksum=checksum,
        source_title=f"BCTC {ticker} {fiscal_year}FY - OCR ({document_id[:8]})",
        fiscal_year=fiscal_year,
        fiscal_period="FY",
        connector_version="1.0",
        metadata={
            "ocr_run_id": meta.get("ocr_run_id", ""),
            "document_id": document_id,
            "local_path": source_uri,
        },
    )


def _ensure_pdf_source(conn, ticker: str, fiscal_year: int, pdf_path: Path) -> str:
    """Register a text-based official PDF in ingest.source_documents. Returns source_doc_id."""
    checksum = hashlib.sha256(str(pdf_path).encode()).hexdigest()
    return upsert_source_document(
        ticker=ticker,
        source_type="annual_report",
        source_tier=1,
        source_uri=str(pdf_path),
        checksum=checksum,
        source_title=f"BCTC {ticker} {fiscal_year}FY - PDF ({pdf_path.name[:30]})",
        fiscal_year=fiscal_year,
        fiscal_period="FY",
        connector_version="1.0",
        metadata={"local_path": str(pdf_path)},
    )


def _upsert_chunks(conn, source_id: str, ticker: str, chunks: list[tuple[str, str, int | None]]) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for idx, (section_title, chunk_text, fiscal_year) in enumerate(chunks):
            checksum = _sha(chunk_text)
            # Check existing
            cur.execute(
                "SELECT chunk_id FROM ingest.document_chunks WHERE source_doc_id=%s AND chunk_index=%s",
                (source_id, idx),
            )
            existing = cur.fetchone()
            meta = {"checksum": checksum}
            if fiscal_year:
                meta["fiscal_year"] = fiscal_year
            if existing:
                cur.execute(
                    """UPDATE ingest.document_chunks
                       SET chunk_text=%s, section_title=%s, fiscal_year=%s,
                           metadata_json=%s::jsonb
                       WHERE source_doc_id=%s AND chunk_index=%s""",
                    (chunk_text, section_title, fiscal_year, json.dumps(meta), source_id, idx),
                )
            else:
                cur.execute(
                    """INSERT INTO ingest.document_chunks
                           (source_doc_id, ticker, chunk_index, section_title, chunk_text,
                            fiscal_year, language, metadata_json)
                       VALUES (%s,%s,%s,%s,%s,%s,'vi',%s::jsonb)
                       ON CONFLICT (source_doc_id, chunk_index) DO UPDATE
                       SET chunk_text=EXCLUDED.chunk_text,
                           section_title=EXCLUDED.section_title,
                           fiscal_year=EXCLUDED.fiscal_year,
                           metadata_json=EXCLUDED.metadata_json""",
                    (source_id, ticker, idx, section_title, chunk_text, fiscal_year, json.dumps(meta)),
                )
                inserted += 1
    return inserted


def _upsert_page_chunks(
    conn,
    source_id: str,
    ticker: str,
    page_chunks: list[tuple[str, str, int, int, dict]],
) -> int:
    """Upsert page-level chunks (OCR or PDF text) with full citation metadata.

    page_chunks: list of (section_title, chunk_text, fiscal_year, page_number, extra_meta)
    chunk_index = page_number - 1 (0-based, preserving page order and idempotency key).
    Returns number of newly inserted chunks.
    """
    inserted = 0
    with conn.cursor() as cur:
        for section_title, chunk_text, fiscal_year, page_number, extra_meta in page_chunks:
            if not chunk_text.strip():
                continue
            chunk_index = page_number - 1
            checksum = _sha(chunk_text)
            meta = {
                "checksum": checksum,
                "fiscal_year": fiscal_year,
                **extra_meta,
            }
            cur.execute(
                "SELECT chunk_id FROM ingest.document_chunks WHERE source_doc_id=%s AND chunk_index=%s",
                (source_id, chunk_index),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """UPDATE ingest.document_chunks
                       SET chunk_text=%s, section_title=%s, fiscal_year=%s,
                           metadata_json=%s::jsonb
                       WHERE source_doc_id=%s AND chunk_index=%s""",
                    (chunk_text, section_title, fiscal_year, json.dumps(meta, ensure_ascii=False),
                     source_id, chunk_index),
                )
            else:
                cur.execute(
                    """INSERT INTO ingest.document_chunks
                           (source_doc_id, ticker, chunk_index, section_title, chunk_text,
                            fiscal_year, language, metadata_json)
                       VALUES (%s,%s,%s,%s,%s,%s,'vi',%s::jsonb)
                       ON CONFLICT (source_doc_id, chunk_index) DO UPDATE
                       SET chunk_text=EXCLUDED.chunk_text,
                           section_title=EXCLUDED.section_title,
                           fiscal_year=EXCLUDED.fiscal_year,
                           metadata_json=EXCLUDED.metadata_json""",
                    (source_id, ticker, chunk_index, section_title, chunk_text,
                     fiscal_year, json.dumps(meta, ensure_ascii=False)),
                )
                inserted += 1
    return inserted


def _index_ocr_artifacts(conn, ticker: str, years: list[int]) -> list[dict]:
    """Walk data/ocr_artifacts/{ticker}/{year}/{doc_id}/pages/ and index page text as chunks.

    Each page file becomes one chunk with extraction_method=ocr, page_number, source_tier=1.
    Only processes runs with status 'completed'. Idempotent.
    """
    ocr_dir = OCR_ARTIFACTS_DIR / ticker
    if not ocr_dir.exists():
        print(f"[build_index] {ticker}: no OCR artifacts directory at {ocr_dir}")
        return []

    sources_indexed: list[dict] = []
    for year in years:
        year_dir = ocr_dir / str(year)
        if not year_dir.exists():
            continue

        for doc_dir in sorted(year_dir.iterdir()):
            if not doc_dir.is_dir():
                continue

            meta_file = doc_dir / "metadata.json"
            if not meta_file.exists():
                continue

            try:
                meta = json.loads(meta_file.read_text(encoding="utf-8"))
            except Exception as exc:
                print(f"[build_index] WARNING: cannot read {meta_file}: {exc}")
                continue

            if meta.get("status") not in ("completed",):
                print(f"[build_index] {ticker} {year}: skipping OCR run {doc_dir.name} (status={meta.get('status')})")
                continue

            document_id = meta.get("document_id", doc_dir.name)
            ocr_run_id = meta.get("ocr_run_id", "")
            ocr_lang = meta.get("ocr_lang", "vie+eng")

            source_id = _ensure_ocr_source(conn, ticker, year, document_id, meta)

            pages_dir = doc_dir / "pages"
            if not pages_dir.exists():
                continue

            page_files = sorted(pages_dir.glob("page_*.txt"))
            if not page_files:
                continue

            page_chunks: list[tuple[str, str, int, int, dict]] = []
            for page_file in page_files:
                try:
                    page_num = int(page_file.stem.split("_")[1])
                except (IndexError, ValueError):
                    continue

                try:
                    page_text = page_file.read_text(encoding="utf-8", errors="ignore").strip()
                except Exception as exc:
                    print(f"[build_index] WARNING: cannot read {page_file}: {exc}")
                    continue

                if not page_text:
                    continue

                extra_meta = {
                    "extraction_method": "ocr",
                    "page_number": page_num,
                    "document_id": document_id,
                    "ocr_run_id": ocr_run_id,
                    "ocr_lang": ocr_lang,
                    "source_tier": 1,
                }
                page_chunks.append((f"Page {page_num}", page_text, year, page_num, extra_meta))

            if not page_chunks:
                continue

            _upsert_page_chunks(conn, source_id, ticker, page_chunks)
            conn.commit()
            sources_indexed.append({
                "source_id": source_id,
                "type": "ocr_pages",
                "document_id": document_id,
                "year": year,
                "chunks": len(page_chunks),
            })
            print(f"[build_index] {ticker} {year}: {len(page_chunks)} OCR page chunks indexed (source={source_id})")

    return sources_indexed


def _index_official_pdf_text(ticker: str, years: list[int]) -> list[dict]:
    """Extract and index text-based official PDFs from data/official_documents/{ticker}/{year}/.

    Uses pdfplumber for text extraction. One chunk per page. Skips scanned PDFs
    (those are handled by _index_ocr_artifacts). Idempotent.
    """
    try:
        import pdfplumber  # type: ignore[import-untyped]
    except ImportError:
        print("[build_index] pdfplumber not available  skipping official PDF text indexing")
        return []

    official_dir = OFFICIAL_DOCS_DIR / ticker
    if not official_dir.exists():
        return []

    sources_indexed: list[dict] = []
    for year in years:
        year_dir = official_dir / str(year)
        if not year_dir.exists():
            continue

        pdf_files = sorted({
            path.resolve()
            for pattern in ("*.pdf", "*.PDF")
            for path in year_dir.glob(pattern)
        })
        if not pdf_files:
            continue

        for pdf_path in pdf_files:
            try:
                with pdfplumber.open(str(pdf_path)) as pdf:
                    # Skip scanned PDFs  they have no text layer
                    sample_text = "".join(
                        p.extract_text() or "" for p in pdf.pages[:5]
                    )
                    if not sample_text.strip():
                        print(f"[build_index] {ticker} {year}: skipping scanned PDF {pdf_path.name} (use --ocr)")
                        continue

                    page_chunks: list[tuple[str, str, int, int, dict]] = []

                    for page in pdf.pages:
                        page_num = page.page_number  # 1-based
                        page_text = (page.extract_text() or "").strip()
                        if not page_text:
                            continue
                        extra_meta = {
                            "extraction_method": "pdf_text",
                            "page_number": page_num,
                            "source_tier": 1,
                            "pdf_name": pdf_path.name,
                        }
                        page_chunks.append((f"Page {page_num}", page_text, year, page_num, extra_meta))

                    if not page_chunks:
                        continue

                    with connect_with_retry(_dsn()) as write_conn:
                        source_id = _ensure_pdf_source(write_conn, ticker, year, pdf_path)
                        _upsert_page_chunks(write_conn, source_id, ticker, page_chunks)
                        write_conn.commit()
                    sources_indexed.append({
                        "source_id": source_id,
                        "type": "pdf_text",
                        "pdf": pdf_path.name,
                        "year": year,
                        "chunks": len(page_chunks),
                    })
                    print(f"[build_index] {ticker} {year}: {len(page_chunks)} PDF text chunks indexed ({pdf_path.name})")

            except Exception as exc:
                print(f"[build_index] WARNING: failed to index {pdf_path}: {exc}")

    return sources_indexed


# Module-level placeholder replaced at runtime
ticker_placeholder = "TICKER"


def build_index(ticker: str, years: list[int], doc_dir: Path | None = None) -> dict:
    global ticker_placeholder
    ticker_placeholder = ticker.upper()
    ticker = ticker.strip().upper()

    conn = None
    total_chunks = 0
    summary: dict = {"ticker": ticker, "years": years, "sources": []}

    try:
        # -- 1. Official PDF text pages (tier 1, extraction_method=pdf_text) ---
        pdf_sources = _index_official_pdf_text(ticker, years)
        for s in pdf_sources:
            total_chunks += s["chunks"]
            summary["sources"].append(s)

        # -- 2. OCR page artifacts (tier 1, extraction_method=ocr) -------------
        conn = connect_with_retry(_dsn())
        ocr_sources = _index_ocr_artifacts(conn, ticker, years)
        for s in ocr_sources:
            total_chunks += s["chunks"]
            summary["sources"].append(s)
        conn.close()
        conn = connect_with_retry(_dsn())

        # -- 3. Synthetic fact-based chunks (from accepted DB facts) ------------
        facts = _get_accepted_facts(conn, ticker, years)
        print(f"[build_index] {ticker}: {len(facts)} accepted facts found across {years}")

        fact_source_id = _ensure_synthetic_source(conn, ticker)
        fact_chunks: list[tuple[str, str, int | None]] = []

        if facts:
            fact_chunks = _build_fact_chunks(facts)

        events = _get_catalyst_events(conn, ticker)
        if events:
            cat_chunk = _build_catalyst_chunk(events)
            if cat_chunk:
                fact_chunks.append(cat_chunk)
            print(f"[build_index] {ticker}: {len(events)} catalyst events added as chunk")

        if fact_chunks:
            _upsert_chunks(conn, fact_source_id, ticker, fact_chunks)
            conn.commit()
            total_chunks += len(fact_chunks)
            summary["sources"].append({
                "source_id": fact_source_id,
                "type": "synthetic_facts",
                "chunks": len(fact_chunks),
            })
            print(f"[build_index] {ticker}: {len(fact_chunks)} fact-based chunks indexed (source={fact_source_id})")

        # -- 4. External .txt documents -----------------------------------------
        search_dir = doc_dir or (DOC_DIR / ticker)
        if search_dir.exists():
            txt_files = list(search_dir.rglob("*.txt"))
            print(f"[build_index] {ticker}: found {len(txt_files)} text documents in {search_dir}")
            for doc_path in txt_files:
                try:
                    text = doc_path.read_text(encoding="utf-8", errors="ignore")
                    doc_source_id = _ensure_doc_source(conn, ticker, doc_path)
                    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                    chunk_size = 3
                    doc_chunks = []
                    for i in range(0, len(paragraphs), chunk_size):
                        chunk_text = "\n\n".join(paragraphs[i:i+chunk_size])
                        doc_chunks.append((doc_path.stem, chunk_text, None))
                    _upsert_chunks(conn, doc_source_id, ticker, doc_chunks)
                    conn.commit()
                    total_chunks += len(doc_chunks)
                    summary["sources"].append({
                        "source_id": doc_source_id,
                        "type": "document",
                        "file": doc_path.name,
                        "chunks": len(doc_chunks),
                    })
                    print(f"[build_index] {ticker}: {len(doc_chunks)} chunks from {doc_path.name}")
                except Exception as exc:
                    print(f"[build_index] WARNING: failed to index {doc_path}: {exc}")
        else:
            print(f"[build_index] {ticker}: no external docs at {search_dir}  skipping")

        summary["total_chunks"] = total_chunks
        print(f"[build_index] {ticker}: total {total_chunks} chunks indexed")

    except Exception:
        if conn is not None and not conn.closed:
            conn.rollback()
        raise
    finally:
        if conn is not None and not conn.closed:
            conn.close()

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build evidence index for a VN pharma ticker.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--years", nargs="+", type=int, default=None,
                        help="Explicit list of fiscal years (alternative to --from-year/--to-year).")
    parser.add_argument("--from-year", type=int, default=DEFAULT_FROM_YEAR, dest="from_year",
                        help="Start of fiscal year range (inclusive).")
    parser.add_argument("--to-year", type=int, default=DEFAULT_TO_YEAR, dest="to_year",
                        help="End of fiscal year range (inclusive).")
    parser.add_argument("--doc-dir", type=Path, default=None, dest="doc_dir",
                        help="Optional directory of .txt documents to also index.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    years = args.years or list(range(args.from_year, args.to_year + 1))
    result = build_index(ticker=args.ticker, years=years, doc_dir=args.doc_dir)
    run_id = os.environ.get("RUN_ID", "")
    out_dir = ROOT / "storage" / "runs" / run_id if run_id else ROOT / "storage" / "runs" / "_index"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out_path = out_dir / f"{args.ticker.upper()}_{ts}_index_summary.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[build_index] Summary saved: {out_path}")
    print("[build_index] done")


if __name__ == "__main__":
    main()
