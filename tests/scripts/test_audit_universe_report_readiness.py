from __future__ import annotations

from pathlib import Path

from scripts import audit_universe_report_readiness as audit


def test_audit_universe_classifies_raw_data_and_pdf_status(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "backend.dataset.config_io.load_universe_rows",
        lambda: [
            {"ticker": "DHG", "company_name": "Duoc Hau Giang", "exchange": "HOSE", "segment": "pharma"},
            {"ticker": "IMP", "company_name": "Imexpharm", "exchange": "HOSE", "segment": "pharma"},
        ],
    )
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    bctc = tmp_path / "data" / "raw" / "bctc" / "DHG"
    bctc.mkdir(parents=True)
    for name in audit.REQUIRED_BCTC_FILES:
        (bctc / name).write_text("{}", encoding="utf-8")
    output = tmp_path / "output"
    output.mkdir()
    (output / "DHG_report.pdf").write_bytes(b"%PDF-1.4")
    (output / "DHG_explanation.pdf").write_bytes(b"%PDF-1.4")

    result = audit.audit_universe(output_dir=output, include_db=False)

    assert result["summary"]["universe_count"] == 2
    assert result["summary"]["raw_bctc_complete_count"] == 1
    assert result["summary"]["local_pdf_ready_count"] == 1
    assert result["summary"]["not_exportable"] == ["IMP"]


def test_audit_universe_excludes_ticker_and_ranks_release_candidates(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "backend.dataset.config_io.load_universe_rows",
        lambda: [
            {"ticker": "DHG", "company_name": "Duoc Hau Giang", "exchange": "HOSE", "segment": "pharma"},
            {"ticker": "DBD", "company_name": "Binh Dinh Pharma", "exchange": "HOSE", "segment": "pharma"},
            {"ticker": "TRA", "company_name": "Traphaco", "exchange": "HOSE", "segment": "pharma"},
        ],
    )
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    for ticker in ("DHG", "DBD", "TRA"):
        bctc = tmp_path / "data" / "raw" / "bctc" / ticker
        bctc.mkdir(parents=True)
        for name in audit.REQUIRED_BCTC_FILES:
            (bctc / name).write_text("{}", encoding="utf-8")

    output = tmp_path / "output"
    output.mkdir()
    for ticker in ("DHG", "DBD"):
        (output / f"{ticker}_report.pdf").write_bytes(b"%PDF-1.4")
        (output / f"{ticker}_explanation.pdf").write_bytes(b"%PDF-1.4")

    result = audit.audit_universe(
        output_dir=output,
        include_db=False,
        exclude_tickers={"DBD"},
        recommend_limit=2,
    )

    assert result["summary"]["universe_count"] == 2
    assert result["summary"]["excluded_tickers"] == ["DBD"]
    assert [item["ticker"] for item in result["summary"]["recommended_release_candidates"]] == [
        "DHG",
        "TRA",
    ]
    assert {record["ticker"] for record in result["records"]} == {"DHG", "TRA"}


def test_parse_exclusions_accepts_repeated_and_comma_separated_values() -> None:
    assert audit._parse_exclusions(["dbd, imp", "TRA"]) == {"DBD", "IMP", "TRA"}


def test_expected_count_mismatch_returns_distinct_code(monkeypatch) -> None:
    monkeypatch.setattr(
        audit,
        "audit_universe",
        lambda **kwargs: {
            "summary": {
                "universe_count": 42,
                "raw_bctc_complete_count": 0,
                "local_pdf_ready_count": 0,
                "exportable_count": 0,
                "missing_raw_bctc": [],
                "missing_local_pdf": [],
                "not_exportable": [],
            },
            "records": [],
        },
    )

    assert audit.main(["--expected-count", "41"]) == 2
