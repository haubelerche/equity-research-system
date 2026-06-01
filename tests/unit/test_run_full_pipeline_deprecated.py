"""run_full_pipeline.py must exit 1 with DEPRECATED message unless --force-legacy is passed."""
import subprocess
import sys
import os

REPO_ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def test_exits_1_without_force_flag():
    """Calling run_full_pipeline.py without --force-legacy should exit 1."""
    result = subprocess.run(
        [sys.executable, "scripts/run_full_pipeline.py", "--ticker", "DHG"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    assert result.returncode == 1, (
        f"Expected exit 1 (DEPRECATED), got {result.returncode}. stderr={result.stderr[:300]}"
    )
    assert "DEPRECATED" in result.stderr or "DEPRECATED" in result.stdout


def test_help_works_with_force_flag():
    """With --force-legacy, --help should work (exit 0) without DEPRECATED warning."""
    result = subprocess.run(
        [sys.executable, "scripts/run_full_pipeline.py", "--force-legacy", "--help"],
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
    )
    # --help exits 0; must not show DEPRECATED warning
    assert result.returncode == 0
    assert "DEPRECATED" not in result.stderr
    assert "DEPRECATED" not in result.stdout
