from __future__ import annotations

from scripts.approve_report import main


def test_approve_report_cli_returns_zero() -> None:
    exit_code = main(["--run-id", "run-1", "--decision", "approve", "--reviewer", "analyst"])
    assert exit_code == 0


def test_approve_report_cli_no_args_returns_zero() -> None:
    exit_code = main([])
    assert exit_code == 0
