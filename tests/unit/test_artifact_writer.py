"""Tests for backend.reporting.artifact_writer — GOAL_OUTPUT.md artifact contracts."""
import json
import pytest
from pathlib import Path

from backend.reporting.artifact_writer import ArtifactWriter, RunArtifacts


def _minimal_arts():
    return RunArtifacts(
        run_id="RUN_TEST_001",
        ticker="DHG",
        report_date="2026-06-01",
        data_cutoff="2025-12-31",
        rating="UNDER_REVIEW",
        current_price=94400.0,
        target_price=137010.0,
        upside_pct=45.1,
        wacc=0.10,
        terminal_growth=0.02,
        equity_value=0,
        shares_outstanding=130_000_000,
        implied_price=137010.0,
        gate_results=[],
        claims=[],
        sources=[],
        fcff_rows=[],
        sensitivity={},
        scenarios={},
        assumptions=[],
        report_status="NEEDS_REVIEW",
    )


def test_write_all_creates_5_files(tmp_path):
    arts = _minimal_arts()
    writer = ArtifactWriter(base_dir=tmp_path)
    result = writer.write_all(arts)
    assert len(result) == 5
    for path in result.values():
        assert path.exists()


def test_valuation_result_schema_keys(tmp_path):
    arts = _minimal_arts()
    writer = ArtifactWriter(base_dir=tmp_path)
    writer.write_all(arts)
    p = tmp_path / "valuation_results" / f"{arts.run_id}_{arts.ticker}_valuation_result.json"
    with open(p, encoding="utf-8") as _f:
        d = json.load(_f)
    for key in [
        "run_id", "ticker", "valuation_date", "current_price", "target_price",
        "upside_downside", "rating_model_output", "fcff_dcf", "sensitivity",
        "scenarios", "assumptions", "reproducibility_hash",
    ]:
        assert key in d, f"Missing key: {key}"


def test_upside_stored_as_decimal(tmp_path):
    arts = _minimal_arts()
    arts.upside_pct = 45.1
    writer = ArtifactWriter(base_dir=tmp_path)
    writer.write_all(arts)
    p = tmp_path / "valuation_results" / f"{arts.run_id}_{arts.ticker}_valuation_result.json"
    with open(p, encoding="utf-8") as _f:
        d = json.load(_f)
    assert abs(d["upside_downside"] - 0.451) < 0.001


def test_claim_ledger_has_claim_id_prefix(tmp_path):
    arts = _minimal_arts()
    arts.claims = [{"claim_text": "Revenue grew 12%", "metric": "revenue_growth"}]
    writer = ArtifactWriter(base_dir=tmp_path)
    writer.write_all(arts)
    p = tmp_path / "claim_ledgers" / f"{arts.run_id}_{arts.ticker}_claim_ledger.json"
    with open(p, encoding="utf-8") as _f:
        d = json.load(_f)
    assert d["claims"][0]["claim_id"].startswith("CLM-")


def test_eval_result_overall_status_warn(tmp_path):
    arts = _minimal_arts()
    arts.gate_results = [{"name": "citation_gate", "status": "warn", "issues": []}]
    writer = ArtifactWriter(base_dir=tmp_path)
    writer.write_all(arts)
    p = tmp_path / "eval_results" / f"{arts.run_id}_{arts.ticker}_eval_result.json"
    with open(p, encoding="utf-8") as _f:
        d = json.load(_f)
    assert d["overall_status"] == "WARN_NEEDS_REVIEW"
    assert d["n_warn"] == 1


def test_reproducibility_hash_is_sha256(tmp_path):
    arts = _minimal_arts()
    writer = ArtifactWriter(base_dir=tmp_path)
    writer.write_all(arts)
    p = tmp_path / "valuation_results" / f"{arts.run_id}_{arts.ticker}_valuation_result.json"
    with open(p, encoding="utf-8") as _f:
        d = json.load(_f)
    assert d["reproducibility_hash"].startswith("sha256:")


def test_source_manifest_schema(tmp_path):
    arts = _minimal_arts()
    arts.sources = [{"source_type": "financial_statements", "source_name": "DHG FS 2024"}]
    writer = ArtifactWriter(base_dir=tmp_path)
    writer.write_all(arts)
    p = tmp_path / "source_manifests" / f"{arts.run_id}_{arts.ticker}_source_manifest.json"
    with open(p, encoding="utf-8") as _f:
        d = json.load(_f)
    assert d["sources"][0]["source_id"].startswith("SRC-")
    for key in ["run_id", "ticker", "generated_at", "sources"]:
        assert key in d


def test_eval_result_critical_fail(tmp_path):
    arts = _minimal_arts()
    arts.gate_results = [
        {"name": "numeric_consistency_gate", "status": "fail", "issues": ["mismatch"]},
    ]
    writer = ArtifactWriter(base_dir=tmp_path)
    writer.write_all(arts)
    p = tmp_path / "eval_results" / f"{arts.run_id}_{arts.ticker}_eval_result.json"
    with open(p, encoding="utf-8") as _f:
        d = json.load(_f)
    assert d["overall_status"] == "CRITICAL_FAIL"
    assert d["n_fail"] == 1


def test_eval_result_pass(tmp_path):
    arts = _minimal_arts()
    arts.gate_results = [
        {"name": "source_gate", "status": "pass", "issues": []},
    ]
    writer = ArtifactWriter(base_dir=tmp_path)
    writer.write_all(arts)
    p = tmp_path / "eval_results" / f"{arts.run_id}_{arts.ticker}_eval_result.json"
    with open(p, encoding="utf-8") as _f:
        d = json.load(_f)
    assert d["overall_status"] == "PASS"
    assert d["n_pass"] == 1


def test_run_log_artifacts_map(tmp_path):
    arts = _minimal_arts()
    writer = ArtifactWriter(base_dir=tmp_path)
    writer.write_all(arts)
    p = tmp_path / "run_logs" / f"{arts.run_id}_{arts.ticker}_run_log.json"
    with open(p, encoding="utf-8") as _f:
        d = json.load(_f)
    assert "artifacts" in d
    assert "claim_ledger" in d["artifacts"]
    assert "source_manifest" in d["artifacts"]
    assert "valuation_result" in d["artifacts"]
    assert "eval_result" in d["artifacts"]


def test_filenames_use_correct_suffix(tmp_path):
    arts = _minimal_arts()
    writer = ArtifactWriter(base_dir=tmp_path)
    result = writer.write_all(arts)
    assert result["claim_ledger"].name.endswith("_claim_ledger.json")
    assert result["source_manifest"].name.endswith("_source_manifest.json")
    assert result["valuation_result"].name.endswith("_valuation_result.json")
    assert result["eval_result"].name.endswith("_eval_result.json")
    assert result["run_log"].name.endswith("_run_log.json")
