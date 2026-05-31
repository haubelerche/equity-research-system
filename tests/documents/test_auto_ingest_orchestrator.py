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
