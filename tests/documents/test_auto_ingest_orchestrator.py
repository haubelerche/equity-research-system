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
