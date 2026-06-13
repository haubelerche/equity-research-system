"""Tests for scripts/generate_fast_report.py without DB/network/browser access."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest


def _fake_render(*, run_id, ticker, mode, output_dir):
    output = Path(output_dir)
    html = output / f"{run_id}_{ticker}_report.html"
    pdf = output / f"{run_id}_{ticker}_report.pdf"
    html.write_text("<html>charts</html>", encoding="utf-8")
    pdf.write_bytes(b"%PDF-1.4 charts")
    return html, pdf, object()


@patch("scripts.generate_fast_report.latest_ready_snapshot", return_value=None)
def test_fails_fast_when_no_ready_snapshot(_snapshot):
    from scripts.generate_fast_report import generate_fast_report

    with pytest.raises(SystemExit) as exc:
        generate_fast_report("DHG")
    assert "ready snapshot" in str(exc.value).lower()


@patch("scripts.generate_fast_report._latest_report_run_ids", return_value=[])
@patch("scripts.generate_fast_report.latest_ready_snapshot", return_value={"snapshot_id": "s"})
def test_fails_fast_when_no_prior_report_run(_snapshot, _run_ids):
    from scripts.generate_fast_report import generate_fast_report

    with pytest.raises(SystemExit):
        generate_fast_report("DHG")


@patch("scripts.generate_fast_report.SupabaseStorageAdapter")
@patch("scripts.generate_fast_report.render_client_report_to_directory", side_effect=_fake_render)
@patch("scripts.generate_fast_report._latest_report_run_ids", return_value=["run_dhg_x"])
@patch("scripts.generate_fast_report.latest_ready_snapshot", return_value={"snapshot_id": "s"})
def test_always_renders_locally_with_current_renderer(
    _snapshot, _run_ids, render, storage_cls, tmp_path, monkeypatch
):
    import scripts.generate_fast_report as fast

    monkeypatch.setattr(fast, "ROOT", tmp_path)
    storage_cls.return_value.exists.return_value = False

    out = fast.generate_fast_report("DHG")

    assert out["run_id"] == "run_dhg_x"
    assert Path(out["pdf_path"]).read_bytes() == b"%PDF-1.4 charts"
    assert Path(out["html_path"]).read_text(encoding="utf-8") == "<html>charts</html>"
    render.assert_called_once()


@patch("scripts.generate_fast_report.SupabaseStorageAdapter")
@patch("scripts.generate_fast_report.render_client_report_to_directory", side_effect=_fake_render)
@patch("scripts.generate_fast_report._latest_report_run_ids", return_value=["run_dhg_x"])
@patch("scripts.generate_fast_report.latest_ready_snapshot", return_value={"snapshot_id": "s"})
def test_downloads_workings_when_present(
    _snapshot, _run_ids, _render, storage_cls, tmp_path, monkeypatch
):
    import scripts.generate_fast_report as fast

    monkeypatch.setattr(fast, "ROOT", tmp_path)
    storage = storage_cls.return_value
    storage.exists.return_value = True

    out = fast.generate_fast_report("DHG")

    assert out["workings_path"].endswith("DHG_valuation_workings.md")
    storage.download_file.assert_called_once()


@patch("scripts.generate_fast_report.SupabaseStorageAdapter")
@patch("scripts.generate_fast_report._latest_report_run_ids", return_value=["run_bad", "run_good"])
@patch("scripts.generate_fast_report.latest_ready_snapshot", return_value={"snapshot_id": "s"})
def test_tries_next_candidate_when_latest_render_fails(
    _snapshot, _run_ids, storage_cls, tmp_path, monkeypatch
):
    import scripts.generate_fast_report as fast

    monkeypatch.setattr(fast, "ROOT", tmp_path)
    storage_cls.return_value.exists.return_value = False

    def render(*, run_id, ticker, mode, output_dir):
        if run_id == "run_bad":
            raise RuntimeError("old run incompatible")
        return _fake_render(
            run_id=run_id, ticker=ticker, mode=mode, output_dir=output_dir
        )

    monkeypatch.setattr(fast, "render_client_report_to_directory", render)

    out = fast.generate_fast_report("DHG")

    assert out["run_id"] == "run_good"
