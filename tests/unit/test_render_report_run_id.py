"""render_report.py must fail-fast without --run-id in production modes."""
import subprocess
import sys


def test_exits_2_without_run_id_in_analyst_draft_mode():
    """render_report.py --mode analyst_draft without --run-id must exit 2."""
    result = subprocess.run(
        [sys.executable, "scripts/render_report.py", "--ticker", "DHG", "--mode", "analyst_draft"],
        capture_output=True, text=True,
        cwd="c:\\Users\\Admin\\Desktop\\multi-agent-equity-research",
    )
    assert result.returncode == 2, (
        f"Expected exit 2 (missing run_id), got {result.returncode}. stderr={result.stderr[:200]}"
    )
    assert "run-id" in result.stderr.lower() or "run_id" in result.stderr.lower()


def test_allow_latest_artifacts_flag_bypasses_run_id_check():
    """--allow-latest-artifacts must bypass the run_id check."""
    result = subprocess.run(
        [sys.executable, "scripts/render_report.py", "--ticker", "DHG",
         "--mode", "analyst_draft", "--allow-latest-artifacts", "--help"],
        capture_output=True, text=True,
        cwd="c:\\Users\\Admin\\Desktop\\multi-agent-equity-research",
    )
    # --help exits 0; must not show the missing-run-id error
    assert result.returncode != 2, (
        f"--allow-latest-artifacts should bypass run_id check, got exit {result.returncode}"
    )


def test_internal_debug_mode_does_not_require_run_id():
    """--mode internal_debug should NOT require --run-id."""
    result = subprocess.run(
        [sys.executable, "scripts/render_report.py", "--ticker", "DHG",
         "--mode", "internal_debug", "--help"],
        capture_output=True, text=True,
        cwd="c:\\Users\\Admin\\Desktop\\multi-agent-equity-research",
    )
    assert result.returncode != 2
