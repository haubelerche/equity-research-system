"""Tests for scripts/auto_ingest_official_documents.py — all offline, no DB, no HTTP."""
from __future__ import annotations


def test_module_imports():
    from scripts.auto_ingest_official_documents import AutoIngestConfig, build_pipeline_plan, run_pipeline
    assert AutoIngestConfig is not None


def test_build_pipeline_plan_returns_correct_years():
    from scripts.auto_ingest_official_documents import build_pipeline_plan, AutoIngestConfig
    cfg = AutoIngestConfig(ticker="DHG", from_year=2021, to_year=2023, dry_run=True, channels=["cafef"])
    plan = build_pipeline_plan(cfg)
    assert plan.years == [2021, 2022, 2023]
    assert plan.ticker == "DHG"
    assert plan.dry_run is True


def test_build_pipeline_plan_single_year():
    from scripts.auto_ingest_official_documents import build_pipeline_plan, AutoIngestConfig
    cfg = AutoIngestConfig(ticker="IMP", from_year=2024, to_year=2024, dry_run=True)
    plan = build_pipeline_plan(cfg)
    assert plan.years == [2024]


def test_run_pipeline_dry_run_no_db():
    """Dry run must complete without DB connection."""
    from scripts.auto_ingest_official_documents import AutoIngestConfig, run_pipeline
    cfg = AutoIngestConfig(ticker="DHG", from_year=2021, to_year=2021,
                           dry_run=True, channels=[])  # no channels → nothing fetched
    results = run_pipeline(cfg)
    assert len(results) == 1
    assert results[0].fiscal_year == 2021
    assert results[0].status == "dry_run"
    assert results[0].ingested == 0


def test_run_pipeline_multiple_years_dry_run():
    from scripts.auto_ingest_official_documents import AutoIngestConfig, run_pipeline
    cfg = AutoIngestConfig(ticker="DHG", from_year=2022, to_year=2024,
                           dry_run=True, channels=[])
    results = run_pipeline(cfg)
    assert len(results) == 3
    years = [r.fiscal_year for r in results]
    assert years == [2022, 2023, 2024]


def test_year_result_defaults():
    from scripts.auto_ingest_official_documents import YearResult
    yr = YearResult(fiscal_year=2023)
    assert yr.cafef_rows == 0
    assert yr.pdf_rows == 0
    assert yr.ingested == 0
    assert yr.promoted == 0
    assert yr.status == "pending"
    assert yr.errors == []
    assert yr.notes == []


def test_validate_pdf_rows_rejects_wrong_year_and_insufficient_coverage():
    from scripts.auto_ingest_official_documents import _validate_pdf_rows

    rows = [
        {"fiscal_year": "2021", "period_type": "FY", "statement_type": "income_statement",
         "metric_id": "revenue.net", "value": "3756.0"},
        {"fiscal_year": "2021", "period_type": "FY", "statement_type": "income_statement",
         "metric_id": "revenue.net", "value": "3756.0"},
    ]
    accepted, errors = _validate_pdf_rows(rows, 2022)
    assert accepted == []
    assert any("ignored rows" in error for error in errors)
    assert any("minimum is 2" in error for error in errors)


def test_validate_pdf_rows_deduplicates_run_year_metrics():
    from scripts.auto_ingest_official_documents import _validate_pdf_rows

    rows = [
        {"fiscal_year": "2022", "period_type": "FY", "statement_type": "income_statement",
         "metric_id": "revenue.net", "value": "4000"},
        {"fiscal_year": "2022", "period_type": "FY", "statement_type": "income_statement",
         "metric_id": "revenue.net", "value": "4000"},
        {"fiscal_year": "2022", "period_type": "FY", "statement_type": "income_statement",
         "metric_id": "net_income.parent", "value": "800"},
    ]
    accepted, errors = _validate_pdf_rows(rows, 2022)
    assert len(accepted) == 2
    assert errors == []


def test_sanitize_extracted_csv_removes_stale_years_and_duplicates(tmp_path):
    import csv
    from scripts.auto_ingest_official_documents import (
        _CSV_FIELDNAMES,
        _sanitize_extracted_csv_for_year,
    )

    path = tmp_path / "extracted_facts.csv"
    rows = [
        {"fiscal_year": "2021", "period_type": "FY", "statement_type": "income_statement",
         "metric_id": "revenue.net", "extraction_method": "pdf_table"},
        {"fiscal_year": "2022", "period_type": "FY", "statement_type": "income_statement",
         "metric_id": "revenue.net", "extraction_method": "pdf_table"},
        {"fiscal_year": "2022", "period_type": "FY", "statement_type": "income_statement",
         "metric_id": "revenue.net", "extraction_method": "pdf_table"},
    ]
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)

    assert _sanitize_extracted_csv_for_year(path, 2022) == 1
    with path.open(encoding="utf-8", newline="") as fh:
        sanitized = list(csv.DictReader(fh))
    assert len(sanitized) == 1
    assert sanitized[0]["fiscal_year"] == "2022"


def test_artifact_includes_error_details(tmp_path, monkeypatch):
    from scripts import auto_ingest_official_documents as mod
    from scripts.auto_ingest_official_documents import AutoIngestConfig, YearResult

    monkeypatch.setattr(mod, "ARTIFACT_DIR", tmp_path)
    result = YearResult(fiscal_year=2022)
    result.errors.append("pdf: no source")

    artifact = mod._write_artifact(
        "DHG",
        AutoIngestConfig(ticker="DHG", from_year=2022, to_year=2022),
        [result],
    )

    text = artifact.read_text(encoding="utf-8")
    assert "## Errors" in text
    assert "FY2022: pdf: no source" in text


def test_artifact_includes_dry_run_notes(tmp_path, monkeypatch):
    from scripts import auto_ingest_official_documents as mod
    from scripts.auto_ingest_official_documents import AutoIngestConfig, YearResult

    monkeypatch.setattr(mod, "ARTIFACT_DIR", tmp_path)
    result = YearResult(fiscal_year=2022)
    result.notes.append("dry_run: would fetch https://issuer.example/report.pdf")

    artifact = mod._write_artifact(
        "DHG",
        AutoIngestConfig(ticker="DHG", from_year=2022, to_year=2022, dry_run=True),
        [result],
    )

    text = artifact.read_text(encoding="utf-8")
    assert "## Notes" in text
    assert "would fetch" in text


def test_download_candidate_pdf_and_metadata_write_local_layout(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from scripts import auto_ingest_official_documents as mod

    class FakeResponse:
        headers = {"Content-Type": "application/pdf"}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self):
            return b"%PDF-1.4 official"

    monkeypatch.setattr(mod.urllib.request, "urlopen", lambda req, timeout=60: FakeResponse())
    candidate = SimpleNamespace(
        source_url="https://issuer.example/report.pdf",
        document_type="annual_report",
        publisher="Issuer",
        source_name="company_ir",
        title="Annual report 2022",
    )

    doc_dir = tmp_path / "data" / "official_documents" / "DHG" / "2022"
    pdf_path, file_hash, content_type = mod._download_candidate_pdf(candidate, doc_dir)
    mod._write_pdf_metadata(
        ticker="DHG",
        fiscal_year=2022,
        candidate=candidate,
        doc_dir=doc_dir,
        pdf_path=pdf_path,
        file_hash=file_hash,
    )

    assert pdf_path == doc_dir / "source_document.pdf"
    assert pdf_path.read_bytes().startswith(b"%PDF")
    assert content_type == "application/pdf"
    import json
    meta = json.loads((doc_dir / "metadata.json").read_text(encoding="utf-8"))
    assert meta["title"] == "Annual report 2022"
    assert meta["local_path"] == str(pdf_path)
