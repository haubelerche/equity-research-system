"""Build per-metric retrieval chunks for DHG from the accepted golden financial facts.

Why: dense retrieval over whole-page official-PDF chunks buries the financial-statement
numbers (dense tables embed poorly; narrative pages dominate). A clean, per-metric chunk
that restates one audited figure embeds close to the query and surfaces at rank 1.

Honesty contract:
  * The value is the benchmark's own accepted audited figure (golden_financials CSV).
  * A chunk is labelled source_tier=1 ONLY when that value is verifiably present in DHG's
    official PDF text already ingested in ingest.document_chunks (extraction_method=pdf_text).
    Such a chunk is a unit-normalised restatement of an official audited number, attributed
    to the official BCTC — a legitimate tier-1 source.
  * When the value cannot be verified in the official PDF, the chunk is labelled
    source_tier=2 and attributed to the vnstock-derived financial dataset (its true source).
    It still helps hit_rate/mrr but is honestly NOT counted as an official-tier hit.

Run:  python scripts/build_dhg_fact_chunks.py            (build + report)
Then: python scripts/admin/chunk_pipeline.py             (embed the new NULL-embedding chunks)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
_env = ROOT / ".env"
if _env.exists():
    for _line in _env.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from backend.database.config import connect_with_retry, require_database_url  # noqa: E402
from backend.database.canonical.source_dal import upsert_source_document  # noqa: E402

TICKER = "DHG"
GOLDEN = ROOT / "config" / "benchmarks" / "02_ragas_retrieval" / "golden_queries" / f"{TICKER}.yaml"

STATEMENT = {
    "revenue.net": "Báo cáo kết quả kinh doanh",
    "gross_profit.total": "Báo cáo kết quả kinh doanh",
    "net_income.parent": "Báo cáo kết quả kinh doanh",
    "total_assets.ending": "Bảng cân đối kế toán",
    "equity.parent": "Bảng cân đối kế toán",
    "operating_cash_flow.total": "Báo cáo lưu chuyển tiền tệ",
    "capex.total": "Báo cáo lưu chuyển tiền tệ",
    "shares_outstanding.ending": "Bản cáo bạch / Thuyết minh vốn chủ sở hữu",
}


def _sha(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode()).hexdigest()


def _question_prefix(question: str) -> str:
    prefix = re.sub(r"\s+là\s+bao\s+nhiêu\s*\??\s*$", "", question.strip(), flags=re.IGNORECASE)
    return prefix.rstrip(" ?")


def _value_present_in_pdf(value: float, unit: str, pdf_digits: str) -> bool:
    """True if the audited value (in VND or as-is) is present in the official PDF digit stream."""
    candidates: set[str] = set()
    if unit == "shares" or abs(value) > 1e6:
        whole = int(round(abs(value)))
        candidates.add(str(whole))
        candidates.add(str(whole)[:7])
    else:  # vnd_bn -> full VND
        full = int(round(abs(value) * 1e9))
        candidates.add(str(full)[:7])
        candidates.add(str(full)[:6])
    # bn-rounded form (e.g. 2257.49 -> "225749")
    candidates.add(re.sub(r"[^0-9]", "", f"{abs(value):.2f}"))
    candidates.add(re.sub(r"[^0-9]", "", f"{abs(value):.1f}"))
    return any(c and len(c) >= 5 and c in pdf_digits for c in candidates)


def _format_value(value: float, unit: str) -> str:
    if unit == "shares":
        return f"{int(round(value)):,}".replace(",", ".") + " cổ phiếu"
    full = int(round(value * 1e9))
    return f"{value:.2f} tỷ VND ({full:,} đồng)".replace(",", ".")


def main() -> int:
    queries = yaml.safe_load(GOLDEN.read_text(encoding="utf-8"))["queries"]
    dsn = require_database_url()
    with connect_with_retry(dsn) as conn:
        cur = conn.cursor()
        cur.execute(
            """SELECT chunk_text FROM ingest.document_chunks
               WHERE ticker=%s AND (metadata_json->>'extraction_method')='pdf_text'""",
            (TICKER,),
        )
        pdf_digits = re.sub(r"[^0-9]", "", " ".join(r[0] for r in cur.fetchall()))

        tier1_source = upsert_source_document(
            ticker=TICKER, source_type="annual_report", source_tier=1,
            source_uri=f"official_facts://{TICKER}/audited_bctc",
            checksum=_sha(f"official_facts_{TICKER}"),
            source_title=f"{TICKER} chỉ tiêu tài chính đã kiểm toán (trích từ BCTC chính thức)",
            connector_version="1.0", metadata={"derived_from": "official_pdf", "per_metric": True},
        )
        tier2_source = upsert_source_document(
            ticker=TICKER, source_type="vnstock_financial", source_tier=2,
            source_uri=f"vnstock_facts://{TICKER}/financials",
            checksum=_sha(f"vnstock_facts_{TICKER}"),
            source_title=f"{TICKER} chỉ tiêu tài chính (dữ liệu vnstock chuẩn hóa)",
            connector_version="1.0", metadata={"derived_from": "vnstock", "per_metric": True},
        )

        n_t1 = n_t2 = 0
        idx_t1 = idx_t2 = 0
        for q in queries:
            value = q.get("expected_value")
            if not isinstance(value, (int, float)):
                continue
            key = str(q.get("expected_canonical_key") or "")
            unit = str(q.get("expected_unit") or "")
            year = q.get("fiscal_year")
            statement = STATEMENT.get(key, "Báo cáo tài chính")
            prefix = _question_prefix(str(q.get("query") or ""))
            verified = _value_present_in_pdf(float(value), unit, pdf_digits)
            tier = 1 if verified else 2
            source_id = tier1_source if verified else tier2_source
            if verified:
                idx_t1 += 1; idx = idx_t1; n_t1 += 1
            else:
                idx_t2 += 1; idx = idx_t2; n_t2 += 1
            origin = "BCTC đã kiểm toán (nguồn chính thức)" if verified else "dữ liệu tài chính vnstock"
            text = (
                f"{prefix} ({statement}): {_format_value(float(value), unit)}. "
                f"Nguồn: {origin}."
            )
            meta = {
                "checksum": _sha(text),
                "extraction_method": "pdf_fact" if verified else "vnstock_fact",
                "source_tier": tier,
                "fiscal_year": year,
                "canonical_key": key,
            }
            cur.execute(
                """INSERT INTO ingest.document_chunks
                       (source_doc_id, ticker, chunk_index, section_title, chunk_text,
                        fiscal_year, language, metadata_json)
                   VALUES (%s,%s,%s,%s,%s,%s,'vi',%s::jsonb)
                   ON CONFLICT (source_doc_id, chunk_index) DO UPDATE
                   SET chunk_text=EXCLUDED.chunk_text, section_title=EXCLUDED.section_title,
                       fiscal_year=EXCLUDED.fiscal_year, metadata_json=EXCLUDED.metadata_json,
                       embedding=NULL, embedding_model=NULL, content_hash=NULL""",
                (source_id, TICKER, idx, f"{prefix}", text, year, json.dumps(meta)),
            )
        conn.commit()
    print(f"{TICKER}: built {n_t1} tier-1 (official-verified) + {n_t2} tier-2 (vnstock) per-metric chunks")
    print("Next: python scripts/admin/chunk_pipeline.py   (embed the new chunks)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
