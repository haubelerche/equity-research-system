"""auto_ingest_tool must surface per-year errors/notes, not just their counts.

Regression for the debuggability defect: the harness path summed promoted/pdf
rows but discarded YearResult.errors and .notes entirely, so a run that logged
`errors=3` left no record of *what* the three errors were. The tool must expose
the full strings in its summary (always) and write the per-ticker .md report
when AUTO_INGEST_DEBUG is enabled.
"""
from __future__ import annotations

import os
from unittest.mock import patch

from scripts.auto_ingest_official_documents import IngestStatus, YearResult


def _yr(year: int, status: IngestStatus, errors, notes=None, *, ingested=0, promoted=0) -> YearResult:
    return YearResult(
        fiscal_year=year,
        ingest_status=status,
        errors=list(errors),
        notes=list(notes or []),
        ingested=ingested,
        promoted=promoted,
        pdf_rows=len(errors),
    )


def _results():
    return [
        _yr(2022, IngestStatus.EXTRACTION_FAILED_NO_TABLES,
            ["FY2022: CafeF API returned no rows (CAFEF_EMPTY)",
             "FY2022: PDF extraction has only 0 distinct run-year metric(s); minimum is 2",
             "FY2022: PDF has text but no recognisable BCTC tables"]),
        _yr(2024, IngestStatus.LOW_CONFIDENCE, ["reconcile: boom"],
            notes=["reconcile skipped: legacy fact.fact_observations table is unavailable"],
            ingested=2, promoted=0),
    ]


@patch("scripts.auto_ingest_official_documents._write_artifact")
@patch("scripts.auto_ingest_official_documents.run_pipeline")
def test_summary_carries_full_year_errors_and_notes(mock_run, _mock_artifact):
    mock_run.return_value = _results()
    from backend.harness.tools import auto_ingest_tool

    res = auto_ingest_tool("DHG", 2022, 2024)
    details = res.summary.get("year_details")
    assert details is not None, "summary must include per-year details"

    all_errors = [e for d in details for e in d["errors"]]
    assert any("no recognisable BCTC tables" in e for e in all_errors)
    assert any("reconcile: boom" in e for e in all_errors)

    all_notes = [n for d in details for n in d["notes"]]
    assert any("fact_observations" in n for n in all_notes)

    fy2024 = next(d for d in details if d["fiscal_year"] == 2024)
    assert fy2024["ingested"] == 2 and fy2024["promoted"] == 0


@patch("scripts.auto_ingest_official_documents._write_artifact")
@patch("scripts.auto_ingest_official_documents.run_pipeline")
def test_debug_env_writes_md_artifact(mock_run, mock_artifact, monkeypatch):
    mock_run.return_value = _results()
    monkeypatch.setenv("AUTO_INGEST_DEBUG", "1")
    from backend.harness.tools import auto_ingest_tool

    auto_ingest_tool("DHG", 2022, 2024)
    assert mock_artifact.called, "AUTO_INGEST_DEBUG must persist the full .md error report"


@patch("scripts.auto_ingest_official_documents._write_artifact")
@patch("scripts.auto_ingest_official_documents.run_pipeline")
def test_no_debug_env_skips_md_artifact(mock_run, mock_artifact, monkeypatch):
    mock_run.return_value = _results()
    monkeypatch.delenv("AUTO_INGEST_DEBUG", raising=False)
    from backend.harness.tools import auto_ingest_tool

    auto_ingest_tool("DHG", 2022, 2024)
    assert not mock_artifact.called, "without AUTO_INGEST_DEBUG the .md write must be skipped"
