from __future__ import annotations

from backend.reporting.local_report_export import prepare_local_report_export_dir


def test_local_export_archives_previous_latest(tmp_path):
    first = prepare_local_report_export_dir("dhg", "run_1", base_dir=tmp_path)
    (first / "old.pdf").write_bytes(b"pdf")

    second = prepare_local_report_export_dir("DHG", "run_2", base_dir=tmp_path)

    assert second == tmp_path / "DHG" / "latest"
    assert (second / "EXPORT_METADATA.json").exists()
    archived = list((tmp_path / "DHG" / "archive").iterdir())
    assert len(archived) == 1
    assert (archived[0] / "old.pdf").exists()
