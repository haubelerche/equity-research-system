from __future__ import annotations

from pathlib import Path

from scripts import extract_facts_from_ocr as mod


def test_mapped_ocr_export_does_not_overwrite_raw_candidate_rows(
    tmp_path: Path,
    monkeypatch,
) -> None:
    run_dir = tmp_path / "storage" / "sources" / "ocr_artifacts" / "DHG" / "2025" / "doc"
    pages_dir = run_dir / "pages"
    pages_dir.mkdir(parents=True)
    (pages_dir / "page_001.txt").write_text(
        "BAO CAO KET QUA HOAT DONG KINH DOANH\n"
        "Doanh thu thuan ve ban hang\n"
        "5.622.839.978.328\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(mod, "_map_label", lambda slug: "revenue.net" if "doanh thu" in slug else None)

    rows = mod.process_ocr_run(run_dir, "DHG", 2025, dry_run=False)

    assert len(rows) == 1
    assert (run_dir / mod.MAPPED_FACT_ROWS_FILENAME).is_file()
    assert not (run_dir / "candidate_rows.csv").exists()


def test_ocr_golden_export_targets_canonical_benchmark_tree() -> None:
    assert mod.GOLDEN_DIR == mod.ROOT / "config" / "benchmarks" / "shared" / "golden_financials"
