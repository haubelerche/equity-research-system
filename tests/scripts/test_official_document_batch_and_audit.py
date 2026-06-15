from __future__ import annotations

from pathlib import Path

from scripts import audit_official_document_readiness as audit
from scripts import run_official_document_batch as batch


def test_official_document_audit_counts_ready_slots(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.dataset.config_io.load_universe_rows",
        lambda: [
            {"ticker": "DHG", "company_name": "DHG", "exchange": "HOSE", "segment": "pharma"},
            {"ticker": "MKP", "company_name": "MKP", "exchange": "HOSE", "segment": "pharma"},
        ],
    )
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    monkeypatch.setattr(audit, "OFFICIAL_DOCS_DIR", tmp_path / "data" / "official_documents")
    monkeypatch.setattr(audit, "OCR_ARTIFACTS_DIR", tmp_path / "storage" / "sources" / "ocr_artifacts")
    year_dir = tmp_path / "data" / "official_documents" / "DHG" / "2022"
    year_dir.mkdir(parents=True)
    (year_dir / "metadata.json").write_text("{}", encoding="utf-8")
    (year_dir / "source_document.pdf").write_bytes(b"%PDF")
    (year_dir / "extracted_facts.csv").write_text(
        "ticker,fiscal_year,metric_id,value\nDHG,2022,revenue.net,1\n",
        encoding="utf-8",
    )

    result = audit.audit_official_documents(2022, 2022)

    assert result["summary"]["expected_document_slots"] == 2
    assert result["summary"]["source_pdf_count"] == 1
    assert result["summary"]["official_research_ready_count"] == 1
    assert result["summary"]["tickers_not_ready"] == ["MKP"]


def test_batch_all_uses_configured_universe_and_expected_count(monkeypatch, capsys) -> None:
    monkeypatch.setattr(batch, "_configured_universe_tickers", lambda: ["DHG", "MKP"])
    commands = []
    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        return type("P", (), {"returncode": 0})()
    monkeypatch.setattr(batch.subprocess, "run", fake_run)

    code = batch.main([
        "--all",
        "--from-year",
        "2022",
        "--to-year",
        "2025",
        "--expected-count",
        "2",
        "--dry-run",
    ])

    out = capsys.readouterr().out
    assert code == 0
    assert "selected=2" in out
    assert "tickers=DHG,MKP" in out
    assert all("--promote-official-only" not in cmd for cmd in commands)


def test_batch_promote_official_only_requires_explicit_flag(monkeypatch) -> None:
    monkeypatch.setattr(batch, "_configured_universe_tickers", lambda: ["DHG"])
    commands = []
    def fake_run(cmd, **kwargs):
        commands.append(cmd)
        return type("P", (), {"returncode": 0})()
    monkeypatch.setattr(batch.subprocess, "run", fake_run)

    code = batch.main([
        "--all",
        "--from-year",
        "2022",
        "--to-year",
        "2025",
        "--expected-count",
        "1",
        "--promote-official-only",
    ])

    assert code == 0
    assert "--promote-official-only" in commands[0]


def test_batch_expected_count_mismatch_fails(monkeypatch) -> None:
    monkeypatch.setattr(batch, "_configured_universe_tickers", lambda: ["DHG", "MKP"])

    try:
        batch.main(["--all", "--from-year", "2022", "--to-year", "2025", "--expected-count", "42"])
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected argparse failure")
