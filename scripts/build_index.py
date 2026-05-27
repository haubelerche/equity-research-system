"""Phase 5 — Evidence Index Builder.

Synthesizes grounded text evidence chunks from accepted canonical financial
facts and catalyst events, then stores them in ingest.document_chunks so the
report generator can cite them.

If a data/documents/{ticker}/ directory exists, plain-text files (.txt) in
that directory are also chunked and indexed.

Usage:
    python scripts/build_index.py --ticker DHG
    python scripts/build_index.py --ticker DHG --doc-dir data/documents/DHG
    python scripts/build_index.py --ticker DHG --years 2021 2022 2023 2024 2025
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

ROOT = Path(__file__).resolve().parents[1]
DOC_DIR = ROOT / "data" / "documents"

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
    return os.getenv("DATABASE_URL", "postgresql://maer:maer_local@localhost:5432/maer_dev")


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def _get_accepted_facts(conn, ticker: str, years: list[int]) -> list[dict]:
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT ff.id, ff.ticker, ff.fiscal_year, ff.fiscal_period,
                   ff.line_item_code, ff.value, ff.unit, ff.currency,
                   li.statement_type
            FROM fact.financial_facts ff
            LEFT JOIN ref.line_items li ON li.line_item_code = ff.line_item_code
            WHERE ff.ticker = %s
              AND ff.fiscal_year = ANY(%s)
              AND ff.validation_status = 'accepted'
              AND ff.fiscal_period = 'FY'
            ORDER BY ff.fiscal_year, ff.line_item_code
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
    source_id = f"syn_facts_{ticker.lower()}"
    checksum = _sha(source_id)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest.sources
                (source_id, logical_id, ticker, source_type, source_uri, source_title,
                 connector_version, reliability_tier, checksum, raw_path, published_at)
            VALUES (%s, %s, %s, 'financial_statement', %s, %s, '1.0', 2, %s, %s, NOW())
            ON CONFLICT (source_id) DO NOTHING
            """,
            (
                source_id,
                f"synthetic_facts_{ticker.lower()}",
                ticker,
                f"internal://canonical_facts/{ticker}",
                f"Synthetic evidence from canonical financial facts — {ticker}",
                checksum,
                f"internal://canonical_facts/{ticker}",
            ),
        )
    return source_id


def _ensure_doc_source(conn, ticker: str, doc_path: Path) -> str:
    source_id = f"doc_{_sha(str(doc_path))}"
    checksum = _sha(str(doc_path))
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO ingest.sources
                (source_id, logical_id, ticker, source_type, source_uri, source_title,
                 connector_version, reliability_tier, checksum, raw_path, published_at)
            VALUES (%s, %s, %s, 'annual_report', %s, %s, '1.0', 1, %s, %s, NOW())
            ON CONFLICT (source_id) DO NOTHING
            """,
            (
                source_id,
                f"doc_{ticker.lower()}_{doc_path.stem}",
                ticker,
                str(doc_path),
                doc_path.stem,
                checksum,
                str(doc_path),
            ),
        )
    return source_id


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


def _upsert_chunks(conn, source_id: str, ticker: str, chunks: list[tuple[str, str, int | None]]) -> int:
    inserted = 0
    with conn.cursor() as cur:
        for idx, (section_title, chunk_text, fiscal_year) in enumerate(chunks):
            checksum = _sha(chunk_text)
            # Check existing
            cur.execute(
                "SELECT chunk_id FROM ingest.document_chunks WHERE source_id=%s AND chunk_index=%s",
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
                       WHERE source_id=%s AND chunk_index=%s""",
                    (chunk_text, section_title, fiscal_year, json.dumps(meta), source_id, idx),
                )
            else:
                cur.execute(
                    """INSERT INTO ingest.document_chunks
                           (source_id, ticker, chunk_index, section_title, chunk_text,
                            fiscal_year, language, metadata_json)
                       VALUES (%s,%s,%s,%s,%s,%s,'vi',%s::jsonb)
                       ON CONFLICT (source_id, chunk_index) DO UPDATE
                       SET chunk_text=EXCLUDED.chunk_text,
                           section_title=EXCLUDED.section_title,
                           fiscal_year=EXCLUDED.fiscal_year,
                           metadata_json=EXCLUDED.metadata_json""",
                    (source_id, ticker, idx, section_title, chunk_text, fiscal_year, json.dumps(meta)),
                )
                inserted += 1
    return inserted


# Module-level placeholder replaced at runtime
ticker_placeholder = "TICKER"


def build_index(ticker: str, years: list[int], doc_dir: Path | None = None) -> dict:
    global ticker_placeholder
    ticker_placeholder = ticker.upper()
    ticker = ticker.strip().upper()

    conn = psycopg2.connect(_dsn())
    total_chunks = 0
    summary = {"ticker": ticker, "years": years, "sources": []}

    try:
        # ── Synthetic fact-based chunks ────────────────────────────────────────
        facts = _get_accepted_facts(conn, ticker, years)
        print(f"[build_index] {ticker}: {len(facts)} accepted facts found across {years}")

        fact_source_id = _ensure_synthetic_source(conn, ticker)
        fact_chunks: list[tuple[str, str, int | None]] = []

        if facts:
            fact_chunks = _build_fact_chunks(facts)

        # Add catalyst chunk
        events = _get_catalyst_events(conn, ticker)
        if events:
            cat_chunk = _build_catalyst_chunk(events)
            if cat_chunk:
                fact_chunks.append(cat_chunk)
            print(f"[build_index] {ticker}: {len(events)} catalyst events added as chunk")

        if fact_chunks:
            n = _upsert_chunks(conn, fact_source_id, ticker, fact_chunks)
            conn.commit()
            total_chunks += len(fact_chunks)
            summary["sources"].append({"source_id": fact_source_id, "type": "synthetic_facts", "chunks": len(fact_chunks)})
            print(f"[build_index] {ticker}: {len(fact_chunks)} fact-based chunks indexed (source={fact_source_id})")

        # ── External text document chunks ──────────────────────────────────────
        search_dir = doc_dir or (DOC_DIR / ticker)
        if search_dir.exists():
            txt_files = list(search_dir.rglob("*.txt"))
            print(f"[build_index] {ticker}: found {len(txt_files)} text documents in {search_dir}")
            for doc_path in txt_files:
                try:
                    text = doc_path.read_text(encoding="utf-8", errors="ignore")
                    doc_source_id = _ensure_doc_source(conn, ticker, doc_path)
                    # Chunk by paragraph (~500 chars each)
                    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
                    chunk_size = 3  # paragraphs per chunk
                    doc_chunks = []
                    for i in range(0, len(paragraphs), chunk_size):
                        chunk_text = "\n\n".join(paragraphs[i:i+chunk_size])
                        section = doc_path.stem
                        doc_chunks.append((section, chunk_text, None))
                    n = _upsert_chunks(conn, doc_source_id, ticker, doc_chunks)
                    conn.commit()
                    total_chunks += len(doc_chunks)
                    summary["sources"].append({"source_id": doc_source_id, "type": "document", "file": doc_path.name, "chunks": len(doc_chunks)})
                    print(f"[build_index] {ticker}: {len(doc_chunks)} chunks from {doc_path.name}")
                except Exception as exc:
                    print(f"[build_index] WARNING: failed to index {doc_path}: {exc}")
        else:
            print(f"[build_index] {ticker}: no external docs directory at {search_dir} — using synthetic chunks only")

        summary["total_chunks"] = total_chunks
        print(f"[build_index] {ticker}: total {total_chunks} chunks indexed")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build evidence index for a VN pharma ticker.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--ticker", required=True)
    parser.add_argument("--years", nargs="+", type=int, default=[2021, 2022, 2023, 2024, 2025])
    parser.add_argument("--doc-dir", type=Path, default=None, dest="doc_dir",
                        help="Optional directory of .txt documents to also index.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    result = build_index(ticker=args.ticker, years=args.years, doc_dir=args.doc_dir)
    out_dir = ROOT / "artifacts" / "index"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    out_path = out_dir / f"{args.ticker.upper()}_{ts}_index_summary.json"
    out_path.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8")
    print(f"[build_index] Summary saved: {out_path}")
    print("[build_index] done")


if __name__ == "__main__":
    main()
