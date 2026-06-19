from __future__ import annotations

import json
from pathlib import Path

from scripts import prepare_benchmark_artifacts as prep


def _rows() -> list[dict[str, str]]:
    keys = set(prep.REQUIRED_FACTS) | {
        "revenue.net",
        "net_income.parent",
        "shares_outstanding.ending",
    }
    return [
        {
            "validation_status": "accepted",
            "period": "2025FY",
            "canonical_key": key,
            "value": "1",
            "source_uri": "local://fixture",
            "source_title": "Fixture BCTC",
        }
        for key in sorted(keys)
    ]


def _valuation() -> dict:
    return {
        "ticker": "TST",
        "generated_at": "2026-06-18T00:00:00+00:00",
        "fy_periods": ["2025FY"],
        "assumptions": {"wacc": 0.1},
        "fcff": {"target_price_vnd": 12_345},
        "fcfe": {"target_price_vnd": 12_000},
        "formula_traces": [
            {"trace_id": "tst_net_debt_bridge"},
            {"trace_id": "tst_fcff_target_price"},
        ],
    }


def test_benchmark_artifacts_do_not_write_user_facing_report_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(prep, "ROOT", tmp_path)
    monkeypatch.setattr(prep, "BENCHMARK_PDF_ROOT", tmp_path / "output" / "evaluation" / "benchmark_artifacts")

    written_pdfs: list[Path] = []

    def fake_build_pdf(path: Path, lines: list[str]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"%PDF-1.4\nbenchmark stub")
        written_pdfs.append(path)

    monkeypatch.setattr(prep, "_build_pdf", fake_build_pdf)

    prep._write_runtime_artifacts("TST", _rows(), _valuation(), "2026-06-18T00:00:00+00:00")

    assert not (tmp_path / "output" / "TST_report.pdf").exists()
    assert not (tmp_path / "output" / "TST_explanation.pdf").exists()
    assert written_pdfs == [
        tmp_path / "output" / "evaluation" / "benchmark_artifacts" / "TST" / "report_stub.pdf",
        tmp_path / "output" / "evaluation" / "benchmark_artifacts" / "TST" / "explanation_stub.pdf",
    ]

    packet_path = tmp_path / "storage" / "runs" / "benchmark_tst" / "benchmark_tst_evidence_packet.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    report_refs = [
        ref["artifact_path"]
        for ref in packet["artifact_refs"]
        if ref["section_key"] == "report_draft"
    ]
    assert report_refs == ["output/evaluation/benchmark_artifacts/TST/report_stub.pdf"]
    quality = packet["report_quality_evaluation"]
    gate_summary = packet["gate_results"]["REPORT_QUALITY_GATE"]["summary"]
    assert gate_summary == quality
    assert quality["section_scores"]["completeness"] >= 90
    assert quality["section_scores"]["valuation_transparency"] >= 85
    assert quality["score"] >= 85
