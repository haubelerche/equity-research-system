"""Phase 3 — Official document ingestion validation (no DB; dry-run on synthetic fixture).

These tests exercise the ingestion/validation logic using a structurally valid synthetic
document placed in tmp_path. They do NOT require real DHG PDFs or the live DB.
"""
from __future__ import annotations

import json

import pytest

import scripts.ingest_official_documents as ing

_MIN = ing.MIN_METRICS


def _write_document(year_dir, *, fiscal_year, metrics, with_pdf=True, declared_hash=None):
    year_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "ticker": "DHG",
        "company_name": "Công ty Cổ phần Dược Hậu Giang",
        "source_type": "audited_financial_statement",
        "issuer": "DHG Pharma",
        "title": f"BCTC kiểm toán DHG {fiscal_year}",
        "url": "https://example.test/dhg.pdf",
        "published_date": f"{fiscal_year + 1}-03-31",
        "fiscal_year": fiscal_year,
        "language": "vi",
        "file_hash": declared_hash or "",
    }
    (year_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    header = ("ticker,fiscal_year,period_type,statement_type,metric_id,value,unit,"
              "document_title,page_number,table_name,extracted_text,extraction_method,"
              "verified_by,verified_at")
    rows = [header]
    for i, m in enumerate(metrics):
        rows.append(
            f"DHG,{fiscal_year},FY,income_statement,{m},{1000 + i},vnd_bn,"
            f"BCTC kiểm toán DHG {fiscal_year},{10 + i},Bảng KQKD,"
            f"trích dòng {m},manual,analyst,2026-01-01"
        )
    (year_dir / "extracted_facts.csv").write_text("\n".join(rows), encoding="utf-8")
    if with_pdf:
        (year_dir / "source_document.pdf").write_bytes(b"%PDF-1.4 synthetic test document")


@pytest.fixture()
def docs_root(tmp_path, monkeypatch):
    monkeypatch.setattr(ing, "DOCS_DIR", tmp_path / "official_documents")
    return tmp_path / "official_documents"


# 1. metadata.json is valid
def test_metadata_json_valid(docs_root):
    yd = docs_root / "DHG" / "2023"
    _write_document(yd, fiscal_year=2023, metrics=_MIN)
    meta = ing.load_metadata(yd)
    assert meta is not None
    assert meta["ticker"] == "DHG"
    assert meta["fiscal_year"] == 2023


# 2. source document file exists
def test_source_document_exists(docs_root):
    yd = docs_root / "DHG" / "2023"
    _write_document(yd, fiscal_year=2023, metrics=_MIN)
    assert (yd / "source_document.pdf").exists()


# 3. file_hash is computed and stored in the summary
def test_file_hash_computed(docs_root):
    yd = docs_root / "DHG" / "2023"
    _write_document(yd, fiscal_year=2023, metrics=_MIN)
    summary = ing.ingest_year("DHG", 2023, dry_run=True)
    assert summary["file_hash"] is not None
    assert len(summary["file_hash"]) == 64  # sha256 hex


# 4. extracted_facts.csv has required columns
def test_extracted_facts_required_columns(docs_root):
    yd = docs_root / "DHG" / "2023"
    _write_document(yd, fiscal_year=2023, metrics=_MIN)
    rows, errors = ing.load_extracted_facts(yd)
    assert errors == []
    assert len(rows) == len(_MIN)


def test_missing_csv_column_detected(docs_root):
    yd = docs_root / "DHG" / "2022"
    yd.mkdir(parents=True)
    (yd / "metadata.json").write_text(json.dumps({"ticker": "DHG", "fiscal_year": 2022}), encoding="utf-8")
    # CSV missing 'table_name' and others
    (yd / "extracted_facts.csv").write_text("ticker,metric_id,value\nDHG,revenue_net,100", encoding="utf-8")
    rows, errors = ing.load_extracted_facts(yd)
    assert errors, "missing required columns should be reported"


# 5. each extracted fact has document title, table name, and metric_id
def test_each_fact_has_required_fields(docs_root):
    yd = docs_root / "DHG" / "2023"
    _write_document(yd, fiscal_year=2023, metrics=_MIN)
    rows, _ = ing.load_extracted_facts(yd)
    for r in rows:
        assert r["metric_id"].strip()
        assert r["document_title"].strip()
        assert r["table_name"].strip()


# 6. DHG has at least the minimum metrics for available years
def test_minimum_metrics_satisfied(docs_root):
    yd = docs_root / "DHG" / "2023"
    _write_document(yd, fiscal_year=2023, metrics=_MIN)
    summary = ing.ingest_year("DHG", 2023, dry_run=True)
    assert summary["missing_metrics"] == [], f"unexpected missing: {summary['missing_metrics']}"
    assert summary["facts_ingested"] == len(_MIN)


def test_incomplete_year_reports_missing_metrics(docs_root):
    yd = docs_root / "DHG" / "2024"
    _write_document(yd, fiscal_year=2024, metrics=["revenue_net", "net_income"])
    summary = ing.ingest_year("DHG", 2024, dry_run=True)
    assert "net_income.parent" not in summary["missing_metrics"]  # alias mapped + present
    assert "eps.basic" in summary["missing_metrics"]              # genuinely absent


# Missing document year is reported, never fabricated
def test_missing_document_reported(docs_root):
    summary = ing.ingest_year("DHG", 2021, dry_run=True)
    assert summary["status"] == "missing"
    assert summary["facts_ingested"] == 0


# file_hash mismatch is detected
def test_file_hash_mismatch_detected(docs_root):
    yd = docs_root / "DHG" / "2025"
    _write_document(yd, fiscal_year=2025, metrics=_MIN, declared_hash="0" * 64)
    summary = ing.ingest_year("DHG", 2025, dry_run=True)
    assert summary["status"] == "hash_mismatch"
