from __future__ import annotations

from scripts.approve_report import main


def test_approve_report_cli_rejects_ticker_scoped_approval() -> None:
    exit_code = main(["--ticker", "DHG", "--decision", "approve", "--reviewer", "analyst"])

    assert exit_code == 2


def test_approve_report_cli_requires_run_id() -> None:
    exit_code = main(["--decision", "approve", "--reviewer", "analyst"])

    assert exit_code == 1
