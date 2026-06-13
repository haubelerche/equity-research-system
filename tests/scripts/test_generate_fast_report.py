"""Tests for scripts/generate_fast_report.py — fully mocked (no DB/network)."""
from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock


@patch("scripts.generate_fast_report.latest_ready_snapshot", return_value=None)
def test_fails_fast_when_no_ready_snapshot(_m):
    from scripts.generate_fast_report import generate_fast_report
    with pytest.raises(SystemExit) as e:
        generate_fast_report("DHG")
    assert "ready snapshot" in str(e.value).lower()


@patch("scripts.generate_fast_report._latest_report_run_ids", return_value=[])
@patch("scripts.generate_fast_report.latest_ready_snapshot", return_value={"snapshot_id": "s"})
def test_fails_fast_when_no_prior_report_run(_s, _r):
    from scripts.generate_fast_report import generate_fast_report
    with pytest.raises(SystemExit):
        generate_fast_report("DHG")


@patch("scripts.generate_fast_report.SupabaseStorageAdapter")
@patch("scripts.generate_fast_report.ClientReportPublisher")
@patch("scripts.generate_fast_report._latest_report_run_ids", return_value=["run_dhg_x"])
@patch("scripts.generate_fast_report.latest_ready_snapshot", return_value={"snapshot_id": "s"})
def test_renders_from_latest_run(_s, _r, mock_pub, mock_storage):
    published = MagicMock()
    published.to_dict.return_value = {
        "pdf": {"storage_bucket": "runs", "storage_path": "run_dhg_x/report.pdf"},
        "html": {"storage_bucket": "runs", "storage_path": "run_dhg_x/report.html"},
    }
    mock_pub.return_value.publish.return_value = published
    from scripts.generate_fast_report import generate_fast_report
    out = generate_fast_report("DHG")
    assert out["run_id"] == "run_dhg_x"
    mock_pub.return_value.publish.assert_called_once()


@patch("scripts.generate_fast_report.SupabaseStorageAdapter")
@patch("scripts.generate_fast_report.ClientReportPublisher")
@patch("scripts.generate_fast_report._latest_report_run_ids", return_value=["run_dhg_x"])
@patch("scripts.generate_fast_report.latest_ready_snapshot", return_value={"snapshot_id": "s"})
def test_downloads_workings_md_when_present(_s, _r, mock_pub, mock_storage):
    published = MagicMock()
    published.to_dict.return_value = {
        "pdf": {"storage_bucket": "runs", "storage_path": "run_dhg_x/report.pdf"},
        "html": {"storage_bucket": "runs", "storage_path": "run_dhg_x/report.html"},
        "workings_md": {"storage_bucket": "runs", "storage_path": "run_dhg_x/report_workings.md"},
    }
    mock_pub.return_value.publish.return_value = published
    from scripts.generate_fast_report import generate_fast_report
    out = generate_fast_report("DHG")
    assert out["workings_path"].endswith("DHG_valuation_workings.md")
    downloaded = {c.args[1] for c in mock_storage.return_value.download_file.call_args_list}
    assert "run_dhg_x/report_workings.md" in downloaded
