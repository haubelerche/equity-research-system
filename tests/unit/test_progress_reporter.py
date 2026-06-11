from __future__ import annotations

import io
from backend.harness.progress import ProgressReporter


def test_stage_start_prints_name():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf)
    reporter.stage_start("INGEST_AND_VALIDATE", stage_index=2, total_stages=9)
    output = buf.getvalue()
    assert "INGEST_AND_VALIDATE" in output
    assert "[3/9]" in output


def test_stage_end_prints_elapsed():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf)
    reporter.stage_end("PREFLIGHT", elapsed_sec=1.23, status="completed")
    output = buf.getvalue()
    assert "1.2s" in output
    assert "PREFLIGHT" in output


def test_gate_result_pass():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf)
    reporter.gate_result("data_quality_gate", passed=True, issues=[])
    output = buf.getvalue()
    assert "PASS" in output
    assert "data_quality_gate" in output


def test_gate_result_fail_shows_reasons():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf)
    reporter.gate_result("valuation_gate", passed=False, issues=["missing WACC"])
    output = buf.getvalue()
    assert "FAIL" in output
    assert "missing WACC" in output


def test_agent_activity():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf)
    reporter.agent_start("financial_analysis", "Create typed financial analysis")
    reporter.agent_end("financial_analysis", status="completed", confidence=0.85, latency_ms=3200)
    output = buf.getvalue()
    assert "financial_analysis" in output
    assert "3.2s" in output


def test_tool_activity():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf)
    reporter.tool_start("build_facts", agent_id="data_evidence")
    reporter.tool_end("build_facts", status="completed")
    output = buf.getvalue()
    assert "build_facts" in output


def test_run_summary():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf)
    reporter.run_summary(
        run_id="run_dhg_20260610T120000_abc",
        ticker="DHG",
        final_status="approved",
        total_elapsed_sec=45.6,
        stages_completed=22,
        stages_total=22,
        gate_results={"data_quality_gate": True, "valuation_gate": False},
        output_path="output/pdf/DHG_run_dhg_20260610T120000_abc_report.pdf",
        errors=[],
    )
    output = buf.getvalue()
    assert "DHG" in output
    assert "45.6s" in output
    assert "output/pdf/" in output


def test_blocking_reason():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf)
    reporter.blocking("VALUATION_GATE", "missing WACC assumption")
    output = buf.getvalue()
    assert "BLOCKED" in output
    assert "missing WACC" in output


def test_quiet_mode_suppresses():
    buf = io.StringIO()
    reporter = ProgressReporter(stream=buf, quiet=True)
    reporter.stage_start("PREFLIGHT", stage_index=0, total_stages=22)
    assert buf.getvalue() == ""
